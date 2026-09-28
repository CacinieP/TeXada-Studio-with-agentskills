# 当前架构与运行边界

TeXada 包含 Studio 交互界面和读取已有结构树的 CLI。两条路径共用公式校验脚本和本地模型提供方，但不是完全相同的执行管线。

```text
Studio 浏览器
  Monaco 本站资源 → FastAPI → 行内公式与简单 tabular 检查
                          → 本地 Ollama 文本候选 → SymPy 回判
                          → Tectonic 编译 → diff → 人工采用 → 导出

CLI 已有 layout.json
  Python harness → formula / table checker → 最多两次修复尝试
                 → state.jsonl → 本轮 report.md → 按输入与上下文指纹续跑
```

## Skills 与脚本

`SKILL.md` 提供触发说明、步骤、输入和限制。真实公式模型请求默认启用 Skill：CLI 使用 `--skill-mode on`，Studio 使用 `SKILL_MODE=on`。白名单宿主读取并验证 `doc-formula-verify/SKILL.md`，将实际正文加入系统消息，并记录 Skill 与提示哈希；off 保留基础提示和相同工具流程。Fixture 不加载正文、不请求模型。节点选择、检查器调用和重试仍由 Python 固定编排，未实现任意工具的自主规划，也不使用 MCP。逐个 Skill 的代码映射见 [Skills 技术报告](skills-technical-report.md)，受控实验见[研究协议](../samples/research/README.md)。

- `doc-formula-verify`：SymPy 语法校验脚本；检查器故障不得显示为通过。
- `doc-table-audit`：CLI 对结构化数据做合计校验；Studio 另有面向简单 LaTeX 表格的行解析和重算。
- `doc-report`：CLI 状态报告和 Studio 候选导出约定。
- `doc-layout-parse`：已有 layout 输入的准备说明；没有自动 PDF/OCR 解析器。
- `latex-cleanup`：独立 LaTeX 整理、编译和验证工具集；Studio 当前直接调用 Tectonic，未调用整个 Skill 工具链。
- `spark-ops`：操作者使用的用户级部署说明，未接入自动资源调度。

## Spark 上的实际使用

实测节点为 ARM64，GPU 报告 NVIDIA GB10。当前 Studio 配置的本地模型标签为 `qwen3.8:27b-q4_K_M`，标签和文件存在由节点 Ollama 查询得到，不据此断言模型官方架构。当前请求只有文本，没有传入图像。模型在节点内执行，浏览器通过受保护的服务访问结果。

没有实现 embedding、reranker、LiteLLM、llama-swap 或 16 路并发调度，也没有这些功能的吞吐评测。统一内存有利于在同一节点放置模型和工具，但不能据此推算相对消费级 GPU 的性能倍数。

## 状态和审阅

CLI 仅复用文档/节点标识、输入哈希与执行上下文哈希都匹配的终态。输入、crop 字节、模型参数、Skill 正文、检查器或依赖变化会自动重新检查；旧日志无哈希不能授权跳过。暂时性提供方或检查器故障记为 `resumable:false`，恢复后可在同目录重跑。每次原始检查、提供方调用、候选接受/拒绝都进入追加日志；报告按当前 `run_id` 统计。详见 [Harness 手册](../harness/README.md)。

Studio 在 `state/studio/jobs/<job_id>/` 保存 `job.json` 与逐候选 `events.jsonl`；服务重启后可按已知 job_id 查询已完成结果。执行中的任务仍依赖进程内存，中断后不自动续跑，读取旧任务会提示新建任务。页面尚无任务历史列表，也不能据此恢复未导出的浏览器编辑。只支持可信用户、一个 Uvicorn worker；单 worker 也不等于具备多用户隔离。

Studio 保留原文和候选模型；候选先进入 diff，用户点击采用后才进入编辑器，不自动保存到服务端，需导出保留。报告记录修改、内容哈希、编译结果、耗时与检查范围。语法可解析、PDF 可生成与数学含义正确是不同判断。行内公式使用逐行美元正则，注释或 verbatim 内的类似文本也可能被列为候选，未实现完整 TeX 上下文保护。

## 外部依赖

Monaco 固定版本资源随仓库分发，浏览器访问本站资源。Tectonic 首次可能下载 TeX 包；依赖安装和模型下载也需要网络。旧仪表盘含 KaTeX CDN，因此未宣称整套系统断网可用。
