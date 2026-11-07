# TeXada Studio 本地版

在自己的电脑上编辑 LaTeX、识别图片或 PDF、检查公式和简单表格。查看修复差异，审阅后保存，再编译和导出。

这是在浏览器中打开的本地工作台。源码、文档与运行记录保存在本机；图片识别和模型候选使用你配置的本机模型服务。

[English](README.en.md) · [开始使用](#开始使用) · [配置](#配置) · [完整指南](docs/local-studio.md) · [AgentSkills](docs/agent-skills.md) · [文档导航](docs/index.md)

![TeXada Studio：本地 LaTeX 源码与中文 PDF 双栏工作区](assets/studio-workspace.png)

当前界面截图，使用仓库自带的合成 `welcome.tex` 示例；2026-11-04。

当前面向本地单用户，仍是开发候选，尚无本次正式 Release。已验证范围见[当前验证记录](docs/current-validation.md)，历史录屏和模型实验保留各自日期与版本。

## 这版可以做什么

| 工作 | 操作 |
| --- | --- |
| 管理文档 | 导入或新建 `.tex`，保存、重命名、删除；已保存的修改在刷新后保留 |
| 识别资料 | 导入 PNG、JPEG、WebP 或 PDF，每次最多识别 5 页；支持起始页选择、按页剔除/拆分与续批识别；审阅 LaTeX 候选后新建文档 |
| 编辑与检查 | LaTeX 高亮、常用片段与符号补全、五类文档模板、查找替换、文档大纲、命令面板；检查公式语法及简单合计 |
| 修复与审阅 | 先做保留原文的确定性语法修复；模型候选经过语法和修改范围校验，查看 diff 后明确采用或拒绝 |
| 预览与交付 | 编译当前文档，逐页预览并导出 PDF；也可导出 `.tex` 和质检报告 |
| 连接本机模型 | 保存本地服务地址与模型名称，显式检查连接；不会自动改用云模型 |

保存会检查文件版本，发现其他窗口已修改时停止覆盖。编辑内容变化后，旧 PDF 导出会失效，需要重新编译。示例原文件保留在仓库中，保存时建立本地副本。

左侧活动栏可展开文档导航、搜索、图片/PDF 识别和 Agent。点击“检查”查看底部问题列表；从 Agent 中生成和审阅修复候选。底部“问题”“日志”和右侧 Agent 可随时收起，“导出”菜单提供当前 LaTeX 和已编译 PDF。

## 开始使用

需要 **Python 3.11+**。下面以已安装的 `python3.13` 为例，也可替换为其他满足要求的版本：

```bash
git clone https://github.com/CacinieP/TeXada-Studio-with-agentskills.git
cd TeXada-Studio-with-agentskills
python3.13 -m venv .venv
.venv/bin/python -m pip install -r webui/requirements.txt
.venv/bin/python scripts/run-local-studio.py --check
```

macOS 可双击 `scripts/start-local-studio.command`，或在项目目录运行：

```bash
./scripts/start-local-studio.command
```

启动器打开本机浏览器，文档和模型处理都在本地。编辑器资源已随源码提供，无需前端构建。首次安装依赖、模型与 TeX 资源需要联网准备，完整步骤见[首次准备与离线使用](docs/local-studio.md#首次准备与离线使用)。

macOS 还可以生成桌面应用：**自包含包**（内嵌 Python、Tectonic、TeX 资源与 Poppler，产物不依赖仓库/brew/网络，`desktop/build_bundle.py`）或轻量薄壳（`desktop/build_app.py`），详见[桌面端说明](desktop/README.md)与[捆绑许可审计](desktop/licenses-audit.md)。

## 配置

### 本机模型服务

本地模式仅接受 `http://localhost`、`127.0.0.1` 或 `[::1]` 上的 OpenAI 兼容端点（`/v1/models` 与 `/v1/chat/completions`），无需 API Key，也不会自动改用云模型。三种接法：

1. **在界面里配置**：状态栏「本地模型」→ 保存服务地址与模型名称 → 显式「检查连接」。连接信息保存在用户数据目录。
2. **启动时复用已有服务**（例如已在本机运行的 Ollama）：

   ```bash
   .venv/bin/python scripts/run-local-studio.py \
     --base-url http://127.0.0.1:11434/v1 \
     --model minicpm-v4.7-35b-a3b-q4 --no-auto-model
   ```

   模型名称须与本机服务 `/v1/models` 返回的名称完全一致；退出时只停止启动器自己启动的进程，不影响已有服务。
3. **自动启动本机权重**：默认查找 `~/.texada/models/` 下的 GGUF 与 projector，需要 `llama-server`；也可用 `--gguf`/`--mmproj` 显式指定路径。

图片/PDF 识别要求端点真实支持 `image_url`，出现在模型列表不代表已验证；确定性语法修复候选不需要模型。模型下载、默认路径与可选参数见[本机模型连接](docs/local-studio.md#本机模型连接)。

默认使用 **35B-A3B Q4_K_M**（`minicpm-v4.7-35b-a3b-q4`），本地服务默认 `http://127.0.0.1:18147/v1`，保留已保存的手动配置；不自动降级到 1B。权重与视觉投影器约 22.3GB，另需运行缓存与系统内存：16GB 不作为支持目标，24GB 不建议；32GB 是未实测的容量起点，64GB Mac 已实测。1B F16 仍可手动配置。[模型对照与证据边界](docs/evaluation-results/v47-local-comparison-01/README.md)。

### 可选工具与 TeX 资源

| 想使用的功能 | 还需准备 |
| --- | --- |
| 编辑、语法检查、简单表格检查 | 上述 Python 依赖；编辑器资源已随源码提供 |
| 模型候选与图片识别 | 本机 MiniCPM-V 4.7 35B-A3B Q4 服务；自动启动还需 `llama-server`、GGUF 和 projector；确定性语法候选不需要模型 |
| PDF 导入 | Poppler 的 `pdfinfo`、`pdftoppm` |
| PDF 编译与预览 | Tectonic、Poppler 和文档所需的 TeX 缓存、字体 |

Tectonic 可一键自举：Studio 设置面板点「下载 Tectonic」，或运行 `.venv/bin/python scripts/install_local_tools.py`——固定官方 Release、SHA256 校验、安装到 `~/.texada/bin` 并自动加入启动 PATH，运行中的会话装完即可编译。macOS 旁的「安装 Poppler」按钮显式走 brew；其他平台用系统包管理器，见[排错说明](docs/troubleshooting.md)。

Studio 编译只使用已缓存的 TeX 资源，不会在文档处理过程中悄悄下载。首次准备：

```bash
.venv/bin/python scripts/prepare-local-tex.py --download-resources
```

完成后可去掉参数重新运行做离线检查。

### 编辑器偏好与本地数据

字号、自动换行、代码小地图等编辑器偏好保存在当前浏览器。文档、运行记录与连接信息保存在用户数据目录；私密浏览器入口写入权限受限的 `session.json`，访问凭据不打印、每次启动更换。备份与恢复见[本地数据与恢复](docs/local-studio.md#本地数据与恢复)。

## 第一份文档

1. 打开 `welcome.tex` 或 `math-clean.tex`，点击“检查”；编译依赖就绪后点击“编译”。
2. 打开 `math-delimiters.tex`，生成修复候选，查看 diff 后决定是否采用；采用后点击“保存”。
3. 刷新页面，确认保存内容仍在，再导出当前版本的 `.tex` 或 PDF。
4. 选择自己有权使用的图片或 PDF，点击“开始识别”；对照原件审阅识别结果，再新建文档。

“保存”或 `⌘/Ctrl+S` 才会把编辑内容写入本地文档。识别结果和修复候选都不会自动覆盖原文。

公式修复遵循保真策略：候选不能改数字、变量、运算符或删项，缺定界符等情况先补再验；方法与边界见[公式修复质量记录](docs/formula-repair-quality.md)。

用顶栏“命令”或 `⌘/Ctrl+Shift+P` 查找操作；侧栏大纲可跳转到章节。查找与替换使用编辑器自带面板，外观菜单可以调整字号、自动换行和小地图，设置会在本机保留。LaTeX 常用命令、定理类环境与希腊字母等符号提供本地片段建议，也可按 `Ctrl+Space` 主动唤出；章节命令、导言区定义与交叉引用键分级着色，结构模块一眼可辨；编辑器支持按章节与环境折叠；侧栏“从模板新建”可按空白文章、数学讲义、试卷、Beamer 演示与英文文章五类骨架创建文档。状态栏显示光标行列、选区和文档字数。

## 边界与检查范围

语法通过、编译通过、转写忠实与数学正确是不同的判断：`∫₀¹ x dx` 可以语法与编译全过，正确值仍是 `1/2`。OCR、修复候选和表格提示都要结合原文复核。

扫描器支持常见行内与显示公式环境并跳过注释与原样文本；复杂对齐、未知宏和不支持的结构保留人工检查。当前工作单位是单个 `.tex`，多文件工程与多人协作未纳入本地版范围。详见[检查与审阅边界](docs/local-studio.md#检查与审阅边界)与[路线图](docs/roadmap.md)。

## 文档与技术资料

日常使用先看[本地使用指南](docs/local-studio.md)与[排错说明](docs/troubleshooting.md)。其余入口：

- [Studio 操作 Skill](skills/texada-studio/SKILL.md)、[AgentSkills 使用指南](docs/agent-skills.md)：工作区操作、公式/表格、OCR 输入与审阅边界。
- [当前验证](docs/current-validation.md)、[架构](docs/architecture.md)、[CLI Harness](harness/README.md)、[源码打包](docs/source-package.md)。
- 案例、验证历史、Skill 实验、系列说明与历史演示的完整清单见[文档导航](docs/index.md)。

旧 `run-minicpm-v47-studio.sh` 是显式选择的云 API 入口，见[兼容说明](docs/local-studio.md#旧云-api-入口与实验功能)，不要将其结果当作本地推理验收。

原创代码、文档和合成样本采用 **AGPL-3.0-only**；第三方组件保留各自归属，见 [LICENSE](LICENSE)、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [Active Calculus 来源声明](samples/research/ACTIVE_CALCULUS_NOTICE.md)。参与开发见 [CONTRIBUTING.md](CONTRIBUTING.md)，求助见 [SUPPORT.md](SUPPORT.md)。

维护者 [@CacinieP](https://github.com/CacinieP)。引用信息见 [CITATION.cff](CITATION.cff)。
