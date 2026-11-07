# Frozen external-input follow-up

Skill 1.1 is frozen at Studio commit `5e6cba0c787907de23e28053f21acb487682c6cd`,
SHA-256 `905b9f5977d8df8c68a21b290c76763b451c2dbdf89d1937084775ad92d76d5c`.
Do not edit the Skill, provider prompt, checker or host gate based on this set.

## Source sample and limits

Use 16 source-reported formulas from public KaTeX/SymPy issues and two TeX
Stack Exchange questions, all predating the Skill revision. Extract formula
text without injecting new errors. Only remove outer math delimiters, decode
one host-language string-escape layer where needed, or remove a display-only
error underline. Record each exception, source URL, author attribution where
applicable, retrieval/body/formula hashes and source license/rights notice.
Do not republish whole discussions, personal metadata or environment dumps.

The search used public issue queries for parse_latex/parse errors/braces and
web discovery of user brace questions. This is a small convenience sample of
reported failures, not a random sample of natural OCR errors. It includes valid
notation that a backend rejected, parser semantic bugs and genuine grouping
errors. Do not relabel all these as malformed formulas. Retain all selected
cases regardless of the current checker result; report initially OK cases and
unsupported cases separately. The sample was not used to write Skill 1.1,
but exposure in the model's pretraining cannot be ruled out.

## Run the actual host first

Compare deterministic-only, host plus Skill 1.0, and host plus Skill 1.1 through
the existing `pipeline.process_formula`, rotating arm order by case. The actual
host decides whether fallback is eligible. Never force a model request merely
to make the model appear useful. The deterministic arm's missing fixture is an
explicit no-model baseline, not an inference measurement.

Use the same local 35B Q4 weight, backend, one slot, context 8192, reasoning off,
temperature=0, seed=0 and 1024-token cap. Preserve model-call counts, terminal
state, original/final text, reasons, timings and append-only journals. A failed
checker or unavailable service is an environment failure, not an incorrect formula.

If candidate-only diagnostic calls are added, label them as bypassing production
prefilters and report them separately from actual delivery. They cannot count
as application repairs. No default switch or timeout increase follows from this set.

## Adjudication and blinding

Source-derived categories and references are provisional and never sent to the
model. Some sources document incompatible grouping corrections, so do not pick
one post hoc to obtain a desired score. Keep such rows uncertain.

Produce an arm-hidden review CSV. Independent reviewers should classify outputs
as safe repair, justified deferral, incorrect repair, missed recoverable repair,
or uncertain, with a source-based reason and review identity. Initial syntax-OK
unchanged source is preservation, not repair success or proof of mathematical
truth. Unsupported cases and unknown truth do not enter a recoverable-repair
denominator. Publish coverage and uncertainty counts with any score.

The task author has seen Skill 1.1 and cannot honestly certify an independent
blind semantic review. Until another qualified reviewer completes the packet,
semantic accuracy and the four semantic-category totals remain pending. Report
measured pipeline behavior and provisional source findings, not invented labels.
