#!/usr/bin/env python3
"""Controlled formula-only Skills comparison and hash-bound human review.

Network requires `run --mode model --base URL --model NAME`. Dry-run and fixture
outputs are runner checks, never measurements of a real model or human accuracy.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from importlib import metadata
from pathlib import Path
import platform
import re
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "harness"))
from docforensics.pipeline import run_verify
from docforensics.vlm import OllamaProvider

GROUPS = ("checker_only", "model_without_skill", "model_with_skill")
KINDS = ("original", "control", "injected")
STATUSES = ("OK", "RETRY", "NEEDS_ENV", "NEEDS_HUMAN")
VERDICTS = ("correct", "incorrect", "uncertain", "unreviewable")
PROVIDER_ENV_REASONS = ("timeout", "network_error", "http_error", "provider_error")
REVIEW_FIELDS = (
    "row_id", "case_id", "case_sha256", "input_sha256", "candidate_sha256",
    "original_latex", "candidate_latex", "source_url", "source_locator", "reference_latex",
    "verdict", "reviewer", "independent_review", "review_seconds", "notes",
)
IMMUTABLE_FIELDS = REVIEW_FIELDS[:10]


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def read_catalog(path):
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    if not nonempty(catalog.get("dataset_id")):
        raise ValueError("dataset_id must be nonempty")
    if catalog.get("dataset_kind") not in ("open-source", "synthetic"):
        raise ValueError("dataset_kind must be open-source or synthetic")
    if catalog.get("annotation_status") != "pending":
        raise ValueError("source catalog annotation_status must be pending; import reviews separately")
    cases = catalog.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every case must be an object")
        cid = case.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", cid) or cid in seen:
            raise ValueError("case id must be unique and stable")
        seen.add(cid)
        if not nonempty(case.get("original_latex")) or "\x00" in case["original_latex"]:
            raise ValueError(f"{cid}: original_latex must be nonempty and contain no NUL")
        if case.get("case_kind") not in KINDS or case.get("review_status") != "pending":
            raise ValueError(f"{cid}: invalid case_kind or review_status")
        if "expected_syntax" in case and case["expected_syntax"] not in STATUSES:
            raise ValueError(f"{cid}: invalid expected_syntax")
        source = case.get("source")
        if not isinstance(source, dict) or any(not nonempty(source.get(key)) for key in ("title", "url", "license", "locator")):
            raise ValueError(f"{cid}: source title/url/license/locator must be nonempty")
        if not isinstance(source.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            raise ValueError(f"{cid}: source.sha256 must identify source bytes")
        for key in ("reference_latex", "injection"):
            if key in case and not isinstance(case[key], str):
                raise ValueError(f"{cid}: {key} must be a string")
        if case["case_kind"] == "injected" and not nonempty(case.get("injection")):
            raise ValueError(f"{cid}: injected cases must describe the mutation")
    return catalog


class FixtureModel:
    """Explicit offline test double. Its invocations are never model calls."""

    def __init__(self, repairs, group):
        self.repairs = repairs
        self.group = group
        self.last_trace = {}
        self.counts = Counter()

    def fingerprint(self):
        return {"provider": "fixture", "group": self.group,
                "skill_mode": "not_executed", "model_calls": 0}

    def repair_formula(self, node):
        cid = node["id"]
        values = self.repairs.get(self.group, {}).get(cid, [])
        index = self.counts[cid]
        self.counts[cid] += 1
        candidate = values[index] if index < len(values) else None
        self.last_trace = {"provider": "fixture", "model_calls": 0,
                           "model_called": False, "skill_loaded": False,
                           "reason": "offline_test_double", "fixture_calls": 1}
        return candidate


def read_fixtures(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(group not in GROUPS[1:] for group in data):
        raise ValueError("fixture keys must be model_without_skill or model_with_skill")
    for records in data.values():
        if not isinstance(records, dict):
            raise ValueError("fixture group must map case ids to candidate lists")
        for values in records.values():
            if not isinstance(values, list) or len(values) > 2 or any(v is not None and not isinstance(v, str) for v in values):
                raise ValueError("fixture candidates must be a list of at most two strings/nulls")
    return data


def sequence(cases):
    # Rotate all three arms per case. No group is always first; ordering is fixed.
    for index, case in enumerate(cases):
        for group in GROUPS[index % 3:] + GROUPS[:index % 3]:
            yield case, group


def checked(latex, verify):
    value = verify(latex)
    if not isinstance(value, dict) or value.get("status") not in STATUSES:
        return {"status": "NEEDS_ENV", "reason": "invalid_checker_output"}
    return value


def run_arm(case, group, mode, provider, initial, verify=None):
    verify = verify or run_verify
    started = time.monotonic()
    original = case["original_latex"]
    current = dict(initial)
    candidate = None
    attempts = []
    if mode != "dry-run" and group != "checker_only" and current["status"] == "RETRY":
        for attempt in (1, 2):
            # Both model arms receive only identical observed input. References,
            # mutation labels and anticipated outcomes never enter the request.
            node = {"id": case["id"], "type": "formula", "data": {"latex": original}}
            proposed = provider.repair_formula(node)
            trace = dict(provider.last_trace)
            event = {"attempt": attempt, "provider_trace": trace,
                     "candidate_latex": proposed if isinstance(proposed, str) else None,
                     "candidate_sha256": digest(proposed) if isinstance(proposed, str) else None}
            if not isinstance(proposed, str) or not proposed.strip() or "\x00" in proposed:
                event["decision"] = "no_candidate"
                attempts.append(event)
                break
            candidate = proposed
            current = checked(candidate, verify)
            event["checker"] = current
            event["decision"] = {"OK": "accepted_by_syntax_checker", "RETRY": "rejected_by_syntax_checker",
                                 "NEEDS_ENV": "environment_failure", "NEEDS_HUMAN": "manual_review"}[current["status"]]
            attempts.append(event)
            if current["status"] != "RETRY":
                break
    accepted = candidate is not None and current["status"] == "OK"
    output = candidate if accepted else original
    if mode == "dry-run":
        outcome = "dry_run_no_execution"
    elif current["status"] == "NEEDS_ENV" or any(a["provider_trace"].get("reason") in PROVIDER_ENV_REASONS for a in attempts):
        outcome = "environment_failure"
    elif initial["status"] == "OK":
        outcome = "initial_syntax_ok_no_repair"
    elif group == "checker_only":
        outcome = "checker_only_no_repair"
    elif accepted:
        outcome = "candidate_syntax_ok_pending_review"
    elif attempts and attempts[-1]["decision"] == "no_candidate":
        outcome = "no_candidate"
    else:
        outcome = "unresolved"
    return {"case_id": case["id"], "case_kind": case["case_kind"], "group": group,
            "mode": mode, "case_sha256": digest(canonical(case)), "input_sha256": digest(original),
            "initial_checker": initial, "final_checker": current,
            "expected_syntax": case.get("expected_syntax"),
            "initial_expectation_match": initial["status"] == case["expected_syntax"] if "expected_syntax" in case and mode != "dry-run" else None,
            "attempts": attempts, "model_calls": sum(a["provider_trace"].get("model_calls", 0) for a in attempts),
            "fixture_calls": sum(a["provider_trace"].get("fixture_calls", 0) for a in attempts),
            "no_candidate": any(a["decision"] == "no_candidate" for a in attempts),
            "provider_environment_failure": any(a["provider_trace"].get("reason") in PROVIDER_ENV_REASONS for a in attempts),
            "candidate_accepted_by_syntax_checker": accepted,
            "original_latex": original, "output_latex": output, "output_sha256": digest(output),
            "output_changed": output != original, "outcome": outcome,
            "elapsed_seconds": round(time.monotonic() - started, 6), "review_status": "pending"}


def summarize(results):
    summary = {}
    for group in GROUPS:
        rows = [r for r in results if r["group"] == group]
        summary[group] = {"cases": len(rows), "model_calls": sum(r["model_calls"] for r in rows),
                          "fixture_calls": sum(r["fixture_calls"] for r in rows),
                          "output_changed": sum(r["output_changed"] for r in rows),
                          "candidate_syntax_ok": sum(r["candidate_accepted_by_syntax_checker"] for r in rows),
                          "no_candidate": sum(r["no_candidate"] for r in rows),
                          "by_case_kind": {kind: {"cases": sum(r["case_kind"] == kind for r in rows),
                                                  "output_changed": sum(r["output_changed"] for r in rows if r["case_kind"] == kind)} for kind in KINDS},
                          "outcomes": dict(Counter(r["outcome"] for r in rows)),
                          "semantic_accuracy": None, "human_reviewed": 0}
    pairs = {}
    for row in results:
        pairs.setdefault(row["case_id"], {})[row["group"]] = row
    different = sum(v["model_without_skill"]["output_sha256"] != v["model_with_skill"]["output_sha256"] for v in pairs.values())
    return {"by_group": summary, "paired_output_differences": different,
            "semantic_accuracy": None, "human_time_savings": None}


def blind_rows(catalog, results, seed):
    cases = {c["id"]: c for c in catalog["cases"]}
    rows = []
    for result in results:
        case = cases[result["case_id"]]
        # IDs are opaque and shuffled, while exact duplicate text stays visible.
        key = digest(canonical([seed, result["case_id"], result["group"], result["case_sha256"], result["output_sha256"]]))
        result["review_row_id"] = key[:24]
        row = {"row_id": key[:24], "case_id": case["id"], "case_sha256": result["case_sha256"],
               "input_sha256": result["input_sha256"], "candidate_sha256": result["output_sha256"],
               "original_latex": case["original_latex"], "candidate_latex": result["output_latex"],
               "source_url": case["source"]["url"], "source_locator": case["source"]["locator"],
               "reference_latex": case.get("reference_latex", "")}
        row.update({field: "" for field in REVIEW_FIELDS[10:]})
        rows.append(row)
    return sorted(rows, key=lambda row: row["row_id"])


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fresh(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def render_run(manifest, results):
    lines = ["# Skills 受控对照运行", "", f"运行模式：**{manifest['mode']}**；数据集：`{manifest['dataset_id']}`（{manifest['dataset_kind']}）。", "",
             "dry-run / fixture 只验证执行器；只有 model 模式记录真实模型请求。语法通过不等于语义正确；pending 人工复核不参与正确率。", "",
             "三组共享同一输入、检查器、模型配置、seed、temperature=0 和每例每组最多两次候选预算；case 间轮换执行顺序。初检 OK 不调用模型。模型端点是否严格遵守 seed 由其实现决定，本工具不保证位级确定性。", "",
             "| 组 | 条目 | 模型请求 | 测试替身调用 | 语法接受候选 | 输出变化 | 环境失败 | 无候选 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for group, row in manifest["summary"]["by_group"].items():
        lines.append(f"| {group} | {row['cases']} | {row['model_calls']} | {row['fixture_calls']} | {row['candidate_syntax_ok']} | {row['output_changed']} | {row['outcomes'].get('environment_failure', 0)} | {row['no_candidate']} |")
    lines += ["", f"执行中代码发生变化：{manifest['code_changed_during_run']}；样本目录发生变化：{manifest['catalog_changed_during_run']}；对照配置校验：{manifest['controlled_configuration_verified']}。代码变化的运行不可导入人工复核，应固定实现后重跑。", "模型请求计数是 HTTP 尝试数，包含超时或 HTTP 错误，不等于确认完成推理的次数。环境失败包括检查器不可用及端点/网络异常；这些情况也可能计入无候选，两个计数不是互斥分类。", "", f"两个模型组最终输出不同的案例：{manifest['summary']['paired_output_differences']}。该数值只能证明文本差异，不能证明一组更准确。", "",
              "## 人工复核", "", "`blind-review.csv` 隐去组名、按固定散列顺序排列，每一行绑定完整 case、原文和最终拟交付文本的 SHA-256。原始返回和被拒绝候选保存在 results.jsonl，不应向盲审人员同时提供分组结果。", "",
              "填写 verdict（correct / incorrect / uncertain / unreviewable）、非空 reviewer、independent_review=yes 和实际 review_seconds；最后一项可留空，但不能据此估计人工节省时间。未填写行继续 pending。review 导入时验证不可变字段和全部绑定哈希；独立性是复核者声明，工具无法证实人员独立性。", "",
              "原样保留的输出同样需要按原来源上下文判断。reference_latex 只提供来源参照，未经人工确认，不是自动真值。只对已完成且 verdict 为 correct / incorrect 的行计算正确比例，同时披露复核覆盖率；不能外推到 pending 行。", "",
              "## 可复核文件", "", "- manifest.json：配置、来源记录、程序/Skill 指纹、顺序、统计及文件哈希。", "- results.jsonl：逐组检查、每次候选、拒绝原因及实际模型请求数。", "- blind-review.csv：人工复核空表，不含虚构结论。", "",
              "本实验仅覆盖公式文本与当前解析器支持范围，不测试 OCR、表格、用户工时节约或跨来源泛化。开放来源提取加人工注入错误也不等于自然发生错误的独立数据集。", ""]
    return "\n".join(lines)


def run(args):
    catalog = read_catalog(args.cases)
    catalog_sha256 = digest(Path(args.cases).read_bytes())
    if args.mode == "model":
        if not args.base or not args.model:
            raise ValueError("model mode requires explicit --base and --model")
        if args.fixture_repairs:
            raise ValueError("model mode cannot use fixture repairs")
    elif args.base or args.model:
        raise ValueError("--base and --model are only allowed in model mode")
    if args.mode == "fixture" and not args.fixture_repairs:
        raise ValueError("fixture mode requires explicit --fixture-repairs")
    if args.mode != "fixture" and args.fixture_repairs:
        raise ValueError("--fixture-repairs is only allowed in fixture mode")
    if not 1 <= args.max_tokens <= 8192 or not 0 <= args.seed < 2 ** 32:
        raise ValueError("max_tokens must be 1..8192 and seed must be 0..2^32-1")
    providers = {}
    if args.mode == "model":
        providers = {group: OllamaProvider(base=args.base, model=args.model, skill_mode=skill,
                                           seed=args.seed, max_tokens=args.max_tokens)
                     for group, skill in zip(GROUPS[1:], ("off", "on"))}
    elif args.mode == "fixture":
        repairs = read_fixtures(args.fixture_repairs)
        unknown = set().union(*(set(v) for v in repairs.values())) - {c["id"] for c in catalog["cases"]}
        if unknown:
            raise ValueError("fixture contains unknown case ids")
        providers = {group: FixtureModel(repairs, group) for group in GROUPS[1:]}
    programs = {str(p.relative_to(REPO)): digest(p.read_bytes()) for p in (
        Path(__file__).resolve(), REPO / "harness/docforensics/vlm.py",
        REPO / "harness/docforensics/pipeline.py", REPO / "skills/doc-formula-verify/scripts/verify.py")}
    fingerprints = {g: p.fingerprint() for g, p in providers.items()}
    controlled = None
    if args.mode == "model":
        left, right = (fingerprints[g] for g in GROUPS[1:])
        keys = ("model", "endpoint_sha256", "base_prompt_sha256", "user_template_sha256", "tool_sha256", "parameters")
        controlled = all(key in left and key in right and left[key] == right[key] for key in keys)
        if not controlled or left.get("skill_mode") != "off" or right.get("skill_mode") != "on" or not right.get("skill_sha256"):
            raise ValueError("model arms must share configuration and load the requested Skill intervention")
    versions = {}
    for name in ("sympy", "antlr4-python3-runtime"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    started = time.monotonic()
    outdir = fresh(args.outdir)
    # Partial outputs remain evidence of completed arms if the process stops.
    # A running manifest cannot be imported as a completed evaluation.
    dump(outdir / "manifest.json", {"schema_version": 1, "status": "running", "mode": args.mode,
                                     "catalog": catalog, "program_sha256": programs,
                                     "provider_fingerprints": fingerprints})
    initial = {}
    results = []
    order = []
    for case, group in sequence(catalog["cases"]):
        if case["id"] not in initial:
            initial[case["id"]] = ({"status": "NEEDS_HUMAN", "reason": "dry_run_not_checked"}
                                    if args.mode == "dry-run" else checked(case["original_latex"], run_verify))
        result = run_arm(case, group, args.mode, providers.get(group), initial[case["id"]])
        blind_rows(catalog, [result], args.seed)
        with (outdir / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(canonical(result) + "\n")
        results.append(result)
        order.append({"case_id": case["id"], "group": group})
    review = blind_rows(catalog, results, args.seed)
    write_csv(outdir / "blind-review.csv", review)
    (outdir / "results.jsonl").write_text("".join(canonical(r) + "\n" for r in results), encoding="utf-8")
    manifest = {"schema_version": 1, "status": "complete", "mode": args.mode, "created_at": datetime.now(timezone.utc).isoformat(),
                "dataset_id": catalog["dataset_id"], "dataset_kind": catalog["dataset_kind"],
                "catalog_sha256": catalog_sha256, "catalog": catalog,
                "catalog_changed_during_run": digest(Path(args.cases).read_bytes()) != catalog_sha256,
                "configuration": {"seed": args.seed, "temperature": 0, "max_tokens": args.max_tokens,
                                  "max_candidates_per_case_per_model_arm": 2,
                                  "max_model_calls": len(catalog["cases"]) * 4 if args.mode == "model" else 0,
                                  "initial_syntax_ok_skips_repair": True},
                "provider_fingerprints": fingerprints, "controlled_configuration_verified": controlled,
                "program_sha256": programs,
                "code_changed_during_run": any(digest((REPO / name).read_bytes()) != value for name, value in programs.items()),
                "environment": {"python": platform.python_version(), "dependencies": versions},
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "execution_order": order, "summary": summarize(results),
                "files": {name: digest((outdir / name).read_bytes()) for name in ("results.jsonl", "blind-review.csv")}}
    (outdir / "report.md").write_text(render_run(manifest, results), encoding="utf-8")
    manifest["files"]["report.md"] = digest((outdir / "report.md").read_bytes())
    dump(outdir / "manifest.json", manifest)
    print(json.dumps({"mode": args.mode, "cases": len(catalog["cases"]), "entries": len(results),
                      "model_calls": sum(r["model_calls"] for r in results), "semantic_accuracy": None,
                      "outdir": str(outdir)}, ensure_ascii=False))
    return 1 if manifest["code_changed_during_run"] or manifest["catalog_changed_during_run"] or any(r["outcome"] == "environment_failure" for r in results) else 0


def read_review(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(REVIEW_FIELDS):
            raise ValueError("review CSV columns must exactly match blind-review.csv")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("review CSV has malformed rows")
    return rows


def review(args):
    source = Path(args.run_dir).resolve()
    manifest_bytes = (source / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != 1 or manifest.get("status") != "complete" or manifest.get("mode") not in ("dry-run", "fixture", "model"):
        raise ValueError("invalid or incomplete run manifest")
    if manifest.get("code_changed_during_run") or manifest.get("catalog_changed_during_run"):
        raise ValueError("code or catalog changed during the run; repeat with frozen inputs and implementation")
    for name in ("results.jsonl", "blind-review.csv", "report.md"):
        if digest((source / name).read_bytes()) != manifest.get("files", {}).get(name):
            raise ValueError(f"run evidence hash mismatch: {name}")
    original = read_review(source / "blind-review.csv")
    submitted = read_review(args.reviews)
    expected = {r["row_id"]: r for r in original}
    results = [json.loads(line) for line in (source / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    mapping = {r["review_row_id"]: r for r in results}
    if len(mapping) != len(results) or set(mapping) != set(expected):
        raise ValueError("result/review row binding mismatch")
    cases = {c["id"]: c for c in manifest["catalog"]["cases"]}
    for rid, row in expected.items():
        result = mapping[rid]
        case = cases[row["case_id"]]
        if (row["case_sha256"] != digest(canonical(case)) or row["case_sha256"] != result["case_sha256"]
                or row["input_sha256"] != digest(row["original_latex"]) or row["input_sha256"] != result["input_sha256"]
                or row["candidate_sha256"] != digest(row["candidate_latex"]) or row["candidate_sha256"] != result["output_sha256"]):
            raise ValueError("case/input/candidate hash binding mismatch")
    seen = set()
    decisions = []
    for row in submitted:
        rid = row["row_id"]
        if rid not in expected or rid in seen:
            raise ValueError("unknown or duplicate review row id")
        seen.add(rid)
        if any(row[field] != expected[rid][field] for field in IMMUTABLE_FIELDS):
            raise ValueError("review modified immutable case/candidate/source fields")
        verdict = row["verdict"].strip()
        if not verdict:
            if any(row[field].strip() for field in ("reviewer", "independent_review", "review_seconds", "notes")):
                raise ValueError("a populated review row requires a verdict")
            continue
        if verdict not in VERDICTS or not row["reviewer"].strip() or row["independent_review"].strip().lower() != "yes":
            raise ValueError("completed review requires valid verdict, named reviewer and independent_review=yes")
        seconds = None
        if row["review_seconds"].strip():
            try:
                seconds = float(row["review_seconds"])
            except ValueError as exc:
                raise ValueError("review_seconds must be finite and positive") from exc
            if not 0 < seconds < float("inf"):
                raise ValueError("review_seconds must be finite and positive")
        decisions.append({**row, "verdict": verdict, "group": mapping[rid]["group"],
                          "output_changed": mapping[rid]["output_changed"], "review_seconds": seconds})
    if not decisions:
        raise ValueError("no completed independent reviews; pending rows cannot yield accuracy")
    totals = {}
    for group in GROUPS:
        rows = [r for r in decisions if r["group"] == group]
        counts = Counter(r["verdict"] for r in rows)
        denominator = counts["correct"] + counts["incorrect"]
        total = sum(r["group"] == group for r in results)
        times = [r["review_seconds"] for r in rows if r["review_seconds"] is not None]
        totals[group] = {"total": total, "reviewed": len(rows), "pending": total - len(rows),
                         "reviewed_coverage": len(rows) / total if total else None,
                         "verdicts": dict(counts), "determinate_reviews": denominator,
                         "correct_fraction_among_determinate_reviews": counts["correct"] / denominator if denominator else None,
                         "recorded_review_seconds": sum(times) if times else None,
                         "timed_rows": len(times), "human_time_savings": None}
    outdir = fresh(args.outdir)
    report = {"schema_version": 1, "mode": manifest["mode"], "run_manifest_sha256": digest(manifest_bytes),
              "review_csv_sha256": digest(Path(args.reviews).read_bytes()),
              "created_at": datetime.now(timezone.utc).isoformat(), "independence": "reviewer_self_attested_not_verified",
              "summary": totals, "reviews": decisions}
    dump(outdir / "review-report.json", report)
    lines = ["# 人工复核汇总", "", f"来源运行模式：**{manifest['mode']}**。fixture/dry-run 的人工复核仍不能转化为真实模型实验。", "",
             "独立性为具名复核者自行声明，工具没有验证其人员关系。正确比例只覆盖 correct/incorrect 的已审行；uncertain、unreviewable 和 pending 分开披露。", "",
             "| 组 | 已审 / 总条目 | pending | correct | incorrect | uncertain | unreviewable | 已审确定结果正确比例 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for group, value in totals.items():
        fraction = value["correct_fraction_among_determinate_reviews"]
        pct = f"{fraction:.1%}" if fraction is not None else "未计算"
        count = value["verdicts"]
        lines.append(f"| {group} | {value['reviewed']} / {value['total']} | {value['pending']} | {count.get('correct', 0)} | {count.get('incorrect', 0)} | {count.get('uncertain', 0)} | {count.get('unreviewable', 0)} | {pct} |")
    lines += ["", "这是已审输出的人工判定汇总，未做代表性抽样、显著性检验或跨来源泛化推断。计时为逐行实际复核时长，缺少人工从零修复基线时不能计算节省时间。", ""]
    (outdir / "review-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"reviewed": len(decisions), "total": len(results), "outdir": str(outdir)}, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="prepare or execute a bounded three-arm run")
    run_parser.add_argument("--cases", type=Path, required=True)
    run_parser.add_argument("--outdir", type=Path, required=True)
    run_parser.add_argument("--mode", choices=("dry-run", "fixture", "model"), default="dry-run")
    run_parser.add_argument("--base")
    run_parser.add_argument("--model")
    run_parser.add_argument("--seed", type=int, default=0)
    run_parser.add_argument("--max-tokens", type=int, default=300)
    run_parser.add_argument("--fixture-repairs", type=Path)
    review_parser = commands.add_parser("review", help="validate and summarize independently completed review rows")
    review_parser.add_argument("--run-dir", type=Path, required=True)
    review_parser.add_argument("--reviews", type=Path, required=True)
    review_parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args) if args.command == "run" else review(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
