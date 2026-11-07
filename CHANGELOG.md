# Changelog

## Unreleased

### Added

- Fourteen Studio documents, including nine original mathematics samples with extraction, syntax and context expectations.
- Twenty-seven checker cases, a casebook and reproducible evaluation reports.
- Formula Skill instruction loading, on/off comparison runs, per-candidate events and context-bound CLI resume.
- A continuous browser demo with real model waiting, candidate review, adoption, downloads and sample navigation; all narration uses one synthetic voice reference.
- `scripts/compile_studio_cases.py` to reproduce twelve archived compilation cases in a fresh output directory.
- Chinese and English setup guides, troubleshooting, contribution guidance and release materials.
- Teaching sample `math-context.tex` (S14) recording comment, verbatim, listings and same-line display-math extraction boundaries, with an author reference repair.
- Context-scanning regressions in `webui/test_tex_context.py`: comment and verbatim extraction, escaped percent handling, display-math exclusion and span-limited candidate edits.

### Changed

- Scan TeX context before Studio checks: text after an unescaped `%`, verbatim-style environment bodies and same-line `$$` display regions no longer produce formula candidates or table audits. Table cells keep their literal content (`20%`-style formats still require human review).
- Accepted formula candidates now rewrite only their scannable span, leaving comment and display text with identical content untouched.
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
