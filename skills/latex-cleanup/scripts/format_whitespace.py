#!/usr/bin/env python3
"""Conservative, source-preserving whitespace edits; dry-run unless --write.

This is a small helper, not a general formatter or a semantic validator.
TeX needs only Python's standard library. Markdown additionally needs markdown-it-py.
"""

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


LITERAL_ENVS = {
    "verbatim", "verbatim*", "Verbatim", "Verbatim*", "BVerbatim", "LVerbatim",
    "SaveVerbatim", "lstlisting", "minted", "comment", "filecontents", "filecontents*",
    "alltt", "luacode", "luacode*", "pycode", "python", "sagesilent",
}


def split_lines(text):
    # Unlike str.splitlines(), do not treat Unicode paragraph/line separators as newlines.
    return [s for s in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text) if s]


def line_parts(line):
    body = line.rstrip("\r\n")
    return body, line[len(body):]


def tex_code(line):
    for match in re.finditer("%", line):
        prefix = line[:match.start()]
        if (len(prefix) - len(prefix.rstrip("\\"))) % 2 == 0:
            return prefix
    return line


def format_tex(text, extra_envs=()):
    lines = split_lines(text)
    visible = "\n".join(tex_code(line) for line in lines)
    if re.search(
        r"\\(?:catcode|endlinechar|obeyspaces|obeylines|ExplSyntaxOn|directlua|"
        r"DefineVerbatimEnvironment|lstnewenvironment|newenvironment|renewenvironment|"
        r"NewDocumentEnvironment|lstinline|mintinline|SaveVerb)\b", visible
    ):
        return text, ["Skipped: custom syntax/literal definitions require contextual editing."]
    envs = LITERAL_ENVS | set(extra_envs)
    active = None
    output = []
    for line in lines:
        body, ending = line_parts(line)
        if active:
            output.append(line)
            if re.fullmatch(r"\s*\\end\{" + re.escape(active) + r"\}\s*", body):
                active = None
            continue
        code = tex_code(body)
        begins = re.findall(r"\\begin\{([^{}]+)\}", code)
        literal = next((name for name in begins if name in envs), None)
        if literal:
            active = literal
            output.append(line)
            continue
        # Keep comments, verb commands and potential control-space endings byte-for-byte.
        if code != body or re.search(r"\\verb(?:\*|\b)", code) or body.rstrip(" \t").endswith("\\"):
            output.append(line)
            continue
        output.append(body.rstrip(" \t") + ending)
    notes = ["Unclosed literal environment: remainder preserved."] if active else []
    return "".join(output), notes


def markdown_view(text):
    """Mask front matter only, retaining line count for source maps."""
    lines = split_lines(text)
    if not lines or lines[0].strip() not in ("---", "+++"):
        return text, set(), []
    opening = lines[0].strip()
    closers = {"---", "..."} if opening == "---" else {"+++"}
    stop = next((i for i in range(1, len(lines)) if lines[i].strip() in closers), None)
    if stop is None:
        return "", set(range(len(lines))), ["Unclosed front matter: entire file preserved."]
    masked = [line_parts(line)[1] for line in lines[:stop + 1]] + lines[stop + 1:]
    return "".join(masked), set(range(stop + 1)), []


def mask_range(characters, start, end, fill=" "):
    """Hide syntax without changing offsets or line boundaries."""
    characters[start:end] = ["\n" if char == "\n" else fill for char in characters[start:end]]


def find_unescaped(text, marker, start):
    while True:
        position = text.find(marker, start)
        if position < 0:
            return -1
        prefix = text[:position]
        if (len(prefix) - len(prefix.rstrip("\\"))) % 2 == 0:
            return position
        start = position + len(marker)


def inline_math_ranges(line):
    """Conservative single-line $...$ spans; do not pair currency-like closers."""
    markers = []
    position = 0
    while True:
        position = find_unescaped(line, "$", position)
        if position < 0:
            break
        if (position == 0 or line[position - 1] != "$") and line[position + 1:position + 2] != "$":
            markers.append(position)
        position += 1
    index = 0
    while index < len(markers):
        begin = markers[index]
        index += 1
        if begin + 1 >= len(line) or line[begin + 1].isspace():
            continue
        for following in range(index, len(markers)):
            end = markers[following]
            if not line[end - 1].isspace() and not line[end + 1:end + 2].isdigit():
                yield begin, end + 1
                index = following + 1
                break


def format_markdown(text):
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise RuntimeError("Markdown formatting not run: markdown-it-py is unavailable.") from exc
    view, protected, notes = markdown_view(text)
    if not view:
        return text, notes
    lines = split_lines(text)
    normalized_view = view.replace("\r\n", "\n").replace("\r", "\n")
    parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    tokens = parser.parse(view)
    offsets = [0]
    for line in split_lines(normalized_view):
        offsets.append(offsets[-1] + len(line))
    extension_chars = list(normalized_view)
    inline_code_lines = set()
    for token in tokens:
        if not token.map:
            continue
        start, end = token.map
        if token.type in {"fence", "code_block", "html_block"}:
            protected.update(range(start, end))
            mask_range(extension_chars, offsets[start], offsets[end])
        elif token.type == "inline" and any(child.type == "code_inline" for child in token.children or []):
            inline_code_lines.update(range(start, end))
    # Delimiters in literal blocks must not open or close a formula in the prose.
    math_view = "".join(extension_chars)
    # Mask display/parenthesized math, including blank lines. Over-protection is intentional.
    for opening, closing in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)")):
        position = 0
        while True:
            begin = find_unescaped(math_view, opening, position)
            if begin < 0:
                break
            end = find_unescaped(math_view, closing, begin + len(opening))
            if end < 0:
                end = len(math_view)
                notes.append(f"Unclosed math delimiter {opening!r}: remainder preserved.")
            else:
                end += len(closing)
            first = math_view.count("\n", 0, begin)
            last = math_view.count("\n", 0, end)
            math_lines = set(range(first, last + 1))
            protected.update(math_lines)
            # Inline code may contain fake math delimiters. If the source boundaries
            # are ambiguous, retain raw-TeX detection instead of hiding a real block.
            if not math_lines & inline_code_lines:
                # Spaces could turn following raw TeX into a fake indented code block.
                mask_range(extension_chars, begin, end, fill="x")
            position = end
    for index, line in enumerate(split_lines("".join(extension_chars))):
        if index in inline_code_lines:
            continue
        for start, end in inline_math_ranges(line):
            protected.add(index)
            mask_range(extension_chars, offsets[index] + start, offsets[index] + end, fill="x")
    extension_view = "".join(extension_chars)
    if re.search(r"(?m)^\s*:::", extension_view):
        return text, ["Skipped: extended container requires the project's renderer."]
    # Inspect parsed prose after masking math. Code spans and literal blocks are
    # examples of TeX, not raw TeX; actual unscoped environments remain conservative.
    for token in parser.parse(extension_view):
        if token.type == "inline" and any(
            child.type == "text" and re.search(r"\\begin\{", child.content)
            for child in token.children or []
        ):
            return text, ["Skipped: raw TeX outside protected math/code requires the project's renderer."]
    eligible = set()
    for index, token in enumerate(tokens):
        if token.type != "paragraph_open" or token.level != 0 or index + 1 >= len(tokens):
            continue
        inline = tokens[index + 1]
        if inline.type != "inline" or not inline.map:
            continue
        if any(child.type not in {"text", "softbreak", "hardbreak"} for child in inline.children or []):
            continue
        start, end = inline.map
        raw = "".join(lines[start:end])
        # Protect inline math, escaped syntax, links, footnotes, HTML, and unknown inline extensions.
        if any(char in raw for char in "$\\`<>[]|{}"):
            continue
        eligible.update(range(start, end))
    output = []
    for index, line in enumerate(lines):
        body, ending = line_parts(line)
        # Only a SINGLE trailing ASCII space on a top-level plain paragraph is eligible.
        # Indentation, blank lines, tabs and 2+ trailing spaces are deliberately left alone.
        if index in eligible - protected and not body.startswith((" ", "\t")) and re.search(r"[^ \t] $", body):
            output.append(body[:-1] + ending)
        else:
            output.append(line)
    result = "".join(output)
    result_view = markdown_view(result)[0]
    if parser.render(view) != parser.render(result_view):
        return text, ["Candidate changed CommonMark rendering; no automatic edits applied."]
    return result, notes


def transform(data, suffix, extra_envs=()):
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    text = data[len(bom):].decode("utf-8")
    if "\x00" in text:
        raise ValueError("NUL byte in source; refused to treat it as a text document.")
    if suffix.lower() == ".tex":
        cleaned, notes = format_tex(text, extra_envs)
    elif suffix.lower() in {".md", ".markdown"}:
        cleaned, notes = format_markdown(text)
    else:
        raise ValueError("Only .tex, .md and .markdown files are supported.")
    return bom + cleaned.encode("utf-8"), notes


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_replace(path, expected, replacement):
    if path.is_symlink() or path.read_bytes() != expected:
        raise RuntimeError(f"Source changed since read: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".cleanup-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if path.is_symlink() or path.read_bytes() != expected:
            raise RuntimeError(f"Source changed before write: {path}")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Explicit files; no recursive discovery")
    parser.add_argument("--write", action="store_true", help="Apply eligible edits after a byte-exact backup")
    parser.add_argument("--backup-dir", type=Path, help="Required for --write; must not already exist")
    parser.add_argument("--diff", action="store_true", help="Print proposed unified diff to stderr")
    parser.add_argument("--verbatim-env", action="append", default=[], help="Additional literal TeX environment")
    args = parser.parse_args(argv)
    if args.write and args.backup_dir is None:
        parser.error("--write requires --backup-dir")
    prepared = []
    report = {"mode": "write" if args.write else "check", "files": [], "status": "ok"}
    try:
        seen = set()
        for candidate in args.files:
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError(f"Expected a regular non-symlink file: {candidate}")
            path = candidate.resolve()
            if path in seen:
                continue
            seen.add(path)
            if args.write and path.stat().st_nlink > 1:
                raise ValueError(f"Refusing to replace a hard-linked file: {path}")
            original = path.read_bytes()
            cleaned, notes = transform(original, path.suffix, args.verbatim_env)
            changed = [i + 1 for i, (a, b) in enumerate(zip(split_lines(original.decode("utf-8")), split_lines(cleaned.decode("utf-8")))) if a != b]
            entry = {"path": str(path), "changed_lines": changed, "before_sha256": digest(original),
                     "after_sha256": digest(cleaned), "notes": notes, "written": False}
            prepared.append((path, original, cleaned, entry))
            report["files"].append(entry)
        changes = [item for item in prepared if item[1] != item[2]]
        if args.write and changes:
            backup = args.backup_dir.resolve()
            backup.mkdir(parents=True, exist_ok=False)
            for index, (path, original, cleaned, entry) in enumerate(changes):
                target = backup / f"{index + 1:04d}-{path.name}"
                with target.open("xb") as stream:
                    stream.write(original)
                entry["backup"] = str(target)
            (backup / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            for path, original, cleaned, entry in changes:
                atomic_replace(path, original, cleaned)
                entry["written"] = True
        if args.diff:
            for path, original, cleaned, entry in changes:
                sys.stderr.writelines(difflib.unified_diff(
                    original.decode("utf-8").splitlines(keepends=True),
                    cleaned.decode("utf-8").splitlines(keepends=True),
                    fromfile=str(path), tofile=str(path) + " (cleaned)"))
    except (OSError, ValueError, RuntimeError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
