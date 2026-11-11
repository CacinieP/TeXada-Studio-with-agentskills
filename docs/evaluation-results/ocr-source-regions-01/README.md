# Operator-provided OCR source regions (issue #24)

2026-11-11, macOS arm64 / Python 3.11. This is an offline region-provenance
contract test, not new model inference, detector evaluation or independent
human semantic/image review.

The [original fixture](../../../samples/ocr/source-regions-01/README.md) draws
`x+1` at known positions in a 40×20 PNG, supplies synthetic text and annotates a
box from its rendering geometry. The label `operator_provided` records the
contract channel; the reviewer is explicitly a synthetic fixture, not a person.

[reviewed/layout.json](reviewed/layout.json) contains the actual PNG SHA256,
raw raster dimensions, source filename and node pixel box; [source.png](reviewed/source.png)
contains exactly the supplied bytes. There is no inferred confidence or crop.

[cli-results.json](cli-results.json) and [host-run/state.jsonl](host-run/state.jsonl)
record the real harness CLI:

1. First run: OK=1 / NEEDS_HUMAN=0, zero model requests.
2. Same input: one matching node reused, zero model requests.
3. Copied source image changed by appending bytes: exit 2 / RUN_ERROR, no reuse.
   The original bytes were restored after the rejection; the final report is
   from the second run, not a successful report for the failed third run.

37 OCR tests, 162 harness tests and 181 workbench tests pass locally. Coverage includes stale image
reviews at unchanged dimensions, missing/invalid boxes, normalized/non-integer
and boolean coordinates, broken PNG headers, exact copied bytes, and real CLI
rejection of changed source bytes, mismatched dimensions, out-of-bounds regions,
missing image metadata and malformed node provenance before terminal reuse.
Existing text-only conversion and legacy layouts retain their behavior.

The converter checks bounded PNG bytes, IHDR identity/dimensions and header CRC;
it does not fully decode image pixels. CLI preflight verifies the source file
hash, declared dimensions and each node's region contract. Neither operation
proves that a box surrounds the correct text. PNG only; no EXIF/rotation
transforms, PDF page detection, cropping or report thumbnail UI is introduced.

This advances #24's explicit source-region correspondence contract. Automatic
region output/detection and independently adjudicated image correspondence still
require separate evidence; reliable low-confidence signals also remain open.
No model defaults or beta.3 release artifacts are changed.

Reproduction: [source fixture commands](../../../samples/ocr/source-regions-01/README.md)
and [review contract](../../../skills/doc-ocr-extract/LAYOUT.md#optional-operator-provided-source-regions).
`SHA256SUMS.json` lists the source fixture and archived artifacts;
`implementation.json` records the converter/host hashes and baseline commit.
