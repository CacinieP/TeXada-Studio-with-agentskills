# OCR candidate → reviewed layout → CLI resume (issue #24)

2026-11-11, macOS arm64 / Python 3.11. This is offline engineering validation,
not a new OCR-model measurement or independent human semantic review.

## Observations

- The original synthetic [fixture](../../../samples/ocr/layout-review-01/README.md)
  converts to [reviewed/layout.json](reviewed/layout.json) with explicit operator
  decisions bound to the entire OCR record SHA256. [review.json](reviewed/review.json)
  retains the review outcome; each node retains its original lines.
- Running the real harness CLI twice produces `OK=3, NEEDS_HUMAN=1` both times.
  The first run checks two formulas and one numeric table, passes through the
  plain-text node with `validated=false`, and escalates the missing operand.
  The second run reuses four matching input/context terminals. There are zero
  provider requests in both runs. The complete journal is
  [host-run/state.jsonl](host-run/state.jsonl); the final report describes the
  second (resumed) run.
- A boundary probe uses the **unchanged archived real OCR record**
  [inlines-01-run-openai.json](../ocr-chain-01/inlines-01-run-openai.json).
  Its table span consists of space-aligned text. An agent parsing probe labels
  it as a pipe table, so conversion produces `ambiguous_table_delimiter` and
  **no layout**. See [archived-ocr-boundary.json](archived-ocr-boundary.json).
  This is not human image adjudication, fresh OCR inference, or a table-quality
  claim. It demonstrates the converter refusing to guess column boundaries.

## Verification and remaining work

The OCR extraction/conversion suite has 29 passing tests, including stale review
hashes, partial review, overlapping decisions, explicit rejection, malformed
and multi-span math, ragged/escaped/Markdown tables, duplicate JSON keys,
non-overwrite behavior, and real CLI first-run/resume. Existing extraction
transport tests are now included in the main regression workflow as well.
The full harness suite is run separately; CI covers the repository regression.

The converter supplies a pending list for objectively unreviewed or unparseable
content, **not an invented low-confidence score**. Whole-page image regions and
calibrated OCR confidence remain out of scope. No bbox/crop is manufactured from
plain text, and text provenance does not replace image evidence. Issue #24 stays
open for those remaining contracts; this PR delivers its candidate-to-layout
conversion subtask only.

Reproduction commands and the review contract:
[LAYOUT.md](../../../skills/doc-ocr-extract/LAYOUT.md).
`SHA256SUMS.json` covers the archived evidence files and fixture inputs. Source
implementation is the containing PR/commit, and `implementation.json` records
converter/checker/host hashes.
