# 开源发布清单

项目源码按 AGPL-3.0-only 开源，[B站实机演示](https://www.bilibili.com/video/BV16Kan6rEGv/)已发布；尚未创建 tag 或 GitHub Release。比赛材料见[提交清单](submission-checklist.md)，准备状态见[开源审查](open-source-readiness.md)。

## 已完成

- [x] AGPL-3.0-only 许可、版权归属及第三方许可说明。
- [x] Monaco 固定版本、MIT 许可、资源摘要和重建脚本。
- [x] 中英文 README、贡献流程、安全说明、社区行为约定、Issue / PR 模板、SUPPORT 和 CITATION.cff。
- [x] 显式认证配置；运行数据与上传文档使用被 Git 忽略的状态目录。
- [x] 原教材节选从可达历史移除；独立新仓库核验完成，旧 blob 在新仓库 API 查询返回404。后续历史脱敏记录见[迁移说明](repository-migration.md)和[扫描复核](security-scan-notes.md)。
- [x] 合成样本及开放教材先导公式的来源、修改和许可分别记录。
- [x] 本轮复现 CLI fixture 的7个 `OK`、1个人工项及再次执行8个 `SKIP`；27例检查器验证与12次样本编译均符合预期。
- [x] 最新连续动态录屏、交付说明与媒体校验记录齐备；运行源码为 `87ca397`，详见[动态演示](dynamic-demo.md)。
- [x] [微信公众号征文](https://mp.weixin.qq.com/s/kDkmQp12pBSPkqw2UpeLXw)已发布，README 与提交资料已补入文章链接。
- [x] GitHub About、Topics、社交预览、发布文案及[首个预发布说明草稿](releases/v0.1.0-alpha.1-draft.md)已准备。

## 公开与版本发布

- [ ] 选定发布提交，复查拟公开分支、标签、历史及附件；核对许可、教材来源和品牌资源。
- [ ] 按[扫描复核](security-scan-notes.md)重扫该版本，检查新增图片与媒体中的部署信息、凭据和用户内容。
- [ ] 确认部署版本与公开源码对应；有本地修改时一并提供，并更新界面源码链接。
- [x] 仓库所有者已授权公开，项目报告、技术报告和演示入口已整理。
- [ ] 核验 Private vulnerability reporting 入口，实际报告送达另行测试。
- [ ] 从选定提交生成源码包，核对媒体附件及 SHA256 清单，创建预发布 tag / Release。
- [ ] 用未登录浏览器核验仓库、源码、演示、报告和微信公众号文章。
- [ ] 邀请目标用户复现，记录失败步骤与有效反馈，再按[发布计划](launch-plan.md)开展传播。

## 打包与版本记录

从仓库根目录执行 `bash scripts/package.sh`，源码包只包含当前提交的 Git tree，不含历史与运行数据。清理前的 bundle、旧 clone 和旧下载包保留在私有备份中，发布附件应从清理后的提交重新生成。

发布说明写明提交号、运行环境、实际执行的检查及结果，链接对应证据。[验证记录](validation.md)区分契约测试、作者参考修订和真实模型运行；旧176.4秒讲解版及 `dff5fc6` 记录保留为历史，当前演示以[动态录屏](dynamic-demo.md)为准。

自动 CI、定时任务、公开试用服务及外部用户验证尚未启用或开展；首次 Release 和外部试跑按后续计划进行。
