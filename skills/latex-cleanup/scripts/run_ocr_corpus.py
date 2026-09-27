#!/usr/bin/env python3
"""Copy a pinned local OCR corpus, apply verified overlays, and export text diffs.

Input files are never written. The output directory contains private full copies;
the separate export directory contains only IDs, hashes, statuses and changed hunks.
This invokes format_whitespace.transform, not a second formatting implementation.
"""

import argparse
import base64
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

import format_whitespace


HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
SCOPE = ("Conservative formatting and explicitly supplied verified overlays only; "
         "not complete OCR proofreading or full-book PDF fidelity verification.")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require_hash(value, label):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def resolve_file(base, value):
    if not isinstance(value, str) or not value:
        raise ValueError("File paths must be nonempty strings")
    path = Path(value)
    return path if path.is_absolute() else base / path


def read_regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular, non-symlink input file")
    return path.read_bytes()


def read_pinned(base, value, expected):
    require_hash(expected, "Input hash")
    data = read_regular(resolve_file(base, value))
    if sha(data) != expected:
        raise ValueError("Pinned input hash does not match current bytes")
    return data


def apply_overlays(original, overlays, base):
    """Locate every original segment before replacing any of them."""
    spans = []
    seen = set()
    for item in overlays:
        if not isinstance(item, dict) or set(item) != {
            "id", "before", "before_sha256", "after", "after_sha256"
        }:
            raise ValueError("An overlay needs exactly id/before/after and their SHA-256 hashes")
        identity = item["id"]
        if not isinstance(identity, str) or not ID.fullmatch(identity) or identity in seen:
            raise ValueError("Overlay IDs must be unique safe identifiers")
        seen.add(identity)
        before = read_pinned(base, item["before"], item["before_sha256"])
        after = read_pinned(base, item["after"], item["after_sha256"])
        if not before:
            raise ValueError("Overlay before segment must not be empty")
        start = original.find(before)
        if start < 0 or original.find(before, start + 1) >= 0:
            raise ValueError("Overlay before segment must occur exactly once in the original")
        spans.append((start, start + len(before), after, {
            "id": identity, "before_sha256": sha(before), "after_sha256": sha(after),
            "start_byte": start, "end_byte": start + len(before),
            "changed": before != after,
        }))
    spans.sort(key=lambda value: value[0])
    for previous, following in zip(spans, spans[1:]):
        if previous[1] > following[0]:
            raise ValueError("Overlay original byte ranges overlap")
    pieces = []
    position = 0
    for start, end, after, _ in spans:
        pieces.extend((original[position:start], after))
        position = end
    pieces.append(original[position:])
    return b"".join(pieces), [item[3] for item in spans]


def git_lines(data):
    """Git counts LF, not Unicode/control separators or an isolated CR, as a line."""
    parts = data.split(b"\n")
    return [part + b"\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def make_diff(before, after, filename):
    # diff_bytes keeps UTF-8, BOM and CRLF exact, including invalid UTF-8 elsewhere.
    lines = difflib.diff_bytes(difflib.unified_diff, git_lines(before), git_lines(after),
                             fromfile=("a/" + filename).encode("ascii"),
                             tofile=("b/" + filename).encode("ascii"), n=0)
    result = bytearray()
    for line in lines:
        result.extend(line)
        if not line.endswith(b"\n"):
            result.extend(b"\n\\ No newline at end of file\n")
    return bytes(result)


def make_text_patch(before, after):
    """JSON-safe, byte-offset patch for hunks that cannot be plain text diffs."""
    old_lines, new_lines = git_lines(before), git_lines(after)
    offsets = [0]
    for line in old_lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for tag, first, last, new_first, new_last in difflib.SequenceMatcher(
        None, old_lines, new_lines
    ).get_opcodes():
        if tag == "equal":
            continue
        old, new = b"".join(old_lines[first:last]), b"".join(new_lines[new_first:new_last])
        try:
            old_value, new_value = old.decode("utf-8"), new.decode("utf-8")
            encoding = "utf-8"
        except UnicodeError:
            old_value, new_value = (base64.b64encode(value).decode("ascii") for value in (old, new))
            encoding = "base64"
        edits.append({"start_byte": offsets[first], "end_byte": offsets[last],
                      "encoding": encoding, "old": old_value, "new": new_value})
    return {"format": "latex-cleanup-byte-patch-v1", "before_sha256": sha(before),
            "after_sha256": sha(after), "edits": edits}


def apply_text_patch(original, patch):
    """Replay only against the pinned original; offsets refer to original bytes."""
    if not isinstance(patch, dict) or set(patch) != {"format", "before_sha256", "after_sha256", "edits"} or patch["format"] != "latex-cleanup-byte-patch-v1":
        raise ValueError("Unsupported text patch format")
    require_hash(patch["before_sha256"], "Patch before hash")
    require_hash(patch["after_sha256"], "Patch after hash")
    if sha(original) != patch["before_sha256"]:
        raise ValueError("Patch source hash mismatch")
    if not isinstance(patch["edits"], list):
        raise ValueError("Patch edits must be a list")
    parts, position = [], 0
    for edit in patch["edits"]:
        if not isinstance(edit, dict) or set(edit) != {"start_byte", "end_byte", "encoding", "old", "new"}:
            raise ValueError("Invalid patch edit fields")
        start, end = edit["start_byte"], edit["end_byte"]
        if type(start) is not int or type(end) is not int or not position <= start <= end <= len(original):
            raise ValueError("Invalid or overlapping patch byte range")
        if not all(isinstance(edit[key], str) for key in ("old", "new")):
            raise ValueError("Patch old/new must be strings")
        if edit["encoding"] == "utf-8":
            old, new = (edit[key].encode("utf-8") for key in ("old", "new"))
        elif edit["encoding"] == "base64":
            old, new = (base64.b64decode(edit[key], validate=True) for key in ("old", "new"))
        else:
            raise ValueError("Unsupported patch string encoding")
        if original[start:end] != old:
            raise ValueError("Patch old bytes do not match the pinned range")
        parts.extend((original[position:start], new))
        position = end
    parts.append(original[position:])
    result = b"".join(parts)
    if sha(result) != patch["after_sha256"]:
        raise ValueError("Patch output hash mismatch")
    return result


def format_copy(data, suffix):
    """Failures preserve formatter input, which may include verified overlays."""
    try:
        candidate, notes = format_whitespace.transform(data, suffix)
    except (ValueError, RuntimeError, UnicodeError) as exc:
        # The existing helper's exceptions contain no local source path.
        return data, {"status": "refused_preserved", "notes": [str(exc)],
                      "idempotence": "not_run"}
    notes = list(notes)
    if any(note.startswith("Skipped:") for note in notes):
        return data, {"status": "skipped_preserved", "notes": notes,
                      "idempotence": "not_run"}
    try:
        repeated, second_notes = format_whitespace.transform(candidate, suffix)
    except (ValueError, RuntimeError, UnicodeError):
        return data, {"status": "validation_failed_preserved",
                      "notes": notes + ["Second formatting pass failed; candidate was discarded."],
                      "idempotence": "failed"}
    if repeated != candidate or second_notes != notes:
        return data, {"status": "validation_failed_preserved",
                      "notes": notes + ["Formatter is not idempotent; candidate was discarded."],
                      "idempotence": "failed"}
    return candidate, {"status": "review" if notes else ("changed" if candidate != data else "unchanged"),
                       "notes": notes, "idempotence": "passed"}


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "books"}:
        raise ValueError("Manifest needs exactly schema_version and books")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Only manifest schema_version 1 is supported")
    books = manifest["books"]
    if not isinstance(books, list) or not books:
        raise ValueError("Manifest books must be a nonempty list")
    seen = set()
    for item in books:
        if not isinstance(item, dict) or not {"id", "source", "source_sha256"} <= set(item):
            raise ValueError("Each book needs id, source and source_sha256")
        if set(item) - {"id", "source", "source_sha256", "overlays"}:
            raise ValueError("Unrecognized book field")
        identity = item["id"]
        if not isinstance(identity, str) or not ID.fullmatch(identity) or identity.casefold() in seen:
            raise ValueError("Book IDs must be unique safe identifiers")
        seen.add(identity.casefold())
        require_hash(item["source_sha256"], "Source hash")
        resolve_file(path.parent, item["source"])
        if not isinstance(item.get("overlays", []), list):
            raise ValueError("Overlays must be a list")
    return books


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def run(manifest_path, output_dir, export_dir, progress=None):
    manifest_path = Path(manifest_path).resolve()
    books = load_manifest(manifest_path)
    output_dir, export_dir = Path(output_dir).resolve(), Path(export_dir).resolve()
    if output_dir == export_dir or output_dir in export_dir.parents or export_dir in output_dir.parents:
        raise ValueError("Private output and text export directories must be separate and non-nested")
    if output_dir.exists() or export_dir.exists():
        raise ValueError("Output and export directories must both be new")
    output_dir.mkdir(parents=True, exist_ok=False)
    export_dir.mkdir(parents=True, exist_ok=False)
    (export_dir / "diffs").mkdir()
    report = {"schema_version": 1, "scope": SCOPE,
              "runner_sha256": sha(Path(__file__).read_bytes()),
              "formatter_sha256": sha(Path(format_whitespace.__file__).read_bytes()),
              "manifest_sha256": sha(manifest_path.read_bytes()), "books": []}
    private = {"manifest": str(manifest_path), "books": []}
    for index, item in enumerate(books):
        identity = item["id"]
        source = resolve_file(manifest_path.parent, item["source"])
        suffix = source.suffix.lower()
        # Unsupported inputs still get a byte-exact copy with a safe file name.
        filename = identity + (suffix if suffix in {".md", ".markdown", ".tex"} else ".source")
        entry = {"id": identity, "source_sha256": item["source_sha256"],
                 "source_matches_pin": False, "overlays": [], "output": filename,
                 "diff": None, "idempotence": "not_run"}
        original = None
        try:
            original = read_regular(source)
            entry["before_sha256"] = sha(original)
            if entry["before_sha256"] != item["source_sha256"]:
                raise ValueError("Pinned source hash does not match current bytes")
            entry["source_matches_pin"] = True
            prepared, overlays = apply_overlays(original, item.get("overlays", []), manifest_path.parent)
            entry["overlays"] = overlays
            entry["formatter_input_sha256"] = sha(prepared)
            cleaned, formatting = format_copy(prepared, suffix)
            entry["formatter"] = formatting
            entry["idempotence"] = formatting["idempotence"]
            entry["status"] = formatting["status"]
            if read_regular(source) != original:
                raise ValueError("Source changed while this book was being processed")
            entry["original_unchanged"] = True
        except (OSError, ValueError, UnicodeError) as exc:
            cleaned = original
            entry["status"] = "input_error_preserved" if original is not None else "input_unavailable"
            # Avoid exporting exception paths or user-supplied filenames.
            entry["error"] = (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
            try:
                entry["original_unchanged"] = original is not None and read_regular(source) == original
            except (OSError, ValueError):
                entry["original_unchanged"] = None
            entry["overlays"] = []
        if cleaned is not None:
            with (output_dir / filename).open("xb") as stream:
                stream.write(cleaned)
            entry["after_sha256"] = sha(cleaned)
            entry["output_changed"] = cleaned != original
            if cleaned != original:
                diff = make_diff(original, cleaned, filename)
                try:
                    diff.decode("utf-8")
                    textual = not any(byte < 32 and byte not in (9, 10, 13) for byte in diff) and b"\x7f" not in diff
                except UnicodeError:
                    textual = False
                if textual:
                    relative = "diffs/" + identity + ".diff"
                    (export_dir / relative).write_bytes(diff)
                    entry["diff"] = relative
                    entry["diff_sha256"] = sha(diff)
                    entry["diff_export_status"] = "exported"
                else:
                    patch = make_text_patch(original, cleaned)
                    if apply_text_patch(original, patch) != cleaned:
                        raise ValueError("Export patch failed exact replay")
                    relative = "diffs/" + identity + ".patch.json"
                    write_json(export_dir / relative, patch)
                    entry["text_patch"] = relative
                    entry["text_patch_sha256"] = sha((export_dir / relative).read_bytes())
                    entry["text_patch_replay"] = "passed"
                    entry["diff_export_status"] = "json_byte_patch_exported"
            else:
                entry["diff_export_status"] = "no_changes"
        else:
            entry["output"] = None
            entry["output_changed"] = False
            entry["diff_export_status"] = "not_run"
        private["books"].append({"id": identity, "source": str(source), "output": str(output_dir / filename)})
        report["books"].append(entry)
        if progress:
            progress(index + 1, len(books), entry)
    # A long batch can outlive concurrent edits to an early input. Recheck every
    # available original at the end instead of treating earlier snapshots as final.
    for item, entry in zip(books, report["books"]):
        if "before_sha256" not in entry:
            continue
        previously_unchanged = entry["original_unchanged"]
        try:
            current = read_regular(resolve_file(manifest_path.parent, item["source"]))
            entry["original_unchanged"] = sha(current) == entry["before_sha256"]
        except (OSError, ValueError):
            entry["original_unchanged"] = False
        if previously_unchanged is True and not entry["original_unchanged"]:
            entry["status"] = "source_changed_after_processing"
    statuses = Counter(book["status"] for book in report["books"])
    report["summary"] = {"books": len(books), "statuses": dict(sorted(statuses.items())),
                         "changed_outputs": sum(book["output_changed"] for book in report["books"]),
                         "overlay_count": sum(len(book["overlays"]) for book in report["books"]),
                         "originals_unchanged": all(book["original_unchanged"] is True for book in report["books"]),
                         "fully_formatted": all(book["status"] in {"changed", "unchanged"} for book in report["books"]),
                         "diff_apply_command": "git apply --unidiff-zero PATH_TO_DIFF"}
    write_json(output_dir / "local-paths.json", private)
    write_json(output_dir / "summary.json", report)
    write_json(export_dir / "summary.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.manifest, args.output_dir, args.export_dir,
                     lambda done, total, book: print(f"[{done}/{total}] {book['id']}: {book['status']}", file=sys.stderr, flush=True))
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(report["summary"], ensure_ascii=True, indent=2))
    # A completed batch with preserved/refused books is partial, never an all-clear.
    return 0 if report["summary"]["fully_formatted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
