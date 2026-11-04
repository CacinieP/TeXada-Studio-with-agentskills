# 安装与使用排错

本页对应当前本地浏览器版。正常入口是 `scripts/start-local-studio.command`，不是旧云 API 脚本；完整步骤见[本地使用指南](local-studio.md)。文档编辑、确定性检查与可确定的语法候选不需要模型；图片/PDF 转写和模型候选需要配置好的本机服务；PDF 编译另需 TeX 与页面转换工具。

以下命令从仓库根目录运行。遇到问题先保留未保存内容、错误与任务记录，再按相应功能排查。

## 找不到仓库、Python 或依赖

仓库地址为 `https://github.com/CacinieP/TeXada-Studio-with-agentskills.git`。`Repository not found` 时先核对地址和自己的 Git 访问配置。

需要 Python 3.11 或更新版本。用自己实际安装的版本创建虚拟环境，例如：

```bash
python3 -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip install -r webui/requirements.txt
.venv/bin/python -m pip check
.venv/bin/python scripts/run-local-studio.py --check
```

`--check` 只检查 Python 依赖、可选工具和配置，不启动服务、不探测模型、不写会话。缺少 Tectonic 或 Poppler 不影响源码编辑，但相应 PDF 功能不可用。`No module named docforensics` 通常表示绕过了项目入口或 Python 环境不一致；先使用上述 `.venv/bin/python` 和启动器。

安装提示找不到固定版本时，先确认 Python 版本、所用虚拟环境及包源。镜像可能尚未同步；需要时显式使用官方包源安装同一份依赖：

```bash
.venv/bin/python -m pip install --index-url https://pypi.org/simple -r webui/requirements.txt
```

不要只根据镜像显示的版本列表修改固定依赖。开发测试所需依赖和命令另见[回归测试](local-studio.md#回归测试)。

## 启动后没有窗口、端口被占用或显示 401

macOS 可双击 `scripts/start-local-studio.command`；终端入口为：

```bash
./scripts/start-local-studio.command
```

启动器默认打开本机浏览器，在 `127.0.0.1:8888` 提供工作台，并自行生成会话访问凭据。普通本地使用不需要手动配置 `DEMO_TOKEN` 或复制 `.env`。只打开不带会话信息的 `/studio` 地址会返回 401。

同一数据目录的实例仍在运行时，再次启动会重新打开已有工作区。若系统未自动打开浏览器，只在自己机器上使用本次数据目录 `session.json` 中的私密入口；不要打印到共享日志、贴入 Issue 或截进图片。旧会话的链接在服务重启后可能失效，应使用当前实例的入口，不关闭鉴权来绕过 401。

端口被其他程序占用时，选择另一个端口，不停止无关服务：

```bash
.venv/bin/python scripts/run-local-studio.py --port 8890
```

同一数据目录只启动一个实例。需要独立测试配置时，显式选择另一数据目录和空闲端口，见[启动和退出](local-studio.md#启动和退出)。按启动终端中的 `Ctrl+C` 停止；启动器只清理自己启动的模型进程。

## 页面打开，但编辑器空白

工作台入口是 `/studio`。Monaco 编辑器资源已随源码提供，不依赖外部 CDN。核对源码包中的 `webui/static/monaco/0.52.2/` 是否完整，并使用当前实例的私密入口重新打开页面。

编辑器资源通过受限 Cookie 鉴权。允许此本机站点使用 Cookie；仍为空白时，查看浏览器开发者工具中失败请求的状态码。反馈时删除 URL 中的 token、Cookie、私人文件名和正文，不提交 `session.json`。

## 本地模型显示未检查、未连接或缺少目标模型

“未检查”表示尚未进行显式连接检查，不等于服务已经失败。点击状态栏的模型入口或工作区设置中的“本地模型”，核对服务地址与实际模型名称；“检查连接”只检查草稿，“保存设置”才使修改生效。

本地模式仅接受 HTTP 回环地址，例如 `http://127.0.0.1:18081/v1`；不接受云地址或云 API Key，不自动切换云服务。服务需支持 `/v1/models` 和 `/v1/chat/completions`；图片识别还需实际支持 `image_url`。能列出模型名称不证明视觉推理可用。

已有服务可在启动时明确指定：

```bash
.venv/bin/python scripts/run-local-studio.py \
  --base-url http://127.0.0.1:18081/v1 \
  --model MiniCPM-V-4.7-1B --no-auto-model
```

把示例地址和名称替换为本机服务的实际配置。启动器不会下载模型；自动启动需要已有 `llama-server`、GGUF 和 projector，路径见[自动启动已有权重](local-studio.md#自动启动已有权重)。服务可达但缺少目标模型时，也不能把另一份权重当作该模型使用。

没有模型时仍可编辑、保存、做确定性检查和受支持的规则修复。调整连接设置不必通过重启来生效，但已开始的任务不会因此变成使用新配置的任务。

## 检出了问题，却没有修复或没有模型请求

“检查”只检查当前内容，不生成候选。生成修复候选时，宿主先尝试保留原文的确定性语法修复，再用同一检查器回判；成功的规则候选和简单表格重算可以是零模型请求。

缺少操作数、未知宏、复杂结构或已知解析器边界会保留人工核对。例如 `a_` 缺少下标，不能仅为通过解析而猜成 `a_1`。模型返回的文本也必须通过语法与修改范围检查；改变数字、变量、运算符或删项的候选不能直接采用。具体支持范围见[公式修复质量记录](formula-repair-quality.md)。

任务 `done=true` 仅表示已经结束。存在 `error`、超时、取消或中断时，查看日志与历史，不把它称为成功。空响应、非法 JSON 或被拒候选应保留原因；重试有界，并携带上一候选与拒绝反馈。检查器环境故障需先修复依赖，不继续请求模型来“修复”环境。

## 图片或 PDF 无法识别、识别页数不符

先确认已选择 PNG、JPEG、WebP 或 PDF，文件不超过 12 MiB，且本机模型已准备好视觉推理。超大图片需要缩小或裁剪；修改副本，保留原件。PDF 另需 Poppler 的 `pdfinfo` 和 `pdftoppm`，加密、损坏或无法渲染的 PDF 会明确失败。

界面每次可选择识别前 1、3、5 页，不会一次识别整份长 PDF。需要指定起始页时，授权 API 支持 `page_start`，见 [Studio 操作 Skill 的接口说明](../skills/texada-studio/references/local-api.md)。核对结果里的实际来源页码和未处理页状态，不把部分转写标成全文。

识别完成只产生待审候选；对照原件检查后再以新文件名创建文档。可编译不证明转写忠实，看不清的符号、公式定界符和表格结构仍需人工确认。关闭或取消识别后，已发送的本机请求可能尚未结束；等待当前请求结束再重试，迟到结果不会覆盖新审阅内容。

## 源码正常，PDF 编译或页面预览失败

先区分 PDF 编译失败与页面转换失败。PDF 可以已生成，但缺少 `pdftoppm` 导致页面不可见；这时日志会说明转换问题。可检查已安装的工具：

```bash
"${TECTONIC:-tectonic}" --version
pdfinfo -v
pdftoppm -v
```

正常 Studio 编译使用已缓存资源，不会在处理文档时自动下载缺少的包。先离线检查固定样本；确需首次准备时再显式下载资源：

```bash
.venv/bin/python scripts/prepare-local-tex.py
.venv/bin/python scripts/prepare-local-tex.py --download-resources
.venv/bin/python scripts/prepare-local-tex.py
```

第二条仅在允许联网的准备阶段运行。固定样本的准备不覆盖任意文档的宏包、字体和文档类。新文档与 OCR 候选采用 Fandol 中文字体预设，不要求特定 macOS 中文字体；自己的文档仍应核对所用字体。详细说明见[准备 PDF 编译资源](local-studio.md#准备-pdf-编译资源)。

当前支持多页预览和翻页。编辑、切换文件或拒绝候选会清除旧 PDF 的版本绑定；重新编译当前版本后再导出。单次编译的 PDF 与页面地址保持绑定，不以旧页面作为新版本的交付依据。

工作单位仍是单个 `.tex`。依赖外部图片、宏文件或参考文献的工程不能直接当作已支持的整项目上传。

## 保存冲突、刷新后缺内容或候选不能采用

“采用候选”只更新编辑器；“保存”或 `⌘/Ctrl+S` 才写入本地文档。直接导出的 `.tex` 是下载副本，不等于工作区已经保存。刷新或切换前先保留未保存内容。

保存提示版本冲突时，保留当前缓冲区，可先导出源码副本，再比较另一窗口保存的版本或另建文档。不要通过替换版本哈希强行覆盖。示例首次保存会建立本地副本，不修改仓库原件；单个 `.tex` 上限为 2 MiB。

候选绑定生成时的原文、编辑器版本与来源哈希。编辑后撤销也可能让旧候选失效；历史候选只有在当前来源仍匹配时才能恢复审阅。不要把过期候选强行采用到新版本。原文视图与候选 diff 的导出对象也不同，导出前核对当前视图与文件名。

## 重启后找不到文档或任务记录

完成的任务可从工作区设置的“运行记录”或 Agent 中的“最近运行”打开。任务失败或中断时保留日志；未完成任务不因重启而变成成功。

文档和记录保存在启动时选择的用户数据目录，不一定在仓库 `state/`：

| 系统 | 默认数据目录 |
| --- | --- |
| macOS | `~/Library/Application Support/TeXada Studio` |
| Windows | `%LOCALAPPDATA%/TeXada Studio` |
| Linux | `$XDG_DATA_HOME/texada-studio`，未设置时为 `~/.local/share/texada-studio` |

`--state-dir` 或 `TEXADA_STUDIO_STATE_DIR` 可以改变位置。先核对是否启动了另一数据目录，不移动或重置原目录来排错。

其中 `documents/` 保存文档，`documents/.history/` 与 `.trash/` 保存历史或删除副本；界面尚无恢复删除按钮。`jobs/<id>/` 保存修复与审阅事件，`imports/<id>/` 保存 OCR 原件及候选，`local-runtime.json` 保存本机连接设置。恢复副本时先另存比较，不直接覆盖运行中的记录。

备份前保存并停止服务，备份实际用户数据目录。保留私人原件和会话文件的访问限制；不要把整个目录上传到公开 Issue。详见[本地数据与恢复](local-studio.md#本地数据与恢复)。

## Skill 或 CLI 结果与预期不同

外部 Agent 的 Studio 操作入口、运行时加载范围和 Skill 安装方式见[AgentSkills 使用指南](agent-skills.md)。仓库有 `SKILL.md` 不等于它已自动安装到 Agent，或每个步骤都会向模型加载它。

固定公式宿主在 `skill_mode=on` 时加载公式 Skill；自动选择 Skill 是另一项默认关闭的实验。核对实际 `skill_loaded`、`skill_sha256` 和请求记录，不用零请求的确定性路径证明模型读过 Skill。路径或正文校验失败时，先检查源码包完整性。

CLI 读取已有 `layout.json`，不能直接接收 PDF，也不会自动把 Studio 转写候选转换为节点。模型提供方的表格修复尚未实现；fixture 中的预设替换网格不代表真实图像重提取。输入与报告说明见 [Harness 手册](../harness/README.md)。

CLI 续跑核对本轮 `run_id`、`SKIP`、输入与执行上下文哈希；独立实验使用新的 `--state` 目录。相同标签下更换权重或服务实现时，也应记录实际模型身份并使用新目录。暂时性服务或检查器故障恢复后可重跑，旧人工项不等于新成功。

仍有问题时，按 [SUPPORT.md](../SUPPORT.md) 提供提交号、Studio/CLI 入口、环境、实际操作和最小合成样本。只分享去除凭据和私人内容的错误片段。旧云 API 入口单独见[兼容说明](local-studio.md#旧云-api-入口与实验功能)，不能把它当作当前本地版的默认配置。
