"""CLI: python3 -m docforensics run samples/ --state state/run1 [选项]"""

import argparse
from collections import Counter
import difflib
import glob
import json
import os
import re
import sys
import uuid

from . import pipeline, state


def cmd_run(args):
    try:
        provider = pipeline.load_provider(args)
    except ValueError:
        print("invalid model or Skill configuration", file=sys.stderr)
        return 2
    os.makedirs(args.state, exist_ok=True)
    sample_dirs = []
    for p in args.samples:
        if os.path.isfile(os.path.join(p, "layout.json")):
            sample_dirs.append(p)
        elif os.path.isdir(p):
            sample_dirs.extend(sorted(d for d in glob.glob(os.path.join(p, "*"))
                                      if os.path.isfile(os.path.join(d, "layout.json"))))
    if not sample_dirs:
        print("no sample dirs found", file=sys.stderr)
        return 2

    # A display doc id is also the journal/report identity. Reject collisions
    # before any node is checked, instead of silently replacing earlier counts.
    documents = set()
    try:
        for directory in sample_dirs:
            with open(os.path.join(directory, "layout.json"), encoding="utf-8") as source:
                layout = json.load(source)
            if not isinstance(layout, dict):
                raise ValueError("layout must be an object")
            doc = layout.get("doc") or os.path.basename(directory.rstrip("/"))
            if not isinstance(doc, str):
                raise ValueError("layout doc must be a string")
            if doc in documents:
                print("duplicate document identity in this run; assign distinct layout doc ids", file=sys.stderr)
                return 2
            documents.add(doc)
    except (ValueError, OSError):
        print("invalid layout or unavailable input during document identity check", file=sys.stderr)
        return 2

    summary = {}
    run_id = uuid.uuid4().hex
    state.append(args.state, action="RUN_START", run_id=run_id, schema_version=2,
                 provider=provider.name)
    for d in sample_dirs:
        if not os.path.exists(os.path.join(d, "layout.json")):
            continue
        try:
            doc, counts = pipeline.run(d, args.state, provider, run_id=run_id)
        except (ValueError, OSError) as exc:
            state.append(args.state, action="RUN_ERROR", run_id=run_id, error=type(exc).__name__)
            print(f"invalid input or unavailable run directory: {type(exc).__name__}", file=sys.stderr)
            return 2
        summary[doc] = counts
        print(f"{doc}: OK={counts['OK']} NEEDS_HUMAN={counts['NEEDS_HUMAN']}")

    state.append(args.state, action="RUN_END", run_id=run_id, summary=summary)
    report_path = write_report(args.state, provider, run_id=run_id)
    print(f"report: {report_path}")
    return 0


def write_report(run_dir, provider, run_id=None):
    events = state.load_events(run_dir)
    if run_id is None:
        run_id = next((e.get("run_id") for e in reversed(events) if e.get("run_id")), None)
    if run_id is not None:
        return write_run_report(run_dir, provider, events, run_id)
    docs = []
    for e in events:
        if e.get("doc") and e["doc"] not in docs:
            docs.append(e["doc"])

    lines = [f"# 质检报告 · {os.path.basename(run_dir)}", "",
             f"- 修复提供方：**{provider.name}**", ""]
    for doc in docs:
        de = [e for e in events if e.get("doc") == doc]
        repairs = [e for e in de if e.get("repaired")]
        needs = [e for e in de if e.get("status") == "NEEDS_HUMAN"]
        skipped = [e for e in de if e.get("action") == "SKIP"]
        lines += [f"## {doc}", "",
                  f"- 节点修复 {len(repairs)} · 待人工 {len(needs)} · 断点续跑跳过 {len(skipped)}", ""]
        if repairs:
            lines += ["| 节点 | Skill | 修复内容 | 证据 | 尝试 |", "| --- | --- | --- | --- | --- |"]
            for e in repairs:
                if e.get("original"):
                    detail = f'`{e.get("original")}` → `{e.get("latex")}`'
                elif "original_rows" in e and "candidate_rows" in e:
                    detail = "表格行数据差异见下方"
                else:
                    detail = "旧记录未保存原文与候选，无法还原差异"
                lines.append(f'| {e["node_id"]} | {e.get("skill")} | {detail} '
                             f'| {e.get("evidence") or "⚠️ 缺失"} | {e.get("attempts")} |')
            lines.append("")
            for e in repairs:
                if "original_rows" not in e or "candidate_rows" not in e:
                    continue
                original = json.dumps(e["original_rows"], ensure_ascii=False, indent=2).splitlines()
                candidate = json.dumps(e["candidate_rows"], ensure_ascii=False, indent=2).splitlines()
                diff = list(difflib.unified_diff(original, candidate,
                                               fromfile="original_rows", tofile="candidate_rows", lineterm=""))
                lines += [f'### 表格候选 `{e["node_id"]}`', "",
                          "以下为检查通过的候选差异，仍需核对原始证据；未写回源文件。", "",
                          "```diff", *(diff or ["(行数据无变化)"]), "```", ""]
        if needs:
            lines += ["### 待人工（不阻塞流水线）", ""]
            for e in needs:
                lines.append(f'- `{e["node_id"]}` ({e.get("skill")}): {e.get("reason", "")} {e.get("detail", "")}'.rstrip())
            lines.append("")

    path = os.path.join(run_dir, "report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def _block(value, language="json"):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    fence = "`" * max(3, max((len(part) for part in re.findall(r"`+", text)), default=0) + 1)
    return [fence + language, text, fence, ""]


def write_run_report(run_dir, provider, events, run_id):
    current = [e for e in events if e.get("run_id") == run_id]
    lines = ["# 质检报告", "", f"运行：`{run_id}`", f"提供方：{provider.name}", "",
             "本报告按本次运行统计；候选通过检查不表示已被使用者采用。", ""]
    provider_results = [e for e in current if e.get("action") == "PROVIDER_RESULT"]
    model_calls = sum(e.get("model_calls", 0) or 0 for e in provider_results)
    pending_starts = Counter()
    for event in current:
        key = json.dumps([event.get(field) for field in
                          ("doc", "node_id", "attempt", "input_sha256", "context_sha256")],
                         ensure_ascii=False, sort_keys=True)
        if event.get("action") == "PROVIDER_START":
            pending_starts[key] += 1
        elif event.get("action") == "PROVIDER_RESULT" and pending_starts[key] > 0:
            pending_starts[key] -= 1
    unmatched = sum(pending_starts.values())
    known = not unmatched and all(e.get("model_calls_known", False) for e in provider_results)
    lines += [f"本次模型 HTTP 请求尝试：{'至少 ' if not known else ''}{model_calls}",
              "计数包含超时请求，不代表服务端完成推理。" if known else
              "部分提供方或未完成请求没有可确认计数，以上为已知下界，不能将未知记作零。", ""]
    if unmatched:
        lines += [f"有 {unmatched} 条请求开始事件尚无对应结果；是否已发送 HTTP 请求、是否完成推理均未知。", ""]
    if any(e.get("action") == "RUN_START" for e in current) and not any(e.get("action") == "RUN_END" for e in current):
        lines += ["本次运行没有结束记录；以下展示已保存的部分证据，不表示全部节点已经处理。", ""]
    docs = list(dict.fromkeys(e["doc"] for e in current if e.get("doc")))
    for doc in docs:
        scoped = [e for e in current if e.get("doc") == doc]
        final = {}
        for event in scoped:
            if event.get("action") in ("TERMINAL", "SKIP"):
                final[event["node_id"]] = event
        counts = {s: sum(e.get("status") == s for e in final.values()) for s in ("OK", "NEEDS_HUMAN")}
        unfinished = list(dict.fromkeys(e["node_id"] for e in scoped
                                       if e.get("node_id") and e["node_id"] not in final))
        lines += [f"## {doc}", "", f"OK {counts['OK']} · 待人工 {counts['NEEDS_HUMAN']} · "
                  f"复用 {sum(e.get('action') == 'SKIP' for e in final.values())} · 未完成 {len(unfinished)}", ""]
        for nid, event in final.items():
            lines += [f"### 节点 {nid}", "", f"检查终态：{event['status']}",
                      f"输入 SHA256：`{event.get('input_sha256', '')}`",
                      f"执行上下文 SHA256：`{event.get('context_sha256', '')}`", ""]
            terminal = event
            if event["action"] == "SKIP":
                lines += [f"输入与执行上下文一致，复用运行 `{event.get('reused_run_id', '')}` 的终态；本次未修复此节点。", ""]
                terminal = next((e for e in reversed(events) if e.get("action") == "TERMINAL"
                                 and e.get("doc") == doc and e.get("node_id") == nid
                                 and e.get("run_id") == event.get("reused_run_id")
                                 and e.get("input_sha256") == event.get("input_sha256")
                                 and e.get("context_sha256") == event.get("context_sha256")), event)
            if terminal.get("repaired"):
                lines += [f"证据：{terminal.get('evidence') or '⚠️ 缺失'}", "",
                          "以下为通过检查的候选，未写回源文件。", ""]
                if "original_rows" in terminal and "candidate_rows" in terminal:
                    original = json.dumps(terminal["original_rows"], ensure_ascii=False, indent=2).splitlines()
                    candidate = json.dumps(terminal["candidate_rows"], ensure_ascii=False, indent=2).splitlines()
                    lines += _block("\n".join(difflib.unified_diff(original, candidate, fromfile="original_rows",
                                                                 tofile="candidate_rows", lineterm="")), "diff")
                elif "original" in terminal:
                    lines += ["原文：", *_block(terminal["original"], "latex"),
                              "候选：", *_block(terminal.get("latex", ""), "latex")]
            if terminal.get("reason"):
                lines += ["处置原因：", *_block(str(terminal["reason"]), "text")]
            if terminal.get("provider_reason"):
                lines += ["提供方结果：", *_block(str(terminal["provider_reason"]), "text")]
            if terminal.get("resumable") is False:
                lines += ["该终态不复用；修复暂时故障后，同一状态目录重跑会重新检查。", ""]
            history = [e for e in scoped if e.get("node_id") == nid and e.get("action") not in ("TERMINAL", "SKIP")]
            if history:
                lines += ["#### 检查与候选记录", "", *_block(history)]
        for nid in unfinished:
            history = [e for e in scoped if e.get("node_id") == nid]
            lines += [f"### 节点 {nid}", "",
                      "未完成：已保存事件中没有终态。不计入 OK 或 NEEDS_HUMAN，也不推断请求或修复成功。", "",
                      "#### 已保存的检查与候选记录", "", *_block(history)]
    path = os.path.join(run_dir, "report.md")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="docforensics")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="跑样本目录（天然支持断点续跑）")
    r.add_argument("samples", nargs="+", help="样本目录（含 layout.json）或其父目录")
    r.add_argument("--state", default="state/run1")
    r.add_argument("--vlm", help="OpenAI 兼容端点（如 http://127.0.0.1:11434）；缺省用 fixture 测试替身")
    r.add_argument("--vlm-model", default="qwen2.5vl:7b")
    r.add_argument("--fixture-repairs", help="fixture 修复表 JSON（仅离线测试用）")
    r.add_argument("--skill-mode", choices=("on", "off"), default="on",
                   help="模型请求是否加载公式 Skill 正文；off 用于受控对照")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--max-tokens", type=int, default=300)
    r.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
