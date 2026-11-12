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
