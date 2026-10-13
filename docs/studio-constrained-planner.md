# Studio constrained planner experiment

The Studio sidebar has an independent **受限 Agent 规划** checkbox, initially
unchecked. `/api/studio/fix` accepts `planner_mode: true` as an explicit per-job
choice. Omission keeps the existing fixed workflow. The choice is frozen and
persisted before the background job starts; historical jobs retain their mode.
The configured MiniCPM checkpoint selects each action through the same provider
and credential environment as formula repair. No extra planning model is used.

Python extracts existing inline text-formula nodes and one document-level table
audit node. This is the existing restricted text parser, not OCR or complete TeX
parsing. The model receives node IDs, kinds, checker states and a host-generated
action mask. It can choose `check-formula`, `check-table`, `propose-repair`, or
`request-human`. Every decision must echo the exact current `state_rev`, refer to
one listed node, and supply the exact parameter schema. Check and repair params
are empty; human requests carry one bounded reason. There is no apply, code,
shell, import, file, or arbitrary tool action.

Checks and candidates are host callbacks. Only a `RETRY` formula can reach the
text repair provider; each candidate must pass the syntax checker and has at
most two attempts. Environment failures mask repairs and request human help.
Simple numeric total candidates come from the existing Decimal checker, without
a model repair request. A table containing an unsupported problem goes to human
review rather than partly treating uncertain cells as known source values.
The result derives remaining problems from these host outcomes rather than
re-running unchosen checks after a refusal or budget exhaustion.
Candidate edits are bound to the source offsets and original text, assembled in
a separate diff buffer, and never written to the original source. Syntax
acceptance still does not establish mathematical meaning or human adoption.

A job permits at most 12 decisions, 12 reserved model HTTP calls, and a 240-second
planning window. Planner calls and formula repair calls share this budget. A
failed attempt consumes its reservation. HTTP calls use the remaining window
(up to 120 seconds per request); the existing local checker has its own bounded
subprocess timeout. The host stops starting new actions when time expires. All
unresolved nodes become visible human requests. Actual HTTP attempts are counted
separately from reservations, so an offline test fixture does not claim inference.

The persisted job trace contains `PLANNER_PROPOSED`, `PLANNER_REJECTED`,
`PLANNER_EXECUTED`, provider results, candidate checks, and human requests. Unknown
actions, stale revisions, wrong nodes, masked actions, bad params and exhausted
budgets cannot reach checker/repair callbacks. `PLANNER_END` preserves node
outcomes, counts and budget settings; the downloadable Studio report includes
the trace. The experiment remains disabled by default and carries no quality or
latency improvement claim.

Run a paired comparison over five fixed public synthetic cases:

```sh
python scripts/evaluate_studio_planner.py --provider fixture --output work/planner-paired.json
# Optional actual model calls, using the operator's authorized VLM_* environment:
python scripts/evaluate_studio_planner.py --provider live --output work/planner-live-paired.json
```

Each case runs the fixed and planner arms on identical source text, reporting
checker completion, illegal/rejected actions, actual calls, reservations and
elapsed time. The default fixture comparison verifies routing only; live runs
are tagged separately. Unsupported table cases deliberately retain the source.
No compiler, private document or image is involved. These cases do not measure
semantic correctness, establish a general completion rate, or justify enabling
the experiment by default.
