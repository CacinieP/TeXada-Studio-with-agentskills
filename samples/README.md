# 样本与测试替身

演示文档、结构化 fixture 与 `evaluation/` 是合成测试样本，随主项目采用 AGPL-3.0-only。`research/active_calculus_cases.json` 新增开放教材原文及明确注入的错误，单独采用 CC-BY-SA-4.0，见[来源与许可](research/ACTIVE_CALCULUS_NOTICE.md)。不要把自己的上传文件或私人文档加入本目录；Studio 上传内容保存在被 Git 忽略的 `state/studio/documents/`。

## 三种使用入口

- **Studio 文档**：`docs/report-01.tex` 与 `docs/exam-01.tex` 有意包含表格合计或公式语法错误；另有 `clean-control.tex` 正常对照、`semantic-boundary.tex` 数学语义反例、`manual-review.tex` 人工处理边界，共5份。用于源码编辑、候选对比与人工采用；新样本的分析测试不等于编译验收。启动方式见[根目录 README](../README.md)，逐份预期见[案例手册](../docs/casebook.md)。
- **CLI 结构化输入**：下面三个目录中的 `layout.json` 与占位 crop。CLI 直接读取这些结构化数据，不负责从上述 `.tex` 或 PDF 中生成它们。两个入口的同名样本不应视为完全相同的输入。
- **确定性检查案例**：[`evaluation/cases.json`](evaluation/cases.json) 包含正例、反例和边界，通过[独立运行器](../scripts/evaluate_cases.py)直接调用检查脚本，不生成修复候选。解释见[案例手册](../docs/casebook.md)。

| CLI 样本 | 内容 | 注入错误 |
| --- | --- | --- |
| `paper-01/` | 论文页：3 个公式节点 | `f-002` 下标丢失（预设候选 `a_1`）；`f-003` 花括号失衡，无 fixture 修复 |
| `exam-01/` | 试卷页：1 公式 + 2 表格 | `f-101` 定界符缺失；`t-201` 合计行 4.5 与数据行和 4.0 不一致 |
| `report-01/` | 报表：2 表格 | `t-301` 行数 3 与预期 4 不一致；`t-302` 为干净对照 |

## 无需模型的 fixture 运行

先按根 README 安装 Python 依赖，以下命令在仓库根目录执行：

```bash
PYTHONPATH=harness python -m docforensics run samples \
  --state state/fixture-check --fixture-repairs samples/fixture_repairs.json
```

预期结果：`exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。报告是 `state/fixture-check/report.md`，会注明 `fixture (offline test double)`。

再次运行相同命令会跳过 8 个输入与上下文一致的可复用终态节点。输入、依赖、检查器、模型或 Skill 变化会使旧终态失效；暂时性环境/提供方故障会在重跑时重新处理。独立评测仍使用新的状态目录。详细约束见 [Harness 说明](../harness/README.md)。

## 直接检查输入契约与边界

```bash
python scripts/evaluate_cases.py --outdir state/evaluation-01
```

该入口不调用模型，不使用 `fixture_repairs.json`，也不做 CLI 状态续跑。每次创建新的报告目录，输出每例的预期、实际状态和限制；不可将匹配数当作模型准确率。详见[评估案例说明](evaluation/README.md)。三条路径如何连接见 [Skills 技术报告](../docs/skills-technical-report.md)，其他资料见[文档导航](../docs/index.md)。

## 真实模型运行

在本机启动兼容服务并核对已安装模型，然后替换标签：

```bash
export VLM_MODEL='替换为已安装的模型标签'
PYTHONPATH=harness python -m docforensics run samples \
  --state state/model-check \
  --vlm http://127.0.0.1:11434 --vlm-model "$VLM_MODEL"
```

真实模式发送**公式文本**，不发送 crop；不应预期得到与 fixture 相同的计数。当前 CLI 没有模型表格重提取实现，需要修复的表格进入 `NEEDS_HUMAN`。Studio 的简单合计重算是另一套确定性逻辑，不调用模型。

## 结果应如何解释

- `layout.json` 是版面解析的测试替身；crop 是占位灰块，不是真实图像解析证据。
- `fixture_repairs.json` 是预设修复，不可用作模型效果评测。`a_` 的候选 `a_1` 能通过语法检查，但原意仍需人核对。
- fixture 验证的是状态流转、检查与报告链路。真实模型评测需单独提供数据来源、模型标签、调用方式和人工判定方法。
- 历史教材节选已移出分发范围，见[发布清单](../docs/open-source-release.md)。不要将私密旧备份重新放回本目录。

新增[三组研究入口](research/README.md)分别运行仅检查器、同模型不加载 Skill、同模型加载 Skill。12 条开放来源先导样本包含 6 条原文和 6 条人工注入错误；来源参考与真实候选一起进入人工待审表，未完成复核不报告语义准确率。
