---
name: doc-layout-parse
description: Prepare inputs for TeXada document checks. Use for a supplied layout.json tree or for routing images and PDFs through the local Studio transcription workflow. Distinguish reviewable page LaTeX from structured layout extraction.
---

# Document Input Preparation

## Choose the input route

The repository has two implemented routes. Select from the user's source and intended output:

| Source and goal | Route | Output |
| --- | --- | --- |
| Existing document nodes for CLI formula/table checks | Inspect a supplied `layout.json`, then use the harness | Node checks, candidates and a report |
| PNG, JPEG, WebP or PDF to edit as LaTeX | Use Studio's image/PDF import with the configured local vision model | Page transcriptions merged into a reviewable `.tex` candidate |

Read [input contracts and layout proposals](references/vlm-prompts.md) for the relevant request and output fields. Do not treat the Studio candidate as a `layout.json` tree.

## Supplied layout tree

- Inspect examples under `samples/`: a document has `doc` and `nodes`; each node has `id`, `type` and `data`. Formula data uses `latex`; table data uses `rows` and `expected`.
- Keep `doc` unique within a run and node IDs unique within their document. Preserve existing page/source locations and crop paths; paths are resolved relative to the command's working directory. Sample crops are test doubles, not measured OCR evidence.
- Run from the repository root when using repository-relative crop paths. The CLI accepts a directory containing `layout.json`, or a parent with such directories one level below. It does not accept a PDF or generate nodes from a `.tex` candidate.
- Resume only with stable input and execution context: terminal reuse is bound to their hashes, not just IDs. Use a fresh state directory for an independent evaluation.

## Local Studio transcription

- Open the local Studio WebUI and use image/PDF import. Its authenticated `POST /api/studio/import` calls `LocalRuntime.import_document`; no separate `scripts/parse.py` exists.
- Import only the user's chosen source. The local route accepts a file up to 12 MiB, sends image content to an explicitly configured loopback vision endpoint, and handles at most five PDF pages per request. PDF rasterization requires `pdfinfo` and `pdftoppm`.
- Keep the original file and inspect the returned pages and LaTeX against it, including formulas, notation, page coverage and `[UNREADABLE]` spans. `requires_review: true` means a candidate awaits review; the import does not save over an existing document. Creating a new Studio document is a separate explicit action.
- Preserve the import ID, source/content hashes and available page metadata when the user needs provenance. Report the actual imported page range; a request starting after page 1 or returning `has_more_pages: true` does not cover the whole PDF. The API supports `page_start`; the current import dialog selects a page limit and starts at page 1.
- Compilation or a syntax check can help inspect the candidate, but neither establishes OCR fidelity or mathematical correctness. For CLI checking afterward, prepare an explicit layout tree from reviewed content; no automatic Studio-to-layout converter is implemented.

## Scope and runtime loading

Studio implements page-to-LaTeX OCR, not evaluated block segmentation, bbox extraction, calibrated confidence or cross-page reading-order reconstruction. The reference's block-JSON prompt is an integration proposal, not the current API response. Never invent those fields or regenerate crop evidence by assumption.

This Skill guides an agent's workflow. Studio's OCR prompt is fixed in `webui/local_runtime.py`; it does not dynamically load this Skill into the model. The CLI formula host's separate Skill-loading trace must not be claimed as OCR Skill loading.

## Guardrails

Keep inputs read-only. Write derived outputs to a separate state directory. Do not fetch private documents or send them to external services without authorization.
