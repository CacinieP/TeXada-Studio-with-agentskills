# 验证记录

TeXada Studio with Agent Skills · LinguistsWantTech。以下按验证对象记录输入、环境和结果；运行命令见[README](../README.md)、[案例手册](casebook.md)和[研究协议](../samples/research/README.md)。

## 文档复现核对（2026-09-29）

本轮整理文档并增加样本编译运行器，应用运行时、Skill正文及样本输入保持原版本。使用本机Python 3.13和Tectonic 0.16.9完成以下核对；项目最低Python版本统一为3.11。

| 检查 | 实际结果 | 复现入口 |
| --- | --- | --- |
| CLI fixture首跑 | 7个`OK`、1个`NEEDS_HUMAN`，模型HTTP请求0次 | [快速开始](../README.md#1-先跑无需模型的样本) |
| 相同输入续跑 | 8个`SKIP` | [Harness手册](../harness/README.md) |
| 确定性检查器 | 27/27符合预期 | [检查案例](../samples/evaluation/README.md) |
| 三组评测流程 | dry-run和fixture运行完成，模型HTTP请求0次 | [研究协议](../samples/research/README.md) |
| Studio样本编译 | 12/12符合预期：7份PDF、5份预期失败 | [编译命令与判定](evaluation-results/studio-latex/README.md) |
| 编译输出保护 | 已有目录被拒绝且内容不变；缺编译器时不创建输出目录 | `scripts/compile_studio_cases.py` |
| 文档一致性 | 中英文命令、本地链接和锚点通过核对，`git diff --check`通过 | [文档导航](index.md) |

编译运行器核对输入摘要、退出码、PDF产物和对应诊断。8份原稿与4份作者参考修订均从固定输入生成；参考修订来自作者。新输出另存运行目录，[原始编译档案](evaluation-results/studio-latex/compilation.json)保留不变。

## 当前连续实录（2026-09-29）

录制源码为`87ca397`，连续区间222.071秒，完整保留模型等待。S06完成1次真实模型请求；服务端任务总耗时70.86秒，包含检查、请求与前后编译。

| 项目 | 实际结果 |
| --- | --- |
| 定界符修复 | 仅补`\right)`，编译失败转为成功；人工采用后完成PDF、TeX和报告下载 |
| 编辑与预览 | 注释键入后撤销，原文逐字一致；三次“适应”恢复整页；语义反例L18可见 |
| 页面与样本 | 浏览器页面错误0，侧栏列出13份文档 |
| 媒体核对 | 两份成片完整解码通过，444处原片时间对应抽样通过；7个场景、44条操作、30条字幕记录完整 |

[操作与下载证据](dynamic-demo-evidence.json) · [逐候选轨迹](dynamic-demo-trace.json) · [媒体清单](media/dynamic-demo-manifest.json) · [媒体验收](media/dynamic-demo-validation.json)。

7段旁白现使用同一份合成女声参考，见[一致性记录](media/narration-consistency.json)。录屏继续使用同一连续原片。重做操作的步骤见[演示脚本](demo-script.md)。

## 既有自动回归

下表汇总运行时及样本开发阶段已执行的检查。本次文档整理没有重跑这些完整测试组。Python环境为3.13.13、SymPy 1.14.0、ANTLR 4.11.0；完整命令列于README。

| 检查组 | 最近记录 | 覆盖内容 |
| --- | ---: | --- |
| Web Python | 55项通过 | 输入与接口、任务记录、编译隔离、候选事件和样本契约 |
| Harness Python | 57项通过 | Skill加载、请求序列化、故障分类、上下文绑定续跑与日志恢复 |
| 两个评测运行器 | 35项通过 | 检查器11项、Skills三组运行器24项；输入协议、超时、盲审导入及输出保护 |
| Studio JavaScript | 通过 | 页面逻辑、候选与报告内容 |
| latex-cleanup | Python 77项、JavaScript 37项通过 | 导入模块的检查与整理逻辑 |
| 开放样本重建 | 12条输入逐字节一致 | 固定来源、提取规则及许可摘要 |

27个检查案例另有[逐例响应](evaluation-results/checker-report.md)和[JSON记录](evaluation-results/checker-report.json)，包括24个契约案例和3个语义边界。现有13份Studio文档中，新增S06–S13共8份；检查器案例、CLI节点与研究输入各用各自的分母。

## Skills先导实验

固定输入来自6条Active Calculus公式及6条注入变体。三组共36条结果，实际发起17次HTTP尝试，含1次超时。两个模型组各有5个候选被语法接受，最终文本差异为0/12；独立人工语义复核待完成。

输入、配置、候选和清单见[先导档案](evaluation-results/skills-pilot/manifest.json)，分析与复核步骤见[实验解读](skills-pilot-analysis.md)。此次文档核对运行的是dry-run/fixture，真实模型先导记录仍为原实验。

## 历史演示

| 版本 | 当时结果 | 证据 |
| --- | --- | --- |
| 176.4秒LaTeX讲解版，`dff5fc6` | S06单次任务67.99秒，1次模型请求、1处修复；等待段有省略标注 | [结果](demo-evidence.json)、[轨迹](demo-trace.json) |
| 160.7秒报表与试卷版，`e0cc8f8` | 报表合计修复，任务6.96秒；试卷任务150.98秒，缺失下标的两次候选被拒绝，编译仍失败 | [失败归档](evaluation-results/studio-earlier/README.md) |
| 早期节点演示 | 报表与试卷任务分别6.94秒、105.73秒；包括人工核对下标候选 | [整理前的历史记录](https://github.com/CacinieP/TeXada-Studio-with-agentskills/blob/fd58759/docs/validation.md) |

各耗时均是当次服务端任务总耗时。视频、实验与源码按各自版本追溯，演示文件入口见[演示索引](demo.md)。

## 后续验证

优先完成独立语义复核和外部用户安装复现。多来源自然错误、强制终止后的任务恢复、全流程断网及多用户并发仍需专项验证，安排见[路线图](roadmap.md)。
