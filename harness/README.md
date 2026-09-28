# CLI 质检管线

Harness 读取已有的 `layout.json`，运行公式语法检查和表格数据检查，记录候选修复与待人工节点。它不直接读取 PDF、执行 OCR、编译 TeX，或把修复写回原始 `.tex`。Studio 的编辑、编译和人工采用流程是另一条入口，见[根目录 README](../README.md)。

## 首次运行

以下命令均在仓库根目录执行，先按根 README 创建并激活 Python 虚拟环境。

```bash
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

预期结果：`exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。报告写入 `state/quickstart/report.md`，提供方明确标注为 `fixture (offline test double)`。依赖装好后，这条命令不调用模型服务；测试替身的结果不代表真实模型效果。

当前只有 `run` 子命令；没有独立的 `resume` 或 `report` 子命令。重复执行同一条 `run` 即续跑，结束时自动重写 Markdown 报告。

```bash
PYTHONPATH=harness python -m docforensics run --help
```

## 选择修复提供方

| 模式 | 启用方式 | 公式修复 | 表格修复 |
| --- | --- | --- | --- |
| Fixture | `--fixture-repairs <JSON>`，不传 `--vlm` | 读取预设候选 | 读取预设行数据 |
| 真实文本模型 | `--vlm <本机服务根地址> --vlm-model <已安装标签>` | 向 `/v1/chat/completions` 发送公式文本并回判语法 | 未实现重提取；需要修复的表格进入 `NEEDS_HUMAN` |
| 无修复表的 fixture | 两项均不传 | 只检查，没有候选可用 | 只检查，没有候选可用 |

`--vlm` 优先于 `--fixture-repairs`。兼容接口需支持无需 API key 的上述路径；请求中没有图像。建议只接本机可信模型服务。CLI 接受显式传入的地址，代码并不强制它必须为回环地址。

例如，先用 `ollama list` 核对已安装模型，再填写自己的标签：

```bash
export VLM_MODEL='替换为已安装的模型标签'
PYTHONPATH=harness python -m docforensics run samples \
  --state state/model-check \
  --vlm http://127.0.0.1:11434 --vlm-model "$VLM_MODEL"
```

`--vlm-model` 的 CLI 默认值是 `qwen2.5vl:7b`，不代表该模型已安装，也不同于 Studio 的默认标签。程序不自动安装模型、启动模型服务或下载依赖。表格合计的确定性重算是 **Studio** 的能力，不是 CLI 真实模型模式的表格修复能力。

## 检查、修复与终态

| 状态 / 事件 | 当前行为 |
| --- | --- |
| `OK` | 当前检查通过；不等于数学语义正确 |
| `RETRY` | 检查器认为可尝试修复，调用提供方取得候选后重新检查 |
| `NEEDS_HUMAN` | 重试耗尽、提供方无候选或检查环境缺失等情况，写入报告并继续后续节点 |

每个节点最多调用修复提供方 **2 次**；若提供方没有返回候选，会提前结束。公式检查器的 `NEEDS_ENV` 被记录为带 `env:` 原因的 `NEEDS_HUMAN`，不是检查通过。模型异常可能只体现为没有修复结果，报告不能据此区分所有服务故障。

两次公式修复请求都基于节点原始公式，不是把上次失败候选持续反馈给模型。当前实现也没有图像重识别、LiteLLM 路由、多模型调度或检索。

## 输入、输出与续跑

`run` 接受含有 `layout.json` 的样本目录，或这些目录的父目录。输入结构可参考 [`samples/paper-01/layout.json`](../samples/paper-01/layout.json)；公式使用 `data.latex`，表格使用 `data.rows` 与 `data.expected`。其他节点类型仅按 `pass-through` 记录为 `OK`，不代表做过质检。

```text
<--state 指定目录>/
├── state.jsonl     # 追加事件：检查、修复、终态和 SKIP
├── report.md       # 每次运行结束后重写
└── crops/          # 有可用 crop 时复制；保留原文件名
```

`--state` 默认是 `state/run1`。路径相对于运行命令的工作目录；crop 路径也直接按当前工作目录解析，因此仓库样本应从仓库根目录运行。占位 crop 只用于测试产物链路，不是视觉证据；缺少 crop 会在修复报告中显示。不同源文件的同名 crop 可能覆盖，应在自有样本中使用唯一文件名。

续跑按 `doc + node_id` 查找 `OK` 或 `NEEDS_HUMAN` 终态并跳过，**不检查输入内容、模型或环境是否变化**。修改样本、修复依赖或更换模型后，请使用新的 `--state` 目录；否则此前待人工节点也会跳过。状态文件没有并发写入锁，不要让多个进程共享一个状态目录。

这些产物被 Git 忽略。报告保留累计事件；重复运行次数、既往提供方等需结合 `state.jsonl` 解释。CLI 正常结束的退出码不表示所有节点均通过，请同时查看各状态计数和报告。
