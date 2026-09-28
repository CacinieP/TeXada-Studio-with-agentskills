# 安装与使用排错

以下命令在仓库根目录、已激活的 Python 虚拟环境中执行。README 使用 POSIX shell；Windows 可用 WSL，原生 PowerShell 的激活和环境变量语法需另行适配，尚未验收。

## 先确认自己在跑什么

| 入口 | 模型是否必要 | 编译器是否必要 | 成功标准 |
| --- | --- | --- | --- |
| CLI fixture 样本 | 不需要 | 不需要 | 首轮得到预期计数，报告标明 test double |
| Studio 编辑与分析 | 编辑、语法和表格分析不需要模型 | 分析不需要；PDF 预览需要 | 编辑器显示样本，问题栏有对应问题 |
| Studio 公式修复 | 需要本机已安装模型 | 编译状态需要 | 候选可审阅；语义仍需人工判断 |
| CLI 真实模型 | 尝试修复公式时需要 | 当前管线不使用 | 报告说明提供方、候选和人工项 |

## clone 返回 Repository not found

当前仓库私有。确认 GitHub 账号有访问权限且 Git 已认证；这不一定是拼写错误。授权成员也可从维护者获取源码包。不要通过删除认证或公开 token 来解决。

## No module named docforensics / 依赖缺失

确认当前路径包含 `harness/`，使用 README 命令中的 `PYTHONPATH=harness`。执行：

```bash
python --version
python -m pip --version
python -m pip install -r harness/requirements.txt
python -c 'import sympy, antlr4; print(sympy.__version__)'
PYTHONPATH=harness python -m docforensics --help
```

SymPy LaTeX 解析使用 requirements 中固定的 antlr4 4.11 运行时。不要把环境问题当成公式“检查通过”。Python 3.13 已验证；其他解释器和操作系统组合尚未完整验收。

## 服务拒绝启动 / 401 / 编辑器空白

先生成非空 `DEMO_TOKEN`，在启动前打印自己的本地访问链接。复制 `.env.example` 并不会自动加载变量；需要执行 `set -a; . ./.env; set +a`。服务重启后如果 token 改变，旧链接不再有效。

通过带正确 token 的 `/studio` 页面进入，允许同源 Cookie；Monaco 的静态资源会验证限定路径 Cookie。旧标签页或直接打开资源地址可能返回 401。可关闭旧页面后用新链接重开。问题仍存在时，检查开发者工具中的加载失败请求，提交报告前删去 token。

## 编辑器可用，但预览失败

```bash
command -v tectonic
tectonic --version
command -v pdftoppm
pdftoppm -v
```

`TECTONIC` 若设为绝对路径，应直接验证那个可执行文件。中文样本需要 `Noto Sans CJK SC`，缺字体与缺 TeX 包会出现在编译日志中。Tectonic 首次可能联网下载包。按所在系统的官方说明准备这些依赖；在共享节点仅做获准的用户级安装。

公式/表格问题和编译失败是不同维度。当前只预览第一页、只上传单个 tex；多文件项目缺少依赖时不能靠重复点击修复解决。

## 模型连接失败 / model not found

```bash
ollama list
curl --fail http://127.0.0.1:11434/v1/models
```

在启动 Studio 的终端设置 `export VLM_MODEL="已安装的完整模型标签"`，再启动服务。默认标签只记录实测节点配置，不意味着新机器已有模型。Studio 的模型 URL 固定为本机；CLI 可通过 `--vlm` 指定兼容端点。不要把 API key 粘贴到 Issue；当前 Studio 没有远程鉴权配置界面。

## 重跑没有产生新候选

CLI 会从同一 `--state` 目录重放日志，跳过已有终态。修改样本、模型或参数后，请换新的目录，例如 `--state state/experiment-02`。旧目录是实验记录，不必删除。CLI 的返回码 0 表示管线运行完成，不代表没有 `NEEDS_HUMAN` 或所有数学内容正确。

## fixture 能修表格，真实 CLI 却不能

fixture 读取预设修复表，目的是测试循环与报告。当前真实模型提供方没有实现表格修复，无法获得候选的节点进入人工处理。Studio 对简单合计的规则重算是另一条实现路径，不能把两者视为同一能力。

## 如何提交一个有用的问题

按 [SUPPORT.md](../SUPPORT.md) 选择入口，附提交号、运行路径、模型模式和最小合成样本。暂不提供全局安装脚本、公共匿名上传或多用户部署；需求可进入路线图讨论。
