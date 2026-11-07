# Changelog

## Unreleased

### Added

### Added

- Per-task model routing for the agent stack: `REPAIR_MODEL` (preferred, with `VLM_MODEL` fallback) and `OCR_MODEL` (vision-capable default `minicpm-ocr:latest`) drive Studio, the background CLI and the reports; `/api/nodeinfo` exposes both tags.
- A MiniCPM pilot record under `docs/evaluation-results/minicpm-pilot-01/`: budget-300 traces that exposed thinking-channel token exhaustion, the budget fix, 1B/2B candidate-quality evidence and a vision probe for the OCR chain.
- Thirteen Studio documents, including eight original mathematics samples with extraction, syntax and compilation expectations.
- Twenty-seven checker cases, a casebook and reproducible evaluation reports.
- Formula Skill instruction loading, on/off comparison runs, per-candidate events and context-bound CLI resume.
- A continuous browser demo with real model waiting, candidate review, adoption, downloads and sample navigation; all narration uses one synthetic voice reference.
- `scripts/compile_studio_cases.py` to reproduce twelve archived compilation cases in a fresh output directory.
- Chinese and English setup guides, troubleshooting, contribution guidance and release materials.

### Changed

- Raised the default response budget `--max-tokens` from 300 to 8192 across the provider, CLI and evaluation runner: thinking-channel models need room for reasoning plus the answer; non-thinking models still stop at `finish_reason=stop`. The budget is part of the provider fingerprint, so resumed runs re-check after upgrading.
- Formula repair in Studio now reports the effective `REPAIR_MODEL` instead of the legacy variable; deployments that only set `VLM_MODEL` behave exactly as before.
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
