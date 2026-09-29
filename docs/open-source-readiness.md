# 开源准备状态

更新：2026-09-29。项目源码按 AGPL-3.0-only 开源，[实机演示](https://www.bilibili.com/video/BV16Kan6rEGv/)已在B站发布。当前作为实验原型供本地复现；首个 Release 和外部用户试跑待安排。

## 已具备的条件

| 项目 | 当前状态 | 入口 |
| --- | --- | --- |
| 首次使用 | 中英文 README、安装步骤、离线样例和预期结果齐备 | [README](../README.md)、[English README](../README.en.md) |
| 许可与来源 | 主项目 AGPL-3.0-only；Monaco MIT 许可及固定资源保留；教材先导公式采用 CC-BY-SA-4.0 | [许可](../LICENSE)、[来源声明](../samples/research/ACTIVE_CALCULUS_NOTICE.md) |
| 协作与维护 | 贡献流程、问题模板、排错页、CITATION.cff 和预发布文案齐备；About 与 Topics 已配置 | [求助入口](../SUPPORT.md)、[路线图](roadmap.md)、[发布草稿](releases/v0.1.0-alpha.1-draft.md) |
| 历史清理 | 教材内容已从可达历史移除，并迁入独立私有仓库；后续完成邮件元数据、部署示例和图片脱敏 | [迁移记录](repository-migration.md)、[扫描复核](security-scan-notes.md) |
| 演示与传播 | B站连续实录、微信公众号征文已发布；项目与技术报告齐备 | [动态演示](dynamic-demo.md)、[微信公众号征文](https://mp.weixin.qq.com/s/kDkmQp12pBSPkqw2UpeLXw)、[发布计划](launch-plan.md) |

## 复现结果

本轮按文档重新核对了三条路径：CLI fixture 首次7个 `OK`、1个 `NEEDS_HUMAN`，重复执行得到8个 `SKIP`；27例检查器输入全部符合预期；8份 Studio 原稿与4份作者参考修订共12次编译，7份生成 PDF、5份预期失败。命令和环境见[案例手册](casebook.md)、[编译复现](evaluation-results/studio-latex/README.md)及[验证记录](validation.md)。

Studio 现有13份文档。最新演示从 `87ca397` 连续录制，时长222.071秒，完整保留浏览器操作和模型等待；主例完成1次模型请求、1处定界符修复、人工采用及 PDF、TeX、报告导出。旧讲解视频及其独立运行数据归入[演示历史](demo.md)。

既有 Web、Harness、评测运行器及前端回归结果统一保存在[验证记录](validation.md)。CITATION.cff 已通过 CFF 1.2.0 schema 验证。外部目标用户试跑尚未开展。

## 后续发布工作

1. 选定发布提交，复核许可、来源、拟公开 refs 和附件；从该提交生成源码包及校验清单。
2. 核验源码、报告、演示、微信公众号文章与私密漏洞入口的访问。
3. 创建首个预发布 tag / Release，确认实际部署版本对应的源码可访问。
4. 邀请少量目标用户按 README 试跑，收集安装失败、误改和漏检案例，处理后再扩大传播。

执行时使用[发布清单](open-source-release.md)。现阶段优先保证试跑顺畅、反馈有人处理；独立官网、更多渠道和自动化可随实际需求增加。
