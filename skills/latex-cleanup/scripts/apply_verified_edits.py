#!/usr/bin/env python3
"""Apply an explicit, evidence-cited replacement plan; dry-run unless --write.

This checks exact source matches and supplied evidence fields, not evidence truth.
Only explicitly replaced spans change: UTF-8 BOM and all other bytes are retained.
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
from urllib.parse import urlsplit


BOM = b"\xef\xbb\xbf"
EVIDENCE_NOTICE = "User/agent-supplied evidence only; reference contents and correctness were not independently validated."


def digest(data):
    return hashlib.sha256(data).hexdigest()


def nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    value.encode("utf-8")
    return value


def require_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} requires exactly these fields: {', '.join(keys)}")


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def local_path(value, base):
    path = Path(value).expanduser()
    # Do not resolve the final symlink: the read/write checks must still see it.
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def validate_plan(plan):
    require_keys(plan, ("schema_version", "source", "source_sha256", "edits"), "plan")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    nonempty_string(plan["source"], "source")
    if not isinstance(plan["source_sha256"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", plan["source_sha256"]):
        raise ValueError("source_sha256 must be a 64-character SHA-256 hex digest")
    if not isinstance(plan["edits"], list):
        raise ValueError("edits must be an array")
    seen = set()
    for index, edit in enumerate(plan["edits"]):
        label = f"edits[{index}]"
        require_keys(edit, ("id", "old", "new", "evidence"), label)
        edit_id = nonempty_string(edit["id"], f"{label}.id")
        if edit_id in seen:
            raise ValueError(f"Duplicate edit id: {edit_id}")
        seen.add(edit_id)
        if not isinstance(edit["old"], str) or not edit["old"]:
            raise ValueError(f"{label}.old must be a nonempty string; anchor insertions in existing text")
        if not isinstance(edit["new"], str):
            raise ValueError(f"{label}.new must be a string (empty is allowed for deletion)")
        for name in ("old", "new"):
            edit[name].encode("utf-8")  # Reject lone surrogate escapes in JSON.
            if "\x00" in edit[name]:
                raise ValueError(f"{label}.{name} must not contain NUL")
        evidence = edit["evidence"]
        require_keys(evidence, ("kind", "reference", "locator", "note"), f"{label}.evidence")
        for key, value in evidence.items():
            nonempty_string(value, f"{label}.evidence.{key}")


def read_source(path, for_write=False):
    if path.is_symlink():
        raise ValueError(f"Refusing a symlink source: {path}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Expected a regular file: {path}")
        if for_write and before.st_nlink != 1:
            raise ValueError(f"Refusing to replace a hard-linked source: {path}")
        data = stream.read()
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise RuntimeError(f"Source changed while being read: {path}")
    current = path.lstat()
    if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
        raise RuntimeError(f"Source changed while being read: {path}")
    return data, before


def prepare_edits(original, plan, plan_dir):
    if digest(original) != plan["source_sha256"].lower():
        raise ValueError("Stale plan: source_sha256 does not match the current source bytes")
    bom = BOM if original.startswith(BOM) else b""
    text = original[len(bom):].decode("utf-8")
    if "\x00" in text:
        raise ValueError("NUL byte in source; expected a UTF-8 text document")
    resolved = []
    for edit in plan["edits"]:
        old = edit["old"]
        start = text.find(old)
        if start < 0:
            raise ValueError(f"Edit {edit['id']}: old text was not found")
        # Moving by one, not len(old), also detects overlapping matches like aa in aaa.
        if text.find(old, start + 1) >= 0:
            raise ValueError(f"Edit {edit['id']}: old text is ambiguous; include more surrounding context")
        reference = edit["evidence"]["reference"]
        resolved_reference = reference if urlsplit(reference).scheme else str(local_path(reference, plan_dir))
        prefix_lines = list(re.finditer(r"\r\n|\r|\n", text[:start]))
        resolved.append({
            **edit,
            "start_char": start,
            "end_char": start + len(old),
            "line": len(prefix_lines) + 1,
            "column": start - (prefix_lines[-1].end() if prefix_lines else 0) + 1,
            "resolved_reference": resolved_reference,
        })
    ordered = sorted(resolved, key=lambda item: item["start_char"])
    for previous, current in zip(ordered, ordered[1:]):
        if previous["end_char"] > current["start_char"]:
            raise ValueError(f"Overlapping edits: {previous['id']} and {current['id']}")
    cleaned = text
    for edit in reversed(ordered):
        cleaned = cleaned[:edit["start_char"]] + edit["new"] + cleaned[edit["end_char"]:]
    return bom + cleaned.encode("utf-8"), resolved


def assert_unchanged(path, original, snapshot):
    current, info = read_source(path, for_write=True)
    if current != original or (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns) != (
        snapshot.st_dev, snapshot.st_ino, snapshot.st_mode, snapshot.st_mtime_ns, snapshot.st_ctime_ns
    ):
        raise RuntimeError(f"Source changed since validation: {path}")


def write_exclusive(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def apply_with_backup(path, original, cleaned, snapshot, backup, plan_bytes, report):
    assert_unchanged(path, original, snapshot)
    # mkdir is exclusive. An existing directory, file, or symlink is never reused.
    backup.mkdir(parents=True, exist_ok=False)
    report["backup"] = str(backup / "original.bin")
    report["record"] = str(backup / "record.json")
    mode = stat.S_IMODE(snapshot.st_mode)
    write_exclusive(backup / "original.bin", original, mode)
    write_exclusive(backup / "plan.json", plan_bytes)
    # A prepared record is written before the source is touched. It deliberately
    # makes no claim that the later atomic replacement succeeded.
    record = {**report, "status": "prepared", "written": False}
    write_exclusive(backup / "record.json", (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    fd, temporary = tempfile.mkstemp(prefix=".verified-edits-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(cleaned)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        assert_unchanged(path, original, snapshot)
        os.replace(temporary, path)
        report["written"] = True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def print_diff(path, original, cleaned):
    def lines(data):
        return [part for part in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", data.decode("utf-8")) if part]
    for line in difflib.unified_diff(lines(original), lines(cleaned), fromfile=str(path), tofile=str(path) + " (proposed)"):
        sys.stderr.write(line)
        if not line.endswith(("\r", "\n")):
            sys.stderr.write("\n\\ No newline at end of file\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        "Plan schema: {schema_version: 1, source: path, source_sha256: hex, edits: "
        "[{id, old, new, evidence: {kind, reference, locator, note}}]}. "
        "All evidence fields are nonempty strings supplied by the plan author, not machine-verified facts. "
        "Relative source and local evidence reference paths are relative to the plan file; URL/URI references are retained. "
        "--backup-dir is relative to the current working directory. old must match once, including overlapping matches; "
        "new may be empty. Offsets in the report count Unicode characters excluding a UTF-8 BOM. "
        "No newline normalization occurs; spell any intended newline edits exactly in the plan. "
        "A write saves original.bin, the exact plan.json, and a prepared record.json before replacing the source."
    ))
    parser.add_argument("plan", type=Path, help="UTF-8 JSON plan for one source file")
    parser.add_argument("--write", action="store_true", help="Apply validated edits after creating a new backup directory")
    parser.add_argument("--backup-dir", type=Path, help="Required for --write; must not already exist")
    parser.add_argument("--diff", action="store_true", help="Print the proposed unified diff to stderr")
    args = parser.parse_args(argv)
    if args.write and args.backup_dir is None:
        parser.error("--write requires --backup-dir")
    report = {"schema_version": 1, "mode": "write" if args.write else "check", "status": "ok", "written": False,
              "evidence_verification": EVIDENCE_NOTICE}
    try:
        plan_path = args.plan.absolute()
        plan_bytes = plan_path.read_bytes()
        plan = json.loads(plan_bytes.decode("utf-8-sig"), object_pairs_hook=json_object)
        validate_plan(plan)
        path = local_path(plan["source"], plan_path.parent)
        if path.resolve() == plan_path.resolve():
            raise ValueError("The source must not be the plan file")
        original, snapshot = read_source(path, for_write=args.write)
        cleaned, edits = prepare_edits(original, plan, plan_path.parent)
        report.update({"plan": str(plan_path), "plan_sha256": digest(plan_bytes), "source": str(path),
                       "before_sha256": digest(original), "after_sha256": digest(cleaned),
                       "changed": original != cleaned, "edits": edits})
        if args.diff:
            print_diff(path, original, cleaned)
        if args.write:
            backup = args.backup_dir.absolute()
            if backup.exists() or backup.is_symlink():
                raise ValueError(f"Backup directory must be new: {backup}")
            if original != cleaned:
                apply_with_backup(path, original, cleaned, snapshot, backup, plan_bytes, report)
    except (OSError, ValueError, RuntimeError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
