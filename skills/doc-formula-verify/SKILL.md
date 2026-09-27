---
name: doc-formula-verify
description: Verify and repair OCR-extracted mathematical formulas by round-tripping through a symbolic parser and visual re-render. Use when processing scanned papers, textbooks, exam papers, or any document containing LaTeX/handwritten formulas, or when the user mentions formula OCR errors, MathML, or TeX conversion.
---

# Formula Verification

## Workflow

1. Read the parse tree produced by `doc-layout-parse`; collect nodes typed `formula`.
2. For each node run `scripts/verify.py` — SymPy parse; on failure emit `RETRY` with the failure reason.
3. On `RETRY`, re-crop with 20% padding and re-invoke the local VLM at higher resolution (see `references/vlm-prompts.md`).
4. After two failed retries mark `needs_human` and continue — never block the pipeline.
5. Append every decision to `state.jsonl` so an interrupted run can resume.

## Guardrails

- Never silently rewrite a formula; every edit must carry the original crop as evidence.
- Do not exceed 3 VLM calls per formula node.
