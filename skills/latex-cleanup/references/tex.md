# TeX 专属规则

## 主文件、引擎和依赖

先读取编辑器的 root / program magic comment、`.latexmkrc`、构建脚本、
`.vscode/settings.json`、`Tectonic.toml` 和用户说明。按项目实际配置选主文件与引擎；
包名只作辅助证据，不能单凭 `\usepackage` 决定引擎。

追踪 `\input` / `\include` 及相关 `.bib`、资源路径。静态扫描不一定理解动态宏、条件分支、
自定义引用命令和生成文件；不要把单文件未找到的标签或注释中的引用当成未定义引用。
片段应由所属主文件验证；无主文件时说明只能静态检查，不擅自添加文档骨架。

## 格式与内容

- 遵循已有缩进和换行习惯；不要机械地在 equation / figure / table 后增加空行，
  或把一个段落拆成多个段落。
- 保留 `%` 及其抑制行尾空白的作用，保护 `\verb`、verbatim、lstlisting、minted、
  文件生成环境及项目自定义的原样输出区域。不了解的宏或 catcode 操作保守处理。
- `latexindent` 仅在已有配置或确认适用的范围内使用。不要默认启用重排段落、替换文本或
  修改换行的选项；在副本上检查结果后再应用。
- 不把 `R`、`\mathbb{R}` 或 `\epsilon`、`\varepsilon` 自动合并。先根据定义确认概念；
  即使写法疑似不一致，缺少依据时也只报告。保留上下标、正负号、单位和数字。
- 不将所有算子改成 `\mathrm`，或把所有字母视作向量。符号样式由含义和模板共同决定。

## 引用和文献

`\citet` 和 `\citep` 可以合法共存，分别适用于叙述式和括号式引用。先识别 natbib、biblatex
或模板提供的引用接口，再检查是否与句子用途相符。不要为“统一”而改写有效命令。

BibTeX / BibLaTeX 的字段要求取决于条目类型和选用样式。book、misc、online 等不能统一要求
booktitle / journal。保留有意义的大括号、大小写保护、LaTeX 转义和作者字段。缺元数据时
报告具体条目，不编造。去重前确认是同一文献并同步所有引用；不默认重命名已有 key。

## 图表和溢出

- 缺少 label 或正文引用通常是建议，未必是错误；仅在文档结构确实需要时添加。
  figure / table 的 label 通常跟在对应 caption 后。
- 根据实际容器选择 `\linewidth`、`\columnwidth` 或 `\textwidth`，检查 minipage、
  列表、双栏、subfigure 等上下文，不统一替换所有宽度。
- 根据日志定位 overfull 来源，先检查盒子、边距、空白、不可断行内容和列定义。
  必要时调整实际尺寸或排版。测试报告里的 `0.98\columnwidth` 只是特定样例修复，
  不能作为新的通用比例。
- 不因 `[h]` 出现就替换浮动参数，不把 `\resizebox` 作为所有表格的第一选择。
  优先改善断行、列宽和结构；缩字号、缩放、跨栏应结合可读性和模板要求。

## 编译验收

优先复用已有构建命令。latexmk 可以管理重复编译及参考文献处理；Tectonic 项目继续使用
Tectonic，不强制替换工具。自定义 Biber、索引或生成资源步骤沿用项目配置。

在独立的新构建目录保留真实退出码、控制台和最终 `.log`；不能用 grep 的退出码判断编译。
检查 PDF 是否实际生成，以及未定义引用、文献、重跑提示和 overfull。编译成功仍可能有警告；
只修复本次引入或本次要求处理的问题，不无休止追逐无关警告。

缺包、离线缓存不全、字体不可用和排版错误要分别说明。不要因缓存不全就反复无界重试，
也不要自行启用 shell escape。需要联网补资源时遵循用户和宿主的现有授权。

## 字体、宏包与引擎陷阱（源自实际修复）

- fontspec 按名字找**操作系统字体**；`The font "X" cannot be found` 表示系统缺该字体，
  不是 TeX 包缺失。macOS 上 TeX Gyre 系列可用 `brew install --cask font-tex-gyre-pagella`
  等装入用户字体目录；改用同源系统字体（Pagella ≈ Palatino）需用户同意。
- 西文文档里的少量 CJK 字符（占位注释、〔〕等括号）会静默缺字，日志表现为
  `Missing character: There is no ...`。修复用 `\usepackage{xeCJK}` +
  `\setCJKmainfont{PingFang SC}`，不要删除或替换这些字符。
- tcolorbox 没有 `dashed` 键（报 `I do not know the key '/tcb/dashed'`）。
  虚线框写法是 `enhanced` + `frame style={dashed}`（skins 库，`[most]` 已含）。
- 编译后出现 `accessing absolute path ... build may not be reproducible`
  只是系统字体的无害提示，不算失败。
- `% !TEX program = xelatex` 等 magic comment 会覆盖编辑器构建配方；系统无对应二进制时
  报 `spawn xelatex ENOENT`。Tectonic 项目把 magic comment 改成实际引擎（如 tectonic），
  或让编辑器强制使用配方（LaTeX Workshop `latex-workshop.latex.build.forceRecipeUsage`）。
- 无衬线数学：`\usepackage{unicode-math}` + `\setmathfont{Fira Math}`；Fira Math 无
  Homebrew cask，从 CTAN 镜像 `fonts/firamath` 取 OTF 装入用户字体目录。
- tikz 画「标题旁水平细线」时，两端若一个用节点相对坐标（`n.east`）一个用图纸坐标
  （`\linewidth, -3pt`），y 不在同一水平线上，线会肉眼可见地发斜。用投影写法保证同一 y：
  `\draw (a) -- (a -| b);`（`a -| b` 取 b 的 x 与 a 的 y）。线宽按半宽收回，避免
  `\linewidth` 端点溢出 0.3pt overfull。
- Tectonic 长时间无输出挂在「Running TeX ...」之前，多是联网校验宏包索引而非语法错误。
  先试 `--only-cached`，或临时让 HTTP(S) 代理指向死端口令其快速失败；成功编译后再把
  离线策略写进项目 README。

模板转换仅在明确要求时执行：先取得真实目标模板，保留正文及依赖映射，逐项适配接口并编译。
不能通过盲目替换 documentclass 或删除不认识的命令声称完成转换。
