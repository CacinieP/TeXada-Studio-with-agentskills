# 演示

最新演示是一段 **222.071 秒（约3分42秒）的连续浏览器实录**：从正常数学讲义出发，定位缺失定界符，等待真实模型返回候选，审阅 diff、采用并导出，最后查看积分语义反例。录制源码为 `87ca397`。

| 素材 | 用途 | 入口 |
| --- | --- | --- |
| `TeXada-Studio-真实动态录屏.mp4` | 完整操作、统一合成女声、中文字幕 | [操作与结果](dynamic-demo.md) |
| `TeXada-Studio-原速无配音实录.mp4` | 核对同一区间的实际操作和等待 | [文件规格与摘要](media/dynamic-demo-manifest.json) |
| `TeXada-Studio-真实动态录屏.srt` | 配音版外挂字幕 | 同上 |

视频已本地交付，公共播放地址待补；仓库仍为私有。

## 自己操作一遍

按 [README](../README.md) 启动 Studio，准备本地模型、Tectonic 和 Poppler，然后依次打开：

1. **`math-clean.tex`**：查看正常讲义，调整源码字号，切换预览的100%与适应模式。
2. **`math-delimiters.tex`**：分析并点击问题定位，生成候选，核对 diff 后采用，导出 PDF、源码和质检报告。
3. **`math-semantics.tex`**：积分值故意写成1；正确值是1/2，但语法检查和编译都会通过。
4. **`math-align-boundary.tex`**：当前分析器没有抽取多行公式；编译会指出文档错误。

本次主案例只补上 `\right)`：1次模型请求、1处修改、编译失败→通过，任务总耗时70.86秒。复跑时以实际候选和检查结果为准。[操作证据](dynamic-demo-evidence.json) · [逐候选记录](dynamic-demo-trace.json) · [演示脚本](demo-script.md)。

13份 Studio 文档的用途见[案例手册](casebook.md)；新增8份数学样本的预期见[机器可读清单](../samples/studio-cases.json)。[编译复现](evaluation-results/studio-latex/README.md)可独立检查8份原稿与4份作者参考修订。

## 历史演示

| 版本 | 对应记录 |
| --- | --- |
| 176.4秒 LaTeX 分段讲解版、44.1秒公式短片 | 独立的67.99秒任务；省略等待并使用说明图卡。见[结果](demo-evidence.json)、[轨迹](demo-trace.json)、[媒体清单](media/demo-manifest.json)、[验收](media/validation.json) |
| 更早报表与试卷演示 | 见[历史任务存档](evaluation-results/studio-earlier/README.md)，保留成功候选及失败结果 |

当前默认传播连续实录。公开步骤与文案见[发布计划](launch-plan.md)。
