# 工具与 VS Code

技能主体由 agent 执行，下面的脚本只辅助保守空白清理和编译记录。所有命令中的路径应替换成
本次任务的真实路径，脚本路径相对于技能目录。Python 要求 3.9+。

## 空白清理

```sh
python3 scripts/format_whitespace.py /path/to/main.tex /path/to/notes.md --diff
python3 scripts/format_whitespace.py /path/to/main.tex --write --backup-dir /path/to/work/backup-01
```

默认仅检查和输出 JSON，`--diff` 把差异输出到 stderr。`--write` 才修改文件；备份目录必须
是新目录。它先备份全部待改文件并写出带 SHA-256 的 manifest，再逐项写入。保留 UTF-8 BOM、
原有换行和文件权限；拒绝直接指定符号链接和写入硬链接文件。不递归扫描目录，不创建 Git 提交。
批量过程中若某个文件变化或写入失败，已写入文件会在 JSON 中标记，备份仍可用于恢复。
备份 manifest 是写入前记录，`written` 状态以命令最终 JSON 为准。

- TeX：只移除普通源码行末水平空白，保留注释、控制空格和已知原样环境；
  `--verbatim-env CustomCode` 可增加原样环境。发现自定义语法定义时跳过整个文件。
  项目在 `.sty` 中定义的特殊环境仍需要 agent 识别并传入，不是完整 TeX 解析器。
- Markdown：使用 `markdown-it-py` 的源码位置，只处理顶层普通段落末尾的单个 ASCII 空格。
  保护代码、front matter、公式区域、嵌套结构及硬换行，并比较 CommonMark HTML。
  无法确认的内容保留。这个对比不代表 VS Code 的所有扩展都已验收。
  已识别的 `$...$`、`$$...$$`、`\[...\]` 和 `\(...\)` 内的 `\begin{...}` 不会触发
  整文件跳过；代码示例同样保留，普通正文继续检查。单美元公式仅识别同一行内的保守边界，
  不把货币数字当成闭合定界符。公式未闭合时保留余下内容；公式与行内代码混排等边界不明确
  的情况可能扩大保护范围。公式和代码以外的原始 TeX 环境、未支持的 `:::` 容器仍会导致
  整文件保留并报告原因，需要 agent 按项目渲染器局部处理。
- Markdown 的可选依赖为 `markdown-it-py`（本次验证版本见测试报告）；缺少时会明确报错，
  不执行任何文件修改，也不自动安装。用户已授权配置环境时，可在虚拟环境执行
  `python3 -m pip install markdown-it-py`；否则 agent 可做有依据的局部修改。
- 退出码 0 表示检查/操作完成，不代表没有格式建议；2 表示输入、依赖或写入错误。

## 编译记录

先确定主文件和已有编译配置，再调用；项目有专用构建脚本时直接运行它并记录退出码。

```sh
python3 scripts/compile_tex.py /path/to/main.tex --engine tectonic --offline --outdir /path/to/work/build-before
python3 scripts/compile_tex.py /path/to/main.tex --engine tectonic --offline --outdir /path/to/work/build-after
```

`--engine pdflatex|xelatex|lualatex` 使用已安装的 latexmk 管理编译；不会自动回退或安装编译器。
`--offline` 只支持 Tectonic。默认超时 60 秒，可显式调整；缓存不完整会如实失败。
Tectonic 项目的 workspace 构建和复杂 recipe 应使用项目已有命令。

输出目录必须不存在，避免把旧 PDF 当成成功结果。结果同时打印为 JSON 并保存到新目录的
`build-result.json`，含真实子进程退出码、命令、PDF 路径及日志诊断；控制台保存为 `console.log`。
它检查最终日志的 overfull、未定义引用/文献和部分重跑提示，完整日志仍需查看。
成功含警告时 `status` 仍为 `success`，警告不会消失。PDF 文件头检查只排除缺失/明显无效输出，
不是视觉验收或完整 PDF 校验。

退出码：成功 0；编译失败保留可用的编译器非零退出码；未执行 2；超时 124。

## 有依据的精确补丁

对照原稿完成判断后，可用 `apply_verified_edits.py` 执行可复核的替换：

```sh
python3 scripts/apply_verified_edits.py /path/to/edits.json --diff
python3 scripts/apply_verified_edits.py /path/to/edits.json --write --backup-dir /path/to/new-backup
```

计划字段为 `schema_version: 1`、`source`、`source_sha256` 和 `edits` 数组；每项包含
唯一 `id`、非空 `old`、`new`（允许为空，以删除）及 `evidence`。
证据包含非空 `kind`、`reference`、`locator`、`note`，如原 PDF、物理页码和核对说明。
相对源文件及本地证据路径相对于计划文件解析。脚本不打开或验证证据内容，也不替 agent 作判断。

所有替换在同一原始版本上匹配：要求源 SHA-256 一致、旧片段恰好出现一次、补丁不重叠。
出现多次时扩大上下文或合并相邻补丁，不能随意选第一次。未满足条件时整批拒绝。
不自动转义反斜杠或规范化换行；JSON 字符串须表达准确的原文。

默认只预览；`--write` 使用全新备份目录，先保存 `original.bin`、`plan.json`、`record.json`，
再替换源文件。保留未改动字节及文件权限，拒绝直接符号链接及写入硬链接。备份记录表示
写入前的 prepared 状态，最终是否 written 以 stdout JSON 和磁盘哈希为准。空编辑数组或
完全相同的新旧片段不产生备份。退出码 0 为执行成功（不表示语义正确），2 为验证或写入错误。

OCR 实验使用副本作为 `source`；工具也适用于用户已授权的源文件编辑。完成后再次检查
全部 diff，并分别记录语法、内容和视觉验证。

## VS Code 使用

在支持 skill 的 AI 扩展中调用 `latex-cleanup`。Codex IDE 扩展的示例请求：

> 使用 $latex-cleanup 清洗 main.tex 和 notes.md，保留内容含义，完成后验证并汇总差异。

也可明确要求“只检查”或“修复编译错误”。LaTeX Workshop 继续负责 PDF 预览，Markdown
继续使用项目现有预览。保存时的格式化器可能和清洗规则冲突，应先检查项目配置，不更改全局设置。

项目内使用 Codex 时，可把整个技能目录放在项目的 `.agents/skills/latex-cleanup/`，
让该目录下直接包含 `SKILL.md`。只有复制 `SKILL.md` 会丢失本版的规则和脚本。
其他 agent 按其技能发现机制安装整个目录。

参考：[官方 skill 文档](https://learn.chatgpt.com/docs/build-skills)、
[markdown-it-py](https://markdown-it-py.readthedocs.io/en/latest/using.html)、
[latexmk](https://ctan.org/pkg/latexmk)。
