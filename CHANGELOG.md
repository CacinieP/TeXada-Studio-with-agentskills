# Changelog

## Unreleased

## 0.2.0-beta.4 — 2026-11-11

### Added

- Convert explicitly reviewed OCR lines into formula/table/text layouts with source hashes, pending-item blocking and resumable CLI checks.
- Bind operator-provided pixel regions to original PNG bytes, and retain source snapshots, annotated/zoom previews and original transcription in portable review reports.
- Route truncated, unconfirmed, refused, non-text and suspect-character OCR output into structured review items without inventing confidence scores.
- Offer an explicit `--profile minicpm-ocr` for official recognition prompts/decoding, while retaining generic transport defaults.
- Archive a real local dedicated-OCR and separate Studio V4.7 smoke run on an original mixed-content page, including manual formatting/syntax review, rejected/accepted table repair, source-change blocking and exports.

### Distribution and validation

- Set the macOS app build number to 4; short version remains 0.2.0.
- 583 local Python tests and four JavaScript suites pass. Full observations and limitations: [beta.4 acceptance](docs/evaluation-results/beta4-acceptance-01/README.md). One synthetic page and agent review do not establish OCR accuracy or independent human adjudication.

## Earlier development log

### Fixed

- Keep a failed Tectonic run in the preview and repair logs when its output is not valid text for the process locale. Non-UTF-8 bytes are replaced instead of aborting the request with `UnicodeDecodeError` or HTTP 500.
- Point the self-contained macOS app at `AppIcon.icns`. py2app left `CFBundleIconFile` on `PythonApplet`, so Finder showed the default applet icon.
- Re-sign the self-contained app after the icon plist edit. Changing `Info.plist` invalidated the py2app signature, so `codesign --verify --deep --strict` failed on a fresh build.

### Added

- Produce a notarized DMG in CI when signing secrets are configured: the bundle workflow imports a Developer ID Application certificate into a temporary keychain, signs the app with a hardened runtime and timestamp, notarizes and staples it, then builds/signs/notarizes/staples a UDZO disk image (with an /Applications symlink) and gates it through `spctl`; without secrets it falls back to the unsigned zip artifact.
- Add a CI build for the self-contained desktop app: a macOS arm64 workflow installs the pinned Tectonic release and Poppler, prepares the TeX cache, runs `desktop/build_bundle.py`, smoke-tests the bundle in an isolated environment (stripped PATH/HOME, offline compile against the bundled cache), then uploads a ditto-zipped artifact with a SHA256 checksum.
- Ship a fully self-contained macOS app: `desktop/build_bundle.py` freezes the Python runtime, server dependencies, Tectonic, the TeX resource cache and Poppler (with a hand-rolled dylib collector that rewrites load commands and re-signs ad hoc) into one `TeXada Studio.app`; the backend runs as an in-process thread so quitting the window leaves nothing behind. License audit for every bundled component ships as `desktop/licenses-audit.md`.
- Add PDF page-splitting OCR import: the import dialog gains a start-page field, the review dialog lists per-page candidates that can be excluded or split into one document per page, and a continuation button batches the remaining pages of long PDFs.
- Add one-click Poppler install (macOS): a second settings-dialog button and `tool_fetch.install_poppler` drive `brew install poppler` explicitly, mirroring the pinned Tectonic bootstrap.
- Add an optional macOS desktop shell: a locally generated `TeXada Studio.app` opens the private entry in its own WKWebView window, reuses a running session or starts (and cleanly reclaims) its own backend, with orphan detection so a force-killed window never leaves a stray server behind.
- Add one-click Tectonic bootstrap: a settings-dialog button and `scripts/install_local_tools.py` download the pinned official release (`tectonic@0.17.0`), verify its SHA256, install to `~/.texada/bin`, and make it available to a running session without restart; the launcher prepends that directory to PATH.
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

- Restructure both READMEs for end users: add a consolidated Configuration section (model service with an Ollama reuse example, optional tools and TeX cache, editor preferences and local data) and move scanner boundaries, packaging and historical-material links into the documentation index and local guide.
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

## Local 35B profile and experiment archive (2026-11-08)

- Keep the current mainline editor, guarded OCR importer and revision-bound review flow; do not restore the obsolete Cline UI.
- Default local profile to verified MiniCPM-V 4.7 35B-A3B Q4_K_M, loopback port 18147; preserve saved/manual settings. Update auto-launch weight selection and document memory requirements.
- Preserve standalone MiniCPM-OCR candidate CLI, OpenAI-compatible transport, original synthetic OCR samples and historical three-variant evidence. Old-branch results do not validate the newer mainline repair implementation.

- Support explicit local profiles for both model sizes: default 35b-q4, optional 1b-f16 / 1b-q4, with variant-specific GGUF selection and isolated projector directories; preserve explicit server settings. Launcher regression: 20 tests passed.
