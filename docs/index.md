# 文档导航

从[首页快速开始](../README.md)运行无需模型的示例，再按目标进入下列文档。

| 目标 | 入口 | 能找到什么 |
| --- | --- | --- |
| 看完整操作 | [连续实录](dynamic-demo.md) | 源码编辑、候选审阅、完整等待与导出 |
| 本地运行与排错 | [README](../README.md) · [English](../README.en.md) · [排错](troubleshooting.md) | 安装、启动、模型配置和常见故障 |
| 选择样本 | [样本目录](../samples/README.md) · [案例手册](casebook.md) | `.tex`、结构化输入、逐例预期 |
| 使用 CLI | [Harness 手册](../harness/README.md) | 输入结构、参数、报告和续跑 |
| 复现检查器行为 | [27 个检查案例](../samples/evaluation/README.md) | 运行命令、预期状态与结果解释 |
| 比较 Skill 指令 | [研究协议](../samples/research/README.md) · [先导实验解读](skills-pilot-analysis.md) | 三组对照、来源、候选和人工复核 |
| 理解实现 | [架构](architecture.md) · [Skills 技术报告](skills-technical-report.md) | 模块关系、指令加载和修复流程 |
| 查看已有验证 | [验证记录](validation.md) · [编译记录](evaluation-results/studio-latex/README.md) | 当次输入、环境和结果 |
| 修改项目 | [贡献说明](../CONTRIBUTING.md) · [路线图](roadmap.md) | 开发约定、相关测试和后续工作 |
| 部署与维护 | [部署手册](../deploy/README.md) · [安全说明](../SECURITY.md) | 配置、升级、数据备份和信任边界 |

## 项目、赛事与发布

- 项目介绍：[项目报告](project-report.md)、[技术征文](technical-article.md)、[提交清单](submission-checklist.md)。
- 发布准备：[开源清单](open-source-release.md)、[准备度记录](open-source-readiness.md)、[发布与传播计划](launch-plan.md)、[Release 草案](releases/v0.1.0-alpha.1-draft.md)。
- 维护记录：[CHANGELOG](../CHANGELOG.md)、[迁移记录](repository-migration.md)、[隐私扫描记录](security-scan-notes.md)。
- 引用项目：[CITATION.cff](../CITATION.cff)，同时注明所用提交号。

演示原始证据从[演示页](demo.md)和[连续实录页](dynamic-demo.md)进入。历史报告保留各自的输入、环境和时间条件；当前操作方式以 README 和模块手册为准。

## 变更时同步哪些文档

| 改动 | 同步检查 |
| --- | --- |
| 依赖、启动或配置 | 中英文 README、部署、排错 |
| 输入契约与检查器 | Skill、案例定义、案例手册、技术报告 |
| CLI 状态、重试或报告 | Harness 手册与相关回归 |
| Skill 请求与研究协议 | 研究说明、架构、技术报告 |
| Studio 交互 | README、案例手册；需要时更新演示 |
| 版本与发布 | CHANGELOG、发布清单、首页状态 |

每个主题保留一个主要说明，其他页面链接到它。新增结果另存运行目录；文档引用准确的输入和结果，不覆盖既有实验记录。
