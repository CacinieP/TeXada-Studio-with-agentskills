# Changelog

## Unreleased

### Added

- Expand the local Monaco snippet pack from 25 to 82 entries, adding amsthm theorem-class environments, matrices and determinants, cross-references, accents, adaptive delimiters and common Greek letters and math symbols.
- Add five offline document templates (blank article, lecture notes, exam paper, Beamer, English article) with a picker reachable from the sidebar and the command palette; blank new documents now come from the same template module.
- Highlight TeX's modular building blocks with dedicated token classes: sectioning commands (bold blue), preamble and definition directives including `\input`/`\include` file splits (violet), and cross-references with their keys (`\label`/`\ref`/`\cite`, teal) join the existing keyword/comment/math coloring in the shipped theme.
- Fold documents by TeX structure: a local folding provider pairs `\begin`/`\end` environments and closes sections at the next heading of the same or higher level, ignoring commented-out structure and verbatim content; unterminated environments fold to the end of the document.
- Refresh the bilingual repository entry with a current synthetic-workspace screenshot, local deployment/troubleshooting guides and source distribution checksums with per-file manifests.
- Add a Studio operation Skill and current AgentSkills guide; align formula, table, OCR-input and reporting instructions with the local Web UI and its review/version boundaries.
- Fresh local verification records for 2026-10-15, with installation and model-switch troubleshooting.

- Thirteen Studio documents, including eight original mathematics samples with extraction, syntax and compilation expectations.
- Twenty-seven checker cases, a casebook and reproducible evaluation reports.
- Formula Skill instruction loading, on/off comparison runs, per-candidate events and context-bound CLI resume.
- A continuous browser demo with real model waiting, candidate review, adoption, downloads and sample navigation; all narration uses one synthetic voice reference.
- `scripts/compile_studio_cases.py` to reproduce twelve archived compilation cases in a fresh output directory.
- Chinese and English setup guides, troubleshooting, contribution guidance and release materials.

### Changed

- Reorganize documentation around setup, reproducible examples and implementation details; require Python 3.11+ for the Harness.
- Vendor Monaco 0.52.2 locally, preserve its MIT license and verify pinned package and file hashes.
- Use scoped signed cookies for editor assets and an explicit token for API access.
- Keep uploads and run outputs in `state/`; source packages contain committed files only.
- Adopt AGPL-3.0-only for project-authored material and retain separate third-party and dataset licenses.

### Fixed

- Prefer source-preserving deterministic formula repairs inspired by Math Agent; reject mathematical drift, retain unsupported/ambiguous input, and carry bounded rejection feedback across model retries. Apply the same scope policy in Studio, the constrained planner and CLI, with policy hashes bound to resume identity.
- Clear stale PDF pages and compiler logs when the source changes, and keep Safari IME confirmation from executing command-palette actions.
- Use TeX lexical context for single-formula handoffs and reject candidates that consume or escape the existing closing delimiter.
- Isolate damaged task history and reject incomplete candidate bindings or malformed review decisions without server errors.
- Classify invalid reference totals as input errors before attempting table repair.
- Run the JavaScript behavior and LaTeX cleanup suites in CI alongside the existing Python regressions.
- Preserve the editor until the user adopts a reviewed candidate; reset failed controls and discard stale file or preview responses.
- Fix empty diff panels, stale comparisons, hidden collapse controls and preview resizing.
- Reject partial LaTeX parses and malformed checker input; handle missing dependencies without issuing repair requests.
- Validate table structure and complete numeric cells, size Decimal precision to the input, and record only actual edits.
- Preserve rejected candidates, original table rows, process exit codes and bounded response excerpts in reports.
- Remove embedded deployment credentials, private paths and an unlicensed textbook extract from distributed source and reachable history.

Historical runtime results remain in [validation records](docs/validation.md); previous media are listed in the [demo archive](docs/demo.md).
