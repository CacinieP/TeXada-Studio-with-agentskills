# 质检报告

运行：`TR04`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：1
计数包含超时请求，不代表服务端完成推理。

## TR04

OK 1 · 待人工 0 · 复用 0 · 未完成 0

### 节点 TR04

检查终态：OK
输入 SHA256：`782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c`
执行上下文 SHA256：`8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b`

证据：⚠️ 缺失

以下为通过检查的候选，未写回源文件。

```diff
--- original_rows
+++ candidate_rows
@@ -13,6 +13,6 @@
   ],
   [
     "合计",
-    "4.5"
+    "4.0"
   ]
 ]
```

#### 检查与候选记录

```json
[
  {
    "run_id": "TR04",
    "doc": "TR04",
    "node_id": "TR04",
    "input_sha256": "782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CHECK",
    "stage": "original",
    "attempt": 0,
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "checker_detail": "total row vs data rows, col 1: row says 4.5, data sums to 4.0",
    "original": [
      [
        "项目",
        "金额"
      ],
      [
        "A",
        "1.5"
      ],
      [
        "B",
        "2.5"
      ],
      [
        "合计",
        "4.5"
      ]
    ],
    "schema_version": 2,
    "ts": "2026-11-10T22:37:05+0800"
  },
  {
    "run_id": "TR04",
    "doc": "TR04",
    "node_id": "TR04",
    "input_sha256": "782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:05+0800"
  },
  {
    "run_id": "TR04",
    "doc": "TR04",
    "node_id": "TR04",
    "input_sha256": "782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 1,
    "candidate": [
      [
        "项目",
        "金额"
      ],
      [
        "A",
        "1.5"
      ],
      [
        "B",
        "2.5"
      ],
      [
        "合计",
        "4.0"
      ]
    ],
    "model_calls": 1,
    "model_calls_known": true,
    "model_called": true,
    "reason": "ok",
    "skill_id": "doc-table-audit",
    "skill_name": "doc-table-audit",
    "skill_sha256": "ea05cfe54802f8eddf3cc650ea62cfdb0bcda63f5dc5c576de3c85f0dd0219f0",
    "prompt_sha256": "86aa26da5a64e5928386c851e6cbaebbc458e78ffffc9027da1b3e3b92901424",
    "skill_loaded": true,
    "response_truncated": false,
    "skill_mode": "on",
    "elapsed_seconds": 1.799519,
    "usage": {
      "prompt_tokens": 1348,
      "completion_tokens": 35,
      "total_tokens": 1383
    },
    "raw_candidate_response": "{\"rows\": [[\"项目\", \"金额\"], [\"A\", \"1.5\"], [\"B\", \"2.5\"], [\"合计\", \"4.0\"]]}",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:07+0800"
  },
  {
    "run_id": "TR04",
    "doc": "TR04",
    "node_id": "TR04",
    "input_sha256": "782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CHECK",
    "stage": "candidate",
    "attempt": 1,
    "checker_status": "OK",
    "checker_reason": "",
    "checker_detail": "",
    "candidate": [
      [
        "项目",
        "金额"
      ],
      [
        "A",
        "1.5"
      ],
      [
        "B",
        "2.5"
      ],
      [
        "合计",
        "4.0"
      ]
    ],
    "schema_version": 2,
    "ts": "2026-11-10T22:37:07+0800"
  },
  {
    "run_id": "TR04",
    "doc": "TR04",
    "node_id": "TR04",
    "input_sha256": "782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_SCOPE",
    "attempt": 1,
    "candidate": [
      [
        "项目",
        "金额"
      ],
      [
        "A",
        "1.5"
      ],
      [
        "B",
        "2.5"
      ],
      [
        "合计",
        "4.0"
      ]
    ],
    "scope": {
      "allowed": true,
      "reason": "authorized_table_scope",
      "method": "recompute_total_row",
      "row_index": 3
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:37:07+0800"
  },
  {
    "run_id": "TR04",
    "doc": "TR04",
    "node_id": "TR04",
    "input_sha256": "782994d97bab553e17e15a271b9510ec08d990f89bf3522b2cd242eccc4bde0c",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_ACCEPTED",
    "attempt": 1,
    "candidate": [
      [
        "项目",
        "金额"
      ],
      [
        "A",
        "1.5"
      ],
      [
        "B",
        "2.5"
      ],
      [
        "合计",
        "4.0"
      ]
    ],
    "checker_status": "OK",
    "checker_reason": "",
    "checker_detail": "",
    "scope": {
      "allowed": true,
      "reason": "authorized_table_scope",
      "method": "recompute_total_row",
      "row_index": 3
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:37:07+0800"
  }
]
```
