# Table repair pilot 01 (issue #25)

Recorded 2026-11-10 (Asia/Shanghai). Synthetic contract cases from
[`samples/research/table_repair_cases.json`](../../../samples/research/table_repair_cases.json).
Host acceptance requires both `doc-table-audit` and `assess_table_candidate`.
This is not a semantic-accuracy benchmark.

## Arms

| Arm | Model | Skill | TR01–TR03 authorized repairs | TR04 outcome | Notes |
| --- | --- | --- | ---: | --- | --- |
| [`minicpm-v47-off`](minicpm-v47-off/report.md) | `openbmb/minicpm-v4.7:latest` | off | 3 / 3 | repaired total (authorized), not data mutation | 1 call each |
| [`minicpm-v47-on`](minicpm-v47-on/report.md) | same | on | 3 / 3 | same authorized total repair | Skill body loaded |
| [`minicpm5-1b-off`](minicpm5-1b-off/report.md) | `texada-minicpm5-1b:baseline` | off | 0 / 3 | no candidate | `incomplete_response` ×2 |
| [`minicpm5-1b-off-2048`](minicpm5-1b-off-2048/report.md) | same | off | 0 / 3 | no candidate | max_tokens 2048 still truncated |

TR04’s original grid matches TR01 (wrong total). A correct model fixes the total
row; the catalog’s adversarial data-row rewrite is checked offline by the host
guard (`table_data_modified`) and covered by unit tests. Path-2/path-3 failure
modes are demonstrated in `harness/tests/test_table_repair.py` with controlled
provider doubles.

## Reproduce

```bash
.venv/bin/python scripts/run_table_repair_pilot.py \
  --base http://127.0.0.1:11434/v1 \
  --model openbmb/minicpm-v4.7:latest \
  --skill-mode off \
  --outdir work/table-repair-pilot-rerun \
  --max-tokens 1024
```

Use a fresh empty `--outdir`. Manifests pin case hashes, provider fingerprints
and implementation SHA-256 values for that run.
