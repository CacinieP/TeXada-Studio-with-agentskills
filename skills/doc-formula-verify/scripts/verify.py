#!/usr/bin/env python3
"""SymPy 解析回判：校验 OCR 抽取的 LaTeX 公式语法合法性。

输入（二选一）:
  - 命令行参数:  verify.py '\\frac{1}{2}'
  - stdin JSONL: {"id": "f-014", "latex": "..."}  每行一条
输出: JSONL  {"id": "...", "status": "OK|RETRY|NEEDS_ENV|NEEDS_HUMAN", "reason": "..."}

约定（与 SKILL.md 一致）:
  - OK       语法可解析
  - RETRY    解析失败，候选文本修复由上游决定，本脚本不调用模型
  - NEEDS_ENV 本机缺 sympy/antlr 依赖（不是公式问题，不得当作 RETRY）
  - NEEDS_HUMAN 输入不是含字符串 latex 的 JSON 对象，不请求模型修补输入协议

依赖: 按 harness/requirements.txt 安装 SymPy 与 antlr4 4.11
"""

import json
import re
import sys

EXIT_OK = 0


def check(latex: str):
    """返回 (status, reason)。"""
    if not isinstance(latex, str):
        return "NEEDS_HUMAN", "bad_input"
    latex = latex.strip()
    if not latex:
        return "RETRY", "empty latex"
    try:
        from sympy.parsing.latex import parse_latex
    except ImportError as e:
        return "NEEDS_ENV", f"missing dependency: {e.name}"

    try:
        # Validate original delimiters first. ANTLR skips sizing commands, so its
        # strict start/end offset test otherwise rejects valid \left(...\right).
        parse_latex(latex)
        normalized = re.sub(r"\\(?:left|right)(?![A-Za-z])", "", latex).strip()
        expr = parse_latex(normalized, strict=True)
    except ImportError as e:
        return "NEEDS_ENV", f"missing parser dependency: {e}"
    except Exception as e:  # antlr/LaTeX ParseException 及其包装
        return "RETRY", f"parse error: {type(e).__name__}: {e}"

    if expr is None:
        return "RETRY", "parser returned None"
    return "OK", ""


def main() -> int:
    args = sys.argv[1:]
    out = sys.stdout
    code = EXIT_OK

    if args:
        status, reason = check(" ".join(args))
        out.write(json.dumps({"id": "argv", "status": status, "reason": reason}) + "\n")
        return 2 if status == "NEEDS_ENV" else 1 if status == "NEEDS_HUMAN" else code

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            out.write(json.dumps({"id": None, "status": "NEEDS_HUMAN", "reason": "bad_input", "detail": str(e)}) + "\n")
            code = max(code, 1)
            continue
        if not isinstance(rec, dict):
            out.write(json.dumps({"id": None, "status": "NEEDS_HUMAN", "reason": "bad_input", "detail": "record must be an object"}) + "\n")
            code = max(code, 1)
            continue
        status, reason = check(rec.get("latex"))
        out.write(json.dumps({"id": rec.get("id"), "status": status, "reason": reason}) + "\n")
        if status == "NEEDS_ENV":
            code = 2  # 提醒调用方修环境，而不是刷 RETRY
        elif status == "NEEDS_HUMAN":
            code = max(code, 1)
    return code


if __name__ == "__main__":
    sys.exit(main())
