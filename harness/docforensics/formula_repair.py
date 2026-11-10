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
_RELATIONS = frozenset({"=", "<", ">", "≤", "≥", "≠", r"\le", r"\leq", r"\ge", r"\geq",
                        r"\ne", r"\neq", r"\equiv", r"\approx", r"\sim", r"\simeq"})
_TWO_ARGUMENT_COMMANDS = frozenset({
    r"\frac", r"\dfrac", r"\tfrac", r"\binom", r"\dbinom", r"\tbinom",
})


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int


def _tokens(text):
    return [_Token(match[0], match.start(), match.end()) for match in _TOKEN.finditer(text)]


def _duplicate_script(tokens):
    """Recognize duplicate scripts only when their first argument is unambiguous."""
    stack, group_ends = [], {}
    for index, token in enumerate(tokens):
        if token.text == "{":
            stack.append(index)
        elif token.text == "}" and stack:
            group_ends[stack.pop()] = index + 1
    for index, token in enumerate(tokens[:-1]):
        if token.text not in {"^", "_"}:
            continue
        end = index + 1
        argument = tokens[end].text
        if argument == "{":
            if end not in group_ends:
                continue
            end = group_ends[end]
        elif len(argument) == 1 and argument.isalnum():
            end += 1
        else:
            # TeX consumes one character of an unbraced multi-digit literal;
            # treating the entire number as the script would invent a conflict.
            continue
        if end < len(tokens) and tokens[end].text == token.text:
            return True
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


def _skip_argument(tokens, index):
    """Return the index after one TeX argument, or ``None`` when it is absent."""
    if index >= len(tokens):
        return None
    if tokens[index].text != "{":
        return index + 1
    depth = 0
    for cursor in range(index, len(tokens)):
        if tokens[cursor].text == "{":
            depth += 1
        elif tokens[cursor].text == "}":
            depth -= 1
            if depth == 0:
                return cursor + 1
    return None


def _missing_required_argument(text):
    """True when a known two-argument command still lacks one after brace closing."""
    tokens = _tokens(text)
    for index, token in enumerate(tokens):
        if token.text not in _TWO_ARGUMENT_COMMANDS:
            continue
        first = _skip_argument(tokens, index + 1)
        if first is None or _skip_argument(tokens, first) is None:
            return True
    return False


def repair_blocker(original):
    """Return a stable reason for source that must not be guessed, or ``None``."""
    if not isinstance(original, str) or not original.strip():
        return "invalid_original"
    text = original.strip()
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
    if _parser_coverage_unsupported(tokens):
        return "parser_coverage_unsupported"
    if tokens[-1].text == "\\":
        return "incomplete_command"
    if tokens[-1].text in {"^", "_"}:
        return "missing_script_operand"
    if tokens[-1].text in _TRAILING_OPERATORS:
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
    """Authorize only an unchanged body or the same deterministic syntax patch.

    ``reason`` is a bounded, stable rejection category. The first differing
    mathematical token is also returned for useful retry feedback. Ordered
    tokens include grouping; token equality alone never authorizes an edit.
    """
    rejected = {"allowed": False, "reason": "invalid_candidate", "method": "none"}
    if not isinstance(original, str) or not original.strip():
        return {**rejected, "reason": "invalid_original"}
    if not isinstance(candidate, str) or not candidate.strip():
        return rejected
    if len(candidate) > MAX_FORMULA_CHARS:
        return {**rejected, "reason": "candidate_too_large"}
    before, after = original.strip(), candidate.strip()
    if any((ord(char) < 32 and char not in _MATH_WHITESPACE) or ord(char) == 127 for char in candidate):
        return {**rejected, "reason": "control_character_in_candidate"}
    if before == after:
        return {"allowed": True, "reason": "unchanged_source", "method": "unchanged"}
    expected, method = _deterministic_patch(original)
    if expected is not None and after == expected.strip():
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
