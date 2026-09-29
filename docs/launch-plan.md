# 发布与传播计划

源码、报告和[B站实机视频](https://www.bilibili.com/video/BV16Kan6rEGv/)作为公开入口。微信公众号征文由作者审核后手动发布，文章链接待补；尚未创建 tag 或 GitHub Release。

## 受众与主线

**TeXada 将 LaTeX 错误定位、修复候选和人工审阅放进同一个编辑器。**

首个案例用缺少闭合定界符的分式：定位源码、查看模型候选、核对 diff、采用并导出。随后展示能编译却算错的积分等式，让读者看到检查器和人工判断各自处理什么。

| 受众 | 内容入口 | 希望获得的反馈 |
| --- | --- | --- |
| 教师、科研写作者 | 连续实录、正常讲义与积分反例 | 一个原创或获授权的错误样本 |
| LaTeX / Python 开发者 | README、无需模型的 fixture | 安装卡点、最小复现或规则改进 |
| 本地模型 / Agent Skills 开发者 | 技术文章、架构、三组对照 | 候选回判、失败处理和指令加载的具体建议 |
| 赛事评委与参赛者 | 完整演示、项目报告、验证记录 | 按文档复现实现与结果 |

## 发布素材与统一入口

统一入口为[项目仓库](https://github.com/CacinieP/TeXada-Studio-with-agentskills)，README 连接安装、演示和反馈。

| 素材 | 当前版本与位置 |
| --- | --- |
| 主视频 | [B站完整实录](https://www.bilibili.com/video/BV16Kan6rEGv/)，约3分42秒；录制源码 `87ca397`，见[动态演示](dynamic-demo.md) |
| 无配音版 | 与主片相同的连续画面，保留完整操作和模型等待；摘要见动态演示页 |
| 技术文章 | [微信公众号审核稿](technical-article.md)，作者手动发布后补公共链接 |
| 复现材料 | [13份Studio文档](../samples/README.md)、[27个检查案例](../samples/evaluation/README.md)、[12项编译复现](evaluation-results/studio-latex/README.md) |
| 封面 | [social-preview.png](images/social-preview.png)，1280×640 |
| 版本说明 | [预发布草案](releases/v0.1.0-alpha.1-draft.md) |
| 贡献入口 | [路线图](roadmap.md)、[贡献说明](../CONTRIBUTING.md) |

主片中的定界符任务耗时70.86秒，产生1次模型请求和1处编辑，前后编译失败→通过，完成采用和三类导出。任务耗时与整片时长分别标注。早期讲解素材从[演示页](demo.md)的历史入口查阅。

仓库 About、社交封面与 Topics 随功能更新；Topics 使用 `latex`、`python`、`sympy`、`fastapi`、`monaco-editor`、`ollama`、`tectonic`、`agent-skills`。视频托管于B站，仓库保存摘要与复现证据。每次版本发布按[开源清单](open-source-release.md)核对许可、源码和附件。

## 渠道与执行顺序

先维护 GitHub 代码与反馈入口，再选择一个团队能持续回复的内容渠道。

| 阶段 | 执行动作 | 完成标准 |
| --- | --- | --- |
| 首轮试跑 | 团队邀请3位目标用户按README试跑 | 收到3份环境、运行结果和卡点记录 |
| 首次版本发布 | 从选定提交创建带源码与校验值的预发布版本 | tag、附件和记录对应同一提交 |
| 微信公众号 | 作者审核征文与配图后手动发布 | 回填文章链接，文章与B站视频都指向项目仓库 |
| 首周后半段 | 向相关LaTeX、Python或本地模型社区分享复现方法 | 按社区规则发布，逐条回应具体问题 |
| 下一轮 | 汇总反馈，修正文档或样本，更新CHANGELOG | 每个已解决问题都有可验证的版本或命令 |
| 英文扩展 | 有精力接收英文反馈时，再发布DEV文章 | 英文安装步骤与当前README一致 |

每轮记录：试跑完成数、可复现问题数、已解决卡点和收到的贡献。第一轮目标为3人试跑、解决2个卡点、形成1个外部贡献候选；这些是待完成目标。

## 可直接使用的文案

试跑邀请：

> TeXada Studio 已开放源码，欢迎按 README 试跑。它把 LaTeX 源码定位、修复候选、diff 和人工采用放进一个界面。我们准备了13份文档和无需GPU的运行入口，希望收集安装卡点，以及一个你认为值得检查的合成错误样本。

项目介绍：

> 一份分式缺少闭合定界符，另一份积分等式能编译却算错。TeXada Studio 用这两个例子展示源码检查、模型候选和人工审阅。完整视频保留真实操作和等待，仓库提供13份文档、离线样本和编译复现步骤。欢迎试跑并反馈具体问题。
>
> 项目：https://github.com/CacinieP/TeXada-Studio-with-agentskills

英文介绍：

> TeXada Studio brings LaTeX checks, local model suggestions, a source diff, and human review into one editor. The continuous demo follows a missing delimiter through repair and export, then examines an incorrect integral that still compiles. Try the 13 sample documents and the GPU-free walkthrough, and share a reproducible issue or a small synthetic example.
>
> Repository: https://github.com/CacinieP/TeXada-Studio-with-agentskills
