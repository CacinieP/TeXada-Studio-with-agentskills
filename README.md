# TeXada Studio with Agent Skills

在 LaTeX 编辑器里检查公式语法和简单表格合计，审阅修复候选，再决定是否采用。

[English](README.en.md) · [演示视频](https://www.bilibili.com/video/BV16Kan6rEGv/) · [Skill 设计与技术报告](docs/skills-technical-report.md) · [文档导航](docs/index.md) · [案例手册](docs/casebook.md)

TeXada 将 Monaco 编辑器、规则检查、本地模型和 Tectonic 预览放在同一个工作台中。公式候选以 diff 展示，手动采用后可导出 `.tex`、PDF 和质检报告。

当前为可复现的实验原型，源码采用 AGPL-3.0-only，尚无正式 Release。部署面向可信用户，使用单进程和共享 token。

![Studio 源码、预览与候选审阅](docs/images/studio-overview.png)

## 演示与参赛材料

第三届 NVIDIA DGX Spark 黑客松 · Agent Skills 开发挑战赛参赛项目。

| 内容 | 入口 |
| --- | --- |
| 实机演示 | [B 站视频](https://www.bilibili.com/video/BV16Kan6rEGv/)：约3分42秒，保留模型等待、diff 审阅和人工采用；[录制说明与证据](docs/dynamic-demo.md) |
| 项目介绍 | [项目报告](docs/project-report.md)：使用场景、工作流与实现范围 |
| Skill 技术报告 | [设计与实现](docs/skills-technical-report.md)：职责划分、状态契约、加载方式、扩展与验证 |
| 参赛征文 | [仓库全文](docs/technical-article.md)；微信公众号链接：**待作者审核后手动发布并补充** |
| 可复现结果 | [案例手册](docs/casebook.md) · [验证记录](docs/validation.md) · [Skill 对照实验](docs/skills-pilot-analysis.md) |

公式 Skill 用 `SKILL.md` 说明检查与修复步骤，脚本给出确定性结果，Python 宿主管理状态和最多两次模型请求。模型只产生候选，候选经检查后进入人工审阅。当前接入模型请求的是 `doc-formula-verify`；小样本对照尚未观察到 Skill 带来输出改善，具体设计与实验记录见上表。

## 1. 先跑无需模型的样本

需要 Python 3.11+，已验证版本为 3.13。以下命令在 POSIX shell 中执行，Windows 可使用 WSL。首次安装依赖需要网络。

```bash
git clone https://github.com/CacinieP/TeXada-Studio-with-agentskills.git
cd TeXada-Studio-with-agentskills
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

预期输出：

```text
exam-01: OK=3 NEEDS_HUMAN=0
paper-01: OK=2 NEEDS_HUMAN=1
report-01: OK=2 NEEDS_HUMAN=0
report: state/quickstart/report.md
```

打开 `state/quickstart/report.md` 查看候选和待人工项。此模式读取预设修复，验证处理流程；无需 GPU、模型或 TeX。重复同一命令可验证续跑，详见 [CLI 手册](harness/README.md)。

## 2. 打开 Studio

在同一虚拟环境中安装 Web 依赖并启动：

```bash
python -m pip install -r webui/requirements.txt
export DEMO_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf 'http://127.0.0.1:8888/studio?token=%s&file=math-clean.tex\n' "$DEMO_TOKEN"
python -m uvicorn app:app --app-dir webui --host 127.0.0.1 --port 8888 --workers 1
```

打开打印的本地链接，按 `Ctrl-C` 停止。token 是访问凭据，请保存在本机；应用不会自动加载 `.env`，使用配置文件时先执行 `set -a; . ./.env; set +a`。配置项见 [`.env.example`](.env.example)。

先看 `math-clean.tex`，再切换 `math-delimiters.tex` 检查缺失的闭合定界符，最后看 `math-semantics.tex` 中语法合法但积分值错误的反例。现有 [13 份 Studio 样本](samples/README.md)。

| 功能 | 所需依赖 |
| --- | --- |
| 编辑、公式分析、简单表格检查 | 上述 Python 依赖；Monaco 0.52.2 已随仓库提供 |
| PDF 编译与第一页预览 | [Tectonic](https://tectonic-typesetting.github.io/) 和 Poppler 的 `pdftoppm`，放入 `PATH`；也可用 `TECTONIC` 指定编译器路径 |
| 中文样本编译 | `Noto Sans CJK SC` 字体；新增英文数学样本无需该字体 |
| 公式候选生成 | 下一节中的本机模型服务 |

Tectonic 首次编译可能下载 TeX 包。安装与预览问题见[排错说明](docs/troubleshooting.md)，持久运行和升级见[部署手册](deploy/README.md)。

## 3. 接入真实模型

先准备本机 Ollama 兼容服务，选择已经安装的模型标签：

```bash
ollama list
curl --fail http://127.0.0.1:11434/v1/models
export VLM_MODEL='替换为已安装的完整模型标签'
export SKILL_MODE=on
```

在设置这些变量的终端启动或重启 Studio。模型接口固定为 `127.0.0.1:11434`；程序发送公式文本，最多尝试两次候选。`SKILL_MODE=on` 会读取公式 Skill 正文加入系统消息，`off` 用于对照。默认模型标签因入口而异，显式设置可避免误用。

CLI 使用同一模型时：

```bash
PYTHONPATH=harness python -m docforensics run samples \
  --state state/model-01 \
  --vlm http://127.0.0.1:11434 --vlm-model "$VLM_MODEL" --skill-mode on
```

真实候选和计数取决于模型。报告仍写入 `--state` 指定目录。Skill 加载记录、请求参数和续跑规则见 [CLI 手册](harness/README.md)。

## 4. 测试与评估复现

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_*.py' -v
python -m unittest discover -s harness/tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p 'test_evaluate_*.py' -v
python -m unittest discover -s skills/latex-cleanup/tests -p 'test_*.py' -v
node webui/test_studio.cjs
node skills/latex-cleanup/tests/test_audit_math.cjs
```

JavaScript 测试使用 Node.js 22。以上回归测试无需模型。Studio 样本编译见下表，latex-cleanup 的编译测试见[该模块说明](skills/latex-cleanup/tests/CASES.md)。

| 要复现的内容 | 命令或入口 | 结果位置 |
| --- | --- | --- |
| 27 个确定性检查案例 | `python scripts/evaluate_cases.py --outdir state/evaluation-01` | `report.json`、`report.md` |
| Skills 三组执行计划 | 下方 dry-run 命令 | 配置、逐项结果、报告、复核空表 |
| 同模型有 / 无 Skill 对照 | [研究协议](samples/research/README.md) | 新运行目录；人工语义判定另行导入 |
| 12份 Studio 编译输入 | `python scripts/compile_studio_cases.py --outdir state/studio-compile-01` | `report.json`、源码、日志和PDF；[依赖与预期](docs/evaluation-results/studio-latex/README.md) |
| 已有实验与编译记录 | [验证记录](docs/validation.md) | 固定输入、环境和原始结果 |

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-dry-01 --mode dry-run
```

评估与编译运行器都要求新的输出目录。Dry-run 只验证执行计划；检查器案例、fixture 和真实模型结果按各自方法解释，详见对应入口。

## 支持范围与数据

Studio 接收单个 `.tex`，目前按行提取 `$...$` 公式并检查简单表格；CLI 接收已有 `layout.json`，运行公式和表格检查。Studio 可按规则重算简单合计，CLI 真实模型模式只修复公式。PDF 预览显示第一页。完整项目上传、OCR、多行公式提取和多用户隔离在[路线图](docs/roadmap.md)中。

语法通过、编译通过和数学结论正确是不同判断。例如 `∫₀¹ x dx = 1` 可通过前两项，正确值仍是 `1/2`。候选需对照原意审阅。

上传文件保存在 `state/studio/documents/`，同名上传会覆盖已有上传版本；任务记录在 `state/studio/jobs/`。已完成任务可按 job ID 查询，中断任务需重新发起。部署只接收可信文档；TeX 编译的信任边界见 [SECURITY.md](SECURITY.md)。

## 开发与许可证

代码入口：[`webui/`](webui/) 是 Studio，[`harness/`](harness/) 是 CLI，[`skills/`](skills/) 是指令与检查工具，[`samples/`](samples/) 是可运行输入，[`scripts/`](scripts/) 是评估和打包工具。参与方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，求助见 [SUPPORT.md](SUPPORT.md)。

原创代码、文档和合成样本采用 **AGPL-3.0-only**，见 [LICENSE](LICENSE)。第三方组件及开放教材样本保留各自许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [Active Calculus 来源声明](samples/research/ACTIVE_CALCULUS_NOTICE.md)。网络部署的修改版本应提供对应源代码入口。

团队 LinguistsWantTech：队长邓一纯，队员刘丰华；维护者 [@CacinieP](https://github.com/CacinieP)。引用见 [CITATION.cff](CITATION.cff)。赛事材料和发布资料集中在[文档导航](docs/index.md)。
