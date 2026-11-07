# 运行、部署与维护

当前默认交付是本地单用户 WebUI：在自己的电脑运行 FastAPI，用浏览器编辑 `.tex`，连接同机模型服务。CLI 布局树检查是独立入口。源码包不包含 Python 环境、模型权重、TeX 工具或用户数据，不是安装即用的桌面二进制应用。

## 准备独立目录

使用已审阅的提交或源码包建立新目录，保留旧版本以便回滚。需要把已提交源码传到自己管理的另一台机器时，可在仓库根目录执行；将 `texada-node` 换成自己的 SSH 别名：

```bash
git archive HEAD | ssh texada-node \
  'mkdir ~/texada-candidate && tar -xf - -C ~/texada-candidate'
```

目录已存在时 `mkdir` 会失败，避免覆盖旧部署。此方式不传输未提交改动、配置或运行数据。

在目标项目目录使用 Python 3.11+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r webui/requirements.txt
.venv/bin/python -m pip check
.venv/bin/python scripts/run-local-studio.py --check
```

`--check` 离线检查依赖和配置，不连接模型、不启动服务、不写入会话。编辑、文档管理和确定性检查不需要模型；模型候选及图片识别另需可用的本机服务。当前实机验收以 macOS 为主，路径中的 Windows/Linux 分支不代表完成了这些平台的实机测试。

PDF 编译与导入还需要 Tectonic、Poppler 和预先准备的 TeX 资源。`TECTONIC` 可以指定已有编译器路径。先执行 `.venv/bin/python scripts/prepare-local-tex.py` 离线检查固定样本；需要首次联网准备时，再显式加 `--download-resources`。Studio 正常编译使用 `--untrusted --only-cached`，缺缓存会提示失败。字体及首次准备范围见[本地使用指南](../docs/local-studio.md#首次准备与离线使用)。

## 默认本地启动

macOS 可双击 `scripts/start-local-studio.command`，或从项目目录运行：

```bash
.venv/bin/python scripts/run-local-studio.py
```

默认监听 `127.0.0.1:8888` 并打开浏览器。使用已部署的本机模型时可明确指定：

```bash
.venv/bin/python scripts/run-local-studio.py \
  --base-url http://127.0.0.1:18081/v1 \
  --model minicpm-v4.7-35b-a3b-q4 --no-auto-model
```

只接受 `http://localhost`、`127.0.0.1` 或 `[::1]` 的 OpenAI-compatible `/v1` 服务，模型名必须与该服务实际标签一致。本地请求绕过代理、拒绝重定向，不读取或发送云 API Key，也不自动回退到其他服务。指定模型不可用时，保留配置并提示连接问题；不要据此切换成云服务。

自动启动需要本机已有 `llama-server`、GGUF 与视觉 projector；启动器不下载它们。退出只停止自己启动的模型，不关闭已有 Ollama 或其他服务。安装与可选路径参数见[本机模型连接](../docs/local-studio.md#本机模型连接)。

启动器生成私密访问 token，关闭 Uvicorn 访问日志，只把入口写入受限权限的 `session.json`。同一数据目录已有运行会话时重新打开该会话。需要选择目录、端口或不自动打开浏览器时：

```bash
.venv/bin/python scripts/run-local-studio.py \
  --state-dir ./state/local-profile --port 8890 --no-browser
```

私密 URL、token 和 `session.json` 不应进入截图、报告或源码包。此访问控制不是多用户账号系统；远程共享需另行设计权限与隔离，信任边界见[安全说明](../SECURITY.md)。

## 数据、升级与回滚

默认数据位于系统用户数据目录；`--state-dir` 或 `TEXADA_STUDIO_STATE_DIR` 可另选位置。直接启动 Uvicorn 且未配置目录时才使用仓库 `state/studio/`，不要把这个兼容默认值当成本地启动器的数据位置。

1. 升级前保存当前文档，等待任务结束并停止服务，再备份实际用户数据目录。
2. 备份包括 `documents/`（含历史与删除副本）、`jobs/`、`imports/` 与本机模型设置；来源文件和事件可能含私人内容。不要把当前 `session.json` 作为普通报告分发。
3. 在独立候选目录安装依赖，用自己的新测试数据目录验收。保留旧源码、虚拟环境和原数据备份，不覆盖运行中的版本。
4. 验收后仅迁移需要且兼容的数据。回滚前另存新版本产生的文档，再启动旧目录和对应环境。

完成任务可从界面历史恢复候选，采用/拒绝会记录在任务中；采用只更新编辑器，保存才写入文档。保存、改名、删除和同名导入有版本检查，发现冲突需重开核对。中断任务保留已有事件但不继续后台执行，应重新发起。完整数据位置见[本地数据与恢复](../docs/local-studio.md#本地数据与恢复)。

## 验收候选版本

- 先运行[无需模型的 CLI 样本](../harness/README.md#跑通一个样本)和[开发回归](../docs/local-studio.md#回归测试)。截至 `ceae9a7` 的本轮记录为 420 项 Python 测试通过；它们不是模型准确率评测。
- 用 `math-clean.tex` 检查加载、保存、刷新、编译和多页预览；更改内容后确认旧 PDF 不再代表当前版本。
- 用 `math-delimiters.tex` 检查确定性候选、diff、拒绝与采用，再保存和刷新。修复成功可能为零模型请求，不能把它记成实际推理。
- 使用自己有权处理的固定图片/PDF，单独验证本机视觉端点、来源页码和新文档审阅；CLI `layout.json` 与公式文本修复不替代 OCR 验收。

[公式质量记录](../docs/formula-repair-quality.md)记录本轮 20 个合成案例的保真范围和本机对照；[较早本地验收](../docs/local-studio-acceptance.md)与[历史验证](../docs/validation.md)仅证明各自日期的版本。缺资源、模型或编译失败时，保留具体状态，不以另一种执行模式的结果替代。

## 旧云 API 兼容入口

`scripts/run-minicpm-v47-studio.sh` 是需要明确选择的旧 API profile，设置 `TEXADA_LOCAL_MODE=0`，默认使用 `https://api.modelbest.cn/v1` 与 `MiniCPM-V-4.7-1B`。它与上述本地启动器不同，不提供“无云端请求”的保证；公式文本会发送到配置的端点。只有在已有授权的云配置下使用。

通过当前进程环境提供自己的 `DEMO_TOKEN` 和 `VLM_API_KEY`（或兼容的 `TEXADA_OPENAI_API_KEY`），不把值写进文档、源码或共享命令记录。配置好后可运行：

```bash
export TEXADA_STUDIO_PYTHON="$PWD/.venv/bin/python"
export SKILL_MODE=on
export TEXADA_STUDIO_STATE_DIR="$PWD/state/legacy-api-profile"
./scripts/run-minicpm-v47-studio.sh --workers 1
```

需要覆盖端点时在启动前明确设置 `VLM_BASE_URL`；模型 profile 固定选择 MiniCPM-V 4.7 1B。`.env.example` 只提供配置示例，启动脚本不会自动读取 `.env`。这个旧 profile 不提供云 OCR；需要图片/PDF 导入时，使用上述本地启动器和已验证的本机视觉服务，分别运行和验收。

手动启动 WebUI 或经 SSH 隧道、HTTPS 反向代理访问时，仍只使用一个 worker，并处理 URL token 的历史和日志泄漏问题。Tectonic 的 `--untrusted` 不是操作系统隔离；当前服务面向个人可信文档，没有多用户权限、配额或任务队列。详细边界见[安全说明](../SECURITY.md)，旧模型请求契约见[4.7 适配说明](../docs/minicpm-v47.md)。常见故障见[排错说明](../docs/troubleshooting.md)。
