# Studio OCR integration after mainline reconciliation

The current Studio already has a local image/PDF import workflow through
`/api/studio/import`, with image validation, page selection, preview, candidate
review and explicit document creation. Its existing version/dirty-document
guards remain authoritative. This change does not restore the older PNG-only
`/api/studio/ocr` endpoint or replace the current editor with the obsolete page.
See [local Studio](local-studio.md) for the current interface and API.

The independent `skills/doc-ocr-extract/scripts/ocr_extract.py` CLI is retained
for MiniCPM-OCR experiments. It supports OpenAI-compatible transport and an
explicit Ollama fallback, with its own candidate-only contract and archived
synthetic source. It is not substituted for Studio's existing guarded importer.

The default local Studio profile is MiniCPM-V 4.7 35B-A3B Q4_K_M on a loopback
llama.cpp service. The earlier [three-variant comparison](evaluation-results/v47-local-comparison-01/README.md)
used the old branch's prompt/provider and remains historical evidence; it must
not be presented as acceptance results for the newer mainline repair guards.
