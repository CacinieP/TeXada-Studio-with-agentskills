# 质检报告

运行：`TR02`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：1
计数包含超时请求，不代表服务端完成推理。

## TR02

OK 1 · 待人工 0 · 复用 0 · 未完成 0

### 节点 TR02

检查终态：OK
输入 SHA256：`2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3`
执行上下文 SHA256：`8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b`

证据：⚠️ 缺失

以下为通过检查的候选，未写回源文件。

```diff
--- original_rows
+++ candidate_rows
@@ -12,6 +12,7 @@
     "2.5"
   ],
   [
-    "total"
+    "total",
+    "4.0"
   ]
 ]
```

#### 检查与候选记录

```json
[
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CHECK",
    "stage": "original",
    "attempt": 0,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "checker_detail": "col count mismatch at rows [3]",
    "original": [
      [
        "item",
        "amount"
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
        "total"
      ]
    ],
    "schema_version": 2,
    "ts": "2026-11-10T22:37:01+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:01+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 1,
    "candidate": [
      [
        "item",
        "amount"
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
        "total",
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
    "prompt_sha256": "0cb3948526dcc42472ec9223b1df32218aefdbce2ab17331c0a5a1dd072a9e9c",
    "skill_loaded": true,
    "response_truncated": false,
    "skill_mode": "on",
    "elapsed_seconds": 1.549007,
    "usage": {
      "prompt_tokens": 1344,
      "completion_tokens": 35,
      "total_tokens": 1379
    },
    "raw_candidate_response": "{\"rows\": [[\"item\", \"amount\"], [\"A\", \"1.5\"], [\"B\", \"2.5\"], [\"total\", \"4.0\"]]}",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:03+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
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
        "item",
        "amount"
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
        "total",
        "4.0"
      ]
    ],
    "schema_version": 2,
    "ts": "2026-11-10T22:37:03+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_SCOPE",
    "attempt": 1,
    "candidate": [
      [
        "item",
        "amount"
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
        "total",
        "4.0"
      ]
    ],
    "scope": {
      "allowed": true,
      "reason": "authorized_table_scope",
      "method": "complete_total_row",
      "row_index": 3
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:37:03+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "8f460623ba9c48b7da6311836ac11596b46d5d97417e3365e86fad8fcfb5e13b",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_ACCEPTED",
    "attempt": 1,
    "candidate": [
      [
        "item",
        "amount"
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
        "total",
        "4.0"
      ]
    ],
    "checker_status": "OK",
    "checker_reason": "",
    "checker_detail": "",
    "scope": {
      "allowed": true,
      "reason": "authorized_table_scope",
      "method": "complete_total_row",
      "row_index": 3
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:37:03+0800"
  }
]
```
