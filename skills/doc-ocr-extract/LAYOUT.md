# Reviewed OCR lines → layout.json

`ocr_to_layout.py` is an offline converter. It neither calls a model nor changes
an existing document or harness journal. Its input is **one** JSON record from
`ocr_extract.py`; a multi-record JSONL stream must be split into page records.
A record's `status=OK` only means OCR text exists, not that it is correct.

## Review gate

First create a fresh review workspace (exit 1 means review is required):

```bash
python skills/doc-ocr-extract/scripts/ocr_to_layout.py ocr.json \
  --doc example-ocr --page 1 --output-dir state/ocr-review-draft
```

The directory contains `review.json` (numbered source lines and pending reasons)
and `review-template.json`. It contains **no layout.json**. Compare the full lines
against the authorized image, copy the template to your decisions file and fill
in the operator name and line decisions. Line numbers are 1-based and inclusive:

```json
{
  "record_sha256": "copy the exact digest from review-template.json",
  "reviewer": "name of the reviewing operator",
  "decisions": [
    {"start_line": 1, "end_line": 1, "action": "accept", "type": "formula"},
    {"start_line": 2, "end_line": 2, "action": "accept", "type": "text"},
    {"start_line": 3, "end_line": 6, "action": "accept", "type": "table", "separator": "pipe"},
    {"start_line": 7, "end_line": 7, "action": "reject", "reason": "explain why this line is excluded"}
  ]
}
```

Then create a **new** sample directory:

```bash
python skills/doc-ocr-extract/scripts/ocr_to_layout.py ocr.json \
  --review decisions.json --doc example-ocr --page 1 --output-dir state/ocr-reviewed
PYTHONPATH=harness python -m docforensics run state/ocr-reviewed --state state/ocr-check
# Repeating the last command resumes only matching content and checker context.
```

Every line must have exactly one valid accept/reject decision. Changed OCR text,
model metadata or record id invalidates the review digest; overlapping ranges,
missing rejection reasons and invalid types are rejected. Unreviewed lines and
unparseable accepted spans stay in `review_items`, and block layout emission.
An entirely rejected page also produces no layout. A complete usable review
creates both `review.json` and `layout.json`; the former retains excluded lines
with reasons. Existing output directories are never overwritten.

The reviewer field is an **operator attestation**, not identity verification or
proof of independent human review. Do not fill it with a person's name unless
that person actually reviewed the source. Synthetic tests explicitly use a test
operator. Never use a successful conversion as a mathematical accuracy claim.

## Node contract and limits

- `formula`: exactly one source line. Only a complete surrounding `$...$`,
  `$$...$$`, `\(...\)` or `\[...\]` wrapper is removed; the original line is
  preserved in `ocr_source.text`. Multiple separately delimited spans on one line
  stay pending rather than being stripped as one formula. The converter does not
  fix the formula.
- `text`: exactly one line, preserved verbatim. The harness passes this node
  through with `validated=false`; `OK` is not a text/OCR validation result.
- `table`: 2–64 lines and 2–32 columns with a nonempty header, explicitly
  separated by literal tabs (`separator=tab`) or pipes (`separator=pipe`).
  An optional single outer pipe on each side is removed, and cell-edge whitespace
  is trimmed. Data values are not changed and no totals are inferred. Escaped
  delimiters, Markdown separator rows, ragged rows and cells over 256 characters
  require review instead of silent guessing. Space-aligned and merged-cell tables
  need a separate reviewed normalization step; this converter does not invent one.

Node ids derive from source line ranges, node order follows source order, and
`ocr_source` records the OCR digest, range, original text and reviewer. Page is
provided explicitly by the operator, not inferred from a model. Image boxes,
confidence scores and image-grounded correctness are not fabricated. Source
images/crops must be retained separately; text provenance is not a crop.

Inputs are capped at 4 MiB each, 4096 lines and 32768 characters per line.
Exit codes: 0 = layout created; 1 = review required (review bundle only);
2 = invalid input, stale review or filesystem error. JSON must be UTF-8 with
unique keys and finite numbers. Only ASCII document ids of up to 80 characters
are accepted; path-like ids are rejected.

A reproducible **synthetic conversion fixture**, not fresh OCR evidence, lives in
`samples/ocr/layout-review-01/`. The archived real OCR sample under
`docs/evaluation-results/ocr-chain-01/` contains space-aligned table text; marking
that span as a table with pipe/tab syntax must remain pending rather than guess
column boundaries.
