---
name: doc-report
description: Summarize document quality-check events, repair candidates, and remaining review items. Use after the CLI pipeline or Studio repair workflow, when the user needs an auditable record of what changed and what remains uncertain.
---

# Quality Check Report

## Workflow

1. For CLI runs, read `state.jsonl` and generate `report.md` with the supplied harness. For Studio, export the report after a repair task finishes.
2. Identify the provider explicitly. Fixture repairs are offline test doubles, never measured model performance. Current real model calls send text only.
3. Report original and candidate text, source line or node, checker outcome, and unresolved items. Studio adds content SHA256 hashes, elapsed time, and compilation outcomes.
4. Include crop paths only when those files exist. The CLI marks missing evidence; do not fabricate crops or confidence deltas.
5. State that syntax and successful compilation do not prove mathematical meaning. A reviewer must approve candidate changes.

## Guardrails

Report generation must not trigger another model call or silently edit source files. Exclude credentials, allocated network details, and private document content from material intended for publication. Package existing evidence with relative paths when sharing a CLI run.
