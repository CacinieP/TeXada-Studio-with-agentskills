# Original source-region geometry fixture

`generate.py` draws small bitmap glyphs for `x+1` using only Python's standard
library and writes the source PNG, OCR-shaped text fixture and hash-bound review.
This is an original deterministic geometry fixture, **not an OCR result,
automatic region detection or independently human-reviewed annotation**. The
reviewer label explicitly identifies a synthetic rendering fixture.

Coordinates `[3,5,30,14]` are derived from the known glyph placement and padding.
They use raw top-left pixels with exclusive right/bottom bounds. The source
image is 40×20 grayscale PNG; no font or model is needed.

From repository root, select fresh output/state directories:

```bash
python samples/ocr/source-regions-01/generate.py state/region-fixture-input
python skills/doc-ocr-extract/scripts/ocr_to_layout.py \
  state/region-fixture-input/record.json \
  --review state/region-fixture-input/fixture-review.json \
  --source-image state/region-fixture-input/source.png \
  --doc source-region-fixture --output-dir state/region-fixture-reviewed
PYTHONPATH=harness python -m docforensics run state/region-fixture-reviewed --state state/region-check
PYTHONPATH=harness python -m docforensics run state/region-fixture-reviewed --state state/region-check
```

Expected: OK=1 / NEEDS_HUMAN=0; second run reuses one node, no model calls.
Replacing the copied `source.png` must fail the next run before any reuse.
See `docs/evaluation-results/ocr-source-regions-01/` for archived observations.
This feature preserves whole-source identity and explicit coordinates; it does
not create cropped `data.crop` evidence or add report thumbnails.
