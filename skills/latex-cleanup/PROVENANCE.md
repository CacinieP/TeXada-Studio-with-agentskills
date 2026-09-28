# PROVENANCE · latex-cleanup

## 本仓库的分发许可

这份同一维护者 CacinieP 导入的副本按仓库根目录 `LICENSE` 中的 AGPL-3.0-only 分发。
这里只声明本仓库副本的许可，不修改独立来源仓库的授权状态。下述提取范围保持不变。

- 来源仓库：`CacinieP/latex-cleanup`（GitHub，私有）
- 提取版本：v0.2.3 · commit `bdca55a`（后续 0.2.4 的 OCR 损伤修复规则见源仓 references/ocr-pitfalls.md，按需重新提取）
- 提取日期：2026-09-28 · 方式：`git archive HEAD` 按路径提取 · 源仓 main 已合入 0.2.3（merge b4759b6）并发布 0.2.4（commit 0e9d0f1）

## 包含

`SKILL.md`（原样）· `CHANGELOG.md` · `references/`（tex/markdown/ocr/tools/verification/corpus）·
`scripts/`（audit_math.cjs、apply_verified_edits.py、compile_tex.py、format_whitespace.py、run_ocr_corpus.py）·
`tests/`（fixtures 与行为用例）

## 排除（含个人语料，不入参赛仓）

`evaluation/`（2026-09-22 评测产物与个人语料 diff）、`examples/gtm-corpus/`（GTM 书目语料）、
`agents/openai.yaml`、`.gitignore`

## 在 TeXada Studio with Agent Skills 中的定位

这份快照提供可独立运行的数学审计、实际编译与保守清理工具。当前 Studio 直接调用 Tectonic，不调用本 Skill 的完整工具链；当前 CLI Harness 调用公式和表格检查脚本，不调用本快照的 Node 审计或编译回环。把它接入这些路径属于后续工作，不能将工具存在视为已经接入。

本仓库维护了本地测试和文档调整；重新从来源仓提取时先核对差异，保留适用的修复与来源说明，不覆盖已经验证的行为。此次开源准备修正了样本/命令路径及历史语料链接，并处理编译超时测试对 Python 启动时序的依赖。运行时编译器实现未因此改动。
