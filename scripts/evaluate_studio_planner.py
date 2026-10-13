#!/usr/bin/env python3
"""Paired fixed/planner runs over public synthetic text; fixture is the default.

Live mode uses the operator's VLM_* process environment. No private documents,
compiler, source writes, or automatic candidate adoption are involved.
"""
import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

CASES = [
    {"id": "plain", "content": "Plain text.", "expected": "Plain text."},
    {"id": "formula-valid", "content": "Value $x+1$", "expected": "Value $x+1$"},
    {"id": "formula-retry", "content": r"Value $\frac{x+1}{3$", "expected": r"Value $\frac{x+1}{3}$"},
    {"id": "table-total", "content": "\\begin{tabular}{lr}\nItem & Value \\\\\nA & 2 \\\\\nTotal & 3 \\\\\n\\end{tabular}\n"},
    {"id": "table-unsupported", "content": "\\begin{tabular}{lr}\nItem & Value \\\\\nA & 2 kg \\\\\nTotal & 3 \\\\\n\\end{tabular}\n"},
]


class FixtureDecisions:
    name = "offline-fixture"

    def __init__(self):
        self.last_trace = {}

    def plan_action(self, snapshot, *, timeout=120):
        self.last_trace = {"model_calls": 0, "reason": "offline_fixture"}
        node = next(n for n in snapshot["nodes"] if n["action_mask"])
        action = node["action_mask"][0]
        return {"action": action, "node_id": node["id"], "state_rev": snapshot["state_rev"],
                "params": {"reason": "unsupported_or_uncertain"} if action == "request-human" else {}}

    def select_skill(self, snapshot, *, timeout=120):
        self.last_trace = {"model_calls": 0, "reason": "offline_fixture_selection"}
        selected = next(cap["skill_id"] for cap in snapshot["catalog"] if cap["node_kind"] == snapshot["node"]["kind"])
        return {"skill_id": selected, "state_rev": snapshot["state_rev"], "reason": "fixture route"}

    def repair_formula(self, node, *, timeout=120, loaded_skill=None):
        self.last_trace = {"model_calls": 0, "reason": "offline_fixture"}
        return {r"\frac{x+1}{3": r"\frac{x+1}{3}"}.get(node["data"]["latex"])


def load_studio():
    os.environ.setdefault("DEMO_TOKEN", "offline-evaluation-only-token")
    spec = importlib.util.spec_from_file_location("studio_planner_evaluation", ROOT / "webui/app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def evaluate(provider_mode="fixture"):
    studio = load_studio()
    results = []
    for case in CASES:
        for arm in ("fixed", "planner", "selection", "planner-selection"):
            selecting = arm in {"selection", "planner-selection"}
            provider = FixtureDecisions() if provider_mode == "fixture" else studio._new_provider(skill_selection=selecting)
            events = []
            emit = lambda action, **fields: events.append({"action": action, **fields})
            started = time.monotonic()
            if arm == "fixed":
                candidate, edits = studio._apply_fixes(case["content"], [], provider=provider, emit=emit)
                planner = None
            else:
                candidate, edits, planner = studio._apply_planned_fixes(case["content"], [], provider=provider, emit=emit,
                                                                       skill_selection=selecting, use_model_planner=arm != "selection")
            problems = studio._analyze(candidate)
            calls = sum(e.get("provider_trace", {}).get("model_calls", 0) or 0 for e in events
                        if e["action"] in {"PROVIDER_RESULT", "PLANNER_RESULT", "SKILL_SELECTION_PROPOSED"})
            results.append({"case_id": case["id"], "arm": arm, "source_sha256": hashlib.sha256(case["content"].encode()).hexdigest(),
                            "checker_complete": not problems, "fixture_expected_match": candidate == case["expected"] if "expected" in case else None,
                            "illegal_actions": planner["rejected"] if planner else 0,
                            "selection_rejections": planner["selection_rejections"] if planner else 0,
                            "loaded_skills": planner["loaded_skills"] if planner else [],
                            "model_calls": calls, "reserved_model_calls": planner["reserved_model_calls"] if planner else None,
                            "elapsed_seconds": round(time.monotonic() - started, 6), "edits": len(edits), "planner": planner})
    summary = {}
    for arm in ("fixed", "planner", "selection", "planner-selection"):
        rows = [r for r in results if r["arm"] == arm]
        summary[arm] = {"checker_completion_rate": sum(r["checker_complete"] for r in rows) / len(rows),
                        "illegal_actions": sum(r["illegal_actions"] for r in rows),
                        "selection_rejections": sum(r["selection_rejections"] for r in rows),
                        "model_calls": sum(r["model_calls"] for r in rows),
                        "elapsed_seconds": round(sum(r["elapsed_seconds"] for r in rows), 6)}
    return {"schema_version": 1, "provider_mode": provider_mode,
            "evidence_level": "offline_fixture_routing" if provider_mode == "fixture" else "live_public_synthetic",
            "semantic_correctness": "NOT_CHECKED", "default_changed": False,
            "notes": ["Fixture decisions are test data, not model inference.", "Checker completion is syntax/simple totals, not mathematical truth.",
                      "Timings include local checker process startup; these five cases do not establish a performance benefit.",
                      "No private document, PDF compilation, OCR or candidate adoption occurs."],
            "summary": summary, "rows": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate(args.provider)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
