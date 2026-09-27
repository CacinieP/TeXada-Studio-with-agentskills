---
name: doc-report
description: Generate a quality-control report for a parsed document, summarizing per-node verdicts, applied repairs with before/after diffs, evidence crops, and remaining human-review items. Use after layout parsing and quality-check skills have run, or when the user asks "what was fixed" / "what needs review" for a document pipeline run.
---

# Report

## Workflow

1. Read `state.jsonl` for the run; group events by document and node.
2. Render `report.md` with:
   - summary table (nodes total / OK / repaired / needs_human, per skill)
   - per-repair diff: original text → repaired text, with evidence crop path and confidence delta
   - a `needs_human` section listing node ids, crops, and failure reasons
3. Link every claim to evidence; a repair without a crop path is a bug — fail the report instead.
4. Append a final line to `state.jsonl` (action=REPORT, path=...).

## Guardrails

- Read-only over state; the report must not trigger any re-processing.
- Keep the report self-contained: relative paths only, so the folder can be zipped and shared.
