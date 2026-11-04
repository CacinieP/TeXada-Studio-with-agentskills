---
name: doc-report
description: Summarize TeXada CLI checks, Studio repair candidates or local image/PDF transcription evidence. Use when the user needs an auditable account of changes, review decisions and remaining uncertainty, keeping OCR fidelity separate from syntax and compilation.
---

# Quality Check Report

## Select the evidence source

| Workflow | Existing records | Report route |
| --- | --- | --- |
| CLI node checks | Run directory `state.jsonl`, available `crops/`, generated `report.md` | Use the harness report generated for the relevant `run_id`; report-generation functions are in `harness/docforensics/__main__.py` |
| Studio `.tex` repair | Studio data directory `jobs/<job_id>/job.json` and `events.jsonl`; authenticated job/status APIs | Export the completed task's `.audit.md` from Studio, supplementing from persisted evidence when requested |
| Studio image/PDF transcription | `imports/<import_id>/source.<ext>` and `candidate.json` | Summarize the import record and human comparison with the source; OCR import has no separate built-in audit export |

Use the configured Studio data directory, not an assumed repository-relative location: the local launcher defaults to the user's application data directory. Report generation must not rerun OCR, repair, compilation or the CLI pipeline merely to refresh a summary.

## Report what actually happened

- Identify the workflow, provider and model from recorded evidence. CLI and Studio formula-repair requests send formula text; Studio OCR sends page images to the local vision endpoint. Fixture repairs are offline test doubles, never measured model performance. Deterministic table checks have no model request.
- For checks and repairs, include original and candidate text, source line or node, checker outcomes, attempted/rejected candidates and unresolved items. Preserve recorded reasons; missing responses after interruption are missing evidence. Bounded response excerpts may be truncated.
- For Studio repair tasks, use `result.original_sha256`, `candidate_sha256`, `edits`, `problems_after`, `trace`, `elapsed_seconds` and compilation records when present. `compile_ok` and `preview_ok` are separate: a PDF may compile while image conversion fails. A `NOT_CHECKED` compilation was not a failed compilation.
- Separate checker acceptance from human adoption. `CANDIDATE_ACCEPTED` records checker acceptance; `USER_ACCEPTED`/`USER_REJECTED` and top-level job `review` record the user's decision. Adoption into the editor is separate from saving a document. The current exported `.audit.md` includes result trace, but does not automatically include later review events from `events.jsonl`; inspect those records for a requested review audit.
- For OCR, record source name/hash, import ID, configured `model`, page `reported_model`, `content_sha256`, imported page range and `has_more_pages`. Summarize unreadable spans and only the discrepancies actually compared against the original. `requires_review: true` marks a candidate, not completed review. The import record does not establish that the candidate was adopted or saved.
- OCR `pages[].raw_response` is the cleaned transcription, not a complete raw transport response. Per-page `usage` may be absent; the import record has no repair-style `model_calls` or per-request event journal. Do not invent HTTP-attempt counts, elapsed time, OCR scores, bbox accuracy or confidence from page count/token metadata. Import source and field details are in [the input contract](../doc-layout-parse/references/vlm-prompts.md).
- Include crop paths only when the files exist. Studio retains the original image/PDF; temporary PDF page images are not retained as CLI crops. A page image hash is provenance metadata, not a surviving image attachment. Mark missing evidence instead of fabricating it.
- Keep OCR fidelity, syntax, compilation and mathematical correctness as separate conclusions. Successful checks or compilation do not establish faithful transcription or correct mathematics.

## Calls and Skill evidence

Distinguish configured capabilities from operations recorded as executed. Report Skill mode and recorded `skill_loaded`/`skill_sha256` evidence rather than assuming every named Skill ran. Studio OCR uses a fixed prompt and does not load `doc-layout-parse`; report generation is fixed code and does not load `doc-report` into a model.

For CLI request counts, use current-run `PROVIDER_RESULT` records and `model_calls_known`; unmatched starts or unknown counts mean a lower bound. An attempted request that times out may have reached the server, while completion remains unknown. For Studio, keep recorded repair `model_calls` scoped to that task; do not add earlier OCR requests to it or treat missing counts as zero.

## Execution identity

CLI terminal reuse requires matching canonical input and execution-context hashes. A matching node identifier alone is insufficient. Reports must distinguish terminal results from skipped matching work and avoid counting resumed events as fresh quality measurements. Skill-content hashes identify the instructions loaded by the formula host; they do not prove better semantic accuracy.

## Guardrails

Report generation must not trigger another model call or silently edit source files. Exclude credentials, allocated network details, and private document content from material intended for publication. Package existing evidence with relative paths when sharing a CLI run.
