# CLI 质检管线

CLI 读取已有 `layout.json`，逐节点检查公式与表格，生成候选审阅报告，不写回输入。原始 `.tex` 的编辑、保存、PDF 预览和图片识别使用[本地 Studio WebUI](../docs/local-studio.md)。CLI 不提供 OCR 或 PDF 布局提取；已有 crop 只作为报告证据保留。已有 OCR 文本行可先通过[独立审阅转换器](../skills/doc-ocr-extract/LAYOUT.md)生成输入：逐行决定绑定 OCR 内容哈希，未审阅或无法解析的内容会阻止 `layout.json` 生成，不推断区域框或置信度。

## 跑通一个样本

在仓库根目录、Python 3.11+ 环境中执行。已安装 WebUI 依赖时，无需重复安装 harness 依赖：

```bash
.venv/bin/python -m pip install -r harness/requirements.txt
PYTHONPATH=harness .venv/bin/python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

预期：`exam-01 OK=3 NEEDS_HUMAN=0`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2 NEEDS_HUMAN=0`。查看 `state/quickstart/report.md`。fixture 标为 `fixture (offline test double)`；它只在需要时提供预设候选，确定性公式规则可能在此之前完成修复。整个命令没有模型请求，不能用结果衡量模型质量。

## 输入与输出

`run` 接受含 `layout.json` 的目录，或这些目录的父目录；只发现一层子目录。可一次传入多个样本目录。输入参考 [`paper-01/layout.json`](../samples/paper-01/layout.json)：

- 文档标识为 `doc`，同次运行须唯一；省略时使用目录名。
- 节点 `id` 在文档内唯一。公式用 `type="formula"`、`data.latex`；表格用 `type="table"`、`data.rows` 和可选 `data.expected`。
- 其他节点类型按 `pass-through` 记录，并标记未检查；其 `OK` 不是公式或表格验证结论。
- 可选 `data.crop` 相对当前工作目录解析，仓库样本应从仓库根目录运行。已有 crop 的内容哈希副本可进入报告，文本模型不会查看该图片。
- OCR 转换器可另外绑定操作者标注的原图区域：`source_image` 指向样本目录内的 `source.png`，节点 `ocr_source.region` 保存像素框。管线在检查或复用节点前核对原图哈希、尺寸和坐标范围；图片变化或缺失时拒绝运行。报告将原图快照及区域预览保存在运行目录，提供原图、带框标注图、放大图和 OCR 原文；来源事件绑定节点输入、上下文及 revision，续跑同样保留。这些预览不是独立 `data.crop` 或图像内容验收，详见[来源区域契约](../skills/doc-ocr-extract/LAYOUT.md#optional-operator-provided-source-regions)。

```text
state/quickstart/
├── report.md      # 本轮结果、候选差异、原因及复用来源
├── state.jsonl    # 追加保存各轮事件
└── crops/         # 可用 crop 的内容哈希副本
```

带 OCR 区域来源的运行还生成 `sources/`，包含哈希命名的原图 PNG 和带框/放大 SVG。移动或分享报告时保留整个运行目录；报告重建只读取这些快照，不要求原样本仍在。快照缺失或摘要不符时显示不可用，不生成预览。

样本 crop 为占位图，不是识别证据。CLI 不运行 Studio 的 TeX 源码扫描器或整篇编译；布局树需由调用方提供。退出码 `0` 表示管线完成，`2` 表示参数、输入或配置错误；节点是否通过以报告为准。

## 公式修复与表格边界

公式先运行 SymPy 语法检查器。`RETRY` 时先使用[共享保真规则](docforensics/formula_repair.py)生成候选：闭合确定的尾部 `}`、受支持的单个 `\left/\right` 配对或末尾 `\right` 缺匹配定界符，再由原检查器回判。该阶段不调用模型。原文已有内容保持不变，包括数学空白。

缺少操作数、歧义下标、重复上下标及已知解析器覆盖边界保留人工项，不补数、不删项。模型候选最多请求两次，使用原公式和有界 `repair_context` 反馈；语法通过之外仍需满足相同的来源修改范围约束。当前模型 fallback 不能扩大确定性规则已经授权的修复集合。重复候选停止，环境错误不触发继续猜测。规则范围、对照与局限见[公式修复质量记录](../docs/formula-repair-quality.md)。

表格脚本检查矩形网格、显式行列数和有限十进制合计，使用 Decimal 精确求和。非法参考合计或索引是 `bad_expectation`，不应请求模型修表；显式目标形状缺行/缺列仍可报告 `shape_mismatch`。fixture 可以提供替换网格，真实模型提供方不实现表格重提取。格式与状态契约见[表格 Skill](../skills/doc-table-audit/SKILL.md)。

所有通过检查的修改仍是候选。报告保留原文、差异和原因，使用者需要核对来源及数学含义；语法 `OK`、合计一致和编译成功都是不同结论。

## 选择提供方

| 参数 | 行为 |
| --- | --- |
| `--fixture-repairs <JSON>` | 必要时读取公式和表格的预设候选，无模型请求 |
| `--vlm <服务根地址或 /v1 地址> --vlm-model <模型>` | 必要时通过 OpenAI-compatible Chat Completions 请求公式文本候选 |
| 两者均省略 | 使用空 fixture；仍执行检查与确定性公式修复，无法处理的节点转人工 |

若同时提供，`--vlm` 优先。通用 CLI 提供方接受操作者配置的本机或授权云端地址，不继承 Studio 本地启动器的回环限制。接口使用 `VLM_API_KEY` 作为可选 Bearer 凭据；不将凭据加入提示、提供方指纹或报告。调用不需要鉴权的本机服务时应避免继承云 key，例如：

```bash
env -u VLM_API_KEY PYTHONPATH=harness .venv/bin/python -m docforensics run samples \
  --state state/model-local-01 \
  --vlm http://127.0.0.1:18147/v1 --vlm-model minicpm-v4.7-35b-a3b-q4 \
  --skill-mode on --seed 0 --max-tokens 300
```

该命令使用本机已有服务，不会启动或下载模型，模型名须与服务实际标签相符。需强制回环与无云 key 的本地产品流程时，使用[本地 Studio 启动器](../docs/local-studio.md#本机模型连接)。选择云端时先授权并在进程环境提供自己的凭据；不要把真实值写入命令示例、文档或仓库。旧云配置见[部署手册](../deploy/README.md#旧云-api-兼容入口)。

`OllamaProvider` 作为兼容别名保留，实际提供方为 `OpenAICompatibleProvider`。MiniCPM-V 4.7 请求关闭 thinking；响应须为只含一个非空 `latex` 字符串的严格 JSON，拒绝控制符、多行候选和不合法结构。该文本通道不因模型具有视觉能力就开始读取 crop。

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `--state` | `state/run1` | 事件和报告目录 |
| `--vlm-model` | `minicpm-v4.7-35b-a3b-q4` | 本机服务使用实际标签，可显式覆盖 |
| `--skill-mode` | `on` | 加载公式 Skill；`off` 用于对照 |
| `--seed` | `0` | 传给模型服务的 seed |
| `--max-tokens` | `300` | 每次响应的 token 上限 |

完整参数：`PYTHONPATH=harness .venv/bin/python -m docforensics run --help`。

`on` 读取白名单公式 `SKILL.md` 并加入系统消息；`off` 省略该正文，保留基础模型参数。模型事件保存加载、Skill 和提示哈希；fixture 不加载模型指令。固定 CLI 不启用 Studio 的可选规划或 Skill 选择实验。更多 Skill 边界见[当前指南](../docs/agent-skills.md)，历史对照见[研究协议](../samples/research/README.md)。

## 状态与请求记录

| 状态 | 行为 |
| --- | --- |
| `OK` | 检查通过，或允许的候选通过语法与范围校验，结束节点 |
| `RETRY` | 语法、形状或合计失败，按相应宿主规则尝试候选 |
| `NEEDS_HUMAN` | 保存未解决或不支持原因，继续下一个节点 |

检查器的 `NEEDS_ENV` 被保留为带 `env:` 原因的人工项，不会被当作可修语法错误。每个节点最多两次提供方候选请求；网络错误、无候选、重复响应等可提前结束，部分 JSON 协议错误可携反馈重试一次。确定性修复的 attempt 为 0，不占用模型尝试数。

`state.jsonl` 保留 `CHECK`、`DETERMINISTIC_REPAIR`、`PROVIDER_START/RESULT`、`CANDIDATE_SCOPE`、候选接受或拒绝、`REPAIR_SKIPPED`、`TERMINAL` 和 `SKIP`。记录中的模型调用数反映 HTTP 尝试，包含超时而不保证完成推理；fixture 和确定性修复为 0。未配对的开始事件会使报告显示已知下界。响应摘要最多保存 8192 字符并标注截断。

## 续跑

重复同一条 `run` 即可。每轮有独立 `run_id`，`report.md` 只统计本轮；历史事件留在 JSONL。

复用须同时匹配文档与节点 ID、输入哈希和执行上下文哈希。输入包含节点 JSON 和可用 crop 字节；上下文包含检查器、管线、保真修复策略、扫描器、依赖和提供方配置。任何一项变化都会重新检查。

匹配的可复用 `OK` / `NEEDS_HUMAN` 会产生 `SKIP`。暂时性模型或检查器故障标为 `resumable:false`，恢复后重跑会重新执行，不永久缓存为人工结论。缺少指纹的旧记录或自定义提供方重新检查。

同标签更换模型权重或服务实现时，用新的状态目录并记录模型 digest。一个状态目录只供一个进程写入。独立实验使用新目录，保留旧记录用于比较。

截至 `ceae9a7` 的本轮记录包括 123 项 harness 回归通过，仓库四组 Python 回归共 420 项通过。这是宿主行为覆盖；真实模型、OCR 与数学正确性需分别提供证据，不能由测试数量推导。
