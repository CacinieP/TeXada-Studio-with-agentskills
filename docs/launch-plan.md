# 发布与传播计划

状态：发布准备稿。仓库保持私有，尚未发帖、发布 Release、上传视频或启用公共演示。下文的发布时序从维护者决定公开当天算起，不是已安排的自动任务。

## 1. 项目要让谁在意

**一句话：TeXada 把 LaTeX 错误定位、修复候选和人工审阅放到一个编辑界面里。**

首个故事使用可复现的小错误：45 + 60 被写成 115，即使编译成功也可能错；工具提出 105，使用者看过 diff 再采用。第二个故事讲模型补下标的歧义，解释为什么需要人工审阅。不要以“全自动论文修复”作为标题。

| 受众 | 他们关心什么 | 适合的入口 | 希望获得的具体反馈 |
| --- | --- | --- | --- |
| 教师、科研写作者 | 能否发现常见错误，是否会误改 | 新版演示中的表格案例 + 演示页 | 一个经脱敏/原创的错误样本 |
| LaTeX / Python 开发者 | 能否安装、规则如何扩展 | README + fixture 快速开始 | 一次安装记录或最小复现 |
| 本地模型 / Agent Skills 开发者 | 候选如何回判，失败如何处理 | 技术征文 + 架构与验证记录 | 一个具体的工作流设计意见 |
| 赛事评委与参赛者 | 实现与设想是否分清，实机证据是否可信 | 完整演示 + 项目报告 | 对实现范围和复现证据的检查 |

GitHub 的 Open Source Guides 建议先说明具体价值，统一项目入口，再到相关用户所在的社区交流；这里据此先做小范围复现邀请，避免同时铺开多个无人维护的频道。[Finding Users](https://opensource.guide/finding-users/)

## 2. 单一入口与仓库展示

公开后的统一入口：`https://github.com/CacinieP/TeXada-Studio-with-agentskills`。所有短片、文章与活动介绍都回到该仓库；README 再分流到安装、演示和反馈。现阶段不要把私有仓库写成“任何人都可立即访问”。

- About：以 LaTeX 质检、修复候选、人工审阅为主；竞赛背景放 README，不让赛名遮住产品用途。
- Topics：`latex`、`python`、`sympy`、`fastapi`、`monaco-editor`、`ollama`、`tectonic`、`document-processing`、`agent-skills`。不加未实现的 OCR / autonomous-agent 能力标签。
- Homepage：有稳定页面后再填；目前留空，不挂带认证信息的节点 URL。
- 社交预览：已准备 `docs/images/social-preview.png`（1280 × 640，<1 MB），并保留可编辑 HTML 源文件。公开时在 Settings → Social preview 上传和检查裁切。
- 视频：大媒体单独托管，公开后补到 `docs/demo.md`，不把巨型视频直接塞入 Git 历史。
- 徽章：仅使用真实可核验状态；没有 CI 就不放 build passing，没有正式 Release 就不放版本下载或稳定版徽章。

Topics 名称本身是公开的，即使仓库私有，因此只使用通用技术标签。[Topics 文档](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)
GitHub 推荐社交预览使用 1280 × 640 图像、文件小于 1 MB；私有仓库的可用设置和分享行为有限，素材准备不等于已展示。[Social preview 文档](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)

## 3. 可直接使用的素材

| 素材 | 规格与用途 | 位置 / 状态 |
| --- | --- | --- |
| 仓库首页 | 中文 + 英文，案例、分层体验、命令和反馈入口 | `README.md` / `README.en.md` |
| 完整演示 | 8个场景，160.7秒（2分40.7秒）；剪去等候处明确标记 | 新版参赛材料；未上传 |
| 传播短片 | 36.4秒，新版第2、3场景原速节选；表格问题 → 候选 → 采用 | `TeXada-Studio-表格质检短片.mp4`；本地交付，尚未上传 |
| 社交分享封面 | 1280 × 640，文字与示意图，不冒充实机截图 | `docs/images/social-preview.png` |
| 深入技术文章 | 现有技术征文，讲模型与检查器的职责边界 | `technical-article.md` |
| 可复现实验材料 | 27例合成检查、3份新增 Studio 文档、实际调用关系与失败处理 | [案例手册](casebook.md)、[Skills 技术报告](skills-technical-report.md)；不是模型效果榜单 |
| 首个版本说明 | 候选预发布说明，发布时补提交与校验值 | `releases/v0.1.0-alpha.1-draft.md` |
| 贡献邀请 | 4 项有完成标准的任务草案 | `roadmap.md`，尚未代发 Issues |

新版演示明确标记已剪去的模型等候，保留实际任务结果、修复依据和人工采用的语境；旁白为合成语音。历史6.94秒、105.73秒仅作早前单次实测，不写成新版结果或稳定性能承诺。所有待传播画面均须脱敏，旧媒体不随新版自动分发。技术文章聚焦产品与实验，不列视频制作服务。

下一篇内容可围绕一个具体边界展开：为什么 `1+1=3` 会通过语法检查，或为何遇到百分比与会计括号应保留原文。附稳定案例 ID、复现命令和实际结果，引导读者贡献新的反例。这些选题现有源码可以复现，但尚未录制对应新短片；不要把27例契约匹配包装为100%纠错准确率。

## 4. 发布文案草稿

以下文案中的“发布”措辞只在公开链接和 Release 确认可访问后使用；私有试用邀请应改为“准备开源，欢迎受邀试跑”。

### 中文短介绍（动态 / 相关社群）

> 一份 LaTeX 报表能编译成功，合计却可能是错的。我们做了 TeXada Studio：把公式语法检查、简单表格合计、修复 diff 和人工确认放进一个界面。视频里的 45 + 60 被写成了 115，工具按规则提出 105；模型补下标的候选也必须由人核对。代码采用 AGPL-3.0-only，提供不需要 GPU 的 fixture 体验。目前是可信用户的实验原型，尚不支持自动 OCR 或多用户服务。欢迎带一个合成错误样本来试，反馈“哪里跑不起来、哪里不该改”。
>
> 项目：https://github.com/CacinieP/TeXada-Studio-with-agentskills

### 技术文章标题与开头

标题：**LaTeX 能编译，数字却可能是错的：TeXada 的候选修复与人工审阅**

开头：从 `45 + 60 = 115` 的合成报表讲起，先展示错误和 diff，再解释规则计算、模型候选、SymPy 解析、Tectonic 编译各自解决什么。正文复用现有技术征文，附真实耗时及限制；结尾邀请读者复现 fixture、贡献边界样本。

### English launch copy

> A LaTeX document can compile successfully and still contain an incorrect total. TeXada Studio brings syntax checks, simple table-total checks, local text-model suggestions, and explicit human review into one editor. In our synthetic demo, 45 + 60 was recorded as 115; a deterministic check proposes 105 and shows the diff before adoption. Model-generated formula candidates remain suggestions, not mathematical proofs. The project is an experimental single-process application for trusted documents, licensed under AGPL-3.0-only. A GPU-free fixture walkthrough is available. Automatic OCR and multi-user hosting are not implemented. We would especially welcome a reproducible installation report or a small synthetic edge case.
>
> Repository: https://github.com/CacinieP/TeXada-Studio-with-agentskills

## 5. 渠道与节奏

这是工作建议，不是已取得社区发帖许可。每次发布前检查目标版面的当前规则；技术问答网站用于回答具体问题，不投放与问题无关的广告。

| 时段 | 动作 | 渠道选择 | 负责人和完成标准 |
| --- | --- | --- | --- |
| 公开前 | 邀请 3 位目标用户从零试跑，收集卡点 | 已有联系渠道，一对一邀请须由团队发送 | 团队指定联系人；至少 3 份安装/体验记录，这是目标不是已完成数 |
| D0 | 公开仓库、核对源代码和匿名访问，再发布预发布版本 | GitHub README + Release | 仓库维护者；全新未登录浏览器能看文档和媒体 |
| D1–D2 | 发一个具体案例，附验收后的新版演示或新剪短片和统一入口 | 首选一个已有账号的中文技术平台，如掘金/知乎；B站承载视频可选 | 团队指定作者；正文和播放链接一致，能接住反馈 |
| D3–D5 | 深入解释失败处理、候选回判与 Skills | 现有技术征文；相关 LaTeX/Python 或本地模型社区 | 先按该社区规则分享，不批量重复投放 |
| D6–D7 | 汇总卡点，修文档并关闭已解决问题 | GitHub Issues / Changelog | 维护者；给反馈者可验证的修复版本 |
| 第 2 周 | 再选择一个英文开发者渠道 | GitHub 英文首页 + DEV Community；HN Show HN 仅在能直接试用且符合规则时考虑 | 有精力回复英文反馈后再扩展 |

先维护一个代码入口、一个反馈入口、一个内容渠道。暂不创建独立论坛、Discord、公众号矩阵或付费广告，也不承诺“上榜”。Discussions 可以在使用问答明显多于缺陷报告时再考虑开启。

## 6. 看什么指标

| 阶段 | 指标 | 记录方式与解读 |
| --- | --- | --- |
| 看见 | 页面访问、视频完播/评论 | 用平台可见汇总；不把曝光当使用 |
| 试用 | 安装开始人数、完成 fixture 人数、完成耗时 | 邀请用户自愿填写简短反馈；分母缺失时不报百分比 |
| 获得价值 | 找到真实卡点的反馈数、可复现合成案例数 | Issues 中去重；明确误改与漏检 |
| 参与 | 首次贡献、被合并的文档/测试改进 | 按 PR/Issue 记录，不只看 Star |
| 维护 | 未分类问题、重复问题、需要文档澄清的问题 | 每轮发布后人工整理；无自动定时任务 |

第一轮内部目标可设为：3 人试跑、找到并处理至少 2 个可复现卡点、形成 1 个外部贡献候选。没有达成前不在文章中写成成果。不新增软件内遥测；如未来需要收集数据，应单独设计说明与选择机制。

## 7. 对外发布的最后检查

按 [开源清单](open-source-release.md) 完成权限、历史、许可、漏洞渠道和源码对应关系审阅。Release 需要明确标记 prerelease，记录不可用能力和验证范围。所有对外文章、视频上传、社区发帖及仓库公开由维护者决定；本轮只准备文件与草稿。
