# Objective OCR review signals

The extraction CLI returns transcription candidates, never a confidence score
or a final document. This contract adds **observable protocol/text signals** so
partial or suspect output cannot silently take the successful `lines` path.
It does not estimate OCR accuracy or determine mathematical/image correctness.

## Completion and diagnostic contract

For OpenAI-compatible responses, `finish_reason=stop` confirms termination;
`length` is incomplete. Refusal/content-filter responses are blocked. Missing
or other finish reasons leave completion unconfirmed and require review.
For native Ollama, `done=true` with `done_reason=stop` or no done_reason confirms
termination; `done=false` or `done_reason=length` is incomplete. Other/missing
completion state requires review. New requests to backends that omit this
metadata therefore no longer silently return successful text.

Success remains `status=OK`, `lines=[...]`, with `output_complete=true` and an
empty `review_items`. It still requires the normal image comparison and explicit
review decisions before layout conversion. Optional counters are nonnegative
integers or null; malformed optional usage data does not crash parsing.
Malformed required response structures remain `NEEDS_ENV`.

Flagged output is `NEEDS_HUMAN` with `reason`, structured `review_items` and
bounded `candidate_lines` for diagnostics, **without success-path `lines`**.
`scope=line` uses 1-based indexes in the normalized nonblank candidate lines;
line diagnostics include a bounded text excerpt. The original record retains
candidate text for inspection. Record-level signals apply to the whole result.

| Reason | Observable trigger | Disposition |
| --- | --- | --- |
| `incomplete_output` | Backend length finish or native done=false | Do not adopt the partial text |
| `completion_unconfirmed` | Missing/unrecognized completion metadata | Check backend contract or re-extract |
| `refused_output` | Explicit refusal or content_filter | No transcription success claim |
| `no_text` | No nonblank text lines | Human review / different source |
| `non_text_marker` | Whole normalized line equals `[Non-text]` or `[No text]`, case-insensitive | Preserve the marker and require review, including mixed text/marker responses |
| `replacement_character` | U+FFFD in a line | Inspect that line against the source |
| `control_character` | C0 other than tab/CR/LF, or DEL, in raw output | Inspect before normalization can erase the character |
| `text_limits_exceeded` | Over 4096 lines or 32768 characters in a line | Do not turn a bounded prefix into a complete candidate |

Only whole-line bracketed sentinels are recognized; an ordinary sentence that
mentions a marker is not automatically rejected. These signals can occur in
literal source text too: review is required, not a claim that the model is wrong.
No repeated-character, language, mathematical or layout confidence heuristic is
introduced. No reasoning text, confidence score or model quality ranking is
persisted by this change.

Three flags mean different things:

| Field | Meaning |
| --- | --- |
| `output_complete` | Backend termination: true / false / null (unknown). This is not correctness or coverage. |
| `response_truncated` | Only the stored raw_response excerpt exceeded 1024 characters. Full complete lines may still be valid candidates. |
| `candidate_lines_truncated` | Diagnostic candidate_lines were bounded by the line/count limits; appears on flagged results. Never a success prefix. |

## Unified conversion review bundle

`ocr_to_layout.py` carries the source `reason` into `ocr_reason`, copies bounded
line/record review items, and retains a bounded `diagnostic_excerpt`. It never
creates layout.json for these records, even when a review file accepts every
line. A contradictory `status=OK` does not override nonempty review_items,
an incomplete/unconfirmed output_complete, backend length/filter termination,
or clipped diagnostic candidate_lines. Invalid signal schema
is an input error. Additional purported confidence fields are not forwarded.

Resolve the cause by re-extraction or a separate, explicitly verified corrected
transcript with retained original evidence; do not erase flags or relabel a
partial record as successful. A line-review decision is not permission to infer
missing text or claim that a truncated result is complete.

Legacy archived `OK` records without the new completion/signal fields remain
reviewable under the original hash-bound decision gate. A legacy
`response_truncated=true` by itself never blocks conversion: it referred only
to the logging excerpt. The change applies to the dedicated OCR CLI, not a new
claim about Studio's separate local VLM import path.

Validation fixtures and extract→review-bundle observations are archived in
`docs/evaluation-results/ocr-review-signals-01/`. They simulate provider protocol
responses and are not fresh model inference or independent human adjudication.
