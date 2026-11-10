# Table repair pilot · `texada-minicpm5-1b:baseline` · skill `off`

Synthetic contract cases for issue #25. Checker + host scope decide acceptance; this is not a semantic accuracy score.

- base: `http://127.0.0.1:11434/v1`
- seed: `0`, max_tokens: `1024`
- cases: `samples/research/table_repair_cases.json`

| Case | Path | Status | Repaired | Model calls | Terminal reason | Scope/reject |
| --- | --- | --- | --- | ---: | --- | --- |
| TR01 | normal_recompute_total | NEEDS_HUMAN | False | 2 | `sum_mismatch` | `incomplete_response,incomplete_response` |
| TR02 | normal_complete_total | NEEDS_HUMAN | False | 2 | `shape_mismatch` | `incomplete_response,incomplete_response` |
| TR03 | normal_append_total | NEEDS_HUMAN | False | 2 | `shape_mismatch` | `incomplete_response,incomplete_response` |
| TR04 | reject_data_mutation | NEEDS_HUMAN | False | 2 | `sum_mismatch` | `incomplete_response,incomplete_response` |

## Host adversarial check (TR04)

The catalog also records a checker-passing data-row rewrite. The host scope guard must reject it offline regardless of model output:

```json
{
  "allowed": false,
  "reason": "table_data_modified",
  "method": null,
  "row_index": 2,
  "col_index": 1
}
```

Per-case journals and reports are under `runs/<case-id>/`.
