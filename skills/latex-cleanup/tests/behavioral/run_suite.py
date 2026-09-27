#!/usr/bin/env python3
"""Prepare isolated agent tasks or check their observable file results.

This does not invoke a model or grade the truthfulness of prose reports.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

BASE = Path(__file__).resolve().parent


def prepare(outdir):
    outdir.mkdir(parents=True, exist_ok=False)
    requests = json.loads((BASE / "requests.json").read_text())
    for name, request in requests.items():
        shutil.copytree(BASE / "fixtures" / name, outdir / name)
        (outdir / name / "request.txt").write_text(request + "\n", encoding="utf-8")
    return {"status": "prepared", "cases": list(requests)}


def check(outdir):
    checks = {}
    for name in ("check-only", "uncertain-ocr"):
        for src in (BASE / "fixtures" / name).iterdir():
            target = outdir / name / src.name
            checks[f"{name}/{src.name}_unchanged"] = target.exists() and target.read_bytes() == src.read_bytes()
    clean = outdir / "cleanup/notes.md"
    # Independent oracle: never derive expected preservation from the formatter
    # being evaluated, which would reproduce its bugs in the expected output.
    expected = (BASE / "fixtures/cleanup/notes.md").read_bytes().replace(
        b"Plain paragraph. \r\n", b"Plain paragraph.\r\n", 1)
    checks["cleanup/exact_conservative_change"] = clean.exists() and clean.read_bytes() == expected
    ref = outdir / "cleanup/reference.md"
    checks["cleanup/reference_unchanged"] = ref.exists() and ref.read_bytes() == (BASE / "fixtures/cleanup/reference.md").read_bytes()
    repair = outdir / "repair/main.tex"
    expected = (BASE / "fixtures/repair/main.tex").read_bytes().replace(b"\\end{enumerate}", b"\\end{itemize}")
    # The fixture also uses \\mathbb without loading its package. Either package
    # is a legitimate minimal fix; do not force one model's spelling.
    candidates = [expected.replace(b"\\documentclass{article}\n", b"\\documentclass{article}\n\\usepackage{" + package + b"}\n")
                  for package in (b"amsfonts", b"amssymb")]
    checks["repair/content_preserved_and_dependencies_fixed"] = repair.exists() and repair.read_bytes() in candidates
    builds = []
    for path in (outdir / "repair").rglob("build-result.json"):
        try:
            item = json.loads(path.read_text())
            pdf = Path(item.get("pdf") or "__missing__")
            builds.append(item.get("status") == "success" and pdf.is_file() and pdf.read_bytes().startswith(b"%PDF-"))
        except (OSError, ValueError, TypeError):
            builds.append(False)
    checks["repair/successful_build_artifact_recorded"] = any(builds)
    for name in ("check-only", "cleanup", "repair", "uncertain-ocr"):
        report = outdir / name / "report.md"
        checks[f"{name}/report_present"] = report.exists() and bool(report.read_text().strip())
    result = {"pass": all(checks.values()), "checks": checks,
              "scope": "Observable files and build artifacts only; manually review prose reports and tool traces.",
              "manual_report_review": "not_run"}
    (outdir / "behavioral-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check"))
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.outdir) if args.action == "prepare" else check(args.outdir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("pass") is False else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
