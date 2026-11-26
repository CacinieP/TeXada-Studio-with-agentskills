# 文档总索引

本目录按**日常使用、版本发布、系统架构、验证评测、协作打包**五类整理全部项目文档。

## 一、用户手册与本地部署

| 目标 | 推荐入口 | 说明 |
| --- | --- | --- |
| 日常下载安装与功能上手 | **[用户手册（README）](../README.md)** · **[English Manual](../README.en.md)** | 桌面端安装、界面导览、模板/编译/识图/审阅修复、模型配置与快捷键 |
| 源码启动、命令行与数据目录 | [本地部署与开发指南](local-studio.md) | 虚拟环境、启动器参数、离线 TeX 预热、回归测试与本地 API |
| 排查安装、连接、编译或保存异常 | [安装与使用排错](troubleshooting.md) | 401 会话、模型连接、PDF 预览、OCR 页数与版本冲突排查 |
| 在外部 Agent 中接入本仓库 Skill | [AgentSkills 使用指南](agent-skills.md) | 7 个技能包的职责边界、运行时白名单与外部调用方式 |

## 二、版本发布与变更日志（`docs/changelog/` & `docs/releases/`）

- **总览与流水账**：[版本发布与变更日志总览](changelog/README.md) · [完整 CHANGELOG](changelog/CHANGELOG.md) · [latex-cleanup 子模块版本记录](../skills/latex-cleanup/CHANGELOG.md)
- **正式版发布说明**：[v0.1.4（最新）](releases/v0.1.4.md) · [v0.1.3](releases/v0.1.3.md) · [v0.1.2](releases/v0.1.2.md) · [v0.1.1](releases/v0.1.1.md) · [v0.1.0](releases/v0.1.0.md)
- **早期预发布与准备记录**：[v0.2.0-beta.4](releases/v0.2.0-beta.4.md) · [开源发布清单](open-source-release.md) · [开源准备度](open-source-readiness.md) · [发布计划](launch-plan.md) · [迁移记录](repository-migration.md) · [隐私扫描记录](security-scan-notes.md)

## 三、系统架构与专题设计（`docs/architecture/`）

- **总体架构**：**[系统架构与设计总览](architecture/README.md)**（双平台桌面壳、FastAPI 工作区宿主、AgentSkills 零信任守卫、托管模型与 MiniCPM 1B 结构化约束）
- **核心专题设计**：
  - [AgentSkills 技术设计报告](architecture/skills-technical-report.md)：四态检查器协议、Skill 指纹与 CLI 事件续跑机制
  - [受限 Agent 规划器设计](architecture/constrained-planner.md)：默认关闭的 12 步状态机、动作掩码与审计日志
  - [白名单多 Skill 动态选择设计](architecture/skill-selection.md)：`capability.json` 元数据预检、先验后载与拒绝降级
  - [单公式 Math Agent 交接协议](architecture/formula-handoff.md)：码点范围转换、四元组版本绑定与幂等审阅确认
  - [图片与 PDF 识别导入管线设计](architecture/ocr-pipeline.md)：Studio 受保护导入流程与独立 OCR 实验 CLI 的职责分界
  - [深海蓝视觉工作区交互设计](architecture/visual-workspace.md)：五栏连续布局、按需展开抽屉与无障碍交互基线
  - [早期立项提案导引](architecture/proposal.md) · [CLI Harness 手册](../harness/README.md) · [桌面端打包说明](../desktop/README.md)

## 四、验证记录、复现案例与实验归档

- **当前验证与质量边界**：[当前验证记录](current-validation.md) · [E2E 发行验收摘要](evaluation-results/e2e-release-01/SUMMARY.md) · [公式修复质量记录](formula-repair-quality.md) · [本地修复受控验证](local-repair-controlled-validation.md)
- **复现案例与样本说明**：[案例手册](casebook.md) · [样本总览](../samples/README.md) · [27 例检查器契约](../samples/evaluation/README.md) · [评测结果归档索引](evaluation-results/README.md)
- **专题历史档案**：[MiniCPM-V 4.7 记录](minicpm-v47.md)（[实机证据](minicpm-v47-evidence.md)）· [Jev 转换权重溯源](jev-source-evidence.md) · [外部公式评测协议](external-formula-evaluation-protocol.md) · [Skill 先导实验分析](skills-pilot-analysis.md) · [项目报告](project-report.md) · [技术文章](technical-article.md) · [系列背景](texada-series.md) · [演示归档](demo.md)（[动态演示](dynamic-demo.md)）· [本地验收](local-studio-acceptance.md) · [编辑器打磨验收](editor-polish-acceptance.md) · [研究笔记](research-notes.md) · [历史验证总表](validation.md)

## 五、打包、协作与路线图

- [可复核源码包](source-package.md) · [参与贡献](../CONTRIBUTING.md) · [安全策略](../SECURITY.md) · [求助支持](../SUPPORT.md) · [第三方许可证声明](../THIRD_PARTY_NOTICES.md) · [桌面捆绑组件审计](../desktop/licenses-audit.md) · [路线图](roadmap.md)

## 变更时同步哪些文档

| 变更内容 | 需同步更新的文档 |
| --- | --- |
| 桌面安装、界面交互、常用配置或快捷键 | [`README.md`](../README.md)、[`README.en.md`](../README.en.md)；涉及命令参数或排错时同步 [`local-studio.md`](local-studio.md) 与 [`troubleshooting.md`](troubleshooting.md) |
| 系统分层、模型约束、检查器或 Skill 协议 | [`architecture/README.md`](architecture/README.md) 及对应 `architecture/*.md`、[`agent-skills.md`](agent-skills.md)、[`harness/README.md`](../harness/README.md) |
| 版本发布、打包变更或新校验基线 | [`changelog/CHANGELOG.md`](changelog/CHANGELOG.md)、[`changelog/README.md`](changelog/README.md)、`releases/vX.Y.Z.md` 与 [`current-validation.md`](current-validation.md) |
| 新增样本、评测运行或契约调整 | [`samples/README.md`](../samples/README.md)、[`casebook.md`](casebook.md) 及 [`evaluation-results/`](evaluation-results/README.md) 对应归档 |
