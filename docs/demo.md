# 演示与版本记录

## 当前本地工作流

安装与启动以[本地使用指南](local-studio.md)为准。工作台运行在本机浏览器中，先用 `math-clean.tex` 检查编辑和已准备好的编译环境，再用 `math-delimiters.tex` 审阅语法候选，或用 `report-01.tex` 核对确定性合计。采用、保存和编译当前版本后导出是不同动作。

图片/PDF 转写结果需对照原件审阅，再另建文档；复杂对齐和未知结构保留人工处理。当前实现及实测范围分别见[公式修复质量记录](formula-repair-quality.md)、[本地验收](local-studio-acceptance.md)与[视觉工作区验收](texada-visual-implementation.md)。操作 Skill 见[AgentSkills 使用指南](agent-skills.md)。

下列视频与旧截图保留对应版本的界面、等待时间和结果，不代表当前界面或当前规则的模型请求次数。

## 连续实录（历史版本）

归档视频是一段 **222.071 秒（约3分42秒）的连续浏览器实录**：从正常数学讲义出发，定位缺失定界符，等待真实模型返回候选，审阅 diff、采用并导出，最后查看积分语义反例。录制源码为 `87ca397`。

| 素材 | 用途 | 入口 |
| --- | --- | --- |
| `TeXada-Studio-真实动态录屏.mp4` | 完整操作、统一合成女声、中文字幕 | [B站播放](https://www.bilibili.com/video/BV16Kan6rEGv/) · [操作与结果](dynamic-demo.md) |
| `TeXada-Studio-原速无配音实录.mp4` | 核对同一区间的实际操作和等待 | [文件规格与摘要](media/dynamic-demo-manifest.json) |
| `TeXada-Studio-真实动态录屏.srt` | 配音版外挂字幕 | 同上 |

[B站完整视频](https://www.bilibili.com/video/BV16Kan6rEGv/)已发布，时长约3分42秒。

## 片中版本的操作与结果

以下步骤描述录制版本；当前启动方式见[本地指南](local-studio.md#启动和退出)。片中依次打开：

1. **`math-clean.tex`**：查看正常讲义，调整源码字号，切换预览的100%与适应模式。
2. **`math-delimiters.tex`**：分析并点击问题定位，生成候选，核对 diff 后采用，导出 PDF、源码和质检报告。
3. **`math-semantics.tex`**：积分值故意写成1；正确值是1/2，但语法检查和编译都会通过。
4. **`math-align-boundary.tex`**：录制时的分析器没有抽取多行公式；编译会指出文档错误。当前扫描器会识别常见数学环境，复杂对齐仍保留人工核对，不自动压平修复。

片中主案例只补上 `\right)`：1次模型请求、1处修改、编译失败→通过，任务总耗时70.86秒。这些耗时和请求数属于该次历史任务；当前先尝试确定性语法规则，复跑时以新任务记录为准。[操作证据](dynamic-demo-evidence.json) · [逐候选记录](dynamic-demo-trace.json) · [演示脚本](demo-script.md)。

13份 Studio 文档的用途见[案例手册](casebook.md)；新增8份数学样本的预期见[机器可读清单](../samples/studio-cases.json)。[编译复现](evaluation-results/studio-latex/README.md)可独立检查8份原稿与4份作者参考修订。

## 历史演示

| 版本 | 对应记录 |
| --- | --- |
| 176.4秒 LaTeX 分段讲解版、44.1秒公式短片 | 独立的67.99秒任务；省略等待并使用说明图卡。见[结果](demo-evidence.json)、[轨迹](demo-trace.json)、[媒体清单](media/demo-manifest.json)、[验收](media/validation.json) |
| 更早报表与试卷演示 | 见[历史任务存档](evaluation-results/studio-earlier/README.md)，保留成功候选及失败结果 |

旧版公开步骤与文案保留在[发布计划](launch-plan.md)。当前入口以本页顶部和[项目首页](../README.md)为准。
