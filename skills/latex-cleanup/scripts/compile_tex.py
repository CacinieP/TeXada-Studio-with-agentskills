#!/usr/bin/env python3
"""Compile an explicitly selected root and preserve actual status in a fresh directory.

Use the project's own build command instead for custom recipes/Tectonic workspaces.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


def summarize_log(text):
    patterns = {
        "overfull": r"Overfull \\[hv]box[^\n]*",
        "undefined_references_or_citations": r"[^\n]*(?:Reference|Citation)[^\n]*undefined[^\n]*|[^\n]*There were undefined (?:references|citations)[^\n]*",
        "rerun_requested": r"[^\n]*(?:Rerun to get cross-references right|Please \(re\)run Biber|Please rerun LaTeX)[^\n]*",
    }
    return {name: re.findall(pattern, text, re.IGNORECASE) for name, pattern in patterns.items()}


def run_process(command, cwd, timeout):
    started = time.monotonic()
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=os.name == "posix")
    timed_out = False
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        output, _ = proc.communicate()
    return proc.returncode, output, timed_out, round(time.monotonic() - started, 3)


def compile_document(root, engine, outdir, timeout=60, offline=False):
    root = Path(root).resolve()
    outdir = Path(outdir).resolve()
    result = {"root": str(root), "engine": engine, "outdir": str(outdir),
              "status": "not_run", "compiler_exit_code": None, "pdf": None}
    if not root.is_file() or root.suffix.lower() != ".tex":
        result["reason"] = "Root must be an existing .tex file."
        return result
    if outdir.exists():
        result["reason"] = "Build directory already exists; use a new directory to exclude stale outputs."
        return result
    if offline and engine != "tectonic":
        result["reason"] = "--offline is implemented only for Tectonic."
        return result
    executable = shutil.which("tectonic" if engine == "tectonic" else "latexmk")
    if executable is None:
        result["reason"] = f"Required executable is unavailable: {'tectonic' if engine == 'tectonic' else 'latexmk'}"
        return result
    if engine == "tectonic":
        command = [executable, "--keep-logs", "--keep-intermediates", "--synctex", "--outdir", str(outdir)]
        if offline:
            command.append("--only-cached")
    else:
        switches = {"pdflatex": "-pdf", "xelatex": "-xelatex", "lualatex": "-lualatex"}
        command = [executable, switches[engine], "-interaction=nonstopmode", "-halt-on-error",
                   "-file-line-error", "-synctex=1", "-outdir=" + str(outdir)]
    # Prefix prevents a source filename starting with '-' from becoming an option.
    command.append("./" + root.name)
    result["command"] = command
    outdir.mkdir(parents=True)
    try:
        code, console, timed_out, seconds = run_process(command, root.parent, timeout)
        result.update(compiler_exit_code=code, elapsed_seconds=seconds)
        (outdir / "console.log").write_bytes(console)
        logpath = outdir / (root.stem + ".log")
        log = logpath.read_text(encoding="utf-8", errors="replace") if logpath.exists() else console.decode("utf-8", errors="replace")
        result["diagnostics_source"] = str(logpath if logpath.exists() else outdir / "console.log")
        result["diagnostics"] = summarize_log(log)
        pdf = outdir / (root.stem + ".pdf")
        valid_pdf = False
        if pdf.is_file():
            with pdf.open("rb") as stream:
                valid_pdf = stream.read(5) == b"%PDF-"
        result["pdf"] = str(pdf) if valid_pdf else None
        result["status"] = "timeout" if timed_out else "success" if code == 0 and valid_pdf else "failed"
        if not timed_out and code == 0 and not valid_pdf:
            result["reason"] = "Process exited successfully but produced no PDF with the expected name. Inspect the project recipe."
    except OSError as exc:
        result["reason"] = str(exc)
        result["status"] = "not_run"
    (outdir / "build-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--engine", required=True, choices=["tectonic", "pdflatex", "xelatex", "lualatex"])
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--offline", action="store_true", help="Tectonic: use existing cached resources only")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 3600:
        parser.error("--timeout must be greater than 0 and no more than 3600 seconds")
    try:
        result = compile_document(args.root, args.engine, args.outdir, args.timeout, args.offline)
    except OSError as exc:
        result = {"status": "not_run", "compiler_exit_code": None, "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "success":
        return 0
    if result["status"] == "timeout":
        return 124
    if result["status"] == "not_run":
        return 2
    code = result["compiler_exit_code"]
    return code if isinstance(code, int) and 0 < code < 256 else 1


if __name__ == "__main__":
    sys.exit(main())
