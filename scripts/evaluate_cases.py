#!/usr/bin/env python3
"""Run synthetic checker contracts locally and preserve mismatches as findings.

No model, shell interpolation, network client, or OCR is used. A completed report
is not a model-accuracy or mathematical-correctness benchmark.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
CHECKERS = {
    "formula": REPO / "skills/doc-formula-verify/scripts/verify.py",
    "table": REPO / "skills/doc-table-audit/scripts/audit_table.py",
}
GROUPS = ("contract", "semantic-boundary", "known-gap")
STATUSES = {"OK", "RETRY", "NEEDS_HUMAN", "NEEDS_ENV"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_catalog(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("synthetic") is not True:
        raise ValueError("catalog must declare schema_version=1 and synthetic=true")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("catalog must contain a nonempty cases array")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every case must be an object")
        cid = case.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"[FT][0-9]{2,}", cid) or cid in seen:
            raise ValueError(f"invalid or duplicate case id: {cid!r}")
        seen.add(cid)
        checker = case.get("checker")
        if not isinstance(checker, str) or checker not in CHECKERS or cid[0] != ("F" if checker == "formula" else "T"):
            raise ValueError(f"{cid}: checker must match case prefix")
        if not isinstance(case.get("evaluation_group"), str) or case["evaluation_group"] not in GROUPS:
            raise ValueError(f"{cid}: invalid evaluation_group")
        for key in ("title", "category", "why"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError(f"{cid}: {key} must be a nonempty string")
        expected = case.get("expected")
        if (not isinstance(expected, dict) or not isinstance(expected.get("status"), str)
                or expected["status"] not in STATUSES):
            raise ValueError(f"{cid}: expected.status must be a checker status")
        if "reason" in expected and not isinstance(expected["reason"], str):
            raise ValueError(f"{cid}: expected.reason must be a string")
        spec = case.get("input")
        if not isinstance(spec, dict):
            raise ValueError(f"{cid}: input must be an object")
        if spec.get("transport") == "argv":
            if checker != "formula" or not isinstance(spec.get("latex"), str):
                raise ValueError(f"{cid}: argv is supported only for a formula string")
            if "\x00" in spec["latex"]:
                raise ValueError(f"{cid}: argv latex cannot contain NUL")
        elif spec.get("transport") == "jsonl":
            if ("record" in spec) == ("raw" in spec):
                raise ValueError(f"{cid}: JSONL needs exactly one of record or raw")
            if "raw" in spec and (not isinstance(spec["raw"], str) or any(c in spec["raw"] for c in "\r\n")):
                raise ValueError(f"{cid}: raw must be one JSONL line")
        else:
            raise ValueError(f"{cid}: unknown input transport")
    return data


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value.replace(str(REPO), "<repo>")


def run_case(case, timeout):
    spec = case["input"]
    command = [sys.executable, str(CHECKERS[case["checker"]])]
    stdin = None
    if spec["transport"] == "argv":
        command.append(spec["latex"])
    else:
        stdin = spec["raw"] if "raw" in spec else json.dumps(spec["record"], ensure_ascii=False)
        stdin += "\n"
    started = time.monotonic()
    status = None
    response = None
    returncode = None
    try:
        proc = subprocess.run(command, input=stdin, text=True, capture_output=True,
                              cwd=REPO, timeout=timeout)
        stdout, stderr, returncode = clean_text(proc.stdout), clean_text(proc.stderr), proc.returncode
        lines = stdout.splitlines()
        try:
            response = json.loads(lines[0]) if len(lines) == 1 else None
        except json.JSONDecodeError:
            response = None
        if (not isinstance(response, dict) or not isinstance(response.get("status"), str)
                or response["status"] not in STATUSES):
            outcome = "process-error" if returncode else "invalid-output"
        else:
            status = response["status"]
            expected_code = {"OK": 0, "RETRY": 0, "NEEDS_HUMAN": 1, "NEEDS_ENV": 2}[status]
            if returncode != expected_code:
                outcome = "invalid-exit-code"
            elif status == "NEEDS_ENV":
                outcome = "environment-error"
            else:
                outcome = "checker-result"
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = clean_text(exc.stdout), clean_text(exc.stderr)
        outcome = "timeout"
    except OSError as exc:
        stdout, stderr = "", clean_text(str(exc))
        outcome = "process-error"
    matched = outcome == "checker-result" and status == case["expected"]["status"]
    if matched and "reason" in case["expected"]:
        matched = response.get("reason") == case["expected"]["reason"]
    return {
        **case,
        "observed": {"status": status, "outcome": outcome, "returncode": returncode,
                     "response": response, "stdout": stdout, "stderr": stderr,
                     "elapsed_seconds": round(time.monotonic() - started, 3)},
        "expectation_match": bool(matched),
    }


def summarize(results):
    def counts(items):
        outcomes = Counter(r["observed"]["outcome"] for r in items)
        return {"total": len(items), "matched": sum(r["expectation_match"] for r in items),
                "unmatched": sum(not r["expectation_match"] for r in items),
                "outcomes": dict(sorted(outcomes.items()))}
    return {"all": counts(results),
            "by_group": {group: counts([r for r in results if r["evaluation_group"] == group]) for group in GROUPS},
            "by_checker": {checker: counts([r for r in results if r["checker"] == checker]) for checker in CHECKERS}}


def md(value):
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def render_markdown(report):
    lines = ["# 合成检查器案例报告", "",
             "本报告检查确定性脚本的输入契约和边界行为。没有调用模型、OCR 或网络；预期匹配不代表数学语义正确，也不是模型准确率。", "",
             f"生成时间：{report['created_at']} · Python {report['environment']['python']}。", "",
             f"Catalog SHA-256：`{report['catalog_sha256']}`。", "",
             "## 分组结果", "", "| 分组 | 案例 | 匹配 | 未匹配 |", "| --- | ---: | ---: | ---: |"]
    for group, counts in report["summary"]["by_group"].items():
        lines.append(f"| {group} | {counts['total']} | {counts['matched']} | {counts['unmatched']} |")
    lines += ["", "`contract` 检查声明的确定性行为；`semantic-boundary` 展示语法或支持范围边界；`known-gap` 单独保留尚未满足的要求，不计入契约匹配成绩。任何一组出现未匹配，命令均返回非零。", "",
              "## 逐例结果", "", "| ID | 分类 / 分组 | 预期状态 | 实际状态 / 进程结果 | 匹配 |", "| --- | --- | --- | --- | --- |"]
    for item in report["results"]:
        observed = item["observed"]
        actual = observed["status"] or observed["outcome"]
        if observed["outcome"] != "checker-result" and observed["status"]:
            actual += " / " + observed["outcome"]
        lines.append(f"| {item['id']} | {md(item['category'])} / {item['evaluation_group']} | {item['expected']['status']} | {md(actual)} | {'是' if item['expectation_match'] else '**否**'} |")
    lines += ["", "## 解释与限制", ""]
    for item in report["results"]:
        lines += [f"### {item['id']} · {item['title']}", "", item["why"], ""]
        if item.get("limitation"):
            lines += ["限制：" + item["limitation"], ""]
        if not item["expectation_match"]:
            observed = item["observed"]
            lines += [f"**未满足预期**：{observed['outcome']}，退出码 {observed['returncode']}。完整输入和原始响应见 `report.json`。", ""]
            detail = observed["stderr"] or json.dumps(observed["response"], ensure_ascii=False)
            lines += ["```text", detail[:3000].replace("```", "` ` `"), "```", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=REPO / "samples/evaluation/cases.json")
    parser.add_argument("--outdir", type=Path, required=True, help="new output directory; existing paths are refused")
    parser.add_argument("--timeout", type=float, default=15, help="seconds per case, >0 and <=120")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 120:
        parser.error("--timeout must be >0 and <=120 seconds")
    try:
        catalog = read_catalog(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    outdir = args.outdir.resolve()
    try:
        outdir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"cannot create a fresh output directory: {exc}")
    results = [run_case(case, args.timeout) for case in catalog["cases"]]
    versions = {}
    for name in ("sympy", "antlr4-python3-runtime"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    report = {
        "schema_version": 1, "synthetic": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": catalog.get("scope", "Local checker behavior only."),
        "catalog_sha256": sha256(args.cases),
        "checker_sha256": {name: sha256(path) for name, path in CHECKERS.items()},
        "environment": {"python": platform.python_version(), "system": platform.system(),
                        "machine": platform.machine(), "dependencies": versions},
        "timeout_seconds": args.timeout,
        "summary": summarize(results), "results": results,
    }
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (outdir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(outdir / "report.json"), "summary": report["summary"]}, ensure_ascii=False))
    return 1 if report["summary"]["all"]["unmatched"] else 0


if __name__ == "__main__":
    sys.exit(main())
