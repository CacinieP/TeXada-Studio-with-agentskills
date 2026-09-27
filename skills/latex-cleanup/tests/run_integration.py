#!/usr/bin/env python3
"""Run the supplied document fixtures using an existing Tectonic installation."""

import argparse
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))
import compile_tex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    output = args.outdir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = {"builds": {}, "formatting": {}, "checks": {}, "pdf_text": {}}
    for name in ("basic-error", "basic-repaired", "semantics", "multifile"):
        print(f"Testing {name}", flush=True)
        before = output / name / "before"
        after = output / name / "after"
        shutil.copytree(BASE / "tests/fixtures" / name, before)
        shutil.copytree(before, after)
        files = sorted(after.rglob("*.tex"))
        command = [sys.executable, str(BASE / "scripts/format_whitespace.py"), *map(str, files),
                   "--write", "--backup-dir", str(output / name / "backup")]
        run = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
        results["formatting"][name] = json.loads(run.stdout)
        diff = []
        for target in files:
            relative = target.relative_to(after)
            diff.extend(difflib.unified_diff((before / relative).read_text().splitlines(keepends=True),
                                           target.read_text().splitlines(keepends=True),
                                           fromfile="before/" + str(relative), tofile="after/" + str(relative)))
        (output / name / "cleanup.diff").write_text("".join(diff), encoding="utf-8")
        for stage, source in (("before", before), ("after", after)):
            result = compile_tex.compile_document(source / "main.tex", "tectonic", output / name / ("build-" + stage),
                                                  timeout=60, offline=args.offline)
            results["builds"][name + "/" + stage] = result
        builds = [results["builds"][name + "/" + stage] for stage in ("before", "after")]
        expected = "failed" if name == "basic-error" else "success"
        results["checks"][name + "_status"] = all(build["status"] == expected for build in builds)
        if name == "basic-error":
            results["checks"]["basic_error_is_environment_mismatch"] = all(
                "ended by \\end{enumerate}" in Path(build["diagnostics_source"]).read_text(errors="replace")
                for build in builds if "diagnostics_source" in build) and all("diagnostics_source" in build for build in builds)
        if expected == "success":
            results["checks"][name + "_references_resolved"] = all(
                not build["diagnostics"]["undefined_references_or_citations"] for build in builds)
            results["checks"][name + "_no_overfull"] = all(not build["diagnostics"]["overfull"] for build in builds)
        if name in ("semantics", "multifile"):
            pdftotext = shutil.which("pdftotext")
            if pdftotext and all(build["status"] == "success" for build in builds):
                texts = []
                for build in builds:
                    target = Path(build["outdir"]) / "main.txt"
                    subprocess.run([pdftotext, "-layout", build["pdf"], str(target)], check=True, timeout=30)
                    texts.append(" ".join(target.read_text().split()))
                equal = texts[0] == texts[1]
                results["pdf_text"][name] = {"status": "checked", "equal_normalized_text": equal}
                results["checks"][name + "_pdf_text"] = equal
            else:
                results["pdf_text"][name] = {"status": "not_run", "reason": "PDF or pdftotext unavailable"}
        if name == "multifile":
            results["checks"]["bib_unchanged"] = (before / "references.bib").read_bytes() == (after / "references.bib").read_bytes()
        if name.startswith("basic"):
            results["checks"][name + "_png_unchanged"] = (before / "fig.png").read_bytes() == (after / "fig.png").read_bytes()
    print("Testing extension-only failure probe", flush=True)
    probe = output / "extension-only"
    shutil.copytree(BASE / "tests/fixtures/basic-repaired", probe)
    source = probe / "main.tex"
    source.write_text(source.read_text().replace("{fig.png}", "{fig.pdf}"), encoding="utf-8")
    result = compile_tex.compile_document(source, "tectonic", output / "extension-only-build", offline=args.offline)
    results["builds"]["extension-only"] = result
    results["checks"]["extension_only_fails"] = result["status"] == "failed"
    console = output / "extension-only-build/console.log"
    results["checks"]["extension_only_is_missing_resource"] = console.exists() and "Unable to load picture or PDF file 'fig.pdf'" in console.read_text(errors="replace")
    results["pass"] = all(results["checks"].values())
    (output / "integration-result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": results["pass"], "checks": results["checks"], "report": str(output / "integration-result.json")}, ensure_ascii=False))
    return 0 if results["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
