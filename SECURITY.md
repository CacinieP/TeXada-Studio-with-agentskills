# Security

这是实验性的单用户 / 可信团队应用。当前维护范围为 `main` 的最新提交，没有长期支持分支或修复时限承诺。

## 报告漏洞

当前仓库仍为私有，尚未提供经验证的匿名私密漏洞报告入口。已有访问权限的成员请通过与维护者已有的私密联系渠道报告；不要把漏洞细节写入普通 Issue。
公开发布前，维护者须启用并核验 GitHub 的 Private vulnerability reporting；届时使用仓库 Security → Advisories 中的 Report a vulnerability。若该入口不可用，只在 Issue 中请求建立私密联系，不附利用步骤、真实 token 或用户文档。
GitHub 的该功能面向公共仓库；见 [官方配置说明](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)。
报告应包括受影响提交、最小复现、影响范围和已尝试的缓解措施。

## 部署边界

- `DEMO_TOKEN` 必须显式设置。使用随机 token、单个 Uvicorn worker，默认只绑定 `127.0.0.1`。
- token 目前出现在查询参数中，会进入浏览器历史和默认访问日志。不要转发带 token 的链接或提交日志；共享部署时使用 HTTPS，并配置反向代理 / 日志脱敏。
- Monaco 使用限定路径的签名 Cookie；它不替代 API token。HTTPS 场景通过可信代理传递协议，勿信任任意来源的转发头。
- 服务可编译 TeX，不能视为沙箱。只接收可信文档，以独立低权限用户运行；如需接收不可信上传，先设计容器隔离、文件系统权限、资源限额及网络策略。
- 上传文档和产物写入 `state/`；同名上传覆盖先前上传。定期备份，不依赖 Git 保存用户数据。
- 模型端点固定为本机。旧仪表盘 `/` 使用 KaTeX CDN；Studio 编辑器资源已本地化。首次 TeX 编译和依赖安装仍可能联网。
- 不具备多用户隔离、配额、完整审计或并发任务保护；不要直接作为公共匿名服务部署。

密钥扫描只是一项检查，不能证明不存在泄漏。发现凭证泄漏应先轮换，再审查历史；删除最新文件不能清除历史中的数据。
