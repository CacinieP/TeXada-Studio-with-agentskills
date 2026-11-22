"""Conservative, offset-preserving math extraction for TeX source.

This is a lexical scanner, not a TeX interpreter. It does not expand macros or
change category codes. Closed math regions retain their exact source slices;
only ``checkable`` scalar expressions may be sent to the scalar repair tool.
Unknown commands, alignment structures, and comments inside math are retained
for human review rather than being flattened into a different expression.

All offsets and columns count Unicode code points (Python string indices), not
UTF-8 bytes or JavaScript UTF-16 code units. ``start:end`` includes delimiters;
``body_start:body_end`` is the replacement range that preserves those delimiters.
"""

from bisect import bisect_right
import re


MATH_ENVIRONMENTS = frozenset({
    "equation", "equation*", "align", "align*", "alignat", "alignat*",
    "flalign", "flalign*", "gather", "gather*", "multline", "multline*",
    "displaymath", "math", "eqnarray", "eqnarray*",
})
OPAQUE_ENVIRONMENTS = frozenset({
    "verbatim", "verbatim*", "Verbatim", "Verbatim*", "lstlisting",
    "lstlisting*", "minted", "minted*", "comment",
})
_DEFINITIONS = frozenset({
    "newcommand", "renewcommand", "providecommand", "DeclareRobustCommand",
    "DeclareMathOperator", "newenvironment", "renewenvironment",
    "NewDocumentCommand", "RenewDocumentCommand", "ProvideDocumentCommand",
    "DeclareDocumentCommand", "NewDocumentEnvironment", "RenewDocumentEnvironment",
    "ProvideDocumentEnvironment", "DeclareDocumentEnvironment",
    "def", "gdef", "edef", "xdef",
})
_DOCUMENT_COMMANDS = frozenset({
    "NewDocumentCommand", "RenewDocumentCommand", "ProvideDocumentCommand", "DeclareDocumentCommand",
})
_DOCUMENT_ENVIRONMENTS = frozenset({
    "NewDocumentEnvironment", "RenewDocumentEnvironment",
    "ProvideDocumentEnvironment", "DeclareDocumentEnvironment",
})
_SCALAR_ENVIRONMENTS = frozenset({"equation", "equation*", "math", "displaymath"})
_KNOWN_COMMANDS = frozenset("""
    frac dfrac tfrac sqrt binom dbinom tbinom left right middle
    displaystyle textstyle scriptstyle scriptscriptstyle
    sum prod coprod int iint iiint iiiint oint lim limsup liminf
    sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh coth
    log ln lg exp min max inf sup det gcd Pr
    alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota
    kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon
    phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon
    Phi Psi Omega
    infty partial nabla ell hbar imath jmath Re Im wp aleph
    cdot times div pm mp ast star circ bullet otimes oplus
    le leq ge geq ne neq equiv approx simeq sim cong propto
    in notin ni subset subseteq supset supseteq cup cap setminus emptyset
    forall exists neg land lor to mapsto rightarrow leftarrow leftrightarrow
    Rightarrow Leftarrow Leftrightarrow iff implies
    ldots cdots dots vdots ddots angle perpendicular parallel
    mathrm mathit mathbf mathsf mathtt mathcal mathbb boldsymbol
    overline underline hat widehat bar vec dot ddot tilde widetilde
    quad qquad thinspace negthinspace
    lbrace rbrace langle rangle lvert rvert vert lVert rVert Vert
    big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr
""".split())
_ENVIRONMENT = re.compile(r"\\(begin|end)\s*\{([^{}\r\n]+)\}")
_GRID_ENVIRONMENTS = frozenset({"matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "cases"})
_TEX_UNITS = r"(?:pt|pc|in|bp|cm|mm|dd|cc|sp|em|ex|mu)"
_TEX_DIMEN_ATOM = (
    rf"[+-]?\s*(?:(?:\d+(?:\.\d*)?|\.\d+)\s*(?:true\s*)?(?:{_TEX_UNITS}|\\[A-Za-z@]+)|\\[A-Za-z@]+)"
)
_ROW_SPACING = re.compile(
    rf"^\s*{_TEX_DIMEN_ATOM}(?:\s+plus\s+{_TEX_DIMEN_ATOM})?(?:\s+minus\s+{_TEX_DIMEN_ATOM})?\s*$",
    re.I,
)
_GRID_PAIRS = {
    "{": "}",
    "(": ")",
    "[": "]",
    r"\{": r"\}",
    r"\langle": r"\rangle",
    r"\lvert": r"\rvert",
    r"\lVert": r"\rVert",
}
_GRID_CLOSERS = frozenset(_GRID_PAIRS.values())
_GRID_LR_DELIMITERS = frozenset({
    "(", ")", "[", "]", "|", "/", ".",
    r"\{", r"\}", r"\|",
    r"\vert", r"\rvert", r"\lvert", r"\Vert", r"\lVert", r"\rVert",
    r"\langle", r"\rangle",
})
_GRID_ONE_ARG_COMMANDS = frozenset({
    r"\sqrt", r"\mathrm", r"\mathit", r"\mathbf", r"\mathsf", r"\mathtt",
    r"\mathcal", r"\mathbb", r"\boldsymbol", r"\overline", r"\underline",
    r"\hat", r"\widehat", r"\bar", r"\vec", r"\dot", r"\ddot",
    r"\tilde", r"\widetilde",
})
_GRID_BINARY_ONLY = frozenset({
    "*", "/", r"\cdot", r"\times", r"\div", r"\oplus", r"\otimes",
    "=", "<", ">", "≤", "≥", "≠",
    r"\le", r"\leq", r"\ge", r"\geq", r"\ne", r"\neq",
    r"\equiv", r"\approx", r"\sim", r"\simeq", r"\propto",
    r"\in", r"\notin", r"\ni", r"\subset", r"\subseteq", r"\supset", r"\supseteq",
    r"\to", r"\mapsto", r"\rightarrow", r"\leftarrow", r"\leftrightarrow",
    r"\Rightarrow", r"\Leftarrow", r"\Leftrightarrow", r"\iff", r"\implies",
})
_GRID_UNARY_OR_BINARY = frozenset({"+", "-", r"\pm", r"\mp"})
_GRID_TEXT_COMMANDS = frozenset({
    "text", "textrm", "textbf", "textit", "textsf", "texttt", "textnormal", "emph", "mbox",
})


def _is_row_spacing(spec):
    if any(ch in spec for ch in "\r\n&{}") or not _ROW_SPACING.match(spec):
        return False
    for match in re.finditer(r"\\([A-Za-z@]+)", spec):
        if match.group(1) in _KNOWN_COMMANDS | _DEFINITIONS | {"begin", "end", "verb", "cr"}:
            return False
    return True


def _replace_inline_text_boxes(expr):
    parts = []
    cursor = 0
    while cursor < len(expr):
        if expr[cursor] == "%":
            return None
        if expr[cursor] == "\\":
            command, after = _command(expr, cursor)
            if command in _GRID_TEXT_COMMANDS:
                brace_pos = after
                while brace_pos < len(expr) and expr[brace_pos].isspace():
                    brace_pos += 1
                if brace_pos >= len(expr) or expr[brace_pos] != "{":
                    return None
                end = _balanced_end(expr, brace_pos, "{", "}")
                if end is None:
                    return None
                inner = expr[brace_pos + 1:end - 1]
                if not inner.strip():
                    return None
                pos = 0
                while pos < len(inner):
                    ch = inner[pos]
                    if ch in "%$":
                        return None
                    if ch == "\\":
                        inner_cmd, pos = _command(inner, pos)
                        if inner_cmd in {"", "verb", "begin", "end", "\\", "(", ")", "[", "]"} or inner_cmd in _DEFINITIONS:
                            return None
                        continue
                    pos += 1
                parts.append("(x)")
                cursor = end
                continue
            parts.append(expr[cursor:after])
            cursor = after
            continue
        parts.append(expr[cursor])
        cursor += 1
    return "".join(parts)


def _valid_grid_fragment(expr):
    if not isinstance(expr, str) or not expr.strip():
        return False
    sanitized = _replace_inline_text_boxes(expr)
    if sanitized is None or not sanitized.strip():
        return False
    supported, _ = _checkability(sanitized, "inline")
    if not supported:
        return False
    from .formula_repair import _tokens, deterministic_candidate, repair_blocker

    if repair_blocker(sanitized, allow_parser_gaps=True) is not None or deterministic_candidate(sanitized) is not None:
        return False
    tokens = _tokens(sanitized)
    if not tokens:
        return False

    def is_postfix_script(idx):
        return idx >= 2 and tokens[idx - 1].text == "^" and tokens[idx].text in {"+", "-", "*"}

    stack = []
    left_depths = []
    brace_depth = 0
    index = 0
    while index < len(tokens):
        tok = tokens[index].text
        if tok == "{" and index + 1 < len(tokens) and tokens[index + 1].text == "}":
            return False
        if tok in {r"\left", r"\right"}:
            if index + 1 >= len(tokens) or tokens[index + 1].text not in _GRID_LR_DELIMITERS:
                return False
            if tok == r"\left":
                left_depths.append(brace_depth)
            else:
                if not left_depths or left_depths[-1] != brace_depth:
                    return False
                left_depths.pop()
            delim = tokens[index + 1].text
            if delim in _GRID_PAIRS:
                stack.append((delim, brace_depth))
            elif delim in _GRID_CLOSERS:
                if not stack or _GRID_PAIRS[stack[-1][0]] != delim or stack[-1][1] != brace_depth:
                    return False
                stack.pop()
            index += 2
            continue
        if tok == r"\middle":
            if not left_depths or index + 1 >= len(tokens) or tokens[index + 1].text not in _GRID_LR_DELIMITERS:
                return False
            index += 2
            continue
        if tok in _GRID_PAIRS:
            stack.append((tok, brace_depth))
            if tok == "{":
                brace_depth += 1
        elif tok in _GRID_CLOSERS:
            if tok == "}":
                brace_depth -= 1
                if brace_depth < 0:
                    return False
            if not stack or _GRID_PAIRS[stack[-1][0]] != tok or stack[-1][1] != brace_depth:
                return False
            stack.pop()

        if tok in {"^", "_"}:
            if index + 1 >= len(tokens) or tokens[index + 1].text in {"(", "[", ")", "]"}:
                return False
        if tok in _GRID_ONE_ARG_COMMANDS:
            arg_idx = index + 1
            if tok == r"\sqrt" and arg_idx < len(tokens) and tokens[arg_idx].text == "[":
                depth_b = 0
                while arg_idx < len(tokens):
                    if tokens[arg_idx].text == "[":
                        depth_b += 1
                    elif tokens[arg_idx].text == "]":
                        depth_b -= 1
                        if depth_b == 0:
                            arg_idx += 1
                            break
                    arg_idx += 1
            if arg_idx >= len(tokens) or tokens[arg_idx].text in (
                _GRID_CLOSERS | {r"\right"} | _GRID_BINARY_ONLY | _GRID_UNARY_OR_BINARY | {",", ";"}
            ):
                return False
        if tok in _GRID_BINARY_ONLY and not is_postfix_script(index):
            if index == 0 or index == len(tokens) - 1:
                return False
            prev = tokens[index - 1].text
            nxt = tokens[index + 1].text
            if prev in (_GRID_PAIRS.keys() | _GRID_BINARY_ONLY | _GRID_UNARY_OR_BINARY | {"^", "_", ",", ";"}):
                if not ((tok == "=" and prev in {"<", ">"}) or is_postfix_script(index - 1)):
                    return False
            if nxt in (_GRID_CLOSERS | {r"\right", ",", ";"}):
                return False
        if tok in _GRID_UNARY_OR_BINARY and not is_postfix_script(index):
            if index == len(tokens) - 1:
                return False
            nxt = tokens[index + 1].text
            if nxt in (_GRID_CLOSERS | {r"\right"} | _GRID_BINARY_ONLY | _GRID_UNARY_OR_BINARY | {",", ";"}):
                return False
            if tok == "+" and index > 0 and tokens[index - 1].text == "{":
                if not (index >= 2 and tokens[index - 2].text in {"^", "_"}):
                    return False
        index += 1
    return not stack and not left_depths


def check_math_grids(latex):
    """Check the row/column shape and scalar cell/outer syntax of matrix/cases blocks."""
    controls = list(_ENVIRONMENT.finditer(latex))
    if not controls or len(controls) % 2 != 0 or any(match[2] not in _GRID_ENVIRONMENTS for match in controls):
        return None
    skeleton_parts = []
    last_end = 0
    grids = []
    for index in range(0, len(controls), 2):
        opening = controls[index]
        closing = controls[index + 1]
        if opening[1] != "begin" or closing[1] != "end" or opening[2] != closing[2]:
            return None
        if opening.start() < last_end:
            return None
        skeleton_parts.append(latex[last_end:opening.start()])
        skeleton_parts.append("(x)")
        last_end = closing.end()
        body = latex[opening.end():closing.start()]
        if "%" in body or r"\verb" in body or r"\cr" in body:
            return None
        rows = []
        row_cells = []
        cursor, depth, cell_start = 0, 0, 0
        while cursor < len(body):
            char = body[cursor]
            if char == "\\":
                cmd_start = cursor
                command, next_cursor = _command(body, cursor)
                if command == "\\" and depth == 0:
                    row_cells.append(body[cell_start:cmd_start])
                    rows.append(row_cells)
                    row_cells = []
                    cursor = next_cursor
                    if cursor < len(body) and body[cursor] == "*":
                        cursor += 1
                    had_space = False
                    while cursor < len(body) and body[cursor] in " \t":
                        had_space = True
                        cursor += 1
                    if cursor < len(body) and body[cursor] == "[":
                        end = _balanced_end(body, cursor, "[", "]")
                        if end is None:
                            return None
                        if _is_row_spacing(body[cursor + 1:end - 1]):
                            cursor = end
                        elif not had_space:
                            return None
                    cell_start = cursor
                    continue
                cursor = next_cursor
                continue
            depth += (char == "{") - (char == "}")
            if depth < 0:
                return None
            if char == "&" and depth == 0:
                row_cells.append(body[cell_start:cursor])
                cell_start = cursor + 1
            cursor += 1
        if depth:
            return None
        tail = body[cell_start:]
        if row_cells or tail.strip():
            row_cells.append(tail)
            rows.append(row_cells)
        widths = [len(row) for row in rows]
        env_name = opening[2]
        if env_name == "cases":
            if not widths or len(set(widths)) > 1 or widths[0] not in {1, 2}:
                return {"status": "NEEDS_HUMAN", "reason": f"cases 各行列数为 {widths}，预期每行 1 或 2 列，请核对排版。"}
        elif env_name in {"vmatrix", "Vmatrix"}:
            fixed_width = len(widths)
            if not widths or len(set(widths)) > 1 or widths[0] != fixed_width:
                return {"status": "NEEDS_HUMAN", "reason": f"{env_name} 各行列数为 {widths}，预期每行 {fixed_width} 列，请核对排版。"}
        else:
            if not widths or len(set(widths)) > 1:
                return {"status": "NEEDS_HUMAN", "reason": f"{env_name} 各行列数为 {widths}，请核对排版。"}
        grids.append((env_name, rows))
    skeleton_parts.append(latex[last_end:])
    outer_skeleton = re.sub(r"(?<=\))\s*[.,;]\s*$", "", "".join(skeleton_parts))
    if not _valid_grid_fragment(outer_skeleton):
        return None
    for env_name, rows in grids:
        for row in rows:
            for col_idx, cell in enumerate(row):
                cell_clean = cell
                if env_name == "cases":
                    if col_idx == 0:
                        cell_clean = re.sub(r"[,;]\s*$", "", cell_clean)
                    else:
                        cell_clean = re.sub(r"[.,;]\s*$", "", cell_clean)
                if not _valid_grid_fragment(cell_clean):
                    return None
    return {"status": "OK", "reason": "", "scope": "grid_shape"}


def _command(text, offset):
    """Return an exact control word/symbol and its end, including neither slash."""
    end = offset + 1
    if end >= len(text):
        return "", end
    if text[end].isalpha() or text[end] == "@":
        start = end
        while end < len(text) and (text[end].isalpha() or text[end] == "@"):
            end += 1
        return text[start:end], end
    return text[end], end + 1


def _line_end(text, offset):
    end = text.find("\n", offset)
    return len(text) if end < 0 else end


def _skip_space(text, offset):
    while offset < len(text):
        if text[offset].isspace():
            offset += 1
        elif text[offset] == "%":
            offset = _line_end(text, offset)
        else:
            break
    return offset


def _balanced_end(text, offset, opening="{", closing="}"):
    """Skip one literal argument without interpreting commands in its body."""
    if offset >= len(text) or text[offset] != opening:
        return None
    depth, cursor = 1, offset + 1
    while cursor < len(text):
        value = text[cursor]
        if value == "\\":
            _, cursor = _command(text, cursor)
        elif value == "%":
            cursor = _line_end(text, cursor)
        elif opening == "[" and value == "{":
            end = _balanced_end(text, cursor)
            if end is None:
                return None
            cursor = end
        elif value == opening:
            depth += 1
            cursor += 1
        elif value == closing:
            depth -= 1
            cursor += 1
            if depth == 0:
                return cursor
        else:
            cursor += 1
    return None


def _skip_definition(text, start, command, cursor):
    """Skip conventional command/environment definitions, including body math."""
    if cursor < len(text) and text[cursor] == "*":
        cursor += 1
    cursor = _skip_space(text, cursor)
    if command in {"def", "gdef", "edef", "xdef"}:
        if cursor >= len(text) or text[cursor] != "\\":
            return _line_end(text, start), False
        _, cursor = _command(text, cursor)
        while cursor < len(text) and text[cursor] != "{":
            if text[cursor] == "%":
                cursor = _line_end(text, cursor)
            else:
                cursor += 1
        end = _balanced_end(text, cursor)
        return (end, True) if end is not None else (len(text), False)
    if cursor < len(text) and text[cursor] == "{":
        end = _balanced_end(text, cursor)
        if end is None:
            return len(text), False
        cursor = end
    elif cursor < len(text) and text[cursor] == "\\":
        _, cursor = _command(text, cursor)
    else:
        return _line_end(text, start), False
    cursor = _skip_space(text, cursor)
    while cursor < len(text) and text[cursor] == "[":
        end = _balanced_end(text, cursor, "[", "]")
        if end is None:
            return len(text), False
        cursor = _skip_space(text, end)
    bodies = (3 if command in _DOCUMENT_ENVIRONMENTS else
              2 if command in {"newenvironment", "renewenvironment", *_DOCUMENT_COMMANDS} else 1)
    for _ in range(bodies):
        end = _balanced_end(text, cursor)
        if end is None:
            return len(text), False
        cursor = _skip_space(text, end)
    return cursor, True


def _skip_verb(text, cursor):
    if cursor < len(text) and text[cursor] == "*":
        cursor += 1
    if cursor >= len(text) or text[cursor].isspace() or text[cursor].isalpha():
        return _line_end(text, cursor), False
    delimiter = text[cursor]
    end = text.find(delimiter, cursor + 1, _line_end(text, cursor))
    return (end + 1, True) if end >= 0 else (_line_end(text, cursor), False)


def _skip_opaque(text, cursor, environment):
    close = re.compile(r"\\end\s*\{" + re.escape(environment) + r"\}")
    match = close.search(text, cursor)
    return (match.end(), True) if match else (len(text), False)


def _find_close(text, cursor, closing, environment=None):
    """Find a matching end without letting comments or raw literals close math."""
    nested = []
    while cursor < len(text):
        value = text[cursor]
        if value == "%":
            cursor = _line_end(text, cursor)
            continue
        if value == "\\":
            command, end = _command(text, cursor)
            if command == "verb":
                cursor, _ = _skip_verb(text, end)
                continue
            if command in _DEFINITIONS:
                cursor, _ = _skip_definition(text, cursor, command, end)
                continue
            match = _ENVIRONMENT.match(text, cursor) if command in {"begin", "end"} else None
            if match:
                direction, name = match.groups()
                if direction == "begin":
                    if name in OPAQUE_ENVIRONMENTS:
                        cursor, _ = _skip_opaque(text, match.end(), name)
                        continue
                    nested.append(name)
                elif nested:
                    if name != nested[-1]:
                        return None, match.end(), "mismatched_environment"
                    nested.pop()
                elif environment:
                    if name == environment:
                        return cursor, match.end(), None
                    return None, match.end(), "mismatched_environment"
                cursor = match.end()
                continue
            if not environment and text.startswith(closing, cursor):
                return cursor, cursor + len(closing), None
            # A new explicit display can recover after an unclosed inline or
            # display region. The earlier region stays a diagnostic and is never
            # given a replacement range that swallows the later formula.
            if not environment and command == "[" and closing in {"$", r"\)", r"\]"}:
                return None, cursor, "unclosed_math"
            cursor = end
            continue
        if not environment and value == "$" and closing in {"$", "$$"}:
            if text.startswith(closing, cursor):
                return cursor, cursor + len(closing), None
        cursor += 1
    return None, len(text), "unclosed_math"


def _checkability(body, kind):
    if kind not in {"inline", "display", *_SCALAR_ENVIRONMENTS}:
        return False, "structured_math_environment"
    if not body.strip():
        return False, "empty_math"
    if len(body) > 32768:
        return False, "math_too_large"
    cursor = 0
    while cursor < len(body):
        if body[cursor] == "%":
            return False, "comments_in_math"
        if body[cursor] == "&":
            return False, "alignment_in_math"
        if body[cursor] == "$":
            return False, "nested_math_delimiter"
        if body[cursor] == "\\":
            command, end = _command(body, cursor)
            if command in {"\\", "begin", "end"}:
                return False, "structured_math"
            if command in {"(", ")", "[", "]"}:
                return False, "nested_math_delimiter"
            if command and (command[0].isalpha() or command[0] == "@") and command not in _KNOWN_COMMANDS:
                return False, "unsupported_command:" + command
            cursor = end
        else:
            cursor += 1
    return True, ""


def analyze_math(content):
    """Return closed math ``nodes`` and lexical ``diagnostics``.

    A diagnostic never supplies an editable range. Incomplete delimiters,
    opaque environments, and definitions are left intact. This function makes
    no assertion about mathematical truth or whole-document TeX validity.
    """
    if not isinstance(content, str):
        raise TypeError("TeX content must be text")
    line_starts = [0] + [index + 1 for index, value in enumerate(content) if value == "\n"]

    def location(offset):
        row = bisect_right(line_starts, offset) - 1
        return row + 1, offset - line_starts[row] + 1

    nodes, diagnostics = [], []

    def diagnostic(code, start, **fields):
        line, column = location(start)
        diagnostics.append({"code": code, "start": start, "line": line,
                            "column": column, **fields})

    cursor = 0
    category_codes_changed = False
    while cursor < len(content):
        value = content[cursor]
        if value == "%":
            cursor = _line_end(content, cursor)
            continue
        opening = closing = kind = environment = None
        if value == "$":
            opening = "$$" if content.startswith("$$", cursor) else "$"
            closing = opening
            kind = "display" if opening == "$$" else "inline"
            body_start = cursor + len(opening)
        elif value == "\\":
            command, end = _command(content, cursor)
            if command == "verb":
                start = cursor
                cursor, valid = _skip_verb(content, end)
                if not valid:
                    diagnostic("unclosed_verb", start)
                continue
            if command in _DEFINITIONS:
                start = cursor
                cursor, valid = _skip_definition(content, start, command, end)
                if not valid:
                    diagnostic("unclosed_definition", start, command=command)
                continue
            if command == "catcode":
                category_codes_changed = True
                diagnostic("category_codes_unsupported", cursor)
            match = _ENVIRONMENT.match(content, cursor) if command in {"begin", "end"} else None
            if match and match.group(1) == "begin":
                name = match.group(2)
                if name in OPAQUE_ENVIRONMENTS:
                    start = cursor
                    cursor, valid = _skip_opaque(content, match.end(), name)
                    if not valid:
                        diagnostic("unclosed_opaque_environment", start, environment=name)
                    continue
                if name in MATH_ENVIRONMENTS:
                    opening, closing, kind = match.group(0), r"\end{" + name + "}", name
                    environment, body_start = name, match.end()
            elif command in {"(", "["}:
                opening, closing = "\\" + command, (r"\)" if command == "(" else r"\]")
                kind, body_start = ("inline" if command == "(" else "display"), end
            elif command in {")", "]"}:
                diagnostic("unexpected_math_close", cursor, closing="\\" + command)
            if opening is None:
                cursor = match.end() if match else end
                continue
        if opening is None:
            cursor += 1
            continue
        start = cursor
        body_end, end, error = _find_close(content, body_start, closing, environment)
        if error:
            diagnostic(error, start, opening=opening, expected_closing=closing)
            cursor = max(body_start, end)
            continue
        latex = content[body_start:body_end]
        checkable, reason = _checkability(latex, kind)
        if category_codes_changed:
            checkable, reason = False, "category_codes_unsupported"
        line, column = location(start)
        end_line, end_column = location(end)
        nodes.append({
            "id": f"f-{line:03d}-{len(nodes) + 1}",
            "line": line, "column": column, "end_line": end_line, "end_column": end_column,
            "start": start, "end": end, "body_start": body_start, "body_end": body_end,
            "latex": latex, "opening": opening, "closing": content[body_end:end],
            "kind": kind, "checkable": checkable, "reason": reason,
            "encoding": "unicode-codepoints",
        })
        cursor = end
    return {"nodes": nodes, "diagnostics": diagnostics}


def extract_math(content):
    """Return math nodes; use :func:`analyze_math` when diagnostics are needed."""
    return analyze_math(content)["nodes"]


def mask_opaque(content):
    """Hide comments, raw regions and definitions without changing offsets."""
    masked = list(content)
    cursor = 0
    while cursor < len(content):
        start, end = cursor, None
        if content[cursor] == "%":
            end = _line_end(content, cursor)
        elif content[cursor] == "\\":
            command, after = _command(content, cursor)
            if command == "verb":
                end, _ = _skip_verb(content, after)
            elif command in _DEFINITIONS:
                end, _ = _skip_definition(content, cursor, command, after)
            elif command == "begin":
                match = _ENVIRONMENT.match(content, cursor)
                if match and match.group(2) in OPAQUE_ENVIRONMENTS:
                    end, _ = _skip_opaque(content, match.end(), match.group(2))
            if end is None:
                cursor = after
                continue
        if end is None:
            cursor += 1
            continue
        for position in range(start, end):
            if masked[position] not in "\r\n":
                masked[position] = " "
        cursor = max(end, start + 1)
    return "".join(masked)
