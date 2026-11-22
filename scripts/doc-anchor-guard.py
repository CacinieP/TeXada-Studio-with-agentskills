#!/usr/bin/env python3
r"""doc-anchor-guard：公式候选的算子/希腊字母/上下标锚点漂移判定。

输入（二选一）:
  - 命令行参数:  doc-anchor-guard.py '\\iint_D f' '\\int_D f'
  - stdin JSONL: {"id": "f-014", "original": "...", "candidate": "..."}  每行一条
输出: JSONL  {"id": "...", "status": "OK|RETRY|NEEDS_HUMAN", "reason": "...", "findings": [...]}

约定（与 SKILL 契约一致，issue #28-B）:
  - OK          无锚点漂移（未改动、确定性补丁或内容一致的候选）
  - RETRY       检出锚点漂移，reason 形如 anchor_drift:operator_downgraded:\iint，
                候选退回重试；不做静默放行
  - NEEDS_HUMAN 输入不是含 original/candidate 字符串的 JSON 对象，不请求模型

退出码: 0 = 已给出判定（OK 或 RETRY）；1 = 输入协议问题（NEEDS_HUMAN）。
本脚本不判语法、不调用模型；语法回判仍由 doc-formula-verify 负责。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harness"))
from docforensics.anchor_guard import anchor_drift  # noqa: E402

EXIT_OK = 0
EXIT_BAD_INPUT = 1


def verdict(original, candidate):
    if not isinstance(original, str) or not isinstance(candidate, str):
        return {"status": "NEEDS_HUMAN", "reason": "bad_input", "findings": []}
    result = anchor_drift(original, candidate)
    if result["drift"]:
        return {"status": "RETRY", "reason": result["reason"], "findings": result["findings"]}
    return {"status": "OK", "reason": result["reason"] or "no_anchor_drift", "findings": []}


def emit(record):
    print(json.dumps(record, ensure_ascii=False, allow_nan=False))


def main(argv):
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__, file=sys.stderr)
        return EXIT_BAD_INPUT
    if (len(argv) == 2 and argv[0] not in ("-", "--stdin") and argv[1] not in ("-", "--stdin")
            and not argv[0].startswith("--") and not argv[1].startswith("--")):
        record = verdict(argv[0], argv[1])
        emit(record)
        return EXIT_BAD_INPUT if record["status"] == "NEEDS_HUMAN" else EXIT_OK
    if len(argv) != 1 or argv[0] not in ("-", "--stdin"):
        print(__doc__, file=sys.stderr)
        return EXIT_BAD_INPUT
    exit_code = EXIT_OK
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            emit({"id": None, "status": "NEEDS_HUMAN", "reason": "bad_input", "findings": []})
            exit_code = EXIT_BAD_INPUT
            continue
        if not isinstance(request, dict):
            emit({"id": None, "status": "NEEDS_HUMAN", "reason": "bad_input", "findings": []})
            exit_code = EXIT_BAD_INPUT
            continue
        record = verdict(request.get("original"), request.get("candidate"))
        emit({"id": request.get("id"), **record})
        if record["status"] == "NEEDS_HUMAN":
            exit_code = EXIT_BAD_INPUT
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
