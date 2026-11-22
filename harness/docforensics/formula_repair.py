"""Conservative syntax patches and source-preservation checks, without inference.

Adapted in scope from TeXada Math-Agent a4a0f434fa483a5951e371f934b9837447aedaae,
``core/fixer.py`` and ``agent/mutation_scope.py``: the original is authoritative;
closing known syntax does not authorize changing mathematical tokens. Unlike a
CAS equivalence test, this module permits only an exact, deterministic patch or
unchanged text. The caller must still validate the resulting formula syntax.
"""

from dataclasses import dataclass
import re

from .tex_context import _checkability

MAX_FORMULA_CHARS = 32768
_MATH_WHITESPACE = frozenset({"\n", "\r", "\t"})
_TOKEN = re.compile(r"\\[A-Za-z@]+|\\.|\\$|[0-9]+(?:\.[0-9]+)?|\.[0-9]+|[^\s]", re.DOTALL)
_UNSAFE_COMMANDS = frozenset({
    r"\verb", r"\begin", r"\end", r"\def", r"\gdef", r"\edef", r"\xdef", r"\let",
    r"\futurelet", r"\catcode", r"\newcommand", r"\renewcommand", r"\providecommand",
    r"\newenvironment", r"\renewenvironment", r"\DeclareRobustCommand", r"\DeclareMathOperator",
    r"\NewDocumentCommand", r"\RenewDocumentCommand", r"\ProvideDocumentCommand",
    r"\DeclareDocumentCommand", r"\NewDocumentEnvironment", r"\RenewDocumentEnvironment",
    r"\ProvideDocumentEnvironment", r"\DeclareDocumentEnvironment", r"\\",
})
_TRAILING_OPERATORS = frozenset({"+", "-", "*", "/", "=", "<", ">", r"\cdot", r"\times", r"\pm", r"\mp"})
_PAIRS = {"(": ")", "[": "]", r"\{": r"\}", r"\langle": r"\rangle"}
_CLOSERS = frozenset(_PAIRS.values())
_SCRIPT_INVALID_RIGHT = frozenset({"^", "_", "}", *_CLOSERS, r"\right", ",", ";"})
_RELATIONS = frozenset({"=", "<", ">", "≤", "≥", "≠", r"\le", r"\leq", r"\ge", r"\geq",
                        r"\ne", r"\neq", r"\equiv", r"\approx", r"\sim", r"\simeq"})
_TWO_ARGUMENT_COMMANDS = frozenset({
    r"\frac", r"\dfrac", r"\tfrac", r"\binom", r"\dbinom", r"\tbinom",
})
_POSTFIX_SCRIPT_FOLLOWERS = frozenset(
    {"}", ")", "]", r"\}", r"\rangle", ",", ";", "|", r"\vert", r"\rvert", r"\right"}
    | _RELATIONS
    | _TRAILING_OPERATORS
    | {
        r"\to", r"\rightarrow", r"\leftarrow", r"\leftrightarrow", r"\mapsto",
        r"\implies", r"\iff", r"\Rightarrow", r"\Leftarrow", r"\Leftrightarrow",
        r"\in", r"\notin", r"\ni", r"\subset", r"\subseteq", r"\supset", r"\supseteq",
        r"\quad", r"\qquad", r"\,", r"\;", r"\:", r"\!", r"\thinspace", r"\negthinspace",
    }
)
_UNARY_SCRIPT_COMMANDS = frozenset({
    r"\mathrm", r"\mathit", r"\mathbf", r"\mathsf", r"\mathtt",
    r"\mathcal", r"\mathbb", r"\boldsymbol", r"\overline", r"\underline",
    r"\hat", r"\widehat", r"\bar", r"\vec", r"\dot", r"\ddot",
    r"\tilde", r"\widetilde", r"\sqrt",
})


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int


def _strip_math(text):
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


def _tokens(text):
    return [_Token(match[0], match.start(), match.end()) for match in _TOKEN.finditer(text)]


def _script_arg_end(tokens, index, group_ends):
    if index >= len(tokens):
        return None
    argument = tokens[index].text
    if argument == "{":
        return group_ends.get(index)
    if len(argument) == 1 and argument.isalnum():
        return index + 1
    if (argument.startswith("\\") and len(argument) > 1
            and argument not in {r"\left", r"\right", r"\middle"}):
        if argument in _UNARY_SCRIPT_COMMANDS and index + 1 < len(tokens) and tokens[index + 1].text == "{":
            return group_ends.get(index + 1)
        return index + 1
    # TeX consumes one character of an unbraced multi-digit literal;
    # treating the entire number as the script would invent a conflict.
    return None


def _duplicate_script(tokens):
    """Recognize duplicate scripts only when their preceding arguments are unambiguous."""
    stack, group_ends = [], {}
    for index, token in enumerate(tokens):
        if token.text == "{":
            stack.append(index)
        elif token.text == "}" and stack:
            group_ends[stack.pop()] = index + 1
    for index, token in enumerate(tokens[:-1]):
        if token.text not in {"^", "_"}:
            continue
        seen = {token.text}
        cursor = _script_arg_end(tokens, index + 1, group_ends)
        while cursor is not None and cursor < len(tokens) and tokens[cursor].text in {"^", "_"}:
            script = tokens[cursor].text
            if script in seen:
                return True
            seen.add(script)
            cursor = _script_arg_end(tokens, cursor + 1, group_ends)
    return False


def _parser_coverage_unsupported(tokens):
    """Identify known scalar-parser gaps without rewriting their mathematics."""
    # Evaluation at a boundary is notation, not a missing multiplication or a
    # request to evaluate the expression. Invisible left delimiters are not
    # candidates for the paired-delimiter repair rule either.
    evaluation_left = any(tokens[index].text == r"\left" and tokens[index + 1].text == "."
                          for index in range(len(tokens) - 1))
    if evaluation_left and any(
        tokens[index].text == r"\right" and tokens[index + 1].text in {"|", r"\vert", r"\rvert"}
        and tokens[index + 2].text == "_" for index in range(len(tokens) - 2)
    ):
        return True
    depth, relations, previous = 0, 0, None
    for token in tokens:
        value = token.text
        if value in {"{", *_PAIRS}:
            depth += 1
        elif value in {"}", *_CLOSERS}:
            depth = max(0, depth - 1)
        elif depth == 0 and value in _RELATIONS:
            # An ASCII <= or >= is a single relation, including a spaced form.
            if not (value == "=" and previous in {"<", ">"}):
                relations += 1
                if relations > 1:
                    return True
        previous = value
    return False


def _skip_argument(arg_tokens, index):
    """Return the index after one non-empty TeX argument, or ``None`` when absent."""
    if index >= len(arg_tokens):
        return None
    first = arg_tokens[index]
    if first != "{":
        if first in {"}", "^", "_", r"\left", r"\right", r"\middle", "\\"}:
            return None
        return index + 1
    depth = 0
    has_payload = False
    for cursor in range(index, len(arg_tokens)):
        piece = arg_tokens[cursor]
        if piece == "{":
            depth += 1
        elif piece == "}":
            depth -= 1
            if depth == 0:
                return (cursor + 1) if has_payload else None
        else:
            has_payload = True
    return None


def _missing_required_argument(text):
    """True when a known two-argument command still lacks one after brace closing."""
    arg_tokens = []
    for token in _tokens(text):
        if token.text.startswith("\\"):
            arg_tokens.append(token.text)
        else:
            arg_tokens.extend(token.text)
    for index, piece in enumerate(arg_tokens):
        if piece not in _TWO_ARGUMENT_COMMANDS:
            continue
        first = _skip_argument(arg_tokens, index + 1)
        if first is None or _skip_argument(arg_tokens, first) is None:
            return True
    return False


def _has_missing_script_operand(tokens):
    if tokens[-1].text in {"^", "_"}:
        return True
    for index, left in enumerate(tokens[:-1]):
        if left.text not in {"^", "_"}:
            continue
        if index == 0 or (
            tokens[index - 1].text in {"{", *_PAIRS} | _TRAILING_OPERATORS | _RELATIONS
            and not (index >= 2 and tokens[index - 2].text == "^" and tokens[index - 1].text in {"+", "-", "*"})
        ):
            return True
        right = tokens[index + 1]
        if left.text == "_":
            if right.text in _TRAILING_OPERATORS | _RELATIONS | _SCRIPT_INVALID_RIGHT:
                return True
            continue
        if right.text == "*":
            continue
        if right.text in {"+", "-"}:
            if index + 2 >= len(tokens) or tokens[index + 2].text in _POSTFIX_SCRIPT_FOLLOWERS:
                continue
            return True
        if right.text in (_TRAILING_OPERATORS - {"+", "-", "*"}) | _RELATIONS | _SCRIPT_INVALID_RIGHT:
            return True
    return False


def repair_blocker(original, *, allow_parser_gaps=False):
    """Return a stable reason for source that must not be guessed, or ``None``."""
    if not isinstance(original, str) or not _strip_math(original):
        return "invalid_original"
    text = _strip_math(original)
    if len(text) > MAX_FORMULA_CHARS:
        return "original_too_large"
    if any((ord(char) < 32 and char not in _MATH_WHITESPACE) or ord(char) == 127 for char in original):
        return "control_character_in_source"
    tokens = _tokens(text)
    if any(token.text == "%" for token in tokens):
        return "comment_in_source"
    if any(token.text in _UNSAFE_COMMANDS for token in tokens):
        return "unsupported_source_command"
    if any(token.text == "$" for token in tokens):
        return "math_delimiter_in_body"
    # CLI layout text has not passed Studio's scanner. Apply the same scalar
    # support boundary before closing a group around an unknown/document macro.
    supported, support_reason = _checkability(original, "inline")
    if not supported:
        return "unsupported_source_structure:" + support_reason
    depth = 0
    for token in tokens:
        depth += (token.text == "{") - (token.text == "}")
        if depth < 0:
            return "extra_closing_brace"
    if not allow_parser_gaps and _parser_coverage_unsupported(tokens):
        return "parser_coverage_unsupported"
    if tokens[-1].text == "\\":
        return "incomplete_command"
    if _has_missing_script_operand(tokens):
        return "missing_script_operand"
    if tokens[-1].text in _TRAILING_OPERATORS and not (
        len(tokens) >= 3 and tokens[-2].text == "^" and tokens[-1].text in {"+", "-", "*"}
    ):
        return "missing_operator_operand"
    if tokens[-1].text == "{":
        return "missing_group_content"
    if tokens[-1].text in _PAIRS:
        return "missing_delimiter_content"
    if _duplicate_script(tokens):
        return "duplicate_script"
    # Closing the open groups must not be the repair when a command still lacks
    # an argument that is not present in the source. Inventing one, or deleting
    # a brace to manufacture it, would change the mathematics.
    closed = text + "}" * depth
    if _missing_required_argument(closed):
        return "missing_command_argument"
    return None


def _close_left(text):
    """Add one missing right command only when the visible pair is unambiguous."""
    tokens = _tokens(text)
    lefts = [index for index, token in enumerate(tokens) if token.text == r"\left"]
    if not lefts:
        return text, False
    rights = [token for token in tokens if token.text == r"\right"]
    missing_right_delimiter = len(lefts) == len(rights) == 1 and tokens[-1].text == r"\right"
    if len(lefts) == len(rights) and not missing_right_delimiter:
        return text, False
    if len(lefts) != 1 or (rights and not missing_right_delimiter):
        return None, False
    left = lefts[0]
    if left + 1 >= len(tokens) or tokens[left + 1].text not in _PAIRS:
        return None, False
    stack = []
    group_depth = 0
    left_depth = None
    close_position = None
    for index, token in enumerate(tokens):
        value = token.text
        if value == "{":
            group_depth += 1
        elif value == "}":
            group_depth -= 1
            if left_depth is not None and close_position is None and group_depth < left_depth:
                return None, False
        if value in _PAIRS:
            is_left = index == left + 1
            if is_left:
                left_depth = group_depth
            stack.append((value, is_left, group_depth))
        elif value in _CLOSERS:
            if not stack or _PAIRS[stack[-1][0]] != value or stack[-1][2] != group_depth:
                return None, False
            _, is_left, _ = stack.pop()
            if is_left:
                close_position = token.start
    if close_position is not None:
        if stack or missing_right_delimiter:
            return None, False
        return text[:close_position] + r"\right" + text[close_position:], True
    if len(stack) == 1 and stack[0][1] and stack[0][2] == 0:
        command = "" if missing_right_delimiter else r"\right"
        return text + command + _PAIRS[stack[0][0]], True
    return None, False


def _deterministic_patch(original):
    if repair_blocker(original):
        return None, "none"
    text = original
    depth = sum((token.text == "{") - (token.text == "}") for token in _tokens(text))
    if len(text) + depth > MAX_FORMULA_CHARS:
        return None, "none"
    candidate = text + "}" * depth
    candidate, paired = _close_left(candidate)
    if candidate is None or len(candidate) > MAX_FORMULA_CHARS:
        return None, "none"
    if not depth and not paired:
        return None, "none"
    method = "close_trailing_braces_and_left_right" if depth and paired else (
        "close_trailing_braces" if depth else "pair_left_right")
    return candidate, method


def deterministic_candidate(original):
    """Return a source-preserving syntax candidate; never invent an operand."""
    return _deterministic_patch(original)[0]


def assess_candidate(original, candidate):
    """Authorize unchanged source or an exact deterministic syntax patch.

    Grouping and all existing math tokens are authoritative. The first
    differing token in a rejection is available for bounded retry feedback.
    """
    rejected = {"allowed": False, "reason": "invalid_candidate", "method": "none"}
    if not isinstance(original, str) or not _strip_math(original):
        return {**rejected, "reason": "invalid_original"}
    if not isinstance(candidate, str) or not _strip_math(candidate):
        return rejected
    if len(candidate) > MAX_FORMULA_CHARS:
        return {**rejected, "reason": "candidate_too_large"}
    before, after = _strip_math(original), _strip_math(candidate)
    if any((ord(char) < 32 and char not in _MATH_WHITESPACE) or ord(char) == 127 for char in candidate):
        return {**rejected, "reason": "control_character_in_candidate"}
    if before == after:
        return {"allowed": True, "reason": "unchanged_source", "method": "unchanged"}
    expected, method = _deterministic_patch(original)
    if expected is not None and after == _strip_math(expected):
        return {"allowed": True, "reason": "deterministic_syntax_patch", "method": method}
    reason = repair_blocker(original) or "unauthorized_source_change"
    result = {**rejected, "reason": reason}
    old_tokens, new_tokens = _tokens(before), _tokens(after)
    for index in range(max(len(old_tokens), len(new_tokens))):
        old = old_tokens[index].text if index < len(old_tokens) else None
        new = new_tokens[index].text if index < len(new_tokens) else None
        if old != new:
            result.update(token_index=index, original_token=old, candidate_token=new)
            break
    else:
        result["reason"] = "source_spacing_changed"
    return result
