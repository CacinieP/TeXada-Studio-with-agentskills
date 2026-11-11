# OCR source regions in portable review reports (issue #24)

2026-11-11, macOS arm64 / Python 3.11. This is offline report integration on the
[original geometry fixture](../../../samples/ocr/source-regions-01/README.md),
not a fresh OCR run, automatic region detector or independent human review.

## Actual run and inspection

The real CLI ran the source-linked sample twice using a temporary copy:

- First: OK=1 / NEEDS_HUMAN=0, zero model calls; original PNG snapshotted by SHA256.
- Second: one matching node reused, zero model calls; a new SOURCE_REGION event
  retains the current input/context/revision binding.
- The temporary sample directory was then removed. `write_run_report` rebuilt
  the resumed report using only the journal and run-local source snapshot.

See [cli-results.json](cli-results.json), [state.jsonl](host-run/state.jsonl)
and the resulting [review report](host-run/report.md).

The report displays the original PNG once per source, links to a boxed full-page
SVG and a region zoom SVG, and shows operator coordinates and the original OCR
text. The linked previews were opened in local Chromium and visually checked:
the boxed view shows the known x+1 glyphs inside the fixture box, and the zoom
uses viewBox `3 5 27 9`. This checks rendering/geometry for the synthetic fixture,
not a person's semantic/image adjudication. The SVGs contain no script, remote
URL or embedded untrusted text; both reference the same local PNG.

## Evidence portability and failures

Move/share the **whole host-run directory**, including `sources/`. The SVGs are
intended to be opened directly as linked documents; renderers that load SVG as a
restricted image may suppress its linked PNG. The original PNG is also directly
linked/embedded in Markdown. These are vector views, not new raster crops or
`data.crop` evidence. Existing separate crop reports retain their behavior.

The PNG snapshot is read with a 24 MiB cap and checked against its content hash.
Report generation checks dimensions and region bounds again and permits only
content-addressed local source paths. Missing, altered or inconsistent snapshots
produce an explicit unavailable message with no preview links. A subsequent run
against a valid sample can restore a damaged cached snapshot or generated SVG.
Without a valid snapshot, offline regeneration cannot reconstruct the image.

## Tests and reproduction

172 harness tests, 37 OCR tests and 181 workbench tests pass locally (390 total).
Ten source-report tests cover actual event binding, first-run/resume, offline
rebuild after sample removal, directory moves, missing/changed source bytes,
cache restoration, traversal/remote paths, wrong dimensions, unfinished nodes,
fenced untrusted source text and deduplication of shared original images.

From repository root, using the project Python environment and a fresh state:

```bash
PYTHONPATH=harness python -m docforensics run \
  docs/evaluation-results/ocr-source-regions-01/reviewed --state state/region-report-repeat
PYTHONPATH=harness python -m docforensics run \
  docs/evaluation-results/ocr-source-regions-01/reviewed --state state/region-report-repeat
python -m unittest discover -s harness/tests -p test_source_report.py
```

Open `state/region-report-repeat/report.md`; retain its `sources/` folder.
Programmatic offline report rebuilding is exercised by `test_source_report.py`;
no new report-only CLI command is introduced.

`implementation.json` records the baseline and runtime implementation hashes;
`SHA256SUMS.json` covers this evidence directory. Model defaults and beta.3
artifacts are unchanged. #24 remains open for automatic region acquisition,
independent source correspondence checks and reliable confidence signals.
