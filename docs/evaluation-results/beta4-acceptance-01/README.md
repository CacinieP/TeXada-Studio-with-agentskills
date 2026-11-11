# beta.4 real end-to-end acceptance

2026-11-11. **Outcome: one original mixed-content page completed the real local
OCR → explicit review → CLI/report and Studio save/export paths, with failures
and operator edits preserved.** This is a smoke test, not an accuracy benchmark,
independent human adjudication or default-model qualification.

## Inputs, runtimes and scope

The [original page](../../../samples/ocr/beta4-acceptance/README.md) has body text,
two formulas and a deliberately wrong printed total: Alpha 12 + Beta 7, total 20.
The arithmetic sum is 19, but faithful OCR must preserve the printed 20.
The authored TeX, PDF, 150 dpi PNG and reference text geometry are retained.

[models.json](models.json) records actual host/backend identity and all model,
projector and draft hashes. Dedicated OCR uses MiniCPM-OCR F16 + DSpark at the
existing local service; Studio separately uses MiniCPM-V4.7-1B Q4 with its matching
projector and a task-owned local server. The compiled backend identifies itself
as 0.7.0-dev, commit a08ab75. These are different checkpoints/tasks, not a
controlled model ranking. Models were already installed; no weight download or
default model change was needed.

The dedicated service was already running when start was checked, so its
lifecycle was preserved. The source-test Studio launcher and its owned vision
process were terminated after UI verification. Session data remains outside the
repository; no session authorization, cloud credential or private user document
is included here. Installation/release validation occurs after the tagged build
and is linked from the release/PR as a separate stage.

## Dedicated CLI: actual recognition and review

- [request](cli-ocr/request.json), [response](cli-ocr/response.json),
  [record](cli-ocr/record.json), [transport hashes](cli-ocr/transport.json).
- One real local request used the explicit `minicpm-ocr` profile: official
  `Text Recognition:` prompt, image first, temperature .01/top_p .001/top_k 1/
  repeat_penalty 1.0 and 4096-token cap. Backend termination was stop; 114
  completion tokens were reported. One elapsed observation was about 6.62 s;
  it is not a warm/cold performance benchmark.
- The result has 13 lines, both formulas and all table values, including the
  printed error 20. Agent comparison to the authored source found formatting
  differences, with no numeric correction. This is not independent human review.
- The space-separated table cannot be treated as an explicit pipe grid. The
  [raw conversion](e2e/raw-table-blocked.json) correctly remains pending.
- A separate [reviewed record](e2e/reviewed-record.json) records four exact changes
  from spaces to pipe delimiters. The raw model record and raw_response remain
  unchanged. Record kind, original-record hash, before/after lines and agent
  identity make the normalization explicit; there are **zero numeric edits**.
- [Review plan](e2e/review-plan.json) boxes come from the authored PDF's reference
  geometry plus agent review, not model-detected regions or named-human labels.

The real [CLI first run and resume](e2e/cli-results.json) both return
`OK=9, NEEDS_HUMAN=1`. Seven OK nodes are text pass-through (`validated=false`),
two are syntax-checked formulas, and the table requires review because 20 differs
from 12+7. Ten nodes are reused on the second run. The fallback provider is the
empty fixture provider, not a repair model; repair HTTP request count is zero.
Replacing copied image bytes causes exit 2 before reuse; original bytes were
restored afterward. The [report](e2e/host-run/report.md) is explicitly rebuilt
for the last successful resumed run, not a successful report for the rejected
changed-image run. Source snapshots and static region previews are retained.

## Studio: actual import, failure, review and exports

Two actual V4.7 imports were performed: an instrumented production LocalRuntime
call and the browser's real image import. Both returned the same raw candidate:
[structured request/response](studio-v47/request.json),
[response](studio-v47/response.json), [UI candidate](studio-ui/raw-candidate.json).
The instrumentation delegates to the production transport; responses are not
simulated. Reasoning text is omitted, with character counts retained.

| Stage | Observation | Evidence |
| --- | --- | --- |
| Before adoption | OCR review dialog open; no user document created; requires_review=true | [dialog](studio-ui/ocr-review-dialog.png) and UI checks |
| Raw candidate compile | HTTP 200 with compile_ok=false; Too many }'s | [compile response](studio-ui/raw-compile.json) |
| Explicit syntax review | Remove model-added `<table>` and orphan `}` only; no numbers changed | [exact diff](studio-ui/syntax-review.json) |
| Adopt into new document | Reviewed candidate compiles to one page | [compile response](studio-ui/agent-reviewed-compile.json), [screen](studio-ui/adopted-compiled.png) |
| First table repair | Candidate 20→19 rejected; source keeps 20 | Stored job decision and [diff screen](studio-ui/table-candidate.png) |
| Second table repair | Explicitly accepted 20→19, saved, refreshed | [saved screen](studio-ui/saved-refreshed.png) |
| UI export | PDF and TeX downloaded; saved API content equals exported TeX; PDF text includes total 19 | [PDF](studio-ui/final-reviewed.pdf), [TeX](studio-ui/final-reviewed.tex), [checks](studio-ui/ui-checks.json) |

The original Studio output needs actual syntax review; it is not an automatically
usable LaTeX result. The later 20→19 change is an explicitly accepted arithmetic
repair, **not faithful transcription or an OCR correction claim**. Each of the
two table jobs reports zero model requests, consistent with deterministic table
repair. Job logs and both accept/reject records are stored under `studio-ui/`.
All UI actions were agent automation on the synthetic source; USER_ACCEPTED/
USER_REJECTED are application event labels, not proof of a named person's review.

An initial rejection assertion read the candidate before the asynchronous review
finished. The automation was corrected to wait for the completed hint, then
checked the original 20 and stored rejection. This timing correction is recorded
separately from the genuine raw-candidate compilation failure.

## Verification and reproduction

587 local Python tests pass: harness 172, workbench 181, scripts 82, desktop 19,
LaTeX cleanup 77, OCR 56. Four JavaScript suites pass. [verification.json](verification.json)
records those software checks; they are not model accuracy counts.
The app build number is 4. Tagged signed/notarized DMG validation and final
release assets are recorded separately in the publishing PR and GitHub Release.
The first PR bundle run passed Apple notarization but failed while fetching the
staple ticket (NSURLErrorDomain -1005, exit 68). The release workflow now uses a
shared bounded helper for staple and validate: only exit 68 is retried (three
attempts, 20 seconds apart), while permanent failures remain failures. Four new
desktop tests cover this behavior; the desktop suite was rerun after that fix.

Real capture/replay entry points (run from repo root with the project Python env):

```bash
python docs/evaluation-results/beta4-acceptance-01/run_cli_ocr.py --output state/beta4-cli-new
python docs/evaluation-results/beta4-acceptance-01/run_review_chain.py --record state/beta4-cli-new/record.json --output state/beta4-review-new
python docs/evaluation-results/beta4-acceptance-01/run_studio_import.py --output state/beta4-studio-new
```

The OCR script needs an already running local MiniCPM-OCR service. The Studio
probe needs the explicit local V4.7 service at port 18148. Review-chain replay
uses --record when supplied, otherwise the archived OCR result, and makes no
model requests. It is deliberately scoped to this page's verified line layout;
a different transcription requires renewed source review rather than guessed
line/region mapping. The compile and
UI-archive helpers require the task's isolated Studio state through --state-dir;
no state/session file is published. Commands refuse to overwrite new-run output
directories where applicable. Never relabel an unreviewed model candidate as an
independent human result.

Compiler log state-path prefixes are redacted. Model request/response parameters
and source image bytes are original synthetic public material; authentication
headers are not recorded. `SHA256SUMS.json` covers the evidence and source files;
[implementation.json](implementation.json) identifies baseline/runtime hashes.
Automatic OCR region acquisition, independent source correspondence and quality
validation remain tracked in #24/#23; these smoke observations do not close them.
