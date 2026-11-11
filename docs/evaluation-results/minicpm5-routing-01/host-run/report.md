# 质检报告

运行：`e643049c330c4f15997c0f346a810af5`
提供方：openai-compatible

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：0
计数包含超时请求，不代表服务端完成推理。

## minicpm5-routing-probe

OK 2 · 待人工 1 · 复用 0 · 未完成 0

### 节点 closing-brace

检查终态：OK
输入 SHA256：`80d434719c575db7bea94d2310fcf4829153da39de303ecc894009772d9c394d`
执行上下文 SHA256：`574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499`

证据：⚠️ 缺失

以下为通过检查的候选，未写回源文件。

原文：
```latex
\frac{a+b}{2
```

候选：
```latex
\frac{a+b}{2}
```

#### 检查与候选记录

```json
[
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "closing-brace",
    "input_sha256": "80d434719c575db7bea94d2310fcf4829153da39de303ecc894009772d9c394d",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "CHECK",
    "stage": "original",
    "attempt": 0,
    "checker_status": "RETRY",
    "checker_reason": "parse error: LaTeXParsingError: missing '}' at '<EOF>'\n\\frac{a+b}{2\n~~~~~~~~~~~~^",
    "checker_detail": "",
    "original": "\\frac{a+b}{2",
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  },
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "closing-brace",
    "input_sha256": "80d434719c575db7bea94d2310fcf4829153da39de303ecc894009772d9c394d",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "DETERMINISTIC_REPAIR",
    "candidate": "\\frac{a+b}{2}",
    "scope": {
      "allowed": true,
      "reason": "deterministic_syntax_patch",
      "method": "close_trailing_braces"
    },
    "anchor": {
      "drift": false,
      "findings": [],
      "reason": ""
    },
    "model_calls": 0,
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  },
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "closing-brace",
    "input_sha256": "80d434719c575db7bea94d2310fcf4829153da39de303ecc894009772d9c394d",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "CHECK",
    "stage": "deterministic_candidate",
    "attempt": 0,
    "checker_status": "OK",
    "checker_reason": "",
    "checker_detail": "",
    "candidate": "\\frac{a+b}{2}",
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  },
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "closing-brace",
    "input_sha256": "80d434719c575db7bea94d2310fcf4829153da39de303ecc894009772d9c394d",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "CANDIDATE_ACCEPTED",
    "attempt": 0,
    "candidate": "\\frac{a+b}{2}",
    "checker_status": "OK",
    "scope": {
      "allowed": true,
      "reason": "deterministic_syntax_patch",
      "method": "close_trailing_braces"
    },
    "provider": "deterministic-syntax",
    "model_calls": 0,
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  }
]
```

### 节点 missing-operand

检查终态：NEEDS_HUMAN
输入 SHA256：`c42855da977899e64bd13d8c0b30a9871866e9d5eea54f5124e09cfbfe18f902`
执行上下文 SHA256：`574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499`

处置原因：
```text
missing_operator_operand
```

#### 检查与候选记录

```json
[
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "missing-operand",
    "input_sha256": "c42855da977899e64bd13d8c0b30a9871866e9d5eea54f5124e09cfbfe18f902",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "CHECK",
    "stage": "original",
    "attempt": 0,
    "checker_status": "RETRY",
    "checker_reason": "parse error: LaTeXParsingError: Invalid LaTeX",
    "checker_detail": "",
    "original": "a+b+",
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  },
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "missing-operand",
    "input_sha256": "c42855da977899e64bd13d8c0b30a9871866e9d5eea54f5124e09cfbfe18f902",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "REPAIR_SKIPPED",
    "reason": "missing_operator_operand",
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  }
]
```

### 节点 unchanged-control

检查终态：OK
输入 SHA256：`419b6841440ab4cb052abf89984727c329c7e931edb9cd90879a589ec8388dd9`
执行上下文 SHA256：`574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499`

#### 检查与候选记录

```json
[
  {
    "run_id": "e643049c330c4f15997c0f346a810af5",
    "doc": "minicpm5-routing-probe",
    "node_id": "unchanged-control",
    "input_sha256": "419b6841440ab4cb052abf89984727c329c7e931edb9cd90879a589ec8388dd9",
    "context_sha256": "574e8cb7c65ec026646251d4c8bbef72f78a05d5e32af2f284c4526c08261499",
    "revision": 0,
    "skill": "doc-formula-verify",
    "action": "CHECK",
    "stage": "original",
    "attempt": 0,
    "checker_status": "OK",
    "checker_reason": "",
    "checker_detail": "",
    "original": "a+b",
    "schema_version": 2,
    "ts": "2026-11-11T11:24:03+0800"
  }
]
```
