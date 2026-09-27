# Agent Harness 说明

Harness 是 Skills 的执行外壳：规划循环、三态协议、状态持久化、模型网关。本目录收敛其设计要点，
实现入口为 `python -m docforensics ...`（P0 期间只做薄循环，不引入重框架）。

## 模型网关（LiteLLM → vLLM）

- `30b-moe`（NVFP4）：质检仲裁与重生成，常驻
- `vlm-8b`：版面解析与高分辨率重识别，常驻
- `embed-0.6b` / `rerank-0.6b`：检索与证据匹配，常驻
- 重负载（如批量重生成）串行排队；可选 llama-swap 按需装卸（见 skills/spark-ops）
- 全部端点 127.0.0.1，断网可用

## 三态协议（Skills ↔ Harness）

每个质检 Skill 对每个节点输出：

| 状态 | 含义 | Harness 动作 |
| --- | --- | --- |
| `OK` | 通过 | 记录，继续 |
| `RETRY` | 可修复 | 按 Skill 指令自动修复（如高分辨率重识别），attempt+1 |
| `NEEDS_HUMAN` | 两次重试仍失败 | 标记进报告，**不阻塞**，继续后续节点 |

约束：每公式节点最多 3 次 VLM 调用；所有决策追加写入 `state.jsonl`。

## 断点续跑

- 状态文件：`state/state.jsonl`（append-only）
- 启动时重放事件，已完成节点（存在 `OK`/`NEEDS_HUMAN` 终态）直接跳过
- 证据文件：`state/crops/<node_id>-a<attempt>.png`
- `state/` 不入 git（见 .gitkeep 约定）

## 工具链

- Python（stdlib + SymPy/antlr）：harness、doc-formula-verify、doc-table-audit
- Node：latex-cleanup 的 `audit_math.cjs` 数学审计（修复后检查模式调用，属内部依赖）
- Tectonic（可选，P1/P2）：latex-cleanup 的 `compile_tex.py` 编译回环；目标环境未装时按其
  契约显式报告「未执行」，不得当作通过
- 全部端点 127.0.0.1，断网可用；不新增全局工具安装（沿用 latex-cleanup 的约束）

## 目录约定（TODO P0）

```
harness/
├── docforensics/
│   ├── __init__.py
│   ├── __main__.py      # CLI: run/resume/report
│   ├── pipeline.py      # 节点遍历与三态分发
│   └── state.py         # state.jsonl 读写与重放
└── requirements.txt
```

> P0 切片：pipeline 只需支持 formula/table 两类节点 + report 汇总；
> layout-parse 以外部命令行产出 JSON 结构树方式接入（薄封装）。
