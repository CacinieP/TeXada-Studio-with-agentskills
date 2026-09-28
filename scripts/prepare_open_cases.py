#!/usr/bin/env python3
"""Reproduce a small, source-pinned pilot; no checker/model-guided selection."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

REVISION = "441c5b56853ec898d8adf6ed792f7d7056473862"
UPSTREAM = "https://github.com/active-calculus/active-calculus-single-mbx"
FILES = {
    "sec-1-1-vel.xml": "c6f59b734295d6a5c0a01d9c132cfbeda74ddbc7dcc0bcefbcfa7bb445e3ccc0",
    "sec-1-2-lim.xml": "4ac13e6a39f82ffbbea462cff01c3f2c21706c9262698bb9de834d2dd444bf0c",
    "sec-1-3-derivative-pt.xml": "acb694136f2c19e5b48d95a2526d62260a8fe6af0f3bc52e8b52aafdd154f4c9",
}
LICENSE_SOURCE_SHA256 = "b2a38d9aae8b817363c40a79c092b66b2b201e94ab9d06aba746e8d3daf37e18"
RULE = ("In source order, take the first two unique whitespace-normalized m/me nodes "
        "per listed chapter, 15–130 characters inclusive, with no nested XML or "
        "text/ds/dd/amp/nonumber/lt commands or XML entities. Do not select by checker result. "
        "For each source formula, remove its final closing brace if present; otherwise append '+'.")


def build(source_dir):
    cases = []
    for filename, expected in FILES.items():
        raw = (source_dir / filename).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"source hash mismatch: {filename}")
        content = raw.decode("utf-8")
        selected = []
        seen = set()
        for match in re.finditer(r"<(?:m|me)(?:\s[^>]*)?>([^<]+)</(?:m|me)>", content):
            formula = " ".join(match.group(1).split())
            if not 15 <= len(formula) <= 130 or re.search(r"\\(?:text|ds|dd|amp|nonumber|lt)\b|&", formula):
                continue
            if formula in seen:
                continue
            seen.add(formula)
            selected.append((formula, content[:match.start()].count("\n") + 1))
            if len(selected) == 2:
                break
        if len(selected) != 2:
            raise ValueError(f"insufficient eligible source formulas: {filename}")
        for formula, line in selected:
            cid = f"AC{len(cases) // 2 + 1:02d}"
            source = {"title": "Active Calculus Single Variable, Second Edition",
                      "author": "Matthew Boelkins; contributing authors David Austin, Christina Safranski, Steven Schlicker",
                      "url": f"{UPSTREAM}/blob/{REVISION}/source/{filename}#L{line}",
                      "license": "CC-BY-SA-4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                      "locator": f"source/{filename}, line {line}, m/me node",
                      "revision": REVISION, "sha256": expected}
            common = {"source": source, "reference_latex": formula, "review_status": "pending"}
            cases.append({"id": cid + "-original", **common, "case_kind": "original", "original_latex": formula})
            position = formula.rfind("}")
            injected = formula[:position] + formula[position + 1:] if position >= 0 else formula + "+"
            injection = "remove final closing brace" if position >= 0 else "append trailing plus"
            cases.append({"id": cid + "-injected", **common, "case_kind": "injected",
                          "original_latex": injected, "injection": injection})
    return {"schema_version": 1, "dataset_id": "active-calculus-pilot-v1", "dataset_kind": "open-source",
            "annotation_status": "pending", "license": "CC-BY-SA-4.0", "sampling_rule": RULE,
            "license_source": f"{UPSTREAM}/blob/{REVISION}/source/bibinfo.xml",
            "license_source_sha256": LICENSE_SOURCE_SHA256, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new output file; refuses overwrite")
    parser.add_argument("--fetch", action="store_true", help="explicitly download pinned public sources")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists")
    if args.fetch:
        args.source_dir.mkdir(parents=True, exist_ok=True)
        for filename in [*FILES, "bibinfo.xml"]:
            url = f"https://raw.githubusercontent.com/active-calculus/active-calculus-single-mbx/{REVISION}/source/{filename}"
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            expected = FILES.get(filename, LICENSE_SOURCE_SHA256)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(f"download hash mismatch: {filename}")
            (args.source_dir / filename).write_bytes(raw)
    license_bytes = (args.source_dir / "bibinfo.xml").read_bytes()
    if hashlib.sha256(license_bytes).hexdigest() != LICENSE_SOURCE_SHA256:
        raise ValueError("license source hash mismatch")
    catalog = build(args.source_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(catalog['cases'])} cases to {args.out}")


if __name__ == "__main__":
    main()
