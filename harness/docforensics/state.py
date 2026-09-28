"""Append-only JSONL state, with input/context-bound resumption."""

import hashlib
import json
import os
import time
import uuid

TERMINAL = {"OK", "NEEDS_HUMAN"}
SCHEMA_VERSION = 2


def new_run_id():
    return uuid.uuid4().hex


def canonical_sha256(value):
    """Hash JSON data independent of mapping insertion order, never log its input."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def state_path(run_dir):
    return os.path.join(run_dir, "state.jsonl")


def load_events(run_dir):
    p = state_path(run_dir)
    if not os.path.exists(p):
        return []
    events = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def append(run_dir, **event):
    event.setdefault("schema_version", SCHEMA_VERSION)
    event.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    os.makedirs(run_dir, exist_ok=True)
    # One complete JSON line per append, flushed to disk before returning.
    line = json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
    with open(state_path(run_dir), "a+b") as f:
        # Keep a new event readable after an interrupted, unterminated line.
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                line = "\n" + line
        f.write(line.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return event


def terminal_event(events, doc, node_id, input_sha256, context_sha256):
    """Return a matching terminal only; historical records without hashes are unsafe."""
    if not input_sha256 or not context_sha256:
        return None
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        if (event.get("doc") == doc and event.get("node_id") == node_id
                and event.get("action") == "TERMINAL"
                and isinstance(event.get("status"), str)
                and event["status"] in TERMINAL
                and event.get("input_sha256") == input_sha256
                and event.get("context_sha256") == context_sha256):
            # A later transient failure supersedes older reusable results.
            return event if event.get("resumable") is not False else None
    return None


def terminal_state(events, doc, node_id, input_sha256=None, context_sha256=None):
    """Compatibility wrapper; an identifier alone is insufficient for resumption."""
    event = terminal_event(events, doc, node_id, input_sha256, context_sha256)
    return event["status"] if event else None
