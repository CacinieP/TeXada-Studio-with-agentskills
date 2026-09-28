# TeXada Studio with Agent Skills

**在 LaTeX 编辑器里发现公式语法与简单表格合计问题，审阅修复候选，再决定是否采用。**

[English](README.en.md) · [文档导航](docs/index.md) · [看演示](docs/demo.md) · [案例手册](docs/casebook.md) · [参与贡献](CONTRIBUTING.md)

适合需要整理 `.tex` 文档的教师、科研写作者，以及研究可审阅模型工作流的开发者。项目将 Monaco 编辑、规则检查、本地模型候选、Tectonic 预览和人工确认放进同一个界面。

**状态：实验原型，尚无正式 Release。** 当前仓库保持私有，仅授权成员可访问；项目源码采用 [AGPL-3.0-only](LICENSE)。面向可信用户的单进程部署，尚未提供多用户服务或公共匿名试用。

![Studio 的源码、预览与人工采用流程](docs/images/studio-overview.png)

## 用一个例子了解

| 文档里的问题 | TeXada 的处理 | 使用者仍需判断 |
| --- | --- | --- |
| 利润数据是 45 和 60，合计却写成 115；PDF 仍能编译 | Studio 定位合计行，按规则生成 105 的候选，展示 diff 与报告 | 数据行本身是否正确 |
| 公式下标 `a_` 不完整，原文编译失败 | 本地模型提出候选，SymPy 回判语法，Tectonic 检查编译 | 补成 `a_1` 是否符合作者原意 |

检查通过不等于数学含义正确；候选不会未经确认就覆盖编辑器原文。详见 [实际演示与单次结果](docs/demo.md)。

## 选择体验方式

| 目标 | 从哪里开始 | 需要什么 |
| --- | --- | --- |
| 看操作和边界 | [演示页](docs/demo.md) | 无需安装 |
| 跑一个可重复的样本 | 下方离线 fixture 快速开始 | Python，无需 GPU / 模型 / TeX |
| 检查正例、反例与边界 | [可执行案例集](samples/evaluation/README.md) | Python；无需模型或编译器 |
| 对照 Skill 指令与模型输出 | [研究协议](samples/research/README.md) | 可先 dry-run / fixture；真实模型另需服务 |
| 编辑、分析自己的可信 tex | 下方 Studio 启动步骤 | Python；编译和模型功能另需依赖 |
| 扩展规则、修复或文档 | [贡献说明](CONTRIBUTING.md) | 对应模块的开发与测试环境 |

## 能力与范围

| 能力 | Studio | CLI |
| --- | --- | --- |
| 输入 | 单个 `.tex`；编辑、上传和导出 | 已有 `layout.json` 结构树 |
| 公式 | 部分行内公式语法；本地文本模型最多两次修复尝试 | SymPy 检查；fixture 或文本模型提出候选 |
| 简单表格合计 | 检查并按规则重算候选 | 检查；fixture 可提供替身数据，真实模型模式尚未实现表格修复 |
| 结果审阅 | 候选 diff、手动采用、逐候选事件与质检报告 | 按本轮出报告；输入和上下文一致时复用终态 |
| 编译预览 | Tectonic 编译；预览第一页 PDF | 当前管线不调用编译器 |

模型请求只发送文本，不发送页面图像。自动 PDF/OCR、复杂跨页表格、多用户隔离与通用自主规划尚未实现。`samples/` 中的 crop 和修复数据是测试替身，不代表 OCR 或模型准确率。Studio 的 Monaco 0.52.2 资源随仓库提供，不依赖编辑器 CDN。

## 快速开始：无需 GPU 的离线样本

需要 Python 3.10+；当前已验证环境为 Python 3.13（其他版本尚未逐一验收）。以下命令在仓库根目录执行。初次安装依赖需要网络，安装完成后 fixture 管线不调用模型服务。

仓库私有期间，clone 需要仓库访问权限和已配置的 GitHub 身份；也可使用维护者提供的源码包。

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
再次运行相同命令可验证断点续跑。输入、模型、Skill 或检查器等上下文改变会自动重新检查；暂时故障恢复后同目录重跑。新目录用于独立运行，完整规则见 [Harness 手册](harness/README.md)。

## 执行检查器案例

安装上述 Python 依赖后，可运行 27 个合成公式与表格案例，检查语法、Decimal 合计、非法输入和不支持格式的处理：

```bash
python scripts/evaluate_cases.py --outdir state/evaluation-01
```

输出为新目录中的 `report.json` 和 `report.md`；重跑须换一个目录，避免覆盖证据。案例按契约、语义边界与已知缺口分组，匹配数不代表模型准确率。详见[案例定义与运行说明](samples/evaluation/README.md)、[逐例解读](docs/casebook.md)和 [Skills 技术报告](docs/skills-technical-report.md)。

## 运行 Skills 受控对照

CLI 真实模型模式默认 `--skill-mode on`，Studio 默认 `SKILL_MODE=on`：宿主读取公式 Skill 正文并加入模型系统消息。切换为 off 可保留相同基础提示与检查流程；Fixture 不加载指令、不调用模型。当前仅公式 Skill 接入该宿主，工具执行与重试仍是固定编排。

[研究运行器](scripts/evaluate_skills.py)比较“仅检查器、同模型无 Skill、同模型有 Skill”，保留来源、参数指纹、全部候选及复核空表。先检查无需模型的执行计划：

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-dry-01 --mode dry-run
```

Dry-run 不执行检查器或网络请求；真实运行、fixture 与人工复核命令见[研究协议](samples/research/README.md)。未完成独立人工复核时语义准确率为空；合成样本、人工注入错误和真实自然错误须分别解释。

## 启动 Studio

```bash
python -m pip install -r webui/requirements.txt
export DEMO_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
# 先显示只供自己使用的本地地址，再以前台方式启动
printf 'http://127.0.0.1:8888/studio?token=%s&file=report-01.tex\n' "$DEMO_TOKEN"
python -m uvicorn app:app --app-dir webui --host 127.0.0.1 --port 8888
```

打开启动前打印的本地地址；按 `Ctrl-C` 停止服务。该地址带个人 token，不要分享截图或原样复制进 Issue。
没有设置 token 时服务会拒绝启动。也可复制 [`.env.example`](.env.example) 为 `.env`，填写后执行 `set -a; . ./.env; set +a`；应用不会自动读取 `.env`。

编辑和浏览文件只需要 Python 依赖。完整功能还需要：

| 功能 | 依赖 |
| --- | --- |
| 公式分析 / 表格检查 | `webui/requirements.txt` 中的 SymPy、antlr4 等 |
| 编译 PDF 与第一页预览 | [Tectonic](https://tectonic-typesetting.github.io/)、Poppler 的 `pdftoppm`；可执行文件位于 `PATH` |
| 中文样本编译 | 字体 `Noto Sans CJK SC` 与所需 TeX 包 |
| 模型修复 | 本机 Ollama 的兼容接口，固定访问 `127.0.0.1:11434`；`VLM_MODEL` 必须是已安装的模型标签 |

可通过 `TECTONIC` 指定编译器完整路径，通过 `VLM_MODEL` 更换已安装的模型。
默认标签 `qwen3.8:27b-q4_K_M` 来自实测节点，不保证你的机器已有同名模型。先运行 `ollama list`，再用 `export VLM_MODEL="实际已安装的标签"` 选择；可用 `curl --fail http://127.0.0.1:11434/v1/models` 检查接口。fixture 测试无需模型。程序不会自动安装模型、字体或系统软件。

上传文档保存在 `state/studio/documents/`；同名上传会覆盖此前上传的版本，但不会改写仓库自带样本。任务结果与逐候选事件保存在 `state/studio/jobs/<job_id>/`。服务重启后可按已知 job_id 查询已完成结果；中断任务提示新建，不会自动继续模型调用。页面暂无历史任务列表，浏览器中尚未导出的编辑仍需自行保留。这些产物均被 Git 忽略。

节点部署与用户级安装见 [部署说明](deploy/README.md)。默认只监听本机；共享部署前阅读 [安全说明](SECURITY.md)。不要把当前服务用于接收陌生人的 TeX 文件。

## 测试

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_*.py' -v
python -m unittest discover -s harness/tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p 'test_evaluate_*.py' -v
python -m unittest discover -s skills/latex-cleanup/tests -p 'test_*.py' -v
node webui/test_studio.cjs
node skills/latex-cleanup/tests/test_audit_math.cjs
```

Node.js 22 用于 JavaScript 检查。Harness 测试覆盖 Skill 加载、检查器故障、哈希绑定续跑与候选证据；运行器回归检查输出协议、目录保护及人工复核导入。上述测试不需要 GPU 或模型，也不代表真实浏览器视觉验收或 TeX 编译验收。实际编译检查见 [latex-cleanup 测试说明](skills/latex-cleanup/tests/CASES.md)。

## 限制与复现范围

- 执行中的任务依赖进程内存；仅启动一个 Uvicorn worker。完成结果可以读取恢复，中断任务不自动续跑。并发编辑、任务取消和用户隔离尚未实现。
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
| `samples/` | 可分发的 Studio / CLI 样本、修复替身与确定性检查案例 |
| `deploy/` | DGX Spark 节点部署记录 |
| `docs/` | 架构、提案、演示和比赛提交清单；提案不等于已实现功能 |
| `scripts/` | [案例评估](scripts/evaluate_cases.py)、[Skills 对照与人工复核](scripts/evaluate_skills.py)、Monaco 校验 / 恢复、源码打包与备份 |

## 贡献、分发与许可证

贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，交流约定见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。求助入口与报告要求见 [SUPPORT.md](SUPPORT.md)。问题和功能建议可提交到 [GitHub Issues](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues)。

本项目原创代码、文档和合成样本采用 **GNU AGPL v3.0（SPDX: `AGPL-3.0-only`）**，Copyright (C) 2026 CacinieP。完整条款见 [LICENSE](LICENSE)，第三方组件及保留许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。第三方代码不因位于本仓库而改换原许可证。新增开放教材公式数据及改编单独采用 CC-BY-SA-4.0，见[来源声明](samples/research/ACTIVE_CALCULUS_NOTICE.md)。

提供网络服务的修改版本需遵守 AGPL 第 13 条的对应源代码提供要求；请保留界面的源码链接，并指向实际部署版本可访问的完整源码。上传的用户文档不自动变成本项目的授权内容。

提交并审阅后执行 `bash scripts/package.sh`，生成仅包含当前提交的 `dist/TeXada-Studio-with-agentskills-<commit>.zip`。打包不读取未跟踪文件，也不包含 Git 历史。`scripts/backup.sh` 的 Git bundle 包含历史，仅作私密备份，不作为公开源码包。

## 项目与维护

团队：LinguistsWantTech；队长邓一纯，队员刘丰华。仓库由 [@CacinieP](https://github.com/CacinieP) 维护。研究引用可使用 [CITATION.cff](CITATION.cff)，并注明实际使用的提交号。

这是第三届 NVIDIA DGX Spark 黑客松 Agent Skills 方向的实验项目。参赛材料：[项目报告](docs/project-report.md) · [技术征文](docs/technical-article.md) · [验证记录](docs/validation.md)。

维护者入口：[开源检查](docs/open-source-release.md) · [发布与传播计划](docs/launch-plan.md) · [变更记录](CHANGELOG.md) · [仓库迁移记录](docs/repository-migration.md)。
