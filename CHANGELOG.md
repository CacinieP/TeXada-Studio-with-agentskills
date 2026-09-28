# Changelog

## 2026-09-28 Submission preparation

- Fail closed when formula verification crashes or dependencies are missing; reject partial LaTeX parses while supporting delimiter sizing commands.
- Present repair candidates for review before adopting them into the editor; export audit records with hashes and compile results.
- Reset failed task controls and discard stale file / preview responses.
- Align Skills, architecture, deployment notes and submission documents with actual implementation and the verified form.

## Unreleased

- 参赛仓库使用 `TeXada-Studio-with-agentskills`，作品显示名统一为 TeXada Studio with Agent Skills；更新安装目录、源码链接和打包名称。

- 主项目采用 AGPL-3.0-only，补充第三方许可、贡献和安全说明、安装与测试文档。
- Monaco 0.52.2 资源本地化，保留上游 MIT 许可和完整性清单；静态资源使用限路径签名 Cookie。
- 修复空 diff 占据编辑区、未生成 diff 时导航报错、切换文件遗留 diff，以及预览折叠残留宽度的问题。
- 移除默认 token 和固定仓库路径；管线子进程使用当前 Python，保留真实退出码。
- 用户上传与源码样本分离；默认打开合成报表，当前源码移除无明确再分发授权的教材节选。
- 源码包只包含已提交文件，排除运行数据和 Git 历史。教材节选及其两个历史版本已从可达提交清除；旧 clone 和清理前的私密备份不得重新推回。
