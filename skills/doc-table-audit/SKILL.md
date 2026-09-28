---
name: doc-table-audit
description: Check supplied table grids for declared row and column counts and numeric totals. Use for simple extracted reports or LaTeX tables that have explicit totals. This repository does not implement merged-cell or cross-page reconstruction.
---

# Table Audit

## Workflow

1. For CLI input, collect table nodes from an existing layout tree and run `scripts/audit_table.py` with `rows` and any `expected` dimensions or totals.
2. The script compares Decimal values. Read the reason and cell location when a declared shape or sum fails; do not infer a correct value from appearance alone.
3. The CLI supports fixture replacement grids for testing. Its real provider does not re-extract table images; an unresolved table becomes `NEEDS_HUMAN`.
4. Studio separately checks simple `tabular` rows and can generate a recomputed total as a candidate. It assumes the data rows are correct and the final row is the total; it cannot decide which source cell was misrecognized.
5. Review the original evidence before adopting any change. Preserve the original table and record every candidate in the diff and report.

## Boundaries

No merged-cell verification, cross-page joining, or image re-cropping is implemented here. Unsupported macros, mixed units and complex numeric formatting require manual review. At most two repair attempts are allowed in the CLI. Do not invent source evidence or silently change a document.
