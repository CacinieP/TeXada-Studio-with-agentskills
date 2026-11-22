"""Document-level conservative TeX cleanup inspection and source-preservation guard.

Detects and validates fixes for:
1. Zero-width format noise (``\\ufeff``, ``\\u200b``, ``\\u200c``, ``\\u200d``) outside
   comments, opaque blocks, and math spans;
2. Unclosed single-line prose/section brace commands (``\\section{...``, ``\\textbf{...``, etc.);
3. Unclosed common prose environments (``itemize``, ``enumerate``, ``center``, ``quote``, etc.).

All prose text, author comments, opaque code blocks, and math bodies remain
authoritative and may never be altered or deleted by a cleanup candidate.
"""

from bisect import bisect_right
from functools import lru_cache
import re

from .tex_context import (
    OPAQUE_ENVIRONMENTS,
    _DEFINITIONS,
    _ENVIRONMENT,
    _balanced_end,
    _command,
    _line_end,
    _skip_definition,
    _skip_opaque,
    _skip_verb,
    analyze_math,
)

MAX_CLEANUP_CHARS = 262144
ZERO_WIDTH_CHARS = frozenset({"\ufeff", "\u200b", "\u200c", "\u200d"})
PROSE_BRACE_COMMANDS = frozenset({
    "section", "subsection", "subsubsection",
    "title", "author",
    "textbf", "textit", "emph",
})
PROSE_ENVIRONMENTS = frozenset({
    "itemize", "enumerate", "description",
    "center", "flushleft", "flushright",
    "quote", "quotation", "abstract",
})


def _line_starts(text):
    return [0] + [idx + 1 for idx, ch in enumerate(text) if ch == "\n"]


def _line_of(starts, offset):
    return bisect_right(starts, offset)


def _protected_mask(content, math_report):
    """Mark comments, raw/opaque regions, definitions, and math spans as protected."""
    protected = bytearray(len(content))
    comments = []
    cursor = 0
    while cursor < len(content):
        start, end = cursor, None
        if content[cursor] == "%":
            end = _line_end(content, cursor)
            comments.append(content[start:end])
        elif content[cursor] == "\\":
            command, after = _command(content, cursor)
            if command == "verb":
                end, _ = _skip_verb(content, after)
            elif command in _DEFINITIONS:
                def_end, valid = _skip_definition(content, cursor, command, after)
                if valid or def_end > after:
                    end = def_end
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
        for pos in range(start, min(end, len(content))):
            if content[pos] not in "\r\n":
                protected[pos] = 1
        cursor = max(end, start + 1)

    for node in math_report["nodes"]:
        for pos in range(node["start"], min(node["end"], len(content))):
            protected[pos] = 1
    for diag in math_report["diagnostics"]:
        if diag.get("code") in {"unclosed_math", "mismatched_environment"}:
            for pos in range(diag["start"], len(content)):
                protected[pos] = 1
    return protected, comments


def _command_brace_start_same_line(content, protected, after):
    line_limit = _line_end(content, after)
    cursor = after
    if cursor < line_limit and not protected[cursor] and content[cursor] == "*":
        cursor += 1
    while cursor < line_limit and not protected[cursor] and content[cursor] in " \t":
        cursor += 1
    while cursor < line_limit and not protected[cursor] and content[cursor] == "[":
        end = _balanced_end(content, cursor, "[", "]")
        if end is None or end > line_limit:
            return None
        cursor = end
        while cursor < line_limit and not protected[cursor] and content[cursor] in " \t":
            cursor += 1
    if cursor < line_limit and not protected[cursor] and content[cursor] == "{":
        return cursor
    return None


def inspect_tex_cleanup(content):
    """Inspect ``content`` for conservative format noise or unclosed prose structures."""
    empty = {
        "problems": [],
        "zero_width_offsets": [],
        "unclosed_commands": [],
        "unclosed_environments": [],
        "brace_balanced": False,
        "env_balanced": False,
    }
    if not isinstance(content, str) or not content or len(content) > MAX_CLEANUP_CHARS:
        return empty
    if any((ord(ch) < 32 and ch not in "\n\r\t") or ord(ch) == 127 for ch in content):
        return empty

    math_report = analyze_math(content)
    protected, _ = _protected_mask(content, math_report)
    starts = _line_starts(content)

    zero_width_offsets = [
        idx for idx, ch in enumerate(content)
        if not protected[idx] and ch in ZERO_WIDTH_CHARS
    ]

    brace_stack = []
    brace_negative = False
    env_stack = []
    unclosed_envs = []
    env_mismatch = False
    other_unclosed_env = False

    cursor = 0
    while cursor < len(content):
        if protected[cursor]:
            cursor += 1
            continue
        ch = content[cursor]
        if ch == "\\":
            env_match = _ENVIRONMENT.match(content, cursor)
            if env_match and not any(protected[pos] for pos in range(cursor, env_match.end())):
                direction, raw_name = env_match.groups()
                name = raw_name.strip()
                if direction == "begin":
                    env_stack.append({
                        "name": name,
                        "line": _line_of(starts, cursor),
                        "offset": cursor,
                    })
                else:
                    if env_stack and env_stack[-1]["name"] == name:
                        env_stack.pop()
                    else:
                        match_idx = next(
                            (idx for idx in range(len(env_stack) - 1, -1, -1)
                             if env_stack[idx]["name"] == name),
                            None,
                        )
                        if (match_idx is not None
                                and all(item["name"] in PROSE_ENVIRONMENTS
                                        for item in env_stack[match_idx + 1:])):
                            for item in reversed(env_stack[match_idx + 1:]):
                                unclosed_envs.append(item)
                            del env_stack[match_idx:]
                        else:
                            env_mismatch = True
                cursor = env_match.end()
                continue

            command, after = _command(content, cursor)
            if command in PROSE_BRACE_COMMANDS:
                brace_pos = _command_brace_start_same_line(content, protected, after)
                if brace_pos is not None:
                    brace_stack.append({
                        "command": command,
                        "line": _line_of(starts, cursor),
                        "offset": cursor,
                        "brace_offset": brace_pos,
                    })
                    cursor = brace_pos + 1
                    continue
            cursor = max(after, cursor + 1)
            continue

        if ch == "{":
            brace_stack.append({
                "command": None,
                "line": _line_of(starts, cursor),
                "offset": cursor,
                "brace_offset": cursor,
            })
        elif ch == "}":
            if brace_stack:
                brace_stack.pop()
            else:
                brace_negative = True
        cursor += 1

    for item in reversed(env_stack):
        if item["name"] in PROSE_ENVIRONMENTS:
            unclosed_envs.append(item)
        else:
            other_unclosed_env = True

    unclosed_envs.sort(key=lambda item: item["offset"])

    unclosed_commands = []
    if (not brace_negative
            and not math_report["diagnostics"]
            and brace_stack
            and all(item["command"] in PROSE_BRACE_COMMANDS for item in brace_stack)):
        unclosed_commands = list(brace_stack)

    problems = []
    if zero_width_offsets:
        first_line = _line_of(starts, zero_width_offsets[0])
        problems.append({
            "id": f"c-{first_line:03d}-zwsp",
            "type": "cleanup",
            "kind": "zero_width_noise",
            "line": first_line,
            "count": len(zero_width_offsets),
            "status": "RETRY",
            "deterministic": True,
            "reason": "文档含零宽格式噪声字符，可安全清理",
        })
    if not brace_negative and unclosed_commands:
        for idx, item in enumerate(unclosed_commands, 1):
            problems.append({
                "id": f"c-{item['line']:03d}-brace-{idx}",
                "type": "cleanup",
                "kind": "unclosed_command_brace",
                "command": item["command"],
                "line": item["line"],
                "status": "RETRY",
                "deterministic": False,
                "reason": f"命令 \\{item['command']} 缺少闭合右花括号，可尝试结构补全",
            })
    if not env_mismatch and not other_unclosed_env and unclosed_envs:
        for idx, item in enumerate(unclosed_envs, 1):
            problems.append({
                "id": f"c-{item['line']:03d}-env-{idx}",
                "type": "cleanup",
                "kind": "unclosed_environment",
                "environment": item["name"],
                "line": item["line"],
                "status": "RETRY",
                "deterministic": False,
                "reason": f"正文环境 {item['name']} 缺少闭合 \\end{{{item['name']}}}，可尝试结构补全",
            })

    return {
        "problems": problems,
        "zero_width_offsets": zero_width_offsets,
        "unclosed_commands": unclosed_commands,
        "unclosed_environments": unclosed_envs if not env_mismatch and not other_unclosed_env else [],
        "brace_balanced": not brace_negative and not brace_stack,
        "env_balanced": not env_mismatch and not other_unclosed_env and not unclosed_envs and not env_stack,
    }


def _strip_offsets(text, offsets):
    skip = set(offsets)
    if not skip:
        return text
    return "".join(ch for idx, ch in enumerate(text) if idx not in skip)


def deterministic_cleanup_candidate(content):
    """Strip zero-width format noise outside protected regions when no structural closure is needed."""
    report = inspect_tex_cleanup(content)
    if not report["zero_width_offsets"]:
        return None
    if report["unclosed_commands"] or report["unclosed_environments"]:
        return None
    return _strip_offsets(content, report["zero_width_offsets"])


def _is_unescaped(text, pos):
    slashes = 0
    cursor = pos - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 0


def _decompose_cleanup(original, candidate):
    """Return ``(zw_offsets, insertions, reason, method)`` when valid, else ``(None, None, reason, None)``."""
    if not isinstance(original, str) or not original.strip():
        return None, None, "invalid_original", None
    if not isinstance(candidate, str) or not candidate.strip():
        return None, None, "invalid_candidate", None
    if len(candidate) > MAX_CLEANUP_CHARS:
        return None, None, "candidate_too_large", None
    if any((ord(ch) < 32 and ch not in "\n\r\t") or ord(ch) == 127 for ch in candidate):
        return None, None, "control_character_in_candidate", None
    if original == candidate:
        return None, None, "unchanged_candidate", None

    orig_report = inspect_tex_cleanup(original)
    if not orig_report["problems"]:
        return None, None, "no_cleanup_needed", None

    orig_math = analyze_math(original)
    cand_math = analyze_math(candidate)
    if ([(n["opening"], n["latex"], n["closing"]) for n in orig_math["nodes"]]
            != [(n["opening"], n["latex"], n["closing"]) for n in cand_math["nodes"]]
            or len(orig_math["diagnostics"]) != len(cand_math["diagnostics"])):
        return None, None, "math_content_modified", None

    protected, orig_comments = _protected_mask(original, orig_math)
    _, cand_comments = _protected_mask(candidate, cand_math)
    if orig_comments != cand_comments:
        return None, None, "comment_modified", None

    zw_offsets = orig_report["zero_width_offsets"]
    zw_set = set(zw_offsets)
    base_chars = []
    base_to_orig = []
    for idx, ch in enumerate(original):
        if idx not in zw_set:
            base_chars.append(ch)
            base_to_orig.append(idx)
    base_to_orig.append(len(original))
    base = "".join(base_chars)

    need_braces = len(orig_report["unclosed_commands"])
    need_envs = tuple(item["name"] for item in orig_report["unclosed_environments"])

    if need_braces == 0 and not need_envs:
        if candidate != base:
            return None, None, "unauthorized_cleanup_change", None
        after_report = inspect_tex_cleanup(candidate)
        if after_report["problems"]:
            return None, None, "cleanup_incomplete", None
        return zw_offsets, (), "deterministic_cleanup", "strip_zero_width"

    if need_braces + len(need_envs) > 16:
        return None, None, "cleanup_deficit_too_large", None

    env_patterns = {
        env: re.compile(r"(?:\r?\n)?[ \t]*\\end\{" + re.escape(env) + r"\}(?:\r?\n)?")
        for env in set(need_envs)
    }

    def safe_insert_position(base_idx):
        orig_pos = base_to_orig[base_idx]
        if orig_pos > 0 and orig_pos < len(original) and protected[orig_pos - 1] and protected[orig_pos]:
            return False
        if not _is_unescaped(base, base_idx):
            return False
        for node in orig_math["nodes"]:
            if node["start"] < orig_pos < node["end"]:
                return False
        return True

    @lru_cache(maxsize=16384)
    def dfs(i, j, rem_b, rem_envs):
        if rem_b == 0 and not rem_envs:
            return () if base[i:] == candidate[j:] else None
        min_extra = rem_b + sum(len(env) + 6 for env in rem_envs)
        if len(candidate) - j < (len(base) - i) + min_extra:
            return None
        if j < len(candidate) and safe_insert_position(i):
            if rem_b > 0 and candidate[j] == "}" and _is_unescaped(candidate, j):
                tail = dfs(i, j + 1, rem_b - 1, rem_envs)
                if tail is not None:
                    return ((j, j + 1, base_to_orig[i]),) + tail
            seen_envs = set()
            for idx_env, env in enumerate(rem_envs):
                if env in seen_envs:
                    continue
                seen_envs.add(env)
                match = env_patterns[env].match(candidate, j)
                if match:
                    rest_envs = rem_envs[:idx_env] + rem_envs[idx_env + 1:]
                    tail = dfs(i, match.end(), rem_b, rest_envs)
                    if tail is not None:
                        return ((j, match.end(), base_to_orig[i]),) + tail
        if i < len(base) and j < len(candidate) and base[i] == candidate[j]:
            return dfs(i + 1, j + 1, rem_b, rem_envs)
        return None

    insertions = dfs(0, 0, need_braces, need_envs)
    if insertions is None:
        return None, None, "unauthorized_cleanup_change", None

    after_report = inspect_tex_cleanup(candidate)
    if after_report["problems"] or not after_report["brace_balanced"] or not after_report["env_balanced"]:
        return None, None, "cleanup_incomplete", None
    return zw_offsets, insertions, "structural_cleanup_repair", "structural_cleanup_insertion"


def assess_cleanup_candidate(original, candidate):
    """Authorize only conservative zero-width stripping and/or exact structural closures."""
    zw_offsets, insertions, reason, method = _decompose_cleanup(original, candidate)
    if method is None:
        return {"allowed": False, "reason": reason, "method": "none"}
    return {"allowed": True, "reason": reason, "method": method}


def _tabular_ranges(content):
    ranges = []
    for match in re.finditer(r"\\begin\s*\{tabular\}.*?\\end\s*\{tabular\}", content, re.S):
        ranges.append((match.start(), match.end()))
    return ranges


def cleanup_edits(original, candidate):
    """Build disjoint span edits ``(line, start, end, before, after, skill)`` transforming ``original`` into ``candidate``."""
    zw_offsets, insertions, _reason, method = _decompose_cleanup(original, candidate)
    if method is None:
        return []

    atomic = []
    for offset in zw_offsets:
        atomic.append((offset, offset + 1, ""))
    for j_start, j_end, orig_pos in insertions:
        atomic.append((orig_pos, orig_pos, candidate[j_start:j_end]))
    atomic.sort(key=lambda item: (item[0], item[1]))

    merged = []
    for s, e, text in atomic:
        if merged and s <= merged[-1][1]:
            prev_s, prev_e, prev_text = merged[-1]
            overlap_suffix = original[prev_e:max(prev_e, s)]
            merged[-1] = (prev_s, max(prev_e, e), prev_text + overlap_suffix + text)
        else:
            merged.append((s, e, text))

    starts = _line_starts(original)
    math_ranges = [(n["start"], n["end"]) for n in analyze_math(original)["nodes"]]
    forbidden = sorted(math_ranges + _tabular_ranges(original))

    def overlaps_forbidden(span_s, span_e):
        return any(f_s < span_e and span_s < f_e for f_s, f_e in forbidden)

    line_bounds = []
    for idx, l_start in enumerate(starts):
        next_start = starts[idx + 1] - 1 if idx + 1 < len(starts) else len(original)
        if next_start > l_start and original[next_start - 1] == "\r":
            next_start -= 1
        line_bounds.append((l_start, next_start))

    expanded = []
    for s, e, text in merged:
        line_no = _line_of(starts, min(s, max(len(original) - 1, 0)))
        l_start, l_end = line_bounds[line_no - 1]
        if l_start <= s and e <= l_end and not overlaps_forbidden(l_start, l_end):
            if expanded and expanded[-1]["start"] == l_start and expanded[-1]["end"] == l_end:
                prev = expanded[-1]
                rel_s = s - prev["_cursor"]
                prev["_pieces"].append(original[prev["_cursor"]:s])
                prev["_pieces"].append(text)
                prev["_cursor"] = e
            else:
                expanded.append({
                    "line": line_no,
                    "start": l_start,
                    "end": l_end,
                    "_pieces": [original[l_start:s], text],
                    "_cursor": e,
                })
        else:
            expanded.append({
                "line": line_no,
                "start": s,
                "end": e,
                "_pieces": [text],
                "_cursor": e,
            })

    edits = []
    for item in expanded:
        after_text = "".join(item["_pieces"]) + original[item["_cursor"]:item["end"]]
        before_text = original[item["start"]:item["end"]]
        if before_text != after_text:
            edits.append({
                "line": item["line"],
                "before": before_text,
                "after": after_text,
                "skill": "latex-cleanup",
                "start": item["start"],
                "end": item["end"],
            })

    rebuilt = original
    for edit in sorted(edits, key=lambda item: (item["start"], item["end"]), reverse=True):
        rebuilt = rebuilt[:edit["start"]] + edit["after"] + rebuilt[edit["end"]:]
    if rebuilt != candidate:
        edits = [{
            "line": _line_of(starts, min(s, max(len(original) - 1, 0))),
            "before": original[s:e],
            "after": text,
            "skill": "latex-cleanup",
            "start": s,
            "end": e,
        } for s, e, text in merged if original[s:e] != text]
    return edits
