---
name: doc-layout-parse
description: Parse scanned documents or page images into a structured layout tree with bounding boxes, reading order, and node types (text/table/formula). Use when processing scanned papers, textbooks, exam papers, forms, or when the user asks to extract structured content from document images before quality checks.
---

# Layout Parse

## Workflow

1. Receive one or more page images (or a PDF path) plus an output directory.
2. Invoke the local VLM endpoint (`vlm-8b`, 127.0.0.1) via `scripts/parse.py` to obtain per-page blocks:
   `{page, bbox:[x0,y0,x1,y1], type: text|table|formula|figure, order, text?, confidence}`.
3. Merge cross-page reading order; emit a single `layout.json` structure tree.
4. Nodes with `confidence < 0.8` MUST be flagged `"suspect": true` — do not silently pass them on.
5. Append a decision line to `state.jsonl` (action=PARSE, nodes=n, suspects=m).

## Guardrails

- Read-only on inputs; all output goes to the run's state directory.
- If the VLM endpoint is unreachable, emit `NEEDS_HUMAN` for the whole doc — never fall back to a cloud API.
- Full prompt templates and tuning notes live in `references/vlm-prompts.md`; read only when adjusting.

## Outputs

- `state/<doc>/layout.json` — the structure tree consumed by `doc-table-audit` and `doc-formula-verify`.
