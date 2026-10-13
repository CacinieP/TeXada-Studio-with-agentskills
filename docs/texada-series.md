# TeXada 系列：从公式输入到文档审阅

记录日期：2026-10-13。本文及配套系列材料为本地审阅稿，待审阅后发布。

![TeXada 系列 · Math Agent 与 Studio](../assets/texada-series-poster.png)

TeXada 系列使用 MiniCPM 连接两类工作：先把公式描述、截图或未完成片段变成 LaTeX 候选，再把公式放回文档中检查和审阅。各仓库保留自己的运行方式、发布节奏和许可证，通过清楚的入口组成一个系列。

## 两个工具的职责

| 项目 | 当前输入与任务 | 使用方式 | 源码许可证 |
| --- | --- | --- | --- |
| [TeXada Math Agent](https://github.com/CacinieP/TeXada-the-Math-Agent) | 自然语言转公式、公式图片 OCR、LaTeX 补全；通过 Agent 工具检查候选 | 桌面应用及其后端；MiniCPM-V 4.7-1B 单模型 profile 在本机适配，尚未发布 | 当前开发版本 `AGPL-3.0-or-later`；历史标签以标签内声明为准 |
| [TeXada Studio](https://github.com/CacinieP/TeXada-Studio-with-agentskills) | MiniCPM 生成公式候选；单个 `.tex` 中的公式语法和简单表格合计，diff 审阅、采用与导出 | Monaco / Python 工作台、Skill 任务包和 Tectonic 预览；本轮加入 MiniCPM-V 4.7-1B API 适配 | 原创代码、文档与合成样本 `AGPL-3.0-only`；第三方内容保留自身许可 |

共同设计方向是：**生成候选 → 确定性检查 → 展示证据与差异 → 使用者决定是否采用**。两个项目已有各自的检查和记录方式，统一接口与统一报告格式属于后续迭代。

Studio 的具体支持范围、启动依赖与现有模型配置以 [README](../README.md) 为准，Skill 加载与状态管理见 [技术报告](skills-technical-report.md)。

## 今天可以怎样搭配使用

1. 在 Math Agent 中输入公式描述、粘贴公式截图或补全 LaTeX 片段。
2. 对照原始描述或截图审阅候选，复制要采用的 LaTeX。
3. 把公式手动粘贴进单个 `.tex` 文件，在 Studio 中编辑或上传该文件。
4. 运行公式语法与简单表格检查，查看候选 diff，再决定是否采用。
5. 按需用 Tectonic 编译并查看第一页预览，导出 `.tex`、PDF 和质检报告。

当前交接方式是复制 LaTeX，两个应用分别启动和配置。Studio 目前按行提取 `$...$` 公式，使用这一链路时应选符合该输入范围的样例。完整 LaTeX 项目、文档 OCR 与多行公式提取见 Studio [路线图](roadmap.md)。

语法、编译和数学结论需要分别判断。例如 `\int_0^1 x\,dx = 1` 可具有合法语法并成功编译，正确值仍是 `1/2`。使用者需要结合原意与检查证据作决定。

## MiniCPM-V 4.7 在系列中的位置

本轮两个工具均适配 `MiniCPM-V-4.7-1B`，在本机通过 ModelBest 的 OpenAI-compatible API（`https://api.modelbest.cn/v1`）验证。Math Agent 用同一个模型承担文本和视觉职责；Studio 用它生成公式文本修复候选，继续由检查器回判，再由使用者审阅 diff。Math Agent 的 4.7 链路是可选 profile，现有公开主线的默认配置以各仓库发布记录为准。

模型来源：[官方 1B checkpoint](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B) · [官方 GGUF 仓库](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B-gguf)。Q4 本机部署仍需单独完成兼容性、效果和资源验收；本轮 API 结果不能代表量化后的结果。

Studio 通过 `scripts/run-minicpm-v47-studio.sh` 显式选择 4.7 API profile，通用启动入口仍保留本机服务配置；具体命令见 [README](../README.md#3-接入真实模型)。两项目的发布、真实候选质量与 Skill 对照证据分别记录。接入同一模型之后，两个工具仍保留各自的输入范围和检查方式。

## 系列迭代顺序

| 顺序 | 产物 | 验收条件 |
| --- | --- | --- |
| 本轮：系列入口与模型适配 | 两个仓库互链、中英文介绍、系列海报与 MiniCPM-V 4.7-1B API 配置 | 能从任一仓库找到另一工具；模型适配、候选检查与发布状态写清楚 |
| 下一步：跨工具案例 | 同一原创公式的原始输入、Math Agent 候选、Studio 文档、diff 与编译证据 | 手动交接可重现；分别记录模型、提交号、检查结果和人工结论 |
| 后续：可选连接器 | 经讨论后定义交接字段、失败状态和人工采用点，再实现导入或 API | 用固定案例验证；连接失败不丢失源文档；用户仍能审阅每次采用 |

后两项是路线计划。仓库链接和手动工作流已经足以让两个项目形成系列，后续连接器按实际案例需要推进。

## 维护与许可记录

本文以 Studio `f738799a7271efc9e4c10420c52e4b347b623bff` 为基线整理；已有技术材料见 [项目报告](project-report.md)、[演示与证据](dynamic-demo.md)及 [Skill 技术报告](skills-technical-report.md)。

各仓库保留自身许可证与第三方声明。Studio 见 [LICENSE](../LICENSE) 和 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)；Math Agent 见其 [LICENSE](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/main/LICENSE) 和 [项目说明](https://github.com/CacinieP/TeXada-the-Math-Agent)。发布系列材料时同时核对当前提交和状态日期。

## English overview

The MiniCPM-driven TeXada series connects two complementary tools: Math Agent handles desktop natural language to formulas, formula OCR, and LaTeX completion; Studio generates formula repair candidates, checks syntax and simple table totals in a single `.tex` file, presents candidate diffs, and provides Tectonic previews. The current handoff is manual: copy a reviewed formula's LaTeX from Math Agent into a Studio document.

As of 2026-10-13, both tools are adapting MiniCPM-V 4.7-1B locally through the ModelBest API at `https://api.modelbest.cn/v1`. Math Agent uses the same model for text and vision; Studio sends formula text for repair candidates. Publication and candidate quality evidence remain separate acceptance steps. Q4 deployment requires separate acceptance. A shared import interface and report format are future work; source licenses remain `AGPL-3.0-or-later` for Math Agent's current development and `AGPL-3.0-only` for Studio's original materials.
