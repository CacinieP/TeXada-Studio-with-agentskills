# Spark 用户级部署

遵守团队收到的节点使用手册：仅使用分配节点，不修改系统网络或账号配置，不重启；至少保留 20% 磁盘空间。不要在公开文档、视频中写入账号、凭据和分配端口。

## 代码和依赖

使用自己的 SSH 别名同步源码；示例中 `spark` 为用户本地别名，不包含访问凭据。

```bash
rsync -az --exclude .git --exclude .venv --exclude state --exclude dist \
  ./ spark:~/TeXada-Studio-with-agentskills/
```

大于 1 GB 的文件不得通过 SCP 上传。模型在分配节点内按授权来源下载；不把共享模型目录当作可写目录。

在节点用户目录创建 venv，按根目录 README 安装 Python 依赖。完整 Studio 还需要 Tectonic、Poppler 和 Noto Sans CJK SC 字体。已有安装可直接使用，不要更改系统驱动。

## 运行方式

`DEMO_TOKEN` 必须为随机非空密钥；`TECTONIC` 可指向用户目录的编译器；`VLM_MODEL` 指向实际已安装的 Ollama 模型。仅运行一个 Uvicorn worker，在 tmux 中启动。监听和访问方式按私下发放的节点手册配置，外部服务必须鉴权。

模型服务保持本机访问。Studio 当前只调用文本推理，即使模型具备视觉能力也不等于已实现 OCR。真实节点运行记录与测试范围见项目报告和验证记录。

## 升级和数据

升级前等待修复完成并备份 `state/`。上传文件在 `state/studio/documents/`，不会改写仓库样本。旧部署目录中的私人文件需人工确认后迁移，不自动删除。

Monaco 0.52.2 已随仓库提供，首次获取与恢复可用 `scripts/vendor_monaco.py` 校验固定摘要。浏览器静态资源通过本站受限 Cookie 访问；API 仍需 token。旧仪表盘与 Tectonic 初始依赖可能需要外网，不宣称全流程离线。
