# 安全与部署

TeXada 面向个人或可信团队，使用单个服务进程。安全修复维护在 `main`。

## 报告漏洞

通过 [GitHub 私密漏洞报告](https://github.com/CacinieP/TeXada-Studio-with-agentskills/security/advisories/new)联系维护者。请提供受影响提交、最小复现、影响范围和已尝试的缓解措施；漏洞细节、凭据或用户文档请勿放入普通 Issue。

## 部署要求

- `DEMO_TOKEN` 必须显式设置。使用随机 token、单个 Uvicorn worker，默认只绑定 `127.0.0.1`。
- token 位于 URL 查询参数中；浏览器历史和默认访问日志可能保存它。共享部署使用 HTTPS，并对代理日志脱敏。
- Monaco 静态资源通过限定路径的签名 Cookie 验证，API 仍使用 token。HTTPS 反向代理只信任指定代理的转发头。
- TeX 编译以独立低权限用户运行，只接收可信文档。开放外部上传前需要容器隔离、文件权限、资源限额和网络限制。
- 上传与产物位于 `state/`；同名上传覆盖旧版本。单独备份此目录。
- 模型接口固定在本机；首次编译和依赖安装可能联网。Studio 使用本地 Monaco，旧仪表盘 `/` 使用 KaTeX CDN。

当前没有多用户隔离、配额或并发任务保护，部署方式见 [deploy/README.md](deploy/README.md)。

发现凭据泄漏时，先撤销或轮换，再清理当前文件、历史和分发包。检查记录见 [脱敏记录](docs/security-scan-notes.md)。
