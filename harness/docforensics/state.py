"""state.jsonl 读写与重放（断点续跑协议，见 harness/README.md）。"""

import json
import os
import time

TERMINAL = {"OK", "NEEDS_HUMAN"}


def state_path(run_dir):
    return os.path.join(run_dir, "state.jsonl")


def load_events(run_dir):
    p = state_path(run_dir)
    if not os.path.exists(p):
        return []
    events = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 损坏行跳过，不阻塞重放
    return events


def append(run_dir, **event):
    event.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
    os.makedirs(run_dir, exist_ok=True)
    with open(state_path(run_dir), "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def terminal_state(events, doc, node_id):
    """返回该节点最终三态（OK / NEEDS_HUMAN）；无终态记录返回 None。"""
    result = None
    for e in events:
        if e.get("doc") == doc and e.get("node_id") == node_id and e.get("status") in TERMINAL:
            result = e["status"]
    return result
