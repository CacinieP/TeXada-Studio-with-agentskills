# 质检报告

运行：`TR01`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：2
计数包含超时请求，不代表服务端完成推理。

## TR01

OK 0 · 待人工 1 · 复用 0 · 未完成 0

### 节点 TR01

检查终态：NEEDS_HUMAN
输入 SHA256：`4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be`
执行上下文 SHA256：`be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e`

处置原因：
```text
sum_mismatch
```

提供方结果：
```text
incomplete_response
```

#### 检查与候选记录

```json
[
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
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
    "ts": "2026-11-10T22:36:04+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:04+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 1,
    "candidate": null,
    "model_calls": 1,
    "model_calls_known": true,
    "model_called": true,
    "reason": "incomplete_response",
    "prompt_sha256": "70e26d034f79e559771634fb9b0b5fa8c02091c23458119e024521ece83aec7a",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 7.84914,
    "usage": {
      "prompt_tokens": 306,
      "completion_tokens": 1024,
      "total_tokens": 1330
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:36:11+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_REJECTED",
    "attempt": 1,
    "candidate": null,
    "reason": "incomplete_response",
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:11+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 2,
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:11+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 2,
    "candidate": null,
    "model_calls": 1,
    "model_calls_known": true,
    "model_called": true,
    "reason": "incomplete_response",
    "prompt_sha256": "a5c730506c65cd29ab2b0de90bfb392ee41befcaffd8fc131b478e7b23f6589f",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 3.604016,
    "usage": {
      "prompt_tokens": 315,
      "completion_tokens": 1024,
      "total_tokens": 1339
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:36:15+0800"
  },
  {
    "run_id": "TR01",
    "doc": "TR01",
    "node_id": "TR01",
    "input_sha256": "4b764afd5dc8a38f2a00c6d37adad4df193baad9ff0d08ef3c80c1c73085a2be",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_REJECTED",
    "attempt": 2,
    "candidate": null,
    "reason": "incomplete_response",
    "checker_status": "RETRY",
    "checker_reason": "sum_mismatch",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:15+0800"
  }
]
```
