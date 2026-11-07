# Current-mainline integration acceptance — 2026-11-08

Cline's branch was behind mainline `181ee92`. Integration retains the complete
mainline editor, PNG/JPEG/WebP/PDF importer, local settings, deterministic
preservation checks, revision-bound candidate decisions, desktop packaging and
existing CI. The obsolete PNG-only API and old editor modifications are removed.
The standalone MiniCPM-OCR CLI, synthetic source and historical measurements
remain available without replacing the mainline importer.

## Default model

The current local runtime, direct provider, CLI, settings placeholder and owned
weight lookup use `minicpm-v4.7-35b-a3b-q4` / the 35B-A3B Q4 GGUF. Direct local
requests default to `http://127.0.0.1:18147/v1`; the existing owned-process launcher
still chooses its configured port. Saved and explicit model choices are kept.
Both accepted MiniCPM alias spellings receive the current JSON/thinking
configuration. The explicitly selected legacy 1B cloud profile is unchanged;
it is not the local default.

## Verification

- **473 Python tests passed**: harness 123, Web/API 176, scripts 71, desktop 12,
  LaTeX cleanup 77, standalone OCR 14.
- Four JavaScript suites passed: Studio race/review/OCR behavior, LaTeX language,
  document templates and math audit (37 assertions).
- Native current `/api/studio/probe` confirmed the configured 35B model exists.
  The current `/api/studio/import` processed the original synthetic PNG, returned
  a review-required candidate and did not create a document automatically. Its
  generated text includes Markdown/HTML constructs despite the LaTeX prompt;
  this is an observed candidate defect and requires human editing before use.
  No compile-correctness or transcription-accuracy claim is made.
- The current local provider made a real bounded formula request and returned a
  JSON candidate. Current-provider fingerprints and the response are preserved.
- A fresh actual-model run against the merged provider on the same 12-case
  research catalog again produced syntax-pass candidates for **5 of 7**
  checker-rejected inputs in both Skill arms. The remaining five catalog inputs
  were initially parseable and never invoked the model. Semantic review remains
  pending; the missing-subscript smoke input remained unresolved.
- Complete-run manifest hashes were checked; code/catalog fingerprints were
  stable within the new runs. Weights and projector are the already SHA-verified
  local files from the earlier comparison.

See [regression summary](regression.json), [native API evidence](native-api-acceptance.json)
and `model-probe/` for the fresh current-code traces. Earlier 1B/35B comparisons
remain historical and are not substituted for these current-mainline checks.
No new desktop DMG or Release was produced by this integration.
