# beta.4 original real-OCR acceptance page

Original synthetic source, AGPL-3.0-only. No personal data or copied document.
It contains body text, two formulas and a table with **deliberately incorrect
printed total 20** (12 + 7 = 19). Transcription must preserve 20; changing it to
19 belongs to a later explicit arithmetic repair decision.

- `source.tex`: authored reference.
- `source.pdf`: Tectonic render used in this run.
- `page.png`: 150 dpi source image.
- `geometry.xhtml`: `pdftotext` reference geometry used for agent-provided review
  boxes; these are not automatically detected OCR regions or independent human
  annotations.

Regenerate in a fresh copy/directory using existing tools:

```bash
tectonic --untrusted --only-cached source.tex
pdftoppm -png -r 150 -singlefile source.pdf page
pdftotext -bbox-layout source.pdf geometry.xhtml
```

Real CLI, Studio and review observations are archived under
`docs/evaluation-results/beta4-acceptance-01/`. Model identity, raw candidates,
explicit normalizations and failure cases are retained separately. The sample
is a single-page smoke test, not a quality/accuracy qualification dataset.
