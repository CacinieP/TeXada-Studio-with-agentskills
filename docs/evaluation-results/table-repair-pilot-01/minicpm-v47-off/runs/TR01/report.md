# 质检报告

运行：`TR01`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：1
计数包含超时请求，不代表服务端完成推理。

## TR01

OK 1 · 待人工 0 · 复用 0 · 未完成 0

### 节点 TR01

检查终态：OK
输入 SHA256：`4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be`
执行上下文 SHA256：`32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc`

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
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
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
    "ts": "2026-11-10T22:36:47+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:47+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
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
    "prompt_sha256": "70e26d034f79e559771634fb9b0b5fa8c02091c23458119e024521ece83aec7a",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 1.132613,
    "usage": {
      "prompt_tokens": 300,
      "completion_tokens": 35,
      "total_tokens": 335
    },
    "raw_candidate_response": "{\"rows\": [[\"项目\", \"金额\"], [\"A\", \"1.5\"], [\"B\", \"2.5\"], [\"合计\", \"4.0\"]]}",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:48+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
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
    "ts": "2026-11-10T22:36:48+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
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
    "ts": "2026-11-10T22:36:48+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
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
    "ts": "2026-11-10T22:36:48+0800"
  }
]
```
