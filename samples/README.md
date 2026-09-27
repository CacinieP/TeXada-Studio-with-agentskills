# 样本包（离线 fixtures）

三个样本目录，每个含 `layout.json`（结构树）与占位 crop 截图：

| 样本 | 内容 | 注入错误 |
| --- | --- | --- |
| `paper-01/` | 论文页：3 个公式节点 | `f-002` 下标丢失（`a_` → `a_1`）、`f-003` 花括号失衡（后者无修复 → NEEDS_HUMAN） |
| `exam-01/` | 试卷页：1 公式 + 2 表格 | `f-101` 定界符缺失（`\left` 无 `\right`）；`t-201` 合计行 4.5 ≠ 数据行和 4.0 |
| `report-01/` | 报表：2 表格 | `t-301` 跨页断表（行数 3 ≠ 4）；`t-302` 干净对照 |

## 诚实性声明

- `layout.json` 是 **VLM 解析结果的测试替身**（真实运行由 `doc-layout-parse` 调本地 VLM 产出）；
  crop 为占位灰块（真实运行是 bbox 裁剪图）。
- `fixture_repairs.json` 是**修复测试替身**（模拟 VLM 重识别结果）。用 `--fixture-repairs` 跑时报告会
  如实标注 `provider: fixture (offline test double)`；真实修复用 `--vlm http://127.0.0.1:<port>` 接本地
  Ollama/vLLM，两者不得混淆，BENCHMARK 只认真实模式。

## 跑法

```bash
PYTHONPATH=harness python3 -m docforensics run samples --state state/run1 \
  --fixture-repairs samples/fixture_repairs.json     # 离线演示
PYTHONPATH=harness python3 -m docforensics run samples --state state/run2 \
  --vlm http://127.0.0.1:11434 --vlm-model qwen2.5vl:7b   # 真实 VLM
```
