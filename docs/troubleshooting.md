# 安装与使用排错

以下命令在仓库根目录、已激活的虚拟环境中执行。先区分入口：CLI fixture 验证预设修复流程，Studio 分析只需 Python 依赖，PDF 预览需要编译器，公式候选需要模型。

## Clone 或 Python 导入失败

`Repository not found`：仓库目前私有，请确认账号有访问权限且 Git 已认证；也可使用授权源码包。

`No module named docforensics` 或解析依赖缺失：

```bash
python --version
python -m pip --version
python -m pip install -r harness/requirements.txt
python -c 'import sympy, antlr4; print(sympy.__version__)'
PYTHONPATH=harness python -m docforensics run --help
```

从仓库根目录运行，并保留 `PYTHONPATH=harness`。requirements 固定 ANTLR 4.11；已验证 Python 3.13。Windows 命令建议在 WSL 中运行。

## 服务拒绝启动、401 或编辑器空白

启动前设置非空 `DEMO_TOKEN`，用对应的带 token 链接打开 `/studio`。复制 `.env.example` 后，还需执行 `set -a; . ./.env; set +a` 加载配置。

Monaco 资源通过同源、限定路径 Cookie 鉴权。token 改变后用新链接重新打开页面，允许 Cookie；仍为空白时查看开发者工具中的失败请求。报告问题时删去 URL 中的 token 和 Cookie。

## 编辑器正常，PDF 预览失败

```bash
"${TECTONIC:-tectonic}" --version
pdftoppm -v
```

编译日志可区分 TeX 语法、缺包和缺字体。首次编译可能联网下载包；中文样本需要 `Noto Sans CJK SC`，可先用英文 `math-clean.tex` 核对环境。`TECTONIC` 可设为可执行文件的完整路径。

Studio 只上传单个 `.tex` 并显示第一页。依赖外部图片、宏文件或参考文献的项目需先准备相应资源；当前没有整项目上传入口。

## 模型连接失败或找不到模型

```bash
ollama list
curl --fail http://127.0.0.1:11434/v1/models
export VLM_MODEL='替换为已安装的完整模型标签'
```

在同一终端重启 Studio。Studio 固定请求本机接口；CLI 用 `--vlm` 指定兼容服务根地址。默认模型标签只来自开发环境，显式选择已安装模型更可靠。

## Skill 配置错误或看不到模型请求

CLI 默认 `--skill-mode on`，Studio 默认 `SKILL_MODE=on`。on 模式读取 `skills/doc-formula-verify/SKILL.md`；路径或元数据错误时先检查源码包是否完整。

在提供方记录中核对 `skill_loaded`、`skill_sha256` 和 `prompt_sha256`。初检 `OK` 会跳过模型，fixture 的模型请求数也为零。需要对照时按[研究协议](../samples/research/README.md)运行 on / off 两组。

## CLI 重跑后没有新候选

查看 `report.md` 的本轮 `run_id`、`SKIP` 和复用来源。输入及执行上下文一致时，CLI 会复用已保存的终态；独立实验使用新的 `--state` 目录。

暂时性服务或检查器故障标为 `resumable:false`，环境恢复后重跑同一命令即可。重试耗尽的人工项仍会保留。详细规则见 [Harness 手册](../harness/README.md#续跑)。

## Studio 重启后如何找回结果

完成结果和候选事件在 `state/studio/jobs/<job_id>/`。保存 job ID 后可通过鉴权的任务接口查询；页面暂无历史列表，未导出的编辑内容需自行保留。中断任务重新发起。

启动一个 Uvicorn worker；进行中的任务依赖进程内存。CLI 的同一状态目录也只供一个进程使用。

## Fixture 能修表格，真实 CLI 没有候选

Fixture 读取预设行数据。CLI 的真实模型提供方目前只实现公式修复；表格问题交给人工处理。Studio 的简单合计重算由规则执行，两条路径的结果应分别查看。

仍有问题时，按 [SUPPORT.md](../SUPPORT.md) 提供提交号、命令、环境和最小合成复现。部署配置见[部署手册](../deploy/README.md)。
