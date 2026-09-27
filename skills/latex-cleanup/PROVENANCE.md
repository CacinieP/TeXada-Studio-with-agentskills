# PROVENANCE · latex-cleanup

- 来源仓库：`CacinieP/latex-cleanup`（GitHub，私有）
- 提取版本：v0.2.3 · commit `bdca55ad0dde02885790761d49d69e242b6a04dd`（分支 `docs/layout-recapture-checklist`，领先 main 2 个 docs 提交）
- 提取日期：2026-09-28 · 方式：`git archive HEAD` 按路径提取

## 包含

`SKILL.md`（原样）· `CHANGELOG.md` · `references/`（tex/markdown/ocr/tools/verification/corpus）·
`scripts/`（audit_math.cjs、apply_verified_edits.py、compile_tex.py、format_whitespace.py、run_ocr_corpus.py）·
`tests/`（fixtures 与行为用例）

## 排除（含个人语料，不入参赛仓）

`evaluation/`（2026-09-22 评测产物与个人语料 diff）、`examples/gtm-corpus/`（GTM 书目语料）、
`agents/openai.yaml`、`.gitignore`

## 在 TeXada-WebUI 中的定位

内部依赖（同 `spark-ops`，不单独参赛）：为 `doc-formula-verify` 的修复结果提供**编译回环**验收——
`audit_math.cjs` 数学审计（node）+ `compile_tex.py` 实际编译（Tectonic，P1/P2，目标环境按需）+
`format_whitespace.py` 保守空白清洗。上游宿主（TeXada-WebUI harness）在修复后调用其检查模式，
不修改本 Skill 的契约。上游更新时从来源仓重新提取并更新本文件。
