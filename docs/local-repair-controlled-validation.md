# Local MiniCPM repair validation

This is an experimental protocol for issue #30. It does not approve or change
the current model defaults. The historical 35B Q4 results (5/7 per Skill arm)
measure syntax acceptance, with semantic review pending. They precede mainline
preservation changes and are not measurements of the current implementation.

## Preferred next route

MiniCPM-V4.7-35B-A3B Q4_K_M, local llama.cpp OpenAI-compatible service,
reasoning explicitly disabled, one slot and sequential requests. Record the
exact backend version, weight SHA-256, chat template, startup/offload logs,
and hardware. Do not infer hardware from the model file size. MiniCPM5-1B/2B
text models and V4.7-1B are separate model families/variants.

The old 35B Ollama timeout and successful llama.cpp run changed backend,
scheduler state and thinking configuration together. They do not isolate the
cause. Quantization can change memory use and quality; increasing an HTTP
timeout cannot establish either model capability or mathematical correctness.

## Two sequential single-variable experiments

Freeze the repository revision and server settings. Install harness dependencies.
Use a non-thinking server/template; the V4.7 alias below also makes the provider
send `enable_thinking=false`. Confirm support in server logs, rather than
assuming an accepted HTTP request proves a flag was honored.

```sh
llama-server -m "$MODEL" --host 127.0.0.1 --port 18148 \
  -c 8192 -np 1 -ngl 99 --reasoning off \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --alias minicpm-v4.7-35b-a3b-q4
```

In another terminal, from this repository root:

```sh
python scripts/run_local_repair_control.py \
  --base http://127.0.0.1:18148 --model minicpm-v4.7-35b-a3b-q4 \
  --model-file "$MODEL" --backend-version "$(llama-server --version 2>&1)" \
  --reasoning-configuration 'server reasoning off; enable_thinking=false' \
  --phase budget --outdir work/local-budget-01
```

This compares 1024/4096 output tokens, three repetitions, alternating condition
order. Both fixed catalogs are reused: smoke includes S02 `a_+b`, and Active
Calculus has 12 inputs. The existing three-arm evaluation retains checker-only,
Skill off/on, temperature=0, seed=0, and at most two candidates per model arm.
Initially OK inputs skip the model and never count as model repair successes.

Only after examining budget results, fix the chosen budget and compare text
with requested strict JSON Schema decoding:

```sh
python scripts/run_local_repair_control.py \
  --base http://127.0.0.1:18148 --model minicpm-v4.7-35b-a3b-q4 \
  --model-file "$MODEL" --backend-version "$(llama-server --version 2>&1)" \
  --reasoning-configuration 'server reasoning off; enable_thinking=false' \
  --phase format --budget 1024 --outdir work/local-format-01
```

Change `--budget` only to the preselected value. Schema mode requests exactly
one nonempty string `latex`, with no additional properties. Unsupported-schema
HTTP errors stop the matrix; no unconstrained fallback is hidden. Independently
verify the backend actually enforces the schema. Constraints fix serialization,
not meaning. The option affects formula repair only, never planner schemas.

Do not change model, template, offload, context, Skill or concurrency inside
either phase. The two budgets/formats are the experiment variable; Skill is
the existing paired stratum. Three identical-seed repetitions check stability,
not independent evidence of generalization. Each cell makes at most 32 repair
HTTP attempts across both catalogs under the current checker expectations;
timeouts stop the matrix after preserving that run. HTTP timeout remains 120s.

## Evidence and limitations

Each run preserves manifests, raw bounded candidate traces, checker decisions
and blank blind-review CSVs. Summary validates their digests and rejects fixture,
incomplete or changed-code runs. It reports strict candidate-contract success
over **all HTTP attempts**, syntax acceptance over **all initial RETRY inputs**,
failure reasons, finish reasons, reasoning character counts and whole-arm
latency including retries/checking. It never reports semantic accuracy or
approves a default switch. Raw reasoning text is not stored.

Cold loading, GPU offload, queue time, TTFT and token throughput require server
logs or a separate streaming probe; nonstreaming elapsed time cannot separate
them. Save cold-start measurements separately. Existing background services
must be documented. Label the initial matrix as mixed startup/warm timing;
before latency acceptance, preload/warm the server and then collect at least
100 timed requests. Do not pool smoke and calculus ratios as independent cases.

S02 is underdetermined: without source context, inventing an index is a semantic
failure even if the checker accepts it. Preservation/manual review is the desired
product outcome. The research runner measures the candidate/checker contract,
not the newer editor's preservation gate. Test delivery behavior separately.
Parser-unsupported source notation (for example AV interval notation) remains
in the full-set report; pre-adjudicate a recoverable/supported subset before
computing a separate gate score. Never remove cases after seeing model output.

## Proposed acceptance gates (not measured achievements)

| Metric | Required evidence |
| --- | --- |
| Strict candidate contract | At least 99% over all HTTP attempts, including timeouts/truncation as failures |
| Syntax/checker acceptance | At least 95% of independently pre-adjudicated recoverable, supported inputs; also disclose full-set ratio |
| Semantic preservation | At least 99% of independently reviewed accepted outputs; zero invented operands/indices or dropped terms |
| Underdetermined cases | Preserve source and require human review, including S02 |
| Warm whole-repair latency | P95 <=5s and P99 <=10s including retries/checking, at least 100 requests, zero timeouts |
| Cold startup | Separately measured; proposed <=30s on the named supported machine |
| Coverage | Current fixed sets plus at least 100 distinct independent errors across documents; repeated runs do not increase distinct-case count |

These are operational gates, not statistical confidence claims. Independently
review all accepted outputs in the validation sample, disclose uncertain and
pending counts, compare the previous baseline on the same revision/protocol,
and separately verify the current editor's preservation/delivery decisions.
Use `evaluate_skills.py review` to import completed independent reviews. A
configured default and an evidence-qualified default are different statuses.

## Completed local follow-up

The earlier unavailable-endpoint observation was resolved by starting an
isolated temporary llama.cpp service on loopback port 18149 through the
authorized Mac Studio device. The completed measurements and explicit adoption
decision are in [the controlled follow-up](evaluation-results/local-repair-control-20261108/README.md).
The text-only repair experiment deliberately does not load the vision projector;
it is not an OCR measurement. Existing user services and model defaults are not
modified by these experiments.

Use `scripts/audit_repair_delivery.py --run-dir RUN --out NEW_JSON` to audit
syntax-accepted research outputs against the current source-preservation policy.
This validates the original evidence digests first, and does not rewrite it.
The policy audit is neither an independent semantic review nor a replay of the
whole editor workflow. In particular, a plausible restoration may be rejected
because its placement is underdetermined by the supplied source.
