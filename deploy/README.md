# 部署与维护

当前部署面向可信用户：一个 Uvicorn worker、一个共享 token。TeX 编译尚无沙箱，多用户隔离也未实现；信任边界见 [SECURITY.md](../SECURITY.md)。

## 准备候选版本

使用已审阅的提交，在目标机器的用户目录建立独立目录和虚拟环境。需要 SSH 传输时，在本地仓库根目录执行；将 `texada-node` 换成自己的 SSH 别名：

```bash
git archive HEAD | ssh texada-node \
  'mkdir ~/texada-candidate && tar -xf - -C ~/texada-candidate'
```

目录已存在时 `mkdir` 会失败，避免覆盖旧部署。此方式只传输已提交源码；配置和运行数据另行管理。

在目标机器执行：

```bash
cd ~/texada-candidate
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r webui/requirements.txt
python -m pip check
```

使用 Python 3.11+，已验证版本为3.13。仅编辑和分析时，到此已具备 Python 环境。编译与模型功能另需本机依赖：

```bash
"${TECTONIC:-tectonic}" --version
pdftoppm -v
ollama list
```

`TECTONIC` 可指向用户目录中的编译器。Studio 请求本机 `127.0.0.1:11434`，`VLM_MODEL` 应选 `ollama list` 中的完整标签。中文样本需要 `Noto Sans CJK SC`；英文 `math-clean.tex` 可先用于预览验收。Tectonic 首次编译可能下载 TeX 包。

## 配置和启动

```bash
cp .env.example .env
```

编辑 `.env`：填入随机非空 `DEMO_TOKEN`、已安装的 `VLM_MODEL` 和需要时的 `TECTONIC` 路径。token 可用 `python -c 'import secrets; print(secrets.token_urlsafe(32))'` 生成。

```bash
set -a
. ./.env
set +a
: "${DEMO_TOKEN:?请先配置 token}"
export TEXADA_BIND_PORT=8888
python -m uvicorn app:app --app-dir webui \
  --host 127.0.0.1 --port "$TEXADA_BIND_PORT" --workers 1
```

将端口改为目标机器获准使用的本机端口。通过 SSH 隧道或已配置的 HTTPS 代理访问 `/studio?token=你的token`，访问凭据仅保存在私密配置中。代理配置与日志处理见安全说明。

需要保持终端会话时可先运行 `tmux new -s texada`，在会话内执行上述启动命令；`Ctrl-B D` 脱离，`tmux attach -t texada` 返回。停止前等待任务结束，再按 `Ctrl-C`。

## 验收、升级和回滚

1. 记录提交号与依赖版本，先跑 [README](../README.md#1-先跑无需模型的样本) 的 fixture。
2. 用 `math-clean.tex` 核对样本加载、分析和预览，再用 `math-delimiters.tex` 验证模型候选、diff、采用与导出，记录实际结果。
3. 升级前停止服务，备份原目录的 `state/`。上传文件在 `state/studio/documents/`，任务结果在 `state/studio/jobs/`；它们由 Git 忽略。
4. 保留旧源码与虚拟环境，从候选目录启动服务。仅迁移需要且兼容的数据。
5. 回滚时先另存候选版本产生的新数据，再恢复旧目录、旧环境和备份。

正在执行的任务依赖进程内存；重启后需重新发起，完成任务的磁盘记录仍可查询。Monaco 资源已打包；离线部署还需预备模型、字体和 TeX 包，旧仪表盘 `/` 的 KaTeX 仍来自 CDN。常见问题见[排错说明](../docs/troubleshooting.md)。

## DGX Spark 比赛节点

按团队收到的节点手册使用分配资源：不改系统网络或账号配置，不重启，至少保留20%磁盘空间；大于1GB的文件不通过 SCP 上传。模型在节点内按授权来源下载，共享模型目录保持只读。实际主机、凭据和分配端口存于私密配置，外部演示启用鉴权。
