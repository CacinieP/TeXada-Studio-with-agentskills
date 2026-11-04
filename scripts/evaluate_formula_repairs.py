#!/usr/bin/env python3
"""Replay synthetic cases through Studio's actual formula-repair host.

Fixture mode measures host policy with injected candidates, never model accuracy.
Local-model mode requires an explicit loopback endpoint and model. References and
fixture candidates are used only by the scorer/fixture; they never enter a model
request. No compiler, OCR, cloud provider, user document or credential is needed.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
DEFAULT_CASES = REPO / "samples/evaluation/formula-repair-quality.json"
GROUPS = ("structural", "control", "adversarial", "ambiguous")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def read_catalog(path):
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(catalog, dict) or catalog.get("schema_version") != 1
            or catalog.get("synthetic") is not True or not isinstance(catalog.get("cases"), list)
            or not catalog["cases"]):
        raise ValueError("expected a nonempty synthetic schema_version=1 catalog")
    seen = set()
    for case in catalog["cases"]:
        if not isinstance(case, dict):
            raise ValueError("case must be an object")
        case_id, group = case.get("id"), case.get("group")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("case ids must be nonempty unique strings")
        seen.add(case_id)
        if not isinstance(group, str) or group not in GROUPS:
            raise ValueError("unknown case group")
        if not isinstance(case.get("title"), str) or not case["title"].strip():
            raise ValueError("case title must be nonempty")
        latex = case.get("input_latex")
        if not isinstance(latex, str) or not latex.strip() or len(latex) > 32768 or "\x00" in latex:
            raise ValueError("input_latex must be bounded nonempty text without NUL")
        for key in ("references", "fixture_candidates"):
            values = case.get(key)
            if (not isinstance(values, list) or any(not isinstance(v, str) or not v.strip()
                    or "\x00" in v or len(v) > 32768 for v in values)):
                raise ValueError(f"{key} must contain bounded nonempty strings")
        if not 1 <= len(case["fixture_candidates"]) <= 2:
            raise ValueError("fixture candidates must contain one or two entries")
        if group in {"structural", "adversarial"} and not case["references"]:
            raise ValueError("repairable cases need scoring references")
        if group == "control" and case["references"] != [latex]:
            raise ValueError("control reference must be the unchanged input")
        if group == "ambiguous" and case["references"]:
            raise ValueError("ambiguous cases have no unique reference repair")
    return catalog


def load_studio():
    # Loading app.py constructs a provider but never requests inference. Point
    # its configuration at isolated storage so no saved user settings are read.
    with tempfile.TemporaryDirectory(prefix="texada-quality-import-") as directory, patch.dict(os.environ, {
            "DEMO_TOKEN": "evaluation-only-not-a-serving-session",
            "TEXADA_LOCAL_MODE": "1", "TEXADA_STUDIO_STATE_DIR": directory,
            "VLM_BASE_URL": "http://127.0.0.1:9/v1", "VLM_MODEL": "evaluation-local"}):
        spec = importlib.util.spec_from_file_location("formula_quality_studio", REPO / "webui/app.py")
        studio = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(studio)
    return studio


class FixtureProvider:
    name = "fixture (offline test double)"

    def __init__(self, candidates):
        self.candidates, self.calls, self.last_trace = candidates, 0, {}

    def fingerprint(self):
        return {"provider": self.name, "network": False, "model": None}

    def repair_formula(self, node, **kwargs):
        candidate = self.candidates[min(self.calls, len(self.candidates) - 1)]
        self.calls += 1
        self.last_trace = {"model_calls": 0, "model_called": False, "fixture_calls": 1,
                           "provider": self.name, "reason": "injected_fixture_candidate"}
        return candidate


class BoundedLocalProvider:
    def __init__(self, provider, timeout):
        self.provider, self.timeout, self.calls = provider, timeout, 0

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def repair_formula(self, node, **kwargs):
        if self.calls >= 2:
            raise RuntimeError("evaluation_case_call_budget_exceeded")
        self.calls += 1
        kwargs.setdefault("timeout", self.timeout)
        return self.provider.repair_formula(node, **kwargs)


def run_case(studio, case, provider, mode):
    prefix, suffix = f"Synthetic evaluation {case['id']}.\n$", "$\n"
    source = prefix + case["input_latex"] + suffix
    events, log, edits, error = [], [], [], None
    output = source
    started = time.monotonic()
    try:
        output, edits = studio._apply_fixes(source, log, provider=provider,
                                          emit=lambda action, **fields: events.append({"action": action, **fields}))
    except Exception as exc:
        error = type(exc).__name__  # Do not copy endpoint/dependency exception text.
    wrappers_preserved = output.startswith(prefix) and output.endswith(suffix)
    output_latex = output[len(prefix):-len(suffix)] if wrappers_preserved else None
    unchanged = output == source and error is None
    reference_match = (output_latex in case["references"] and wrappers_preserved and error is None)
    traces = [event.get("provider_trace", {}) for event in events if event["action"] == "PROVIDER_RESULT"]
    traces = [trace for trace in traces if isinstance(trace, dict)]
    model_calls = sum(trace.get("model_calls", 0) or 0 for trace in traces)
    fixture_calls = sum(trace.get("fixture_calls", 0) or 0 for trace in traces)
    fixture_exercised = mode == "fixture" and fixture_calls > 0
    dangerous_fixture_accepted = (case["group"] == "adversarial" and fixture_exercised
                                  and output_latex in case["fixture_candidates"] and not reference_match)
    return {"id": case["id"], "group": case["group"], "title": case["title"],
            "input_latex": case["input_latex"], "input_document": source, "input_sha256": digest(source),
            "expected": {"references": case["references"],
                         "preserve_original": case["group"] in {"control", "ambiguous"},
                         "fixture_candidates": case["fixture_candidates"] if mode == "fixture" else None},
            "output_latex": output_latex, "output_document": output, "output_sha256": digest(output),
            "wrappers_preserved": wrappers_preserved, "unchanged": unchanged,
            "reference_match": reference_match, "unexpected_change": not unchanged and not reference_match and error is None,
            "fixture_exercised": fixture_exercised,
            "fixture_disposition": ("accepted_dangerous_output" if dangerous_fixture_accepted else
                                    "called_output_not_selected" if fixture_exercised else
                                    "not_injected_no_provider_call" if mode == "fixture" else "not_applicable"),
            "dangerous_fixture_accepted": dangerous_fixture_accepted,
            "provider_invocations": provider.calls, "model_calls": model_calls, "fixture_calls": fixture_calls,
            "model_calls_known": mode == "fixture" or len(traces) == provider.calls,
            "provider_fingerprint": provider.fingerprint(),
            "edits": edits, "events": events, "log": log, "error": error,
            "elapsed_seconds": round(time.monotonic() - started, 4)}


def fraction(numerator, denominator):
    return {"count": numerator, "total": denominator,
            "rate": numerator / denominator if denominator else None}


def summarize(results, mode):
    groups = {group: [r for r in results if r["group"] == group] for group in GROUPS}
    structural, controls, adversarial, ambiguous = (groups[group] for group in GROUPS)
    exercised = [row for row in adversarial if row["fixture_exercised"]]
    return {"cases": len(results), "errors": sum(row["error"] is not None for row in results),
            "model_calls": sum(row["model_calls"] for row in results),
            "model_calls_known": all(row.get("model_calls_known", False) for row in results),
            "fixture_calls": sum(row["fixture_calls"] for row in results),
            "structural_reference_match": fraction(sum(r["reference_match"] for r in structural), len(structural)),
            "control_preservation": fraction(sum(r["unchanged"] for r in controls), len(controls)),
            "control_cases_with_provider_calls": sum(r["provider_invocations"] > 0 for r in controls),
            "control_provider_invocations": sum(r["provider_invocations"] for r in controls),
            "adversarial_unexpected_changes": fraction(sum(r["unexpected_change"] for r in adversarial), len(adversarial)),
            "dangerous_fixture_acceptance_when_exercised": (
                fraction(sum(r["dangerous_fixture_accepted"] for r in exercised), len(exercised)) if mode == "fixture" else None),
            "dangerous_fixture_cases_not_exercised": len(adversarial) - len(exercised) if mode == "fixture" else None,
            "ambiguous_preservation": fraction(sum(r["unchanged"] for r in ambiguous), len(ambiguous)),
            "outcomes": dict(Counter("error" if r["error"] else "unchanged" if r["unchanged"] else
                                     "reference_match" if r["reference_match"] else "nonreference_change" for r in results)),
            "model_accuracy": None, "semantic_accuracy": None}


def git_revision():
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def render_markdown(report):
    summary = report["summary"]
    lines = ["# Studio formula repair quality replay", "", f"Mode: `{report['mode']}` · Git: `{report['git_revision']}`", "",
             "Synthetic host-policy/reference-match evaluation. Fixture calls are injected test doubles; they are not model inference.",
             "References use exact LaTeX matching. Non-matching variants require inspection and are not automatically mathematical errors.",
             "A correct control can intentionally contain false mathematics: syntax repair must preserve its source meaning.", "",
             "| Metric | Count / total |", "| --- | --- |"]
    for key in ("structural_reference_match", "control_preservation", "adversarial_unexpected_changes",
                "dangerous_fixture_acceptance_when_exercised", "ambiguous_preservation"):
        value = summary[key]
        lines.append(f"| {key} | {value['count']} / {value['total']} |" if value is not None else f"| {key} | not applicable |")
    lines += ["", f"Control provider invocations: {summary['control_provider_invocations']}; model HTTP attempts: {summary['model_calls']}; fixture calls: {summary['fixture_calls']}.",
              "HTTP counts are a known lower bound when a provider call failed before its result event." if not summary["model_calls_known"] else "All provider calls have corresponding result traces.",
              f"Dangerous fixture cases not exercised: {summary['dangerous_fixture_cases_not_exercised']}. No provider call can mean a deterministic repair preempted injection; it does not prove the candidate guard ran.",
              f"Execution errors: {summary['errors']}. Model and mathematical accuracy remain unmeasured.", "",
              "| Case | Group | Reference match | Preserved | Provider calls | Fixture disposition | Error |",
              "| --- | --- | --- | --- | ---: | --- | --- |"]
    for row in report["results"]:
        lines.append(f"| {row['id']} | {row['group']} | {row['reference_match']} | {row['unchanged']} | {row['provider_invocations']} | {row['fixture_disposition']} | {row['error'] or ''} |")
    lines += ["", "Full synthetic input, expected references, output, edits, events and provider fingerprints are in `report.json`.",
              "Local-model runs send only observed input and host-generated retry context. Fixture candidates and reference answers are never added to model requests.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--outdir", type=Path, required=True, help="fresh output directory; existing paths are refused")
    parser.add_argument("--mode", choices=("fixture", "local-model"), default="fixture")
    parser.add_argument("--base-url", help="required explicit loopback HTTP endpoint for local-model mode")
    parser.add_argument("--model", help="required explicit local model name")
    parser.add_argument("--skill-mode", choices=("on", "off"), default="on")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--timeout", type=float, default=30, help="per-request timeout, at most 120 seconds")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 120 or not 0 < args.max_tokens <= 4096:
        parser.error("timeout must be >0 and <=120; max-tokens must be >0 and <=4096")
    if args.mode == "local-model" and (not args.base_url or not args.model):
        parser.error("local-model requires explicit --base-url and --model")
    if args.mode == "fixture" and (args.base_url or args.model):
        parser.error("fixture mode does not use a model endpoint")
    sys.path.insert(0, str(REPO / "webui"))
    from local_runtime import make_local_provider, validate_base_url
    try:
        catalog = read_catalog(args.cases)
        base = validate_base_url(args.base_url) if args.mode == "local-model" else None
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    outdir = args.outdir.resolve()
    try:
        outdir.mkdir(parents=True, exist_ok=False)
    except OSError:
        parser.error("cannot create fresh output directory")
    studio = load_studio()
    results = []
    for case in catalog["cases"]:
        provider = (FixtureProvider(case["fixture_candidates"]) if args.mode == "fixture" else BoundedLocalProvider(
            make_local_provider(base, args.model, skill_mode=args.skill_mode, seed=args.seed, max_tokens=args.max_tokens), args.timeout))
        row = run_case(studio, case, provider, args.mode)
        results.append(row)
        print(f"{case['id']}: changed={not row['unchanged']} reference={row['reference_match']} provider_calls={row['provider_invocations']}", flush=True)
    paths = ["webui/app.py", "webui/local_runtime.py", "harness/docforensics/vlm.py", "harness/docforensics/tex_context.py",
             "skills/doc-formula-verify/scripts/verify.py", "skills/doc-formula-verify/SKILL.md", "scripts/evaluate_formula_repairs.py"]
    paths = sorted(set(paths) | {str(path.relative_to(REPO)) for path in (REPO / "harness/docforensics").glob("*.py")})
    report = {"schema_version": 1, "synthetic": True, "mode": args.mode,
              "dataset_id": catalog.get("dataset_id"), "scope": catalog.get("scope"),
              "created_at": datetime.now(timezone.utc).isoformat(), "git_revision": git_revision(),
              "source_root": str(REPO), "catalog_sha256": digest(args.cases.read_bytes()),
              "source_sha256": {path: digest((REPO / path).read_bytes()) for path in paths},
              "parameters": {"skill_mode": args.skill_mode, "seed": args.seed, "max_tokens": args.max_tokens,
                             "max_provider_invocations_per_case": 2, "request_timeout_seconds": args.timeout},
              "summary": summarize(results, args.mode), "results": results}
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (outdir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(outdir / "report.json"), "summary": report["summary"]}, ensure_ascii=False))
    # A replay may expose bad repair policy: preserve its report without treating
    # it as an execution error. CI gates can inspect the explicit metrics.
    return 1 if report["summary"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
