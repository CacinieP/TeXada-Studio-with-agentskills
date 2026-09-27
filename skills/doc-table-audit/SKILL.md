---
name: doc-table-audit
description: Audit extracted tables for structural and numeric errors — merged-cell integrity, row/column count consistency, cross-page continuation, and cross-checking totals against row sums. Use when a document contains tables (reports, exam papers, financial scans) and the extracted table needs verification before it is trusted or exported.
---

# Table Audit

## Workflow

1. Collect nodes typed `table` from the layout tree produced by `doc-layout-parse`.
2. For each node run `scripts/audit_table.py` with the extracted grid and any expected metadata
   (declared dimensions, footer totals). The script is deterministic — do not re-derive checks via the model.
3. Interpret the verdict:
   - `OK` — record and continue.
   - `RETRY` with `reason=page_break` — trigger re-parse of the two adjacent pages, then re-audit the merged grid.
   - `RETRY` with `reason=sum_mismatch` — re-crop the table region and re-invoke the VLM; after two failures mark `NEEDS_HUMAN`.
4. Never modify table data directly; repairs must go through re-extraction so evidence stays traceable.
5. Append every verdict to `state.jsonl` with the failing cell indices.

## Guardrails

- Numeric comparisons use exact decimal semantics (the script handles this); do not eyeball totals.
- A table flagged `suspect` by the parser MUST be audited even if it looks fine.
- At most 3 VLM re-invocations per table node; never block the pipeline.
