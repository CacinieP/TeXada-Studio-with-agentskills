# Changelog

## Unreleased

- Studio PNG OCR upload, editable candidate review, explicit undoable adoption, and pending text-node layout export; see [usage](docs/studio-ocr.md).
- Archive the completed v4.7 pilot and correct the 35B/1B model identity and unsupported Mac/CUDA conclusions; see [evidence](docs/evaluation-results/v47-pilot-01/README.md).

### Added

- Verified local MiniCPM-V 4.7 35B Q4, 1B Q4 and non-quantized 1B F16 probes, with real repair/OCR traces, official weight hashes, and reproducible server configuration ([report](docs/evaluation-results/v47-local-comparison-01/README.md)).

- Thirteen Studio documents, including eight original mathematics samples with extraction, syntax and compilation expectations.
- Twenty-seven checker cases, a casebook and reproducible evaluation reports.
- Formula Skill instruction loading, on/off comparison runs, per-candidate events and context-bound CLI resume.
- A continuous browser demo with real model waiting, candidate review, adoption, downloads and sample navigation; all narration uses one synthetic voice reference.
- `scripts/compile_studio_cases.py` to reproduce twelve archived compilation cases in a fresh output directory.
- Chinese and English setup guides, troubleshooting, contribution guidance and release materials.
- `doc-ocr-extract` Skill: image → text candidate lines via a local vision OCR model (`OCR_MODEL`, default `minicpm-ocr:latest`), with raw-bytes input, the checker-family status contract (OK / NEEDS_HUMAN / NEEDS_ENV), bounded response excerpts and ten contract tests under a fake endpoint.
- A reproducible real-text OCR sample: `samples/ocr/source-inlines-01.tex` rendered to `inlines-01.png` via `scripts/make_ocr_samples.py` (Tectonic + pdftoppm), plus the first real-run evidence under `docs/evaluation-results/ocr-chain-01/` including candidate defects that justify mandatory human adoption.
- OpenAI-compatible transport for the OCR chain (issue #30): `ocr_extract.py` defaults to `/v1/chat/completions` with `image_url` data URLs — the same protocol face as the formula-repair provider — while `--transport ollama` keeps the native `/api/chat` fallback; `OCR_TRANSPORT` selects the default and both paths share the status/limits contract.

### Changed

- Keep MiniCPM-V 4.7 35B-A3B Q4_K_M as the default repair model, using the tested local llama.cpp alias/endpoint. `VLM_BASE` configures both Studio and batch requests; document Mac memory requirements and preserve explicit model overrides.

- Reorganize documentation around setup, reproducible examples and implementation details; require Python 3.11+ for the Harness.
- Vendor Monaco 0.52.2 locally, preserve its MIT license and verify pinned package and file hashes.
- Use scoped signed cookies for editor assets and an explicit token for API access.
- Keep uploads and run outputs in `state/`; source packages contain committed files only.
- Adopt AGPL-3.0-only for project-authored material and retain separate third-party and dataset licenses.

### Fixed

- Preserve the editor until the user adopts a reviewed candidate; reset failed controls and discard stale file or preview responses.
- Fix empty diff panels, stale comparisons, hidden collapse controls and preview resizing.
- Reject partial LaTeX parses and malformed checker input; handle missing dependencies without issuing repair requests.
- Validate table structure and complete numeric cells, size Decimal precision to the input, and record only actual edits.
- Preserve rejected candidates, original table rows, process exit codes and bounded response excerpts in reports.
- Remove embedded deployment credentials, private paths and an unlicensed textbook extract from distributed source and reachable history.

Historical runtime results remain in [validation records](docs/validation.md); previous media are listed in the [demo archive](docs/demo.md).
