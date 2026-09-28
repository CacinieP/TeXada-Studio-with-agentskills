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

## 在 TeXada Agent Skills 中的定位

内部依赖（同 `spark-ops`，不单独参赛）：为 `doc-formula-verify` 的修复结果提供**编译回环**验收——
`audit_math.cjs` 数学审计（node）+ `compile_tex.py` 实际编译（Tectonic，P1/P2，目标环境按需）+
`format_whitespace.py` 保守空白清洗。上游宿主（TeXada Agent Skills harness）在修复后调用其检查模式，
不修改本 Skill 的契约。上游更新时从来源仓重新提取并更新本文件。
