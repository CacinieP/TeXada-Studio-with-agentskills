# 样本与测试替身

本目录保留的内容均为合成测试样本，随主项目采用 AGPL-3.0-only。不要把自己的上传文件、真实论文或私人文档加入本目录；Studio 上传内容保存在被 Git 忽略的 `state/studio/documents/`。

## 两种使用入口

- **Studio 文档**：`docs/report-01.tex` 与 `docs/exam-01.tex`，有意包含表格合计或公式语法错误，用于源码编辑、编译预览、候选对比与人工采用。启动方式见[根目录 README](../README.md)。
- **CLI 结构化输入**：下面三个目录中的 `layout.json` 与占位 crop。CLI 直接读取这些结构化数据，不负责从上述 `.tex` 或 PDF 中生成它们。两个入口的同名样本不应视为完全相同的输入。

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

再次运行相同命令会跳过 8 个已有终态节点。输入、依赖或提供方变更后应选择新状态目录；现有终态不会自动失效。详细约束见 [Harness 说明](../harness/README.md)。

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
