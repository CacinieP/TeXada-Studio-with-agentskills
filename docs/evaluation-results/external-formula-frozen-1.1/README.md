# Frozen Skill 1.1 on externally reported inputs

Measured 2026-11-08 Asia/Shanghai. **No additional delivered repair was observed
over the deterministic baseline.** This follow-up does not establish an
independent mathematical-accuracy or natural-error generalization benefit for
Skill 1.1. It narrows the earlier positive result to candidate preservation in
the small development/transfer pilot.

## Frozen setup and source sample

Skill 1.1 was frozen at commit `5e6cba0c787907de23e28053f21acb487682c6cd`, hash
`905b9f5977d8df8c68a21b290c76763b451c2dbdf89d1937084775ad92d76d5c`.
No Skill, base prompt, checker, source-preservation gate or default model was
changed in response to this evaluation. The prior local 35B-A3B Q4 weight was
rehashed; runtime identity is in [runtime.json](runtime.json).

The fixed set contains **16 externally reported formula excerpts**: 9 KaTeX
issues, 5 SymPy issues and 2 TeX Stack Exchange questions, all predating this
Skill revision. No new errors were injected. Formula extraction, the small
normalizations, source links, timestamps/body/formula hashes, and attribution
are in [provenance.json](provenance.json). Whole discussions and environment
dumps are not redistributed. Source-specific rights notices remain attached.

This is a search-derived convenience sample of reported parsing/rendering or
semantic problems. It is independent of this iteration's Skill examples, but
not a random or balanced natural-OCR benchmark. Some inputs are valid notation
that a renderer/parser did not support, rather than author mistakes. No claim
is made that the model had not encountered public sources during pretraining.
All 16 selected inputs were retained regardless of checker outcome.

The protocol was recorded [before model execution](../../external-formula-evaluation-protocol.md).
The model received only the observed formula and host feedback; source-derived
categories and reference corrections were not sent to it.

## Actual host-pipeline results

All three arms ran through the existing `pipeline.process_formula`, with arm
order rotated per case. Unlike the preceding candidate-only experiment, this
run retains the production deterministic prefilter, fallback eligibility,
source-preservation gate, feedback and repeated-candidate stop. The isolated
local backend used one slot, context 8192, reasoning off, temperature=0,
seed=0 and max_tokens=1024.

| Arm | Inputs | Initially parsed and preserved | Human-review terminal | Delivered repairs | Actual model HTTP attempts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Deterministic-only | 16 | 8 | 8 | 0 | 0 |
| Same host + Skill 1.0 | 16 | 8 | 8 | 0 | 4 |
| Same host + Skill 1.1 | 16 | 8 | 8 | 0 | 4 |

There are **48 actual pipeline observations and 8 actual model attempts**,
not 48 model inferences. Final formula text is identical across all arms for
every case. The deterministic arm uses an explicit empty fixture provider as
its no-model fallback; those fixture accesses are never counted as inference.

Only K2612 (`f^{*}'`) and S19075 (`\lambda = v\ T`) reached model fallback.
Six other initial RETRY inputs were intercepted by the existing unsupported
command/structure or extra-closing-brace rules. The eight initially parseable
inputs skipped the model. The sample therefore provides very little exposure
to model fallback and contains no confirmed supported, unambiguously
recoverable positive subset on which to estimate repair recall.

Both model versions still proposed at least one unauthorized change to K2612.
The old Skill also proposed replacing an explicit TeX space in S19075 with a
different spacing command; the new Skill retained the original there. All
unaccepted proposals remained rejected evidence and the original was retained.
This is a small candidate-behavior observation, not a demonstrated delivered
repair benefit or statistically reliable superiority claim.

## Findings that constrain the conclusion

1. **Syntax OK remains a weak signal.** K95 (`a^b^c`) is initially accepted by
   the current SymPy checker, although the original KaTeX issue reports the
   grouping problem. The host preserves it without model involvement. Historical
   SymPy reports about constants, implicit multiplication and fraction parsing
   likewise cannot be declared semantically correct just because this checker
   accepts their text. Some historical bugs may already be fixed; that requires
   separate semantic verification.
2. **Genuine mistakes can coincide with unsupported notation.** KaTeX #138
   includes a missing final brace and an `\over` compatibility issue. The source
   comment documents the missing brace, but the current host does not support
   the `\over` structure, so neither Skill can deliver that repair. Do not
   normalize it into `\frac` merely to manufacture a positive test.
3. **A source may not establish a unique grouping.** TeX question #75331 has
   answers placing the missing square-root closer at different boundaries.
   That source does not justify selecting a single mathematical target after
   observing model output. It remains a review case; the full chained relation
   is also outside the current scalar-host coverage.
4. **The external sample is not a repair-success benchmark.** A zero delivered
   repair count on these 16 inputs is measured yield, not 0% mathematical
   accuracy. With no independently adjudicated recoverable positive subset,
   neither recall nor the semantic four-way score can be computed honestly.

## Semantic review remains open

[guarded/blind-review.csv](guarded/blind-review.csv) contains 48 arm-hidden rows,
with source links and unchanged empty review fields. It is a **prepared review
packet**, not a completed blind review. Identical outputs are recognizable;
only arm labels are hidden. The task author has seen the Skill and cannot claim
independent review. [decision.json](decision.json) therefore leaves safe-repair,
justified-deferral, incorrect-repair and missed-recoverable-repair semantic
counts pending, along with semantic accuracy. Provisional source categories
are kept outside model input and are not ground truth labels.

The next meaningful qualification step is independent source adjudication and
a separately collected set of real, supported, recoverable mistakes. Checker
coverage/false acceptance should be evaluated separately from prompt changes.
Keep Skill 1.1 frozen for that next test; do not tune it against this set. The
earlier default-model qualification remains unproven.

## Reproduce and audit

Start the same isolated local service on port 18149 and prepare the old-Skill
root as described in the [Skill comparison](../formula-skill-1.1-local/README.md).

```sh
NO_PROXY=127.0.0.1,localhost,::1 python scripts/evaluate_external_formulas.py \
  --cases samples/research/external_issue_cases.json \
  --baseline-root work/old-skill --candidate-root skills \
  --outdir work/new-external-validation
```

`guarded/manifest.json` binds frozen inputs/implementation/Skill identities and
all run artifacts. Append-only journals preserve checks, rejected candidates,
source-scope decisions and terminal states. Archive digests are in
[SHA256SUMS.json](SHA256SUMS.json). The temporary service was stopped after
measurement. Two focused tests cover reference-label exclusion and the host's
no-model behavior on blocked source, alongside existing provider/evaluator
regressions. No production or Skill code was altered by this follow-up.
