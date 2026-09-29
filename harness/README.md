# CLI 质检管线

CLI 读取已有 `layout.json`，逐节点检查公式与表格，生成候选审阅报告。原始 `.tex` 的编辑和编译使用 [Studio](../README.md#2-打开-studio)。

## 跑通一个样本

在仓库根目录、已激活的 Python 环境中执行：

```bash
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

预期：`exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。查看 `state/quickstart/report.md`；提供方标为 `fixture (offline test double)`，候选来自预设 JSON。

## 输入与输出

`run` 接受含 `layout.json` 的目录，或这些目录的父目录；只发现一层子目录。可一次传入多个样本目录。输入参考 [`paper-01/layout.json`](../samples/paper-01/layout.json)：

- 文档标识为 `doc`，同次运行须唯一；省略时使用目录名。
- 节点 `id` 在文档内唯一。公式用 `type="formula"`、`data.latex`；表格用 `type="table"`、`data.rows` 和 `data.expected`。
- 其他节点类型按 `pass-through` 记录。可选 `data.crop` 相对当前工作目录解析，仓库样本应从仓库根目录运行。

```text
state/quickstart/
├── report.md      # 本轮结果、候选差异、原因及复用来源
├── state.jsonl    # 追加保存各轮事件
└── crops/         # 可用 crop 的内容哈希副本
```

CLI 保存检查和候选，不写回输入。样本 crop 为占位图；PDF/OCR 输入需先由其他流程转换为 layout。退出码 `0` 表示管线完成，`2` 表示参数、输入或配置错误；节点是否通过以报告为准。

## 选择提供方

| 参数 | 行为 |
| --- | --- |
| `--fixture-repairs <JSON>` | 读取公式和表格的预设候选，无模型请求 |
| `--vlm <服务根地址> --vlm-model <标签>` | 请求 `/v1/chat/completions`，修复公式 |
| 两者均省略 | 仅检查；遇到需修复节点时没有候选可用 |

若同时提供，`--vlm` 优先。模型接口接收文本，当前没有 API key 配置；CLI 可指定兼容端点，建议使用可信本机服务。模型提供方的表格修复尚未实现，相关节点进入人工处理。

```bash
ollama list
export VLM_MODEL='替换为已安装的完整模型标签'
PYTHONPATH=harness python -m docforensics run samples \
  --state state/model-01 \
  --vlm http://127.0.0.1:11434 --vlm-model "$VLM_MODEL" \
  --skill-mode on --seed 0 --max-tokens 300
```

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `--state` | `state/run1` | 事件和报告目录 |
| `--vlm-model` | `qwen2.5vl:7b` | 模型标签，建议显式指定已安装标签 |
| `--skill-mode` | `on` | 加载公式 Skill；`off` 用于对照 |
| `--seed` | `0` | 传给模型服务的 seed |
| `--max-tokens` | `300` | 每次响应的 token 上限 |

完整参数：`PYTHONPATH=harness python -m docforensics run --help`。

on 模式读取 `skills/doc-formula-verify/SKILL.md` 并加入系统消息；事件保存 `skill_loaded`、`skill_sha256` 和 `prompt_sha256`。Fixture 不加载 Skill。节点选择与重试由 Python 管线控制；三组模型对照见[研究协议](../samples/research/README.md)。

## 状态与请求记录

| 状态 | 行为 |
| --- | --- |
| `OK` | 检查通过，结束当前节点 |
| `RETRY` | 向提供方请求候选，再检查候选 |
| `NEEDS_HUMAN` | 保存原因，继续下一个节点 |

每个节点最多请求两次候选；无候选时提前结束。两次公式请求都基于原公式。检查器环境错误记为带 `env:` 原因的人工项，暂时性提供方故障也单独记录。

`state.jsonl` 保留 `CHECK`、`PROVIDER_START/RESULT`、候选接受或拒绝、`TERMINAL` 和 `SKIP`。`model_calls` 是 HTTP 尝试数，包含超时；未配对的开始事件会使报告显示已知下界。候选响应最多保存8192字符并标注截断。`OK` 是检查器结论，数学含义仍需核对。

## 续跑

重复同一条 `run` 即可。每轮有独立 `run_id`，`report.md` 只统计本轮；历史事件留在 JSONL。

复用须同时匹配文档与节点 ID、输入哈希、执行上下文哈希。上下文包含检查器、管线、依赖和提供方配置；输入包含节点 JSON 和可用 crop 字节。变化时自动重查。

匹配的可复用 `OK` / `NEEDS_HUMAN` 会产生 `SKIP`。暂时性模型或检查器故障标为 `resumable:false`，环境恢复后重跑即可重试。缺少指纹的旧记录和自定义提供方重新检查。

同标签更换模型权重或服务实现时，用新的状态目录并记录模型 digest。一个状态目录只供一个进程写入。独立实验使用新目录，保留旧记录用于比较。
