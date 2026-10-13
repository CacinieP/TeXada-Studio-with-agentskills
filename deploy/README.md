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

使用 Python 3.11+，已验证版本为3.13。仅编辑和分析时，到此已具备 Python 环境。编译与预览另需本机依赖：

```bash
"${TECTONIC:-tectonic}" --version
pdftoppm -v
```

`TECTONIC` 可指向用户目录中的编译器。中文样本需要 `Noto Sans CJK SC`；英文 `math-clean.tex` 可先用于预览验收。Tectonic 首次编译可能下载 TeX 包。MiniCPM-V 4.7-1B API profile 通过 `https://api.modelbest.cn/v1` 请求候选，部署端只需网络与 API 配置；本机量化模型服务另行准备和验收。

## 配置和启动

```bash
cp .env.example .env
```

编辑 `.env` 中的非敏感配置：设置 `VLM_BASE_URL=https://api.modelbest.cn/v1`、`VLM_MODEL=MiniCPM-V-4.7-1B`、`SKILL_MODE=on` 和需要时的 `TECTONIC` 路径。`DEMO_TOKEN` 和 `VLM_API_KEY`（或 `TEXADA_OPENAI_API_KEY`）通过当前进程环境提供；示例中的凭据占位保持注释。token 可用 `python -c 'import secrets; print(secrets.token_urlsafe(32))'` 生成。若沿用旧 `.env`，删除空的凭据赋值，避免加载配置时覆盖已有环境变量。

```bash
set -a
. ./.env
set +a
: "${DEMO_TOKEN:?请先配置 token}"
export TEXADA_STUDIO_PYTHON="$PWD/.venv/bin/python"
./scripts/run-minicpm-v47-studio.sh --workers 1
```

启动器显式选择 `MiniCPM-V-4.7-1B`，默认使用 ModelBest API，并在本机 `127.0.0.1:8888` 提供 Studio。通过 SSH 隧道或已配置的 HTTPS 代理访问 `/studio?token=你的token`，访问凭据仅保存在私密配置中。代理配置与日志处理见安全说明，模型请求契约见 [4.7 适配说明](../docs/minicpm-v47.md)。

使用其他本机端口或现有本机模型服务时，显式设置 `VLM_BASE_URL`、`VLM_MODEL` 和 `VLM_API_KEY`，再直接运行 `python -m uvicorn app:app --app-dir webui --host 127.0.0.1 --port 你的端口 --workers 1`。服务根地址或以 `/v1` 结尾的地址均可使用，端点须支持 OpenAI-compatible Chat Completions。

需要保持终端会话时可先运行 `tmux new -s texada`，在会话内执行上述启动命令；`Ctrl-B D` 脱离，`tmux attach -t texada` 返回。停止前等待任务结束，再按 `Ctrl-C`。

## 验收、升级和回滚

1. 记录提交号与依赖版本，先跑 [README](../README.md#1-先跑无需模型的样本) 的 fixture。
2. 用 `math-clean.tex` 核对样本加载、分析和预览，再用 `math-delimiters.tex` 验证模型候选、diff、采用与导出，记录实际结果。
3. 升级前停止服务，备份原目录的 `state/`。上传文件在 `state/studio/documents/`，任务结果在 `state/studio/jobs/`；它们由 Git 忽略。
4. 保留旧源码与虚拟环境，从候选目录启动服务。仅迁移需要且兼容的数据。
5. 回滚时先另存候选版本产生的新数据，再恢复旧目录、旧环境和备份。

正在执行的任务依赖进程内存；重启后需重新发起，完成任务的磁盘记录仍可查询。Monaco 资源已打包；离线部署还需预备本机模型、字体和 TeX 包，仪表盘 `/` 的 KaTeX 仍来自 CDN。API profile 需要网络。常见问题见[排错说明](../docs/troubleshooting.md)。
