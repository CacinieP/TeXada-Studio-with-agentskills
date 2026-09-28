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

当前只有 `run` 子命令；没有独立的 `resume` 或 `report` 子命令。重复执行同一条 `run` 即续跑；每轮生成独立 `run_id`，结束时重写仅统计本轮的 Markdown 报告，历史事件仍保留。

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

## Skill 指令与受控对照

真实模型模式默认 `--skill-mode on`：白名单宿主读取 `skills/doc-formula-verify/SKILL.md`，校验元数据与路径，将实际指令正文加入系统消息。`--skill-mode off` 保留相同基础提示、模型、检查器及重试流程，用于对照。`--seed` 默认 0，`--max-tokens` 默认 300；服务端是否支持严格 seed 重现需另外确认。Fixture 不加载指令、不请求模型，不能作为 on/off 效果实验。

```bash
PYTHONPATH=harness python -m docforensics run samples \
  --state state/model-skill-off \
  --vlm http://127.0.0.1:11434 --vlm-model "$VLM_MODEL" \
  --skill-mode off --seed 0 --max-tokens 300
```

当前宿主只为公式模型请求加载这一个 Skill，节点选择、工具调用和重试仍由 Python 固定编排。其他 Skill 的说明与工具不因此变成自动规划能力。有效加载与调用证据写入提供方事件中的 `skill_loaded`、`skill_sha256` 和 `prompt_sha256`。

完整三组研究入口见[研究协议](../samples/research/README.md)与[受控对照运行器](../scripts/evaluate_skills.py)：只有检查器、同模型无 Skill、同模型有 Skill。先运行 dry-run 或明确的 fixture；真实模型运行必须显式启用，人工复核未完成前不报告语义准确率。

## 检查、修复与终态

| 状态 / 事件 | 当前行为 |
| --- | --- |
| `OK` | 当前检查通过；不等于数学语义正确 |
| `RETRY` | 检查器认为可尝试修复，调用提供方取得候选后重新检查 |
| `NEEDS_HUMAN` | 重试耗尽、提供方无候选或检查环境缺失等情况，写入报告并继续后续节点 |

每个节点最多调用修复提供方 **2 次**；若提供方没有返回候选，会提前结束。公式检查器的 `NEEDS_ENV` 被记录为带 `env:` 原因的 `NEEDS_HUMAN`，不是检查通过。提供方另记超时、网络/HTTP 错误、空响应及 JSON 协议错误等分类；不把端点凭据或异常原文写入日志。`model_calls` 统计实际 HTTP 请求尝试，超时也计入，不能解释为完成推理的次数。Fixture 为 0；无统计契约的自定义提供方会明确标为计数未知。

两次公式修复请求都基于节点原始公式，不是把上次失败候选持续反馈给模型。当前实现也没有图像重识别、LiteLLM 路由、多模型调度或检索。

## 输入、输出与续跑

`run` 接受含有 `layout.json` 的样本目录，或这些目录的父目录。输入结构可参考 [`samples/paper-01/layout.json`](../samples/paper-01/layout.json)；公式使用 `data.latex`，表格使用 `data.rows` 与 `data.expected`。其他节点类型仅按 `pass-through` 记录为 `OK`，不代表做过质检。

```text
<--state 指定目录>/
├── state.jsonl     # 追加事件：run_id、检查、每个候选、终态和 SKIP
├── report.md       # 本轮统计与审阅内容；历史事件留在 JSONL
└── crops/          # 有可用 crop 时按内容哈希命名复制
```

`--state` 默认是 `state/run1`。路径相对于运行命令的工作目录；crop 路径也直接按当前工作目录解析，因此仓库样本应从仓库根目录运行。占位 crop 只用于测试产物链路，不是视觉证据；缺少 crop 会在修复报告中显示。复制的 crop 使用内容哈希命名，原路径相同但字节变化也会改变输入指纹。

续跑同时比较 `doc + node_id`、`input_sha256` 和 `context_sha256`。输入哈希绑定规范化节点 JSON 与可用 crop 字节；上下文包含检查器、管线实现、Python/依赖版本及提供方指纹，后者覆盖模型、参数、Skill 正文与 fixture 内容。输入或这些上下文改变时，同一目录自动重新检查。旧日志无哈希不授权跳过；未知提供方没有稳定指纹时不复用。需要完全独立的实验时仍使用新目录。

只有匹配且可复用的 `OK` / `NEEDS_HUMAN` 终态才生成 `SKIP`。暂时性模型服务或协议故障、检查器环境故障标记 `resumable:false`，服务恢复后重复同一命令会再次检查；语法重试耗尽和明确人工边界可复用，需由人工决定下一步。一个 layout 内拒绝重复节点 ID。当前模型身份使用标签及请求配置，不主动查询权重摘要；同标签替换权重或服务实现升级时，应使用新状态目录并另存模型 digest/服务版本。状态文件没有并发写入锁，不要让多个进程共享一个状态目录。

`state.jsonl` 逐行追加并刷新到磁盘，损坏行与非对象 JSON 不阻止重放。事件包含原始 `CHECK`、`PROVIDER_START` / `PROVIDER_RESULT`、每次 `CANDIDATE_ACCEPTED` / `CANDIDATE_REJECTED`、`TERMINAL` 和 `SKIP`。拒绝候选与检查器原因同样保留；提供方原始候选响应最多保存 8192 字符并标注是否截断。接受仅表示检查器通过，不表示使用者已经采用。

这些产物被 Git 忽略。当前报告按 `run_id` 统计，复用节点展示其来源运行和历史终态候选，不把历史请求计入本轮。终态保留最终通过候选以兼容原报告字段，源文件始终不写回。CLI 正常结束的退出码不表示所有节点均通过，请同时查看状态、失败原因与人工项。
