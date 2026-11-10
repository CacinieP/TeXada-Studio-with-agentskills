#!/usr/bin/env python3
"""Run the issue #25 table-repair contract cases against a live local model.

Usage (from repo root, with Ollama OpenAI-compatible /v1 available):

  .venv/bin/python scripts/run_table_repair_pilot.py \\
    --base http://127.0.0.1:11434/v1 \\
    --model openbmb/minicpm-v4.7:latest \\
    --outdir docs/evaluation-results/table-repair-pilot-01/minicpm-v47 \\
    --skill-mode off

Does not claim semantic accuracy. Records host status, scope, model_calls and
bounded traces only. Reference totals never enter the model payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "harness"))

from docforensics import pipeline, state, vlm  # noqa: E402
from docforensics.__main__ import write_report  # noqa: E402
from docforensics.table_repair import assess_table_candidate  # noqa: E402


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _ollama_show(model: str) -> dict:
    try:
        proc = subprocess.run(
            ["ollama", "show", model, "--modelfile"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        show = subprocess.run(
            ["ollama", "show", model],
            capture_output=True, text=True, timeout=60, check=False,
        )
        return {
            "show_exit": show.returncode,
            "show_stdout": (show.stdout or "")[:8000],
            "modelfile_exit": proc.returncode,
            "modelfile_stdout": (proc.stdout or "")[:4000],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": type(exc).__name__}


def load_cases(path: Path) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("cases"), list):
        raise ValueError("invalid_cases_catalog")
    return catalog


def run_case(provider, case: dict, run_root: Path) -> dict:
    node = {
        "id": case["id"],
        "type": "table",
        "data": {
            "rows": case["original_rows"],
            "expected": case.get("expected") or {},
        },
    }
    directory = run_root / case["id"]
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    status = pipeline.process_table(str(directory), case["id"], node, provider, run_id=case["id"])
    elapsed = round(time.monotonic() - started, 6)
    events = state.load_events(str(directory))
    terminal = next((e for e in reversed(events) if e.get("action") == "TERMINAL"), {})
    scopes = [e for e in events if e.get("action") == "CANDIDATE_SCOPE"]
    rejected = [e for e in events if e.get("action") == "CANDIDATE_REJECTED"]
    accepted = [e for e in events if e.get("action") == "CANDIDATE_ACCEPTED"]
    host_scope = None
    if case.get("adversarial_candidate") is not None:
        host_scope = assess_table_candidate(
            case["original_rows"], case["adversarial_candidate"], case.get("expected"))
    report = Path(write_report(str(directory), provider, run_id=case["id"])).read_text(encoding="utf-8")
    (directory / "report.md").write_text(report, encoding="utf-8")
    return {
        "id": case["id"],
        "path": case.get("path"),
        "status": status,
        "elapsed_seconds": elapsed,
        "repaired": terminal.get("repaired"),
        "reason": terminal.get("reason"),
        "model_calls": terminal.get("model_calls"),
        "attempts": terminal.get("attempts"),
        "provider_reason": terminal.get("provider_reason"),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "scope_reasons": [e.get("scope", {}).get("reason") for e in scopes],
        "rejection_reasons": [
            e.get("reason") or (e.get("scope") or {}).get("reason") for e in rejected
        ],
        "original_rows": case["original_rows"],
        "candidate_rows": terminal.get("candidate_rows"),
        "adversarial_host_scope": host_scope,
        "last_trace": getattr(provider, "last_trace", {}),
        "events_path": str(directory / "state.jsonl"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path,
                        default=REPO / "samples/research/table_repair_cases.json")
    parser.add_argument("--base", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--skill-mode", choices=("on", "off"), default="off")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args(argv)

    catalog = load_cases(args.cases)
    outdir = args.outdir.resolve()
    if outdir.exists() and any(outdir.iterdir()):
        print(f"outdir must be empty or new: {outdir}", file=sys.stderr)
        return 2
    outdir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="table-repair-pilot-"))
    try:
        provider = vlm.OpenAICompatibleProvider(
            base=args.base, model=args.model, skill_mode=args.skill_mode,
            seed=args.seed, max_tokens=args.max_tokens,
        )
        fingerprint = provider.fingerprint()
        results = []
        for case in catalog["cases"]:
            print(f"running {case['id']} ({case.get('path')}) …", flush=True)
            record = run_case(provider, case, work / "runs")
            results.append(record)
            with (outdir / "results.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"  status={record['status']} repaired={record['repaired']} "
                  f"calls={record['model_calls']} reason={record['reason']}", flush=True)

        shutil.copytree(work / "runs", outdir / "runs")
        model_meta = _ollama_show(args.model)
        manifest = {
            "schema_version": 1,
            "pilot_id": "table-repair-pilot-01",
            "dataset_id": catalog.get("dataset_id"),
            "cases_path": str(args.cases.relative_to(REPO)),
            "cases_sha256": _sha256_file(args.cases),
            "source_sha256": catalog["cases"][0]["source"]["sha256"],
            "base": args.base,
            "model": args.model,
            "skill_mode": args.skill_mode,
            "seed": args.seed,
            "max_tokens": args.max_tokens,
            "provider_fingerprint": fingerprint,
            "implementation_sha256": {
                "pipeline": _sha256_file(REPO / "harness/docforensics/pipeline.py"),
                "vlm": _sha256_file(REPO / "harness/docforensics/vlm.py"),
                "table_repair": _sha256_file(REPO / "harness/docforensics/table_repair.py"),
                "skills_runtime": _sha256_file(REPO / "harness/docforensics/skills_runtime.py"),
                "audit_table": _sha256_file(
                    REPO / "skills/doc-table-audit/scripts/audit_table.py"),
            },
            "host": {
                "platform": platform.platform(),
                "python": list(sys.version_info[:3]),
                "machine": platform.machine(),
            },
            "ollama_show": model_meta,
            "case_ids": [c["id"] for c in catalog["cases"]],
            "created_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        (outdir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        lines = [
            f"# Table repair pilot · `{args.model}` · skill `{args.skill_mode}`",
            "",
            "Synthetic contract cases for issue #25. Checker + host scope decide "
            "acceptance; this is not a semantic accuracy score.",
            "",
            f"- base: `{args.base}`",
            f"- seed: `{args.seed}`, max_tokens: `{args.max_tokens}`",
            f"- cases: `{args.cases.relative_to(REPO)}`",
            "",
            "| Case | Path | Status | Repaired | Model calls | Terminal reason | Scope/reject |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
        ]
        for record in results:
            lines.append(
                f"| {record['id']} | {record['path']} | {record['status']} | "
                f"{record['repaired']} | {record['model_calls']} | "
                f"`{record['reason']}` | "
                f"`{','.join(x or '-' for x in (record['rejection_reasons'] or record['scope_reasons'] or ['-']))}` |"
            )
        lines += [
            "",
            "## Host adversarial check (TR04)",
            "",
            "The catalog also records a checker-passing data-row rewrite. The host "
            "scope guard must reject it offline regardless of model output:",
            "",
            "```json",
            json.dumps(next(r["adversarial_host_scope"] for r in results if r["id"] == "TR04"),
                       ensure_ascii=False, indent=2),
            "```",
            "",
            "Per-case journals and reports are under `runs/<case-id>/`.",
            "",
        ]
        (outdir / "report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {outdir}")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
