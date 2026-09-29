# 样本与测试替身

演示文档、结构化 fixture 与 `evaluation/` 是合成测试样本，随主项目采用 AGPL-3.0-only。`research/active_calculus_cases.json` 新增开放教材原文及明确注入的错误，单独采用 CC-BY-SA-4.0，见[来源与许可](research/ACTIVE_CALCULUS_NOTICE.md)。不要把自己的上传文件或私人文档加入本目录；Studio 上传内容保存在被 Git 忽略的 `state/studio/documents/`。

## 三种使用入口

- **Studio 文档**：`docs/` 中共 13 份 `.tex`，包括原有的报表、试卷及边界样本，以及下列 8 份数学讲义与科研笔记。用于源码编辑、候选对比与人工采用；分析测试不等于编译验收。启动方式见[根目录 README](../README.md)，逐份预期见[案例手册](../docs/casebook.md)。
- **CLI 结构化输入**：下面三个目录中的 `layout.json` 与占位 crop。CLI 直接读取这些结构化数据，不负责从上述 `.tex` 或 PDF 中生成它们。两个入口的同名样本不应视为完全相同的输入。
- **确定性检查案例**：[`evaluation/cases.json`](evaluation/cases.json) 包含正例、反例和边界，通过[独立运行器](../scripts/evaluate_cases.py)直接调用检查脚本，不生成修复候选。解释见[案例手册](../docs/casebook.md)。

| CLI 样本 | 内容 | 注入错误 |
| --- | --- | --- |
| `paper-01/` | 论文页：3 个公式节点 | `f-002` 下标丢失（预设候选 `a_1`）；`f-003` 花括号失衡，无 fixture 修复 |
| `exam-01/` | 试卷页：1 公式 + 2 表格 | `f-101` 定界符缺失；`t-201` 合计行 4.5 与数据行和 4.0 不一致 |
| `report-01/` | 报表：2 表格 | `t-301` 行数 3 与预期 4 不一致；`t-302` 为干净对照 |

## 数学讲义与科研笔记

这 8 份文档为本项目原创的合成教学材料，正文采用英文，源码为 ASCII，不需要中文字体。每份文档说明教学目的；错误样本会明确标注有意注入的问题。它们适合直接在 Studio 打开，不能作为 CLI 的 `layout.json` 输入。

建议演示顺序是 [math-clean.tex](docs/math-clean.tex) → [math-delimiters.tex](docs/math-delimiters.tex) → [math-semantics.tex](docs/math-semantics.tex)：先展示分式、积分和上下标的正常排版，再审阅缺失闭合定界符的修复候选，最后检查一个语法合法但积分值错误的反例。

| 案例 | 文档 | 提取的公式数 | 语法问题数 | 用途 |
| --- | --- | ---: | ---: | --- |
| S06 | [math-delimiters.tex](docs/math-delimiters.tex) | 2 | 1 | 分式外层缺失 `\right)`；推荐作为主修复演示 |
| S07 | [math-fractions.tex](docs/math-fractions.tex) | 2 | 1 | 分母缺失闭合花括号 |
| S08 | [math-indices.tex](docs/math-indices.tex) | 2 | 1 | 递推式下标分组缺失闭合花括号 |
| S09 | [math-integrals.tex](docs/math-integrals.tex) | 2 | 1 | 积分上限分组缺失闭合花括号 |
| S10 | [math-clean.tex](docs/math-clean.tex) | 4 | 0 | 分式、积分、极限和递推式的正常对照 |
| S11 | [math-semantics.tex](docs/math-semantics.tex) | 3 | 0 | 积分值故意写错，说明语法通过不能证明数学正确 |
| S12 | [math-align-boundary.tex](docs/math-align-boundary.tex) | 0 | 0 | 有意损坏的多行 `align*` 不在当前提取范围内 |
| S13 | [math-references.tex](docs/math-references.tex) | 0 | 0 | `equation`、交叉引用和文献引用未由当前分析器检查 |

表中的数量来自真实本地检查器。Studio 当前按行提取 `$...$` 中的公式，不覆盖多行环境，也不理解完整 TeX 上下文。S12、S13 的零问题表示未覆盖，不能视为文档通过验证；S11 的零问题也不代表数学真值已核对。

机器可读清单 [studio-cases.json](studio-cases.json) 记录逐公式预期、原文保持要求、提取边界和作者参考修复。四份损坏公式各有一个能通过语法检查的作者候选，用于离线回归；这些候选不是模型输出，也不保证模型运行成功。没有可用候选时应保留原文，正常对照与上述边界样本不应触发公式修复请求。

在仓库根目录运行以下回归测试，可验证样本发现、提取、检查与修复边界：

```bash
python -m unittest discover -s webui -p test_samples.py -v
```

这项测试不调用真实模型、不编译文档。编译结果和实际模型输出需单独记录；不得把作者参考修复或契约匹配数当作模型准确率。

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
