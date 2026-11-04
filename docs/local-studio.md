# TeXada Studio 本地使用指南

本地版采用 TeXada 的深海蓝界面，以源码与 PDF 为主体，将检查、候选、审阅和导出放在一个工作台中。当前面向一位使用者，在自己的电脑上处理单个 `.tex` 文档。已完成本机模型、Chrome 主流程、OCR 和编译 smoke；原始范围与结果见[本地版验收记录](local-studio-acceptance.md)。

## 文档工作流

1. **导入或新建**：打开 `.tex`，或用图片/PDF 识别产生新文档候选。
2. **编辑与保存**：在 Monaco 中编辑，点击“保存”或按 `⌘/Ctrl+S`。未保存修改会显示提示，刷新前仍应保存。
3. **检查**：先做确定性的公式语法与简单表格合计检查。注释、原样文本和复杂数学结构按照支持范围处理。
4. **生成候选**：打开 Agent，点击“修复候选”。先运行保留原文的确定性语法规则，无法处理时保留人工项或请求受限模型候选；宿主检查语法及修改范围。模型流程最多两次请求，并携带拒绝反馈。确定性修复成功时模型请求数为 0。
5. **审阅**：比较原文和候选，明确采用或拒绝。采用只更新编辑器，之后仍需保存。任务与决定保存在历史记录中。
6. **预览和导出**：编译当前内容，切换页面核对。内容改变后，需要重新编译才能导出当前 PDF。

已有本地文档使用版本检查保存。同名上传或其他窗口的更新不会被静默覆盖；冲突时应重新打开核对，或用其他名称保存。仓库示例为只读素材，保存创建用户副本。

### 编辑器操作

深海蓝工作区默认显示文档导航、源码和 PDF。右侧 Agent 与底部活动面板默认收起；旧版浅色主题和面板尺寸不会覆盖这版布局。左侧活动栏依次打开文档、搜索、图片/PDF 识别、Agent 和编辑设置。

主动“检查”会展开问题结果，修复生成后打开候选审阅，任务失败可在日志中持续查看。点击底部“问题”或“日志”切换与收起；Agent 可用开关、关闭按钮或 Esc 收起。设置菜单中可打开本机模型配置、编辑器设置和历史记录。

“导出”菜单包含 LaTeX、PDF 等当前可用操作。PDF 需要先编译当前内容；修改或拒绝候选后，旧 PDF 会变为不可导出。预览“适应”显示整页，“100%”按原始尺寸查看，可滚动检查细节。

- 顶栏“命令”或 `⌘/Ctrl+Shift+P` 打开命令面板；输入操作名筛选，方向键选择，回车执行，Esc 返回编辑。
- 使用“查找”“替换”打开 Monaco 的搜索面板，支持区分大小写、正则与选区搜索；替换会标记为未保存。
- 侧栏“大纲”识别常用章节标题，点击跳转到原文。注释和常见逐字环境中的示例标题不列入大纲；动态宏生成的标题仍需在源码中查找。
- “编辑器外观”可调整字号、自动换行与小地图，设置保存在当前浏览器。底栏实时显示光标行列、选区与字数；字数是编辑信息，不是论文投稿规则的统计口径。
- LaTeX 命令、注释与数学区域有语法高亮；常用公式及成对环境提供本地片段补全，`Ctrl+Space` 可主动唤出。补全只在选择后插入，不调用模型。

大纲、语法高亮和片段补全用于写作导航，不替代 TeX 编译或数学检查。

### 图片与 PDF 识别

选择 PNG、JPEG、WebP 或 PDF 后，主动点击“开始识别”。图片或渲染出的 PDF 页面只发送给配置的本机模型服务。结果在审阅框中显示，可先修改，再用新文件名创建文档。

- 原始文件最多 12 MiB；图片边长和像素数有上限，超限会要求裁剪或缩小。
- 每次 PDF 请求最多处理 1–5 页，界面提供 1、3、5 页的选择。接口还支持指定起始页；返回的来源页码和“仍有未处理页”状态会保留，不会把截取部分标成全文。
- PDF 导入需要本机 Poppler 的 `pdfinfo` 和 `pdftoppm`。加密、损坏或无法渲染的文件会明确失败。
- 来源哈希、逐页最终转写、使用的模型与候选文档保存在本地，便于对照；不会保存模型的隐藏推理作为文稿。
- 识别内容不会直接写入已有文档。看不清的符号、公式和文字仍需对照原件确认。

## 首次准备与离线使用

需要 Python 3.11+；本轮开发和验证环境使用 3.13。先在项目目录准备虚拟环境：

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r webui/requirements.txt
.venv/bin/python scripts/run-local-studio.py --check
```

`--check` 只检查 Python 依赖、可选工具和配置，不探测模型、不启动服务、不写会话。缺少依赖时给出提示，不会自动安装。

Monaco 编辑器及其字体、工作线程资源已随源码提供。安装依赖、模型和 TeX 资源是首次准备工作，可能需要联网；正常使用本地 Studio 的编辑器、检查器和已准备好的模型不需要云 API。

### 准备 PDF 编译资源

PDF 预览需要 Tectonic 和 Poppler。先把 `tectonic`、`pdftoppm`、`pdfinfo` 放入 `PATH`；也可以用 `TECTONIC` 环境变量明确指定本机编译器。

先离线检查中文、公式、表格与两页 PDF 所需资源：

```bash
.venv/bin/python scripts/prepare-local-tex.py
```

如果提示资源不足，可在允许联网的准备阶段明确执行：

```bash
.venv/bin/python scripts/prepare-local-tex.py --download-resources
.venv/bin/python scripts/prepare-local-tex.py
```

第二个命令重新使用缓存检查。准备脚本只覆盖它的固定样本；引入其他宏包、字体或文档类的文档，仍可能需要单独准备相应资源。正常 Studio 编译使用 `--only-cached`，缺资源时保留错误信息，不会隐式补下载。

本次机器已完成固定中文/公式/表格两页样本的资源准备并生成 PDF，离线检查还覆盖了 Fandol 中文、标题和粗斜体。OCR 默认文档使用 `ctexart` 的通用 Fandol 字体集，避免依赖特定 macOS 中文字体。这只证明已检查样本的依赖可用，不代表任意 TeX 工程都能离线编译。

### 启动和退出

macOS 可双击 `scripts/start-local-studio.command`，或运行：

```bash
./scripts/start-local-studio.command
```

启动器使用项目 `.venv`，打开本机浏览器，默认监听 `127.0.0.1:8888`。访问凭据不会打印；私密入口只写入用户数据目录的 `session.json`。不要把该文件或带访问参数的地址放进截图、报告、仓库或公开分享。

按启动终端中的 `Ctrl+C` 停止。启动器只停止自己启动的模型，不会关闭已经存在的 Ollama 或 llama-server 服务。

需要自行打开浏览器、调整端口或选择数据目录时：

```bash
.venv/bin/python scripts/run-local-studio.py --no-browser --port 8890 --state-dir ./state/local-profile
```

此时从自己机器的数据目录打开私密入口。完整参数见：

```bash
.venv/bin/python scripts/run-local-studio.py --help
```

## 本机模型连接

本地模式仅允许 HTTP 回环地址：`localhost`、`127.0.0.1`、`[::1]`。请求绕过环境与系统代理，拒绝重定向，不读取或发送云 API Key，也没有云端自动回退。

支持 OpenAI-compatible `/v1/models` 和 `/v1/chat/completions`。图片识别还需要端点实际支持 `image_url`。仅在模型列表中看到名称，不等于已验证该端点的视觉能力。

### 使用已有服务

在界面的本地模型连接卡片中保存地址与模型名称，再显式检查连接；也可以启动时指定：

```bash
.venv/bin/python scripts/run-local-studio.py \
  --base-url http://127.0.0.1:18081/v1 \
  --model MiniCPM-V-4.7-1B --no-auto-model
```

模型名称必须是本机服务真实使用的名称。Ollama 用户应使用自己已安装并支持所需能力的完整标签。没有可用模型时，文档管理、编辑和确定性检查仍可使用，生成与 OCR 会显示连接错误。

### 自动启动已有权重

启动器可以查找：

```text
~/.texada/models/MiniCPM-V-4_7-1B-Q4_K_M.gguf
~/.texada/models/mmproj-model-f16.gguf
```

同时需要 `PATH` 中的 `llama-server`，或已有的 `~/.texada/bin/llama-server`、`~/.texada/runtime/llama-server`。这些文件不会随 Studio 自动下载。官方模型来源：[1B checkpoint](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B)、[1B GGUF](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B-gguf)。

也可以明确指定已有文件，避免重复保存权重：

```bash
.venv/bin/python scripts/run-local-studio.py \
  --gguf /path/to/model.gguf --mmproj /path/to/mmproj.gguf \
  --model-port 18081
```

自行启动的模型只绑定回环地址，使用单个 slot、8192 上下文和关闭 thinking 的配置。它会占用本机内存；无法启动、端口被占用或缺文件时给出明确提示。退出时只回收启动器持有的进程。

## 本地数据与恢复

默认用户数据目录：

| 系统 | 目录 |
| --- | --- |
| macOS | `~/Library/Application Support/TeXada Studio` |
| Windows | `%LOCALAPPDATA%/TeXada Studio` |
| Linux | `$XDG_DATA_HOME/texada-studio`，未设置时为 `~/.local/share/texada-studio` |

可使用 `--state-dir` 或 `TEXADA_STUDIO_STATE_DIR` 另选目录。当前实际验收以 macOS 为主；提供路径分支不代表已经完成 Windows/Linux 实机验收。

| 内容 | 位置与含义 |
| --- | --- |
| 用户文档 | `documents/`；写入本机并检查保存版本 |
| 历史副本 | `documents/.history/`；覆盖、改名或删除前保存的版本 |
| 删除文件 | `documents/.trash/`；界面尚无恢复按钮，需要从本机目录另存恢复 |
| 修复任务 | `jobs/<id>/job.json`、`events.jsonl`；候选、检查与审阅决定 |
| OCR 来源 | `imports/<id>/`；来源文件与逐页候选记录 |
| 模型设置 | `local-runtime.json`；仅本机地址与模型名，无密钥 |
| 运行入口 | `session.json`；权限受限的当前会话访问入口，退出时清除其私密 URL |

完成的任务可从界面历史打开；候选只有在当前文档内容仍与来源匹配时才可采用。进程中断不会把未完成任务伪装成成功；重新启动后应重新生成需要执行的任务。已保存的文档不依赖浏览器缓存。

备份前先保存并停止服务。文档、来源图片和记录可能包含私人内容，应使用自己的受保护备份位置；不要把 `session.json` 当作普通报告分发。

## 检查与审阅边界

扫描器保持精确来源范围，支持常见行内、显示和数学环境，并跳过注释、原样文本与常见命令定义。它不解释 TeX 的完整宏展开和类别码。`align`、多行对齐、未知宏或检查器不支持的结构会转人工，不以压平结构的方式自动修复。

公式检查与候选回判共用确定性工具；表格合计使用 Decimal 对支持的简单结构重算。数字带复杂单位、宏或不支持的表格形态时保留原文，提示人工检查。

候选通过检查不等于数学结论正确，PDF 编译通过也不等于 OCR 忠实。当前没有独立人工准确率结论。本次本机 smoke 已记录：

| 检查 | 已观察结果与范围 |
| --- | --- |
| MiniCPM-V 4.7 1B Q4 | 一页固定图像转写保留 `x^2+1` 锚点；两页固定 PDF 转写完成；生成的候选 LaTeX 可编译 |
| 公式候选 | 缺失括号样例经一次实际模型请求修复；不据此推算总体修复成功率 |
| 编译与交付 | 英文两页 PDF、页面 PNG 与 PDF 导出；中文 Fandol、标题和粗斜体离线资源检查通过 |
| Chrome 主流程 | 新建/保存/刷新、多页切换与下载、编辑后旧 PDF 失效、表格零模型候选的拒绝与采用记录、刷新历史恢复、采用后保存刷新及 390px 界面检查 |
| 自动化回归 | 当前记录为 Web 144、harness 87、scripts 52，共 283 项 Python 检查；前端 VM 检查通过，确定性检查器 27/27 |

这些结果覆盖固定输入和当前机器，不是手写、真实论文或多来源 OCR 准确率评测，也不证明数学真值或 Windows/Linux 实机表现。完整版本与步骤见[验收报告](local-studio-acceptance.md)。

## 旧云 API 入口与实验功能

`scripts/run-minicpm-v47-studio.sh` 保留为明确选择的旧云 API 入口，使用 `TEXADA_LOCAL_MODE=0`。它与本地启动器是不同的执行配置；云推理记录不能当作本机 Q4 结果。需要沿用时，先通过进程环境提供自己的 API 配置，参阅[历史 MiniCPM 4.7 适配](minicpm-v47.md)与[部署说明](../deploy/README.md)。不要把密钥写进文档或仓库。

默认关闭的[受限 Agent 规划](studio-constrained-planner.md)、[多 Skill 选择](studio-skill-selection.md)和[单公式 Math Agent 交接](studio-formula-handoff.md)保留为实验。交接需要另外运行配置好的 Math Agent；普通本地编辑、候选和 OCR 不依赖它。实验仍受候选审阅、版本绑定和宿主预算约束。

较早的文章、界面图和演示只描述各自日期的版本，不能用来证明本次 UI、离线或 OCR 验收已经完成。

## 开发与复现

### 无需模型的 CLI 样本

```bash
PYTHONPATH=harness .venv/bin/python -m docforensics run samples \
  --state state/quickstart --fixture-repairs samples/fixture_repairs.json
```

预期结果：

```text
exam-01: OK=3 NEEDS_HUMAN=0
paper-01: OK=2 NEEDS_HUMAN=1
report-01: OK=2 NEEDS_HUMAN=0
report: state/quickstart/report.md
```

此模式只读取预设候选，不请求真实模型，也不证明模型质量。重复运行检查续跑复用；数据契约和状态规则见 [CLI 手册](../harness/README.md)。CLI 的 `layout.json` 工作流与 Studio 输入各有明确范围。

### 回归测试

```bash
.venv/bin/python -m pip install -r webui/requirements-test.txt
.venv/bin/python -m unittest discover -s webui -p 'test_*.py' -v
.venv/bin/python -m unittest discover -s harness/tests -p 'test_*.py' -v
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py' -v
.venv/bin/python -m unittest discover -s skills/latex-cleanup/tests -p 'test_*.py' -v
node webui/test_studio.cjs
node webui/test_latex.cjs
node skills/latex-cleanup/tests/test_audit_math.cjs
```

JavaScript 测试使用 Node.js 22。上述回归使用 fixture 或本地 HTTP 测试替身，不把它们记作真实模型验收。完整浏览器、编译器和模型实测分别记录。

| 复现内容 | 入口 |
| --- | --- |
| 确定性检查案例 | `scripts/evaluate_cases.py`；[已有结果](evaluation-results/README.md) |
| Skill 有/无对照与执行计划 | [研究协议](../samples/research/README.md)、[先导分析](skills-pilot-analysis.md) |
| 固定 Studio 编译输入 | `scripts/compile_studio_cases.py`；[依赖与结果](evaluation-results/studio-latex/README.md) |
| latex-cleanup 编译和行为检查 | [测试说明](../skills/latex-cleanup/tests/CASES.md) |
| 项目与接口设计 | [架构](architecture.md)、[Skill 技术报告](skills-technical-report.md)、[历史验证](validation.md) |

评估运行器需要新的输出目录。只验证执行计划的示例：

```bash
.venv/bin/python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-dry-01 --mode dry-run
```

### 研究参考与后续消融

以下一手工作提供可以借鉴的机制。本次产品实现没有复现它们的论文分数，也没有完成这些机制在 MiniCPM 上的独立消融。

| 一手材料 | 可借鉴的机制与本产品边界 |
| --- | --- |
| [SWE-agent](https://arxiv.org/abs/2405.15793) | 缩小动作表面、短反馈与编辑检查；本地 Studio 仍需按自己的文档任务验证收益 |
| [Agentless](https://arxiv.org/abs/2407.01489) | 分阶段定位、候选与验证；可以对比固定流程和受限规划，不预设更自主一定更好 |
| [Design2Code](https://arxiv.org/abs/2403.03163) | 把视觉差异分维度检查；PDF 图片相似不能替代公式或内容正确性 |
| [SWE-bench Multimodal](https://arxiv.org/abs/2410.03859) | 真实视觉问题及可执行验收；适合借鉴带原件的错误样本组织，尚未迁移为本产品基准 |
| [MM-ContextFold](https://arxiv.org/abs/2609.23121) | 视觉子任务按需读取，主上下文保留结果；原研究是多模态检索，本产品未实现其完整分支折叠方案 |
| [ReFold](https://arxiv.org/abs/2610.07863) | 保留原始历史、可恢复地折叠模型视图；不把其大模型实验收益当作本地 1B 模型结果 |

可复用的下一步研究是固定模型和预算，对比普通候选、Skill 指令、受限规划与不同证据视图，分别报告修复成功、错误放行、人工介入、耗时和请求数。训练数据、公开测试与独立复核应保持各自的来源与用途。
