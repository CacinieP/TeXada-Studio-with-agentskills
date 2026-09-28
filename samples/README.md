# 样本包（离线 fixtures）

本目录保留的内容均为合成测试样本，随主项目采用 AGPL-3.0-only。
Studio 自带 `docs/report-01.tex` 和 `docs/exam-01.tex`，有意包含合计或公式语法错误。
历史教材节选 `GTM249-p101-120.tex` 已移出当前分发范围，见 [发布清单](../docs/open-source-release.md)。
用户自己的上传文件放在 `state/studio/documents/`，不要加入本目录。

三个样本目录，每个含 `layout.json`（结构树）与占位 crop 截图：

| 样本 | 内容 | 注入错误 |
| --- | --- | --- |
| `paper-01/` | 论文页：3 个公式节点 | `f-002` 下标丢失（`a_` → `a_1`）、`f-003` 花括号失衡（后者无修复 → NEEDS_HUMAN） |
| `exam-01/` | 试卷页：1 公式 + 2 表格 | `f-101` 定界符缺失（`\left` 无 `\right`）；`t-201` 合计行 4.5 ≠ 数据行和 4.0 |
| `report-01/` | 报表：2 表格 | `t-301` 跨页断表（行数 3 ≠ 4）；`t-302` 干净对照 |

## 诚实性声明

- `layout.json` 是 **VLM 解析结果的测试替身**（当前没有接入真实图像解析器）；
  crop 为占位灰块，不能作为真实视觉模型证据。
- `fixture_repairs.json` 是**修复测试替身**（模拟 VLM 重识别结果）。用 `--fixture-repairs` 跑时报告会
  如实标注 `provider: fixture (offline test double)`；真实修复用 `--vlm http://127.0.0.1:<port>` 接本地
  Ollama/vLLM，两者不得混淆，BENCHMARK 只认真实模式。

## 跑法

```bash
PYTHONPATH=harness python3 -m docforensics run samples --state state/run1 \
  --fixture-repairs samples/fixture_repairs.json     # 离线演示
PYTHONPATH=harness python3 -m docforensics run samples --state state/run2 \
  --vlm http://127.0.0.1:11434 --vlm-model qwen2.5vl:7b   # 真实文本模型
```
