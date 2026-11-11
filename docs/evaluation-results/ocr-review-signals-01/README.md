# OCR protocol signals → unified review bundle (issue #24)

2026-11-11, Python 3.11. These are **offline provider-protocol fixtures**, not
fresh OCR inference, independent human review or a confidence/accuracy benchmark.
Provider bodies and token counters are simulated. No socket or model request
was sent; urllib was replaced with an in-memory fixture transport.

The dedicated OCR CLI previously treated nonempty content as OK regardless of
backend truncation or a literal non-text sentinel. This run exercises the fixed
extractor and the real conversion CLI. Every case includes synthetic accept
line decisions, demonstrating that line acceptance does not override a blocked
extraction record. The operator label explicitly identifies a synthetic test.

| Fixture | Extraction / conversion | Layout |
| --- | --- | --- |
| OpenAI stop with complete content | 0 / 0 | Created for ordinary candidate review |
| Native Ollama done=true | 0 / 0 | Created for ordinary candidate review |
| Complete long output with only raw excerpt clipping | 0 / 0 | Created; excerpt clipping is not generation truncation |
| OpenAI finish_reason=length | 1 / 1 | Blocked; partial text diagnostic only |
| Native Ollama done=false | 1 / 1 | Blocked |
| Non-text marker mixed with ordinary text | 1 / 1 | Blocked; marker line retained in review_items |
| Replacement character | 1 / 1 | Blocked; affected line retained |
| Missing completion metadata | 1 / 1 | Blocked; completeness unconfirmed |
| Raw vertical-tab control | 1 / 1 | Blocked before normalization could erase the signal |
| Explicit refusal with null content | 1 / 1 | Blocked without malformed-shape crash |

Full outcomes and runtime hashes: [run/manifest.json](run/manifest.json).
Each case directory contains its provider fixture, emitted record, synthetic
review decisions and resulting conversion bundle. Examples:

- [Truncated extraction](run/length/record.json) → [pending review](run/length/bundle/review.json)
- [Mixed non-text pending list](run/non_text/bundle/review.json)
- [Long, complete candidate](run/excerpt_only/record.json) → [reviewed text layout](run/excerpt_only/bundle/layout.json)

The three created layouts are successful **fixture contract conversions**, not
proof that OCR text is correct or has been independently reviewed. Text node
pass-through would not be mathematical/OCR validation. The source image is the
project's original small glyph fixture, used only as bounded input bytes; the
simulated provider text is not claimed to be its transcription.

## Tests and reproduction

52 OCR tests, 172 harness tests and 181 workbench tests pass locally (405 total).
Fifteen new signal tests cover both transports, refusal, unknown completion,
non-text sentinels, raw controls, U+FFFD, bounds, malformed shapes/counters,
contradictory OK labels, diagnostic clipping and end-to-end review bundles.
Legacy archived OK records without the new metadata remain reviewable; a
response_truncated excerpt flag alone never blocks a complete candidate.

From repository root, use a fresh output directory and the project Python env:

```bash
python docs/evaluation-results/ocr-review-signals-01/reproduce.py state/review-signals-repeat
python -m unittest discover -s skills/doc-ocr-extract/tests -p 'test_*.py'
```

The script refuses to overwrite an existing directory. File digests are listed
in `SHA256SUMS.json`; implementation hashes are in the run manifest.
The full behavior contract is [REVIEW_SIGNALS.md](../../../skills/doc-ocr-extract/REVIEW_SIGNALS.md).
This change applies to the dedicated OCR extraction/conversion CLI; it does not
relabel Studio's separate VLM import observations or change model defaults.
#24 remains open for automatic region acquisition, independent image/semantic
adjudication and calibrated confidence signals. No release tag is moved here.
