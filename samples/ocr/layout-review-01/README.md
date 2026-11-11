# Reviewed layout conversion fixture

Original synthetic text authored for the offline converter contract; **not a
model OCR result or an independently human-reviewed document**. The reviewer
`synthetic-test-operator` identifies only test decisions. No user image, personal
information or third-party text is included.

- `record.json`: an OCR-shaped fixture containing a whole-line formula, plain
  text, a pipe-separated table and a formula missing an operand.
- `fixture-review.json`: explicit test decisions bound to the record hash. The
  ambiguous formula is accepted as a transcription candidate so the harness can
  demonstrate its NEEDS_HUMAN disposition. Acceptance is not formula correctness.

From the repository root, using the project Python environment:

```bash
python skills/doc-ocr-extract/scripts/ocr_to_layout.py \
  samples/ocr/layout-review-01/record.json \
  --review samples/ocr/layout-review-01/fixture-review.json \
  --doc ocr-layout-synthetic-01 --output-dir state/ocr-layout-repeat
PYTHONPATH=harness python -m docforensics run state/ocr-layout-repeat --state state/ocr-layout-check
PYTHONPATH=harness python -m docforensics run state/ocr-layout-repeat --state state/ocr-layout-check
```

Use a fresh converter output directory. Expected: OK=3 / NEEDS_HUMAN=1, zero
provider calls; the second harness run skips four matching nodes. Text nodes are
explicitly `validated=false`. Archived conversion and resume evidence is under
`docs/evaluation-results/ocr-layout-01/`; the full contract is in
`skills/doc-ocr-extract/LAYOUT.md`.
