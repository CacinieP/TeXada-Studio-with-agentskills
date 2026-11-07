# Pure-local MiniCPM repair: controlled follow-up

Measured 2026-11-08 Asia/Shanghai. **Decision: local execution is feasible;
default-model qualification is not established.** Keep the current defaults
unchanged by this PR. Prefer deterministic syntax patches first and retain the
source-preservation gate around any experimental model candidate.

## Actual environment and scope

- Authorized Mac Studio: Apple M5 Max, 64 GiB memory. This identifies the actual
  measurement host; it does not establish performance on the user's other Macs
  or RTX 5070 Ti.
- llama.cpp 0.7.0, build 11669, commit 620d2225c; one slot, context 8192,
  loopback port 18149, requested GPU layers 99, reasoning off.
- MiniCPM-V4.7-35B-A3B Q4_K_M, 21,166,255,008-byte main GGUF,
  SHA-256 `9ecf91e814d7e9adc64325b1b65f8628a9b1bb8da4f61a92869ca7489bfd888e`,
  identical to the earlier archived 35B identity. No projector was loaded for
  this **text-only formula repair** experiment; no OCR claims follow from it.
- The device enumerates Apple Metal. Actual offloaded-layer count was not
  present in the captured startup log and is not inferred from the requested
  layer count. Startup until `model loaded` was approximately 14.11 s in one
  observation, not a cold-cache loading benchmark.
- Temporary test service was stopped afterward. No pre-existing user service
  was stopped and no model default was changed.

See [runtime.json](runtime.json), phase identities and manifests for exact
fingerprints. The measurements use provider/evaluator code from PR #34 commit
`ba48e3eeda29b9cf991b1e389e1f548798879ebf`; the new delivery audit is a separate
post-processing policy check. Identical prompt/catalog/checker hashes were
preserved within each phase. Requests were sequential; this is not an isolated
hardware throughput benchmark.

## Controlled results

Phase one changed only the output cap (1024/4096). Phase two fixed 1024 and
changed only text/schema output mode. Each condition was repeated three times,
alternating condition order. Every run retained checker-only, Skill off/on,
temperature=0, seed=0, and at most two candidate attempts. No timeout increase.

| Phase / condition | HTTP attempts, both Skill arms | Strict candidate contract | Calculus syntax acceptance per repetition, off/on | Calculus source-policy allowance per repetition, off/on | Whole-repair P95, off/on |
| --- | ---: | ---: | --- | --- | --- |
| Budget: 1024, text | 66 | 66/66 | 5/7; 5/7 | 2/7; 2/7 | 2.850 / 2.809 s |
| Budget: 4096, text | 66 | 66/66 | 5/7; 5/7 | 2/7; 2/7 | 2.693 / 2.796 s |
| Format: 1024, text | 66 | 66/66 | 5/7; 5/7 | 2/7; 2/7 | 2.453 / 2.737 s |
| Format: 1024, JSON Schema | 66 | 66/66 | 5/7; 5/7 | 2/7; 2/7 | 2.678 / 2.663 s |

Total: **264 actual repair HTTP attempts**, zero timeouts, zero length finishes,
and at most 36 completion tokens per response. Request medians range from
0.359 to 0.412 s. Whole-repair medians range from 1.213 to 1.277 s; the maximum
observed whole repair was 3.102 s. Whole-repair timings include candidate
rechecks and retries, but exclude the cached initial check and service startup.
The initial experiment mixes startup/warm effects and repeated prefix caching;
these values do not substitute for a fresh 100-request warm latency validation.

All condition/repetition counts were identical. Larger output caps did not
improve the result and did not automatically cause longer generation: outputs
ended well before either cap. Schema mode also did not improve this catalog's
format success because text mode was already 100%. Do not infer that Schema
constraints are universally unnecessary or that these small latency differences
are statistically meaningful.

The three-case smoke catalog contains one initial RETRY input, S02 `a_+b`.
Every condition/arm returned it unchanged twice: syntax repair 0/1, with no
invented index. That is a sensible abstention-like candidate for underdetermined
source, although the strict contract has no explicit abstention field. The host
must retain the source and require human review. Five initially OK Calculus
inputs and two smoke controls did not call the model and never inflate the
repair-success count. Each condition has only **8 distinct RETRY inputs**;
repetitions do not create new independent cases.

## Why 5/7 is not delivery correctness

The separate audit applies the current `repair_blocker` and `assess_candidate`
rules to the real syntax-accepted outputs. It does not invent independent
semantic labels or replay the entire editor workflow.

| Case | Observed model behavior | Current delivery policy |
| --- | --- | --- |
| AC01-injected, AC04-injected | Deletes the final `+` | Reject: missing operand cannot authorize deleting an operator |
| AC03-injected | Places a closing brace after `a`, restoring the reference spelling | Reject conservatively: grouping position cannot be established by the allowed deterministic patch; this is not a claim that the proposed mathematics is incorrect |
| AC05-injected, AC06-injected | Closes the final denominator brace | Allowed by source-preservation policy; both exactly match the existing deterministic patch |
| AC02 original/injected | Preserves/restores interval-subscript notation | Current scalar checker rejects it; parser coverage and supported notation are a separate limitation |

Thus **2/7** syntax candidates survive the current policy, and those two offer
**zero additional allowed repairs beyond the existing deterministic path** on
this catalog. This does not prove the model has no utility on other inputs.
Independent semantic review remains pending; source-policy allowance is not a
mathematical correctness rate. References were never sent to the model.

The actual backend's schema behavior was also probed separately: a schema
required a sentinel string present only in the schema, while the user message
requested conflicting plain text. The returned object contained the required
sentinel. This is an observed conformance check, not a formula-quality test;
the single extra request is excluded from the 264 repair attempts. See
[schema-conformance.json](schema-conformance.json).

## Route and stopping decision

For additional **experimental** local repair work, use 35B-A3B Q4 through
llama.cpp, reasoning off, 1024-token cap, one slot. Keep Schema opt-in for
transport robustness. Use text-only serving for formula text; load the
appropriate projector only for the separate OCR/vision path. Do not repeat
the old 120-second Ollama experiment with a larger timeout as a capability fix.

MiniCPM5-1B/2B were not remeasured in this follow-up. Their earlier empty/
malformed responses and thinking-budget exhaustion are different failure types
from the now-working V4.7 local route. Earlier V4.7-1B Q4/F16 results are also
different checkpoints, not MiniCPM5 text-model results. Prompt/backend versions
differ, so no new controlled cross-model ranking is claimed here.

The [proposed acceptance gates](../../local-repair-controlled-validation.md)
remain: >=99% strict candidate contract over all HTTP attempts, >=95% checker
acceptance on a pre-adjudicated supported/recoverable set while reporting the
full set, >=99% independently reviewed semantic preservation with no invented
operands/indices, and warm whole-repair P95 <=5 s/P99 <=10 s with zero timeouts.
At least 100 distinct independent errors and separate warm/cold measurements
are required before qualification. This small repeated catalog cannot satisfy
those coverage or semantic requirements. **Stop this pilot with a negative
default-qualification decision; do not silently change the default model.**

## Reproduction and complete evidence

Use [the protocol commands](../../local-repair-controlled-validation.md) with
the exact model identity above and a new output directory. Run budget phase
first, then format phase at 1024. Preserve the three existing arms and inputs.

- [decision.json](decision.json): aggregate metrics and explicit non-approval.
- `budget/` and `format/`: identities, summaries, and 24 complete run directories,
  each with original manifest, JSONL traces, report, blank independent-review CSV,
  and post hoc delivery-policy audit. Original evidence files were not rewritten.
- [SHA256SUMS.json](SHA256SUMS.json): file digests for the archived evidence.

Validation: 49 relevant offline tests passed (21 provider, 24 existing evaluator,
3 matrix-summary accounting, 1 delivery-policy audit). Fixtures/tests are not
included in model measurements. All archived run manifests are complete and
their declared file digests were checked before aggregation.
