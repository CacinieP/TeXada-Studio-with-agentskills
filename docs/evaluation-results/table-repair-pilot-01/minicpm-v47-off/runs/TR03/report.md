# 质检报告

运行：`TR03`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：1
计数包含超时请求，不代表服务端完成推理。

## TR03

OK 1 · 待人工 0 · 复用 0 · 未完成 0

### 节点 TR03

检查终态：OK
输入 SHA256：`ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5`
执行上下文 SHA256：`32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc`

证据：⚠️ 缺失

以下为通过检查的候选，未写回源文件。

```diff
--- original_rows
+++ candidate_rows
@@ -13,5 +13,10 @@
     "2月",
     "120",
     "90"
+  ],
+  [
+    "合计",
+    "220",
+    "170"
   ]
 ]
```

#### 检查与候选记录

```json
[
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CHECK",
    "stage": "original",
    "attempt": 0,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "checker_detail": "rows: got 3, expect 4",
    "original": [
      [
        "月份",
        "收入",
        "支出"
      ],
      [
        "1月",
        "100",
        "80"
      ],
      [
        "2月",
        "120",
        "90"
      ]
    ],
    "schema_version": 2,
    "ts": "2026-11-10T22:36:50+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:50+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 1,
    "candidate": [
      [
        "月份",
        "收入",
        "支出"
      ],
      [
        "1月",
        "100",
        "80"
      ],
      [
        "2月",
        "120",
        "90"
      ],
      [
        "合计",
        "220",
        "170"
      ]
    ],
    "model_calls": 1,
    "model_calls_known": true,
    "model_called": true,
    "reason": "ok",
    "prompt_sha256": "1e151a1020d22938b3482945767d8b4e14de555e80692933b894157a9cfab66b",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 2.08611,
    "usage": {
      "prompt_tokens": 304,
      "completion_tokens": 53,
      "total_tokens": 357
    },
    "raw_candidate_response": "{\"rows\": [[\"月份\", \"收入\", \"支出\"], [\"1月\", \"100\", \"80\"], [\"2月\", \"120\", \"90\"], [\"合计\", \"220\", \"170\"]]}",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:52+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
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
        "月份",
        "收入",
        "支出"
      ],
      [
        "1月",
        "100",
        "80"
      ],
      [
        "2月",
        "120",
        "90"
      ],
      [
        "合计",
        "220",
        "170"
      ]
    ],
    "schema_version": 2,
    "ts": "2026-11-10T22:36:52+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_SCOPE",
    "attempt": 1,
    "candidate": [
      [
        "月份",
        "收入",
        "支出"
      ],
      [
        "1月",
        "100",
        "80"
      ],
      [
        "2月",
        "120",
        "90"
      ],
      [
        "合计",
        "220",
        "170"
      ]
    ],
    "scope": {
      "allowed": true,
      "reason": "authorized_table_scope",
      "method": "append_total_row",
      "row_index": 3
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:36:52+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "32608311649e6612f4d1f372c700d343ecc9773075b61c082c19e003eb28cbbc",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_ACCEPTED",
    "attempt": 1,
    "candidate": [
      [
        "月份",
        "收入",
        "支出"
      ],
      [
        "1月",
        "100",
        "80"
      ],
      [
        "2月",
        "120",
        "90"
      ],
      [
        "合计",
        "220",
        "170"
      ]
    ],
    "checker_status": "OK",
    "checker_reason": "",
    "checker_detail": "",
    "scope": {
      "allowed": true,
      "reason": "authorized_table_scope",
      "method": "append_total_row",
      "row_index": 3
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:36:52+0800"
  }
]
```
