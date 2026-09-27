"""CLI: python3 -m docforensics run samples/ --state state/run1 [选项]"""

import argparse
import glob
import os
import sys

from . import pipeline, state


def cmd_run(args):
    provider = pipeline.load_provider(args)
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

    summary = {}
    for d in sample_dirs:
        if not os.path.exists(os.path.join(d, "layout.json")):
            continue
        doc, counts = pipeline.run(d, args.state, provider)
        summary[doc] = counts
        print(f"{doc}: OK={counts['OK']} NEEDS_HUMAN={counts['NEEDS_HUMAN']}")

    report_path = write_report(args.state, provider)
    print(f"report: {report_path}")
    return 0


def write_report(run_dir, provider):
    events = state.load_events(run_dir)
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
                detail = f'`{e.get("original")}` → `{e.get("latex")}`' if e.get("original") else "重提取"
                lines.append(f'| {e["node_id"]} | {e.get("skill")} | {detail} '
                             f'| {e.get("evidence") or "⚠️ 缺失"} | {e.get("attempts")} |')
            lines.append("")
        if needs:
            lines += ["### 待人工（不阻塞流水线）", ""]
            for e in needs:
                lines.append(f'- `{e["node_id"]}` ({e.get("skill")}): {e.get("reason", "")} {e.get("detail", "")}'.rstrip())
            lines.append("")

    path = os.path.join(run_dir, "report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
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
    r.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
