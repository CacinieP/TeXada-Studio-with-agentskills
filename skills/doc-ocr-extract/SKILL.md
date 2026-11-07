---
name: doc-ocr-extract
description: Turn a page image into plain-text candidate lines with a local vision OCR model (minicpm-ocr by default). The skill proposes candidates only, never repairs, never writes state, and never decides mathematical truth. Human review is mandatory before any line enters a document.
---

# OCR Extraction (divide and conquer)

## Workflow

1. Take an original, authorized page image. `samples/ocr/` records how the synthetic sample is regenerated from its `.tex` source with Tectonic + pdftoppm.
2. Run `scripts/ocr_extract.py` with the image path as one argument, or feed JSONL records `{"id", "image"|"image_path"}` on stdin. The default transport is the OpenAI-compatible `/v1/chat/completions` with `image_url` data URLs — the same protocol face as the formula-repair line; `--transport ollama` keeps the native `/api/chat`+`images` call as an explicit fallback. `OCR_TRANSPORT` selects the default. Raw bytes are sent color-preserving; binarization/upscaling preprocessing was shown to lose content in ablation and is intentionally NOT applied.
3. Output is one JSONL record per input: `status`, `lines` (candidate text lines), a bounded `raw_response` excerpt with an explicit truncation flag, `model`, `eval_count` (ollama) or `completion_tokens` surfaced as the same counter (openai), and `elapsed_seconds`. `OK` means lines exist for review; it does not certify correctness.
4. Reviewers compare `lines` against the image. Low-fidelity lines shape a human-review list and must not be silently adopted. The next integration turns reviewed lines into layout nodes and `.tex` candidates for the Studio adopt workflow; this script never writes those states.
5. Model and endpoint are environment-driven: `OCR_MODEL` (default `minicpm-ocr:latest`) and `OCR_BASE` (default `http://127.0.0.1:11434`). Any OpenAI-compatible local server (Ollama, vLLM, llama.cpp) can serve the model; cloud endpoints are protocol-compatible but never the default.

## Boundaries

- Divide and conquer: OCR proposes candidate text; checkers, repair and state ownership live in the text-side harness (`doc-formula-verify`, `doc-table-audit`). This script has no access to any ledger or document state.
- Do not invent confidence scores, line boxes or semantic validation. Record only what the model returned, plus objective counters from the endpoint.
- Do not send document images to any cloud provider. The endpoint is a local Ollama-compatible service.
- A `[Non-text]`-style or empty response yields `NEEDS_HUMAN`, not an error retry loop; environment failures yield `NEEDS_ENV`.

## Executable contract

Exit codes follow the checker family: `OK: 0`, `NEEDS_HUMAN: 1`, `NEEDS_ENV: 2`; a JSONL stream returns the highest code encountered. Records echo the input `id` when present. The raw excerpt is capped (1 KiB) with an explicit `response_truncated` flag so traces stay small. Image size is capped at 24 MiB and response at 4 MiB to bound memory use.

Evidence for the first real run against `samples/ocr/inlines-01.png` is archived under `docs/evaluation-results/ocr-chain-01/`; the run used `minicpm-ocr:latest` on a local Ollama endpoint.
