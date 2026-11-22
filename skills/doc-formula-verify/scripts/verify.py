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

_VALID_DELIMITERS = frozenset({
    "(", ")", "[", "]", "|", "/", ".",
    r"\{", r"\}", r"\|",
    r"\vert", r"\rvert", r"\lvert", r"\Vert", r"\lVert", r"\rVert",
    r"\langle", r"\rangle", r"\lfloor", r"\rfloor", r"\lceil", r"\rceil",
    r"\backslash",
    r"\uparrow", r"\downarrow", r"\updownarrow",
    r"\Uparrow", r"\Downarrow", r"\Updownarrow",
})
_UNARY_SCRIPT_MACROS = frozenset({
    r"\mathrm", r"\mathit", r"\mathbf", r"\mathsf", r"\mathtt",
    r"\mathcal", r"\mathbb", r"\boldsymbol", r"\overline", r"\underline",
    r"\hat", r"\widehat", r"\bar", r"\vec", r"\dot", r"\ddot",
    r"\tilde", r"\widetilde", r"\sqrt",
})


def _strip_formula(text: str) -> str:
    stripped = text.lstrip()
    while stripped and stripped[-1].isspace():
        slashes = 0
        pos = len(stripped) - 2
        while pos >= 0 and stripped[pos] == "\\":
            slashes += 1
            pos -= 1
        if slashes % 2 == 1:
            break
        stripped = stripped[:-1]
    return stripped


def _lex_tokens(latex: str):
    tokens = []
    i, n = 0, len(latex)
    while i < n:
        ch = latex[i]
        if ch.isspace():
            i += 1
        elif ch == "%":
            nl = latex.find("\n", i)
            i = n if nl < 0 else nl + 1
        elif ch == "\\":
            if i + 1 >= n:
                tokens.append("\\")
                i += 1
            elif ("A" <= latex[i + 1] <= "Z") or ("a" <= latex[i + 1] <= "z") or latex[i + 1] == "@":
                j = i + 2
                while j < n and (("A" <= latex[j] <= "Z") or ("a" <= latex[j] <= "z") or latex[j] == "@"):
                    j += 1
                tokens.append(latex[i:j])
                i = j
            else:
                tokens.append(latex[i:i + 2])
                i += 2
        else:
            tokens.append(ch)
            i += 1
    return tokens


def _validate_group(tokens, index=0, *, inside_brace=False):
    left_open = 0
    nucleus_scripts = None
    while index < len(tokens):
        tok = tokens[index]
        if tok == "\\":
            return None, "incomplete command: trailing backslash"
        if tok == "}":
            if not inside_brace:
                return None, "unmatched closing brace"
            if left_open > 0:
                return None, "unclosed \\left before closing brace"
            return index + 1, None
        if tok == "{":
            next_index, err = _validate_group(tokens, index + 1, inside_brace=True)
            if err:
                return None, err
            nucleus_scripts = set()
            index = next_index
            continue
        if tok == r"\left":
            if index + 1 >= len(tokens) or tokens[index + 1] not in _VALID_DELIMITERS:
                return None, "invalid or missing delimiter after \\left"
            left_open += 1
            nucleus_scripts = None
            index += 2
            continue
        if tok == r"\right":
            if index + 1 >= len(tokens) or tokens[index + 1] not in _VALID_DELIMITERS:
                return None, "invalid or missing delimiter after \\right"
            if left_open <= 0:
                return None, "unmatched \\right"
            left_open -= 1
            nucleus_scripts = set()
            index += 2
            continue
        if tok == r"\middle":
            if left_open <= 0 or index + 1 >= len(tokens) or tokens[index + 1] not in _VALID_DELIMITERS:
                return None, "invalid or unmatched \\middle"
            nucleus_scripts = None
            index += 2
            continue
        if tok in (r"\limits", r"\nolimits"):
            index += 1
            continue
        if tok in ("^", "_"):
            if nucleus_scripts is None:
                nucleus_scripts = set()
            if tok in nucleus_scripts:
                return None, "duplicate superscript" if tok == "^" else "duplicate subscript"
            nucleus_scripts.add(tok)
            if index + 1 >= len(tokens):
                return None, "missing script argument"
            arg = tokens[index + 1]
            if arg == "{":
                next_index, err = _validate_group(tokens, index + 2, inside_brace=True)
                if err:
                    return None, err
                index = next_index
                continue
            if arg in ("}", "^", "_", "\\", r"\left", r"\right", r"\middle"):
                return None, "invalid script argument"
            if arg in _UNARY_SCRIPT_MACROS and index + 2 < len(tokens) and tokens[index + 2] == "{":
                next_index, err = _validate_group(tokens, index + 3, inside_brace=True)
                if err:
                    return None, err
                index = next_index
                continue
            index += 2
            continue
        nucleus_scripts = set()
        index += 1
    if inside_brace:
        return None, "unclosed brace"
    if left_open > 0:
        return None, "unclosed \\left"
    return index, None


def _lexical_error(latex: str):
    if not isinstance(latex, str):
        return "bad_input"
    tokens = _lex_tokens(_strip_formula(latex))
    if not tokens:
        return "empty latex"
    _, err = _validate_group(tokens)
    return err


def check(latex: str):
    """返回 (status, reason)。"""
    if not isinstance(latex, str):
        return "NEEDS_HUMAN", "bad_input"
    latex = _strip_formula(latex)
    if not latex:
        return "RETRY", "empty latex"
    try:
        from sympy.parsing.latex import parse_latex
    except ImportError as e:
        return "NEEDS_ENV", f"missing dependency: {e.name}"

    lexical = _lexical_error(latex)
    if lexical:
        return "RETRY", f"lexical error: {lexical}"

    try:
        # Validate original delimiters first. ANTLR skips sizing commands, so its
        # strict start/end offset test otherwise rejects valid \left(...\right).
        parse_latex(latex)
        normalized = re.sub(r"\\(?:left|right)(?![A-Za-z@])", "", latex).strip()
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
