---
name: doc-table-audit
description: Check supplied table grids for declared row and column counts and numeric totals. Use for simple extracted reports or LaTeX tables that have explicit totals. This repository does not implement merged-cell or cross-page reconstruction.
---

# Table Audit

## Workflow

1. For CLI input, collect table nodes from an existing layout tree and run `scripts/audit_table.py` with `rows` and any `expected` dimensions or totals.
2. The script compares Decimal values with precision sized to the input. Read the reason and cell location when a declared shape or sum fails; do not infer a correct value from appearance alone. Only complete finite decimal cells are numeric: signed decimals and properly grouped thousands are supported; percentages, units and accounting parentheses are rejected.
3. The CLI supports fixture replacement grids for testing. Its real provider does not re-extract table images; an unresolved table becomes `NEEDS_HUMAN`.
4. Studio separately checks simple `tabular` rows and can generate a recomputed total as a candidate. It assumes the data rows are correct and the final row is the total; it cannot decide which source cell was misrecognized.
5. Review the original evidence before adopting any change. Preserve the original table and the final checker-accepted candidate in the diff and report. The CLI stores `original_rows` and `candidate_rows`, together with attempted candidates, checker results and rejection reasons; older events without these fields cannot reconstruct a diff. A checker-accepted candidate still needs user approval.

## Boundaries

No merged-cell verification, cross-page joining, or image re-cropping is implemented here. Unsupported macros, mixed units and complex numeric formatting require manual review. At most two repair attempts are allowed in the CLI. Do not invent source evidence or silently change a document.

## Executable contract

CLI `shape_mismatch / sum_mismatch / bad_number` produce `RETRY`; invalid JSON, row container types or expectations produce `NEEDS_HUMAN`. Indices are nonnegative and in bounds. Exit code is 0 for `OK/RETRY`, 1 for `NEEDS_HUMAN`. Rows must be rectangular with a nonempty header. Without a total row or `expected.totals`, `OK` does not imply numerical validation.

Studio separately parses rectangular, one-row-per-line `tabular` with a textual header and one final total row. Unsupported formats become `NEEDS_HUMAN` with no edit. It records an edit only when source text actually changes. CLI permits English/Chinese grouping commas; Studio currently permits English grouping commas. Neither path interprets currency or percentages. See `evals/evals.json` for T01–T17 and the shared evaluation runner.

Table orchestration remains fixed Python code. The formula instruction host does not load this table Skill into the model. The real provider's table method returns `not_supported` without an HTTP request; fixture replacement grids are test data, and Studio's total candidates are deterministic calculations. Distinguish these paths from model-generated repairs in reports.
