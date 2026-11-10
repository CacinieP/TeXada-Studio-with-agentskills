# Formula Skill 1.1: fewer unauthorized proposals

Measured 2026-11-08 Asia/Shanghai. Updating the Skill body reduced inputs with
source-policy-violating candidates from **7/15 to 1/15**, while retaining all
**5 source-policy-allowed syntax repairs**. This is an improvement in candidate
preservation behavior, not an independently measured mathematical accuracy gain.
The remaining failure is retained in the evidence. No model default, checker or
host source-preservation rule was relaxed.

## Ideas transferred from TeXada Math Agent

The inspected upstream revision is
[`01081290d29b14347b1145bef1f4064a2bff8daa`](https://github.com/CacinieP/TeXada-the-Math-Agent/tree/01081290d29b14347b1145bef1f4064a2bff8daa).

| Upstream idea | Application in this revision |
| --- | --- |
| [Deterministic repair service](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/01081290d29b14347b1145bef1f4064a2bff8daa/src/texada/core/repair.py): repair is a local tool, not a model role | Keep deterministic patches first; use the model only to propose a reviewable candidate |
| [Mutation scope](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/01081290d29b14347b1145bef1f4064a2bff8daa/src/texada/agent/mutation_scope.py): unreliable structural evidence requires review | Return unchanged source for missing operands, extra closers and ambiguous interior grouping |
| [Planner projection](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/01081290d29b14347b1145bef1f4064a2bff8daa/docs/adr/012-planner-projection.md): host state is authoritative; model observation is bounded | Keep model-facing instructions focused on edit decisions; move scanner/transport/editor details to a reference |
| [Fixer](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/01081290d29b14347b1145bef1f4064a2bff8daa/src/texada/core/fixer.py): trailing closers are a narrow repair | Demonstrate a closing-only positive example and source-preserving negative examples; do not copy environment rewrites into the scalar host |

The runtime body is now 559 words / 3823 bytes, versus 886 words / 6430 bytes.
The revision adds an explicit unchanged-source response for abstention, orders
the content/coverage checks before syntax edits, and gives contrasting examples
for a trailing operator, missing index, trailing argument and ambiguous limit
grouping. It preserves the exact one-field JSON contract. The capability
metadata moves to 1.1.0 alongside the body; revision/version validation remains
enforced by the host. Reference material is not automatically added to the
repair prompt.

## Single-variable local comparison

Both snapshots used the same 35B-A3B Q4 weight, llama.cpp build
`b11669-620d2225c`, one slot, context 8192, reasoning off, temperature=0, seed=0,
text response format and 1024-token cap. The weight SHA-256 was rechecked and
matches the previous local experiment. Formula text serving did not load a
vision projector. See [runtime.json](runtime.json).

The baseline is the 1.0.0 body from Studio commit
`f99775864711f37a914ffdd867ad3bdbc5b48af4`. The candidate is the exact 1.1.0
snapshot archived here. The model/checker/provider were unchanged between the
two snapshots; only the loaded Skill instructions differed in the Skill-on
arms. Each run retained checker-only, Skill off and Skill on. The comparison
verified byte-identical no-Skill prompt hashes across the two snapshot roots.
Source references and policy labels were not sent to the model.

| Initial RETRY inputs | Baseline: inputs with any unauthorized candidate | Skill 1.1: inputs with any unauthorized candidate | Allowed syntax repairs, baseline / 1.1 |
| --- | ---: | ---: | ---: |
| Existing smoke | 0/1 | 0/1 | 0 / 0 |
| Existing Active Calculus | 4/7 | 1/7 | 2 / 2 |
| Additional synthetic transfer set | 3/7 | 0/7 | 3 / 3 |
| **Total** | **7/15** | **1/15** | **5 / 5** |

An input counts as conforming only if none of its model candidates violates
the current `assess_candidate` policy. On that limited definition, conformity
improved from **8/15 (53.3%) to 14/15 (93.3%)**. Unchanged source is a deferral,
not a repaired formula. The 5 allowed syntax repairs still require the usual
review and are not asserted to be independently semantically correct.

There were **82 real repair HTTP attempts** across all six three-arm runs:
38 for the baseline snapshot and 44 for the candidate. All 82 produced strict
candidate-contract outputs; there were no timeout/length failures. Skill-on
attempts increased from 19 to 25 because the research runner retries unchanged
unparseable source twice. Therefore this iteration does not claim a latency or
request-count improvement. The existing production repeated-candidate stop is
separate and was not changed or measured by this comparison.

## What changed, and what did not

- The model stopped deleting the trailing `+` in AC01/AC04 and stopped guessing
  the interior limit-group boundary in AC03. These now remain review items.
- In different synthetic expressions, H04's ambiguous group, H05's trailing
  operator and H07's extra closer also remain unchanged. The 3 valid syntax
  patches for the transfer set remain available.
- The candidate still tries to restore an interior brace in **AC02-injected**,
  a formula involving an interval subscript and chained relations. The scalar
  parser rejects that notation and the source policy does not authorize the
  proposal. Do not count it as success or remove it from the report.
- No new repair capability beyond the existing deterministic patches is
  established. The model-default qualification decision from the previous
  experiment remains negative/pending broader evidence.

This was **one greedy pass per snapshot**, baseline first, with a shared
no-Skill control. The additional synthetic set was authored during this Skill
revision, is not an independent held-out benchmark, and contains no verbatim
input from the Skill examples. Improvements on these categories are evidence
of local transfer, not generalization to natural OCR or arbitrary mathematics.
Independent semantic review remains pending; no confidence interval or broad
accuracy claim is made. Parser coverage and mathematically informed grouping
need separate work, not a looser acceptance gate.

## Reproduce and inspect

From the repository root, create an old-Skill root containing the baseline
snapshot and the unchanged checker, then start the same isolated local server:

```sh
mkdir -p work/old-skill/doc-formula-verify/scripts
cp docs/evaluation-results/formula-skill-1.1-local/snapshots/baseline-SKILL.md \
  work/old-skill/doc-formula-verify/SKILL.md
cp skills/doc-formula-verify/scripts/verify.py \
  work/old-skill/doc-formula-verify/scripts/verify.py
NO_PROXY=127.0.0.1,localhost,::1 python scripts/compare_formula_skills.py \
  --base http://127.0.0.1:18149 --model minicpm-v4.7-35b-a3b-q4 \
  --baseline-root work/old-skill --candidate-root skills \
  --outdir work/new-skill-comparison --repeats 1
```

- [decision.json](decision.json): separate input-level policy metrics, repair
  yield, deferrals and strict-output counts.
- [identity.json](identity.json): Skill/checker/program/catalog hashes and
  unchanged request settings; [summary.json](summary.json): per-run accounting.
- `snapshots/`: exact old/new Skill text. Six run directories preserve original
  complete manifests, bounded raw candidates, reports and blank review CSVs.
- [SHA256SUMS.json](SHA256SUMS.json): archive integrity checks. These do not
  turn policy decisions into independent semantic annotations.

The temporary server was stopped after the comparison. **67 relevant offline
tests passed**, covering Skill loading/version binding, the existing provider and
evaluation paths, explicit snapshot selection, and deferral-versus-repair
accounting. Original experiment evidence is retained unchanged.
