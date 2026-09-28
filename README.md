# TeXada-Studio-with-agentskills

LaTeX 文档质检与修复 Studio，面向公式语法和表格合计错误。包含 Monaco 源码编辑器、Tectonic 编译预览、修复对比，以及可断点续跑的命令行质检管线。

这是第三届 NVIDIA DGX Spark 黑客松 Agent Skills 方向的实验项目。当前支持可信用户的单进程演示部署，还不是多用户文档服务。

参赛作品名：**TeXada Studio with Agent Skills · 文档质检与修复**。仓库名：`TeXada-Studio-with-agentskills`。
本仓库承接已经清理的项目历史，原仓库保留私有；命名依据与迁移范围见 [仓库说明](docs/repository-migration.md)。

团队：LinguistsWantTech · 队长邓一纯 · 队员刘风华。
材料入口：[项目报告](docs/project-report.md) · [技术征文](docs/technical-article.md) · [实际提交字段](docs/submission-checklist.md)。

![Studio 的源码、预览与人工采用流程](docs/images/studio-overview.png)

## 当前能力

- Studio：编辑 / 上传 / 导出 `.tex`，并排预览第一页 PDF，查看候选 diff，人工采用后导出质检报告。
- 公式：用 SymPy 检查部分 LaTeX 语法，调用本地模型尝试修复，再做语法回判。
- 表格：检查简单 `tabular` 合计值；复杂跨页表格和任意 LaTeX 宏不在支持范围。
- CLI：读取已有 `layout.json`，输出 `OK / RETRY / NEEDS_HUMAN`、事件日志和 Markdown 报告；重跑跳过已完成节点。
- Studio 的 Monaco 0.52.2 资源随仓库提供，运行时无需编辑器 CDN。

语法检查通过不代表数学含义正确。当前真实模型请求发送文本，不发送页面图像；版面解析 Skill 是工作流说明，CLI 不直接完成 PDF/OCR 解析。`samples/` 中的 crop 和修复数据是测试替身，不能作为模型效果评测。

## 快速开始：无需 GPU 的离线样本

需要 Python 3.10+；开发验证使用 Python 3.13。以下命令在仓库根目录执行。初次安装依赖需要网络，安装完成后 fixture 管线不调用模型服务。

```bash
git clone https://github.com/CacinieP/TeXada-Studio-with-agentskills.git
cd TeXada-Studio-with-agentskills
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

预期计数：`exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。
报告位于 `state/quickstart/report.md`，会注明 `fixture (offline test double)`。
再次运行相同命令可验证断点续跑；使用新的 `--state` 目录开始一次独立运行。

## 启动 Studio

```bash
python -m pip install -r webui/requirements.txt
export DEMO_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m uvicorn app:app --app-dir webui --host 127.0.0.1 --port 8888
```

在同一终端查看自己生成的 `DEMO_TOKEN`，打开
`http://127.0.0.1:8888/studio?token=<你的token>&file=report-01.tex`。
没有设置 token 时服务会拒绝启动。也可复制 [`.env.example`](.env.example) 为 `.env`，填写后手动加载；应用不会自动读取 `.env`。

编辑和浏览文件只需要 Python 依赖。完整功能还需要：

| 功能 | 依赖 |
| --- | --- |
| 公式分析 / 表格检查 | `webui/requirements.txt` 中的 SymPy、antlr4 等 |
| 编译 PDF 与第一页预览 | [Tectonic](https://tectonic-typesetting.github.io/)、Poppler 的 `pdftoppm`；可执行文件位于 `PATH` |
| 中文样本编译 | 字体 `Noto Sans CJK SC` 与所需 TeX 包 |
| 模型修复 | 本机 Ollama 或兼容服务，监听 `127.0.0.1:11434`，已下载 `VLM_MODEL` 指定的模型 |

可通过 `TECTONIC` 指定编译器完整路径，通过 `VLM_MODEL` 更换已安装的模型。
默认模型名称是 `qwen3.8:27b-q4_K_M`；fixture 测试不需要下载它。程序不自动安装模型、字体或系统软件。

上传文档保存在 `state/studio/documents/`；同名上传会覆盖此前上传的版本，但不会改写仓库自带样本。运行结果保存在 `state/`，均被 Git 忽略。

节点部署与用户级安装见 [部署说明](deploy/README.md)。默认只监听本机；共享部署前阅读 [安全说明](SECURITY.md)。不要把当前服务用于接收陌生人的 TeX 文件。

## 测试

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_*.py' -v
python -m unittest discover -s skills/latex-cleanup/tests -p 'test_*.py' -v
node webui/test_studio.cjs
node skills/latex-cleanup/tests/test_audit_math.cjs
```

Node.js 22 用于 JavaScript 检查。上述测试不需要 GPU 或模型，也不代表真实浏览器视觉验收或 TeX 编译验收。实际编译检查见 [latex-cleanup 测试说明](skills/latex-cleanup/tests/CASES.md)。

## 限制与复现范围

- 任务状态存于进程内存；仅启动一个 Uvicorn worker。并发编辑、任务取消和用户隔离尚未实现。
- 编译预览仅显示第一页，上传仅支持单个 `.tex`，不支持整项目依赖上传。
- Tectonic 初次编译可能下载 TeX 包；真正断网前需预备包、模型和字体并单独验收。
- 旧管线仪表盘 `/` 仍使用 KaTeX CDN；离线编辑入口使用 `/studio`。
- 当前源码及 `main` 可达历史已移除无明确再分发授权的教材节选。旧 clone 和私密备份不能重新推回；仓库公开前仍须完成 [发布清单](docs/open-source-release.md)。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `webui/` | FastAPI、Studio、静态资源、HTTP 与 UI 逻辑测试 |
| `harness/` | 命令行管线、修复提供方、断点状态 |
| `skills/` | 公式、表格、版面和报告 Skill；内含 latex-cleanup 工具 |
| `samples/` | 可分发的合成样本与测试替身 |
| `deploy/` | DGX Spark 节点部署记录 |
| `docs/` | 架构、提案、演示和比赛提交清单；提案不等于已实现功能 |
| `scripts/` | Monaco 资源校验 / 恢复、源码打包、Git 备份 |

## 贡献、分发与许可证

贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，交流约定见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。问题和功能建议可提交到 [GitHub Issues](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues)。

本项目原创代码、文档和合成样本采用 **GNU AGPL v3.0（SPDX: `AGPL-3.0-only`）**，Copyright (C) 2026 CacinieP。完整条款见 [LICENSE](LICENSE)，第三方组件及保留许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。第三方代码不因位于本仓库而改换原许可证。

提供网络服务的修改版本需遵守 AGPL 第 13 条的对应源代码提供要求；请保留界面的源码链接，并指向实际部署版本可访问的完整源码。上传的用户文档不自动变成本项目的授权内容。

提交并审阅后执行 `bash scripts/package.sh`，生成仅包含当前提交的 `dist/TeXada-Studio-with-agentskills-<commit>.zip`。打包不读取未跟踪文件，也不包含 Git 历史。`scripts/backup.sh` 的 Git bundle 包含历史，仅作私密备份，不作为公开源码包。
