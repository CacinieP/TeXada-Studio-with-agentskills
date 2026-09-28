# 可信用户的部署与维护

当前服务适合单人或可信团队演示：一个 Uvicorn worker、一个共享 token，不具备多用户隔离或 TeX 沙箱。先阅读[安全边界](../SECURITY.md)；不要开放匿名上传。

## 准备源码与环境

使用已审阅的提交部署，在用户目录建立独立虚拟环境。Python 依赖安装方式见[根目录 README](../README.md)。若通过 SSH 同步，使用自己的主机别名，仅传输已提交源码，例如在本地仓库根目录执行：

```bash
# spark 是你自己的 SSH 别名；远端 candidate 目录应是新的空目录。
git archive HEAD | ssh spark \
  'mkdir -p ~/texada-candidate && tar -xf - -C ~/texada-candidate'
```

此命令不携带 `.git`、未提交修改、被忽略的 `.env` 或运行数据。远端的配置、虚拟环境与数据需单独管理。先在新目录核对依赖，不要覆盖正在运行的服务目录。

完整 Studio 需要已有 Tectonic、Poppler 的 `pdftoppm`、中文字体 `Noto Sans CJK SC`，以及本机模型服务。可使用用户目录中的安装，不修改系统驱动或全局配置。

## 启动前检查

以下命令在目标机器、已激活的虚拟环境内执行；它们只查看依赖，不下载模型或执行真实推理。

```bash
python --version
python -m pip check
python -c 'import fastapi, uvicorn, sympy, antlr4; print("Python dependencies import OK")'
"${TECTONIC:-tectonic}" --version
pdftoppm -v
ollama list
```

- `TECTONIC` 是编译器路径，可设为用户目录中的完整路径；不要附加命令行参数。
- `ollama list` 中必须存在你选择的 `VLM_MODEL`。使用其他兼容服务时，按该服务的方法检查；Studio 的接口固定为本机 `127.0.0.1:11434/v1/chat/completions`，当前不发送 API key。
- 在具有 Fontconfig 的环境中，可执行 `fc-list : family`，确认结果含 `Noto Sans CJK SC`。`fc-match` 可能返回替代字体，不能单独证明所需字体已安装。没有 Fontconfig 时使用该平台已有的字体管理方式检查。
- Tectonic 的首次编译可能下载 TeX 包。预备依赖后，还需实际编译合成样本，才能确认预览可用；版本检查不代替编译验收。

程序不自动安装上述软件、字体或模型。缺少编译器时仍可打开编辑器，但预览与修复前后编译无法完成。模型标签、内存需求与可用性取决于自己的环境。

## 启动与停止

在仓库目录创建 tmux 会话：

```bash
tmux new -s texada
```

然后在 tmux 内激活自己的虚拟环境，加载仅本机保存的配置。若使用 `.env`，先按 `.env.example` 填写随机非空的 `DEMO_TOKEN` 和已安装模型标签，再执行：

```bash
set -a
. ./.env
set +a
: "${DEMO_TOKEN:?请先配置随机非空 token}"
: "${VLM_MODEL:?请先选择已安装模型}"
: "${TEXADA_BIND_PORT:?请设置获准使用的本机监听端口}"
python -m uvicorn app:app --app-dir webui \
  --host 127.0.0.1 --port "$TEXADA_BIND_PORT" --workers 1
```

`TEXADA_BIND_PORT` 由你在当前会话或私密配置中设置；不在仓库填写分配节点的访问参数。默认保持回环监听，通过获准的隧道或已配置的 HTTPS 代理访问 `/studio`。代理和日志脱敏要求见安全说明。

使用 `Ctrl+B`、`D` 脱离 tmux；需要停止时先等待修复结束，再 `tmux attach -t texada`，对 Uvicorn 按 `Ctrl+C`。不要用重启节点作为停止方法。Studio 未完成的任务保存在内存，停止或崩溃后不能恢复。

## 验收、升级与回滚

1. 记录拟部署的提交号、依赖版本和本机配置位置；配置值与 token 不进入截图、日志附件或提交。
2. 在独立目录和独立状态下检查候选版本。先跑 README 的 fixture 与单元测试，再通过 `/studio` 检查样本加载、分析、预览、diff、采用和导出。真实模型验收会产生推理负载，应明确记录模型与结果。
3. 切换前等待任务结束，停止服务并备份原目录的 `state/`。上传文档位于 `state/studio/documents/`；不要依靠 Git 备份这些数据。
4. 保留旧提交目录与原虚拟环境，从候选目录启动同一获准监听入口。只迁移确认需要且兼容的数据，不自动复制私人文档到样本目录。
5. 若验收失败，停止候选服务，使用旧目录、旧环境和切换前的数据备份恢复。先另存切换后新产生的数据，避免回滚覆盖。当前没有数据库迁移或自动回滚工具。

Monaco 0.52.2 随源码提供；恢复和摘要校验见 `scripts/vendor_monaco.py`。旧仪表盘仍使用 KaTeX CDN。模型、字体、包缓存和浏览器请求都需分别检查，不能因编辑器资源本地化而声称全流程离线。

## DGX Spark 比赛节点约束

在赛事分配节点上，还须遵守团队收到的私下使用手册：仅使用分配节点，不修改系统网络或账号配置，不重启，至少保留 20% 磁盘空间。账号、凭据和分配端口不写入公开文档或视频。

大于 1 GB 的文件不得通过 SCP 上传；模型在分配节点内按授权来源下载，不把共享模型目录当作可写目录。具体监听和访问方式按节点手册配置；面向外部的演示必须鉴权。这些比赛约束不等于项目已经实现沙箱隔离或多用户安全。
