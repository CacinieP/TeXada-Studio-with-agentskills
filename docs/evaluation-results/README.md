# 验证结果存档

| 记录 | 内容 | 复现入口 |
| --- | --- | --- |
| [检查器报告](checker-report.md) · [JSON](checker-report.json) | 2026-09-28：27例合成输入，24个契约例和3个语义边界例均符合预期 | [检查器案例](../../samples/evaluation/README.md) |
| [Skills 先导实验](skills-pilot/report.md) | 开放教材公式的检查器、Skill off / on 对照 | [研究协议](../../samples/research/README.md) |
| [Studio 编译](studio-latex/README.md) | 8份原稿与4份作者参考修订，共12次编译 | [样本目录](../../samples/README.md) |
| [早前录屏任务](studio-earlier/README.md) | 报表与试卷的历史候选和失败记录 | [当前演示](../dynamic-demo.md) |

存档保留原始结果。复跑使用新的输出目录，并核对报告中的输入、代码及依赖摘要。检查器报告只测规则行为；模型对照另列于先导实验。

- [MiniCPM-V 4.7 local comparison: 35B Q4 / 1B Q4 / 1B F16](v47-local-comparison-01/README.md) — actual local inference, syntax candidates and OCR observations; semantic accuracy unmeasured.

- [2026-11-08 current-mainline integration acceptance](v47-mainline-integration-01/README.md): 473 Python tests, four JS suites, native local OCR/review boundary and fresh 35B provider measurements.

- [2026-11-10 table repair contract pilot](table-repair-pilot-01/README.md): issue #25 `repair_table` + host scope guard on synthetic grids; MiniCPM-V 4.7 accepts authorized totals, MiniCPM5-1B truncates.

- [2026-11-11 MiniCPM5-2B formula Skill and routing probe](minicpm5-routing-01/README.md): issue #23; three real Skill-loaded provider requests, separate zero-model host replay, and CLI routing audit. Independent human review remains pending; defaults unchanged.

- [2026-11-11 reviewed OCR layout conversion](ocr-layout-01/README.md): issue #24; explicit hash-bound review decisions, formula/table/text nodes, unresolved-span blocking and real CLI resume. Offline synthetic conversion and archived real-OCR parsing boundary; no new OCR-quality claim.

- [2026-11-11 operator-provided OCR source regions](ocr-source-regions-01/README.md): issue #24; PNG identity and explicit pixel boxes, with source-byte checks before harness resume. Synthetic geometry evidence; no automatic detection or human image-validation claim.

- [2026-11-11 portable OCR source-region reports](ocr-region-report-01/README.md): source snapshots, boxed/zoom vector views, original OCR text, and input-bound events retained on resume. Offline report rebuild and local Chromium rendering verified on the synthetic fixture.

- [2026-11-11 objective OCR review signals](ocr-review-signals-01/README.md): dedicated CLI termination, sentinel and character diagnostics propagate to a blocked review bundle. Ten offline protocol fixtures; no model inference or confidence/accuracy claim.

- [2026-11-11 beta.4 real end-to-end acceptance](beta4-acceptance-01/README.md): original mixed page, real dedicated OCR and separate V4.7 Studio import, explicit review/corrections, source-bound CLI resume, arithmetic accept/reject and PDF/TeX exports. Failures retained; single-page agent smoke, not independent human quality validation.
