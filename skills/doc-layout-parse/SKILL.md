---
name: doc-layout-parse
description: Prepare or inspect a supplied layout.json document tree before formula and table checks. Use when structured OCR output is already available or when planning a document layout integration. This repository does not implement PDF or image OCR.
---

# Layout Input Preparation

## Current workflow

1. Request a supplied layout tree or an authorized OCR export. The CLI consumes an existing `layout.json`; it does not run a page parser.
2. Inspect the examples under `samples/` for the expected schema: a document identifier and nodes with `id`, `type`, and `data`. Formula data contains `latex`; table data contains `rows` and `expected`.
3. Preserve source locations and existing crop paths when available. Never invent coordinates, confidence, or image evidence.
4. Confirm that the document and node identifiers are stable before resuming an existing state directory. A changed input should use a new state directory.
5. If only PDF or page images are available, explain that OCR integration is required and stop this step without claiming extraction succeeded.

## Planned integration

`references/vlm-prompts.md` contains prompt drafts for a future local image parser. There is no `scripts/parse.py` implementation in this repository. Cross-page reading order, crop regeneration, and confidence-based routing remain unimplemented.

## Guardrails

Keep inputs read-only. Write derived outputs to a separate state directory. Do not fetch private documents or send them to external services without authorization.
