# 质检报告

运行：`TR03`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：2
计数包含超时请求，不代表服务端完成推理。

## TR03

OK 0 · 待人工 1 · 复用 0 · 未完成 0

### 节点 TR03

检查终态：NEEDS_HUMAN
输入 SHA256：`ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5`
执行上下文 SHA256：`be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e`

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
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
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
    "ts": "2026-11-10T22:36:22+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 1,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:22+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
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
    "prompt_sha256": "1e151a1020d22938b3482945767d8b4e14de555e80692933b894157a9cfab66b",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 3.70449,
    "usage": {
      "prompt_tokens": 304,
      "completion_tokens": 1024,
      "total_tokens": 1328
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:36:26+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_REJECTED",
    "attempt": 1,
    "candidate": null,
    "reason": "incomplete_response",
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:26+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "PROVIDER_START",
    "attempt": 2,
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "provider": "openai-compatible",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:26+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
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
    "prompt_sha256": "09700756ccdd25c22eb690ceaa260c3809d4865a095b6684e2aa86648215c75d",
    "skill_loaded": false,
    "response_truncated": false,
    "skill_mode": "off",
    "elapsed_seconds": 3.558455,
    "usage": {
      "prompt_tokens": 313,
      "completion_tokens": 1024,
      "total_tokens": 1337
    },
    "schema_version": 2,
    "ts": "2026-11-10T22:36:29+0800"
  },
  {
    "run_id": "TR03",
    "doc": "TR03",
    "node_id": "TR03",
    "input_sha256": "ca90e3180763199152fe45389d237adf0763c2f2532d2ca06abf1039cc90d1f5",
    "context_sha256": "be5f4be1c04e6c087259159a0edb4a997e8768963a2adb77e77676c1f032557e",
    "revision": 0,
    "skill": "doc-table-audit",
    "action": "CANDIDATE_REJECTED",
    "attempt": 2,
    "candidate": null,
    "reason": "incomplete_response",
    "checker_status": "RETRY",
    "checker_reason": "shape_mismatch",
    "schema_version": 2,
    "ts": "2026-11-10T22:36:29+0800"
  }
]
```
