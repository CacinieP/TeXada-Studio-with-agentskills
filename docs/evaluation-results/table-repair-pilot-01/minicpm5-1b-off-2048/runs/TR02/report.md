# 质检报告

运行：`TR02`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：2
计数包含超时请求，不代表服务端完成推理。

## TR02

OK 0 · 待人工 1 · 复用 0 · 未完成 0

### 节点 TR02

检查终态：NEEDS_HUMAN
输入 SHA256：`2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3`
执行上下文 SHA256：`7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7`

处置原因：
```text
shape_mismatch
```

提供方结果：
```text
incomplete_response
```

#### 检查与候选记录

```json
[
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
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
    "ts": "2026-11-10T22:37:22+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:22+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 1,
    "candidate": null,
    "model_calls": 1,
    "model_calls_known": true,
    "model_called": true,
    "reason": "incomplete_response",
    "prompt_sha256": "2a203972fef9559dbac33adb70f98c67f2040bedf9eda9f0c0fb12d55a529a43",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 7.390305,
    "usage": {
      "prompt_tokens": 302,
      "completion_tokens": 2048,
      "total_tokens": 2350
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:37:29+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_REJECTED",
    "attempt": 1,
    "candidate": null,
    "reason": "incomplete_response",
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:29+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 2,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:29+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_RESULT",
    "attempt": 2,
    "candidate": null,
    "model_calls": 1,
    "model_calls_known": true,
    "model_called": true,
    "reason": "incomplete_response",
    "prompt_sha256": "a79e388d911afac75130ddddf24dc1163163b7cbbf8765a3a33161f34bd80358",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 7.259578,
    "usage": {
      "prompt_tokens": 311,
      "completion_tokens": 2048,
      "total_tokens": 2359
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:37:36+0800"
  },
  {
    "run_id": "TR02",
    "doc": "TR02",
    "node_id": "TR02",
    "input_sha256": "2d74a253597d4987e40170f30b92d3e88b8b5ee77eaee35f0644ec6411acdad3",
    "context_sha256": "7dc942fc377cc946ab814c8ed54e03bbe0bedbe8ad1cc7951cffa6d1df4462a7",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_REJECTED",
    "attempt": 2,
    "candidate": null,
    "reason": "incomplete_response",
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "schema_version": 2,
    "ts": "2026-11-10T22:37:36+0800"
  }
]
```
