# 文档导航

按当前目标选择入口。README 负责安装与体验，详细文档解释各自的输入、输出与限制；历史报告保留当时的验证条件，不替代当前实现说明。

## 用户：先看到结果，再运行自己的可信文档

1. 从[中文首页](../README.md)或 [English README](../README.en.md)了解能力、安装依赖并运行 Studio。
2. 看[演示与证据](demo.md)，用[案例手册](casebook.md)理解检查结果、修复候选和人工判断的区别。
3. 根据[样本入口](../samples/README.md)选择 Studio 文档、CLI fixture 或独立检查案例；遇到问题查[排错说明](troubleshooting.md)。
4. 共享部署前阅读[安全边界](../SECURITY.md)；无法自行解决的问题按[求助约定](../SUPPORT.md)提供最小合成复现。

## 开发者：找到契约，做小范围改动

1. [架构说明](architecture.md)解释模块关系；[Skills 技术报告](skills-technical-report.md)解释工作流、规则、模型与证据如何配合。
2. [Harness 手册](../harness/README.md)说明实际 CLI 参数、状态与续跑；[案例定义](../samples/evaluation/cases.json)提供可执行输入与期望。
3. 按[贡献说明](../CONTRIBUTING.md)选择相关测试，并用[案例运行器](../scripts/evaluate_cases.py)创建新的报告目录。完整命令集中在 README，具体评估契约见[案例集说明](../samples/evaluation/README.md)。
4. 从[路线图](roadmap.md)选择下一项有明确验收标准的工作；不要把设计草案当作已实现功能。

## 研究者：区分行为证据与效果结论

1. 先读 [Skills 技术报告](skills-technical-report.md)，明确哪些部分是确定性检查、模型调用、人工复核或尚未实现的设计。
2. 用[案例手册](casebook.md)和[案例集说明](../samples/evaluation/README.md)重放正例、反例和边界。语法接受、预期匹配、编译通过与数学语义正确是不同结论。
3. [验证记录](validation.md)与[演示证据 JSON](demo-evidence.json)记录已有验证的条件；单次样本、fixture 和旁白均不是模型准确率基准。
4. 引用时使用 [CITATION.cff](../CITATION.cff)，写明实际提交号、模型或检查器、数据来源和未覆盖范围。公开评测不得使用无再分发授权的原始材料。

## 维护者：交付、部署与公开准备

1. [部署手册](../deploy/README.md)用于依赖检查、启动、升级、数据备份与回滚；[安全说明](../SECURITY.md)定义当前信任边界。
2. 对照[开源发布检查](open-source-release.md)检查授权、源码、历史和可见性；[准备度报告](open-source-readiness.md)是一次审查记录，发布时仍需重核。
3. [发布与传播计划](launch-plan.md)管理传播节奏与事实口径；[Release 草案](releases/v0.1.0-alpha.1-draft.md)不等于已经发布。变更写入 [CHANGELOG](../CHANGELOG.md)。
4. 比赛材料从[项目报告](project-report.md)、[技术征文](technical-article.md)和[提交清单](submission-checklist.md)进入。它们记录阶段性交付，公开发布与表单提交仍是单独操作。

## 各主题的主要文档

| 主题 | 主要入口 | 使用方式 |
| --- | --- | --- |
| 安装、启动和常用测试命令 | [README](../README.md)、[英文版](../README.en.md) | 两种语言保持能力与命令一致 |
| CLI 参数、产物和续跑 | [Harness 手册](../harness/README.md) | 与当前 CLI 实现核对 |
| Skills 机制、执行边界与研究解释 | [Skills 技术报告](skills-technical-report.md) | 与 Skill 指令、检查器和运行记录共同阅读 |
| 可执行输入、预期状态与原因 | [案例 catalog](../samples/evaluation/cases.json) | 稳定 ID 是案例事实来源；runner 生成运行结果 |
| 案例操作与结果解释 | [案例集说明](../samples/evaluation/README.md)、[案例手册](casebook.md) | 前者解释运行协议，后者解释场景和判断 |
| 部署与安全 | [部署手册](../deploy/README.md)、[SECURITY](../SECURITY.md) | 本机配置和私人数据不进入文档 |
| 贡献和未来工作 | [CONTRIBUTING](../CONTRIBUTING.md)、[路线图](roadmap.md) | 区分已实现行为与候选任务 |
| 历史验证与赛事材料 | [验证记录](validation.md)、[项目报告](project-report.md) | 保留环境、范围与时间条件，不扩展结论 |

若文档与代码或实际输出不一致，先保留复现和原始结果，再修正契约或实现。不能仅更改案例期望来掩盖问题；不能依据较早的项目提案扩大当前能力声明。

## 变更时同步哪些文档

| 变更类型 | 应同步检查 |
| --- | --- |
| 安装依赖、入口或启动参数 | 中英文 README、部署与排错说明；实际执行对应命令 |
| 检查器输入契约、状态或数字格式 | Skill 指令、案例 catalog、案例手册、技术报告；运行案例并保留新报告 |
| CLI 重试、续跑或报告结构 | Harness 手册、相关回归、技术报告；检查 fixture 首跑与续跑 |
| Studio 交互或支持范围 | 中英文 README、排错、架构与演示说明；需要时更新截图 |
| 新增能力或关闭已知缺口 | 路线图、CHANGELOG、案例与相关主要文档；保留未覆盖范围 |
| 发布版本、仓库可见性或传播材料 | 发布检查、Release 草案、传播计划与首页状态；记录实际生效时间 |

新增文档时在这里安排明确读者和入口，优先链接主要说明，避免在多个页面复制易过期的测试数量、运行耗时或能力承诺。
