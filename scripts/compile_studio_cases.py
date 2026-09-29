#!/usr/bin/env python3
"""Reproduce the archived Studio compilation cases in a new output directory."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ERRORS = {
    "S06": r"Missing \right. inserted",
    "S07": r"File ended while scanning use of \frac",
    "S08": "Missing } inserted",
    "S09": "Missing } inserted",
    "S12": r"Extra }, or forgotten \right",
}


def matches_expectation(item, exit_code, pdf_generated, timed_out, output, tex_log):
    if timed_out or exit_code != item["exit_code"] or pdf_generated != item["pdf_generated"]:
        return False
    if not item["expected_compile_ok"] and EXPECTED_ERRORS[item["case_id"]] not in output:
        return False
    if item.get("undefined_reference_or_citation_in_tex_log") and "undefined" not in tex_log.lower():
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--compiler", default=os.environ.get("TECTONIC", "tectonic"))
    parser.add_argument("--timeout", type=float, default=120, help="Seconds per compilation")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.outdir.exists():
        parser.error("output directory already exists; choose a new --outdir")
    compiler = shutil.which(args.compiler)
    if not compiler:
        parser.error("Tectonic not found; install it or set TECTONIC to its executable")
    catalog_path = ROOT / "samples/studio-cases.json"
    catalog = json.loads(catalog_path.read_text())
    expected = json.loads((ROOT / "docs/evaluation-results/studio-latex/compilation.json").read_text())
    if hashlib.sha256(catalog_path.read_bytes()).hexdigest() != expected["catalog_sha256"]:
        parser.error("catalog differs from the archived compilation inputs")
    sources = {}
    for case in catalog["cases"]:
        content = (ROOT / "samples" / case["file"]).read_text()
        sources[(case["case_id"], "original")] = content
        if case["reference_edits"]:
            for edit in case["reference_edits"]:
                if content.count(edit["original"]) != 1:
                    parser.error(f"{case['case_id']}: reference edit must match exactly once")
                content = content.replace(edit["original"], edit["candidate"], 1)
            sources[(case["case_id"], "author_reference")] = content
    for item in expected["cases"]:
        content = sources[(item["case_id"], item["variant"])]
        if hashlib.sha256(content.encode()).hexdigest() != item["source_sha256"]:
            parser.error(f"{item['case_id']}/{item['variant']}: source differs from the archive")
    args.outdir.mkdir(parents=True, exist_ok=False)
    outdir = args.outdir.resolve()
    version = subprocess.run([compiler, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    results = []
    for item in expected["cases"]:
        folder = outdir / f"{item['case_id']}-{item['variant']}"
        folder.mkdir()
        source = folder / item["file"]
        source.write_text(sources[(item["case_id"], item["variant"])])
        timed_out = False
        try:
            result = subprocess.run(
                [compiler, "--keep-logs", "--outdir", str(folder), str(source)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=args.timeout,
            )
            output, exit_code = result.stdout, result.returncode
        except subprocess.TimeoutExpired as exc:
            output, exit_code, timed_out = exc.stdout or b"", None, True
        (folder / "compiler-output.txt").write_bytes(output)
        pdf_generated = source.with_suffix(".pdf").is_file()
        compile_ok = exit_code == 0 and pdf_generated
        log_path = source.with_suffix(".log")
        tex_log = log_path.read_text(errors="replace") if log_path.exists() else ""
        matched = matches_expectation(item, exit_code, pdf_generated, timed_out,
                                      output.decode(errors="replace"), tex_log)
        row = {key: item[key] for key in ("case_id", "file", "variant", "source_sha256", "expected_compile_ok")}
        row.update(compile_ok=compile_ok, exit_code=exit_code, pdf_generated=pdf_generated,
                   timed_out=timed_out, expectation_matched=matched, artifacts=folder.name)
        results.append(row)
        print(f"{folder.name}: compile={'ok' if compile_ok else 'failed'}, expectation={'matched' if matched else 'MISMATCH'}")
    report = {"compiler": version, "catalog_sha256": expected["catalog_sha256"], "cases": results,
              "matched": sum(row["expectation_matched"] for row in results), "total": len(results)}
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{report['matched']}/{report['total']} expectations matched; report: {args.outdir / 'report.json'}")
    return 0 if report["matched"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
