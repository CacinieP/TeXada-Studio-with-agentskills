# 检查器案例结果存档

本目录是2026-09-28的27例合成输入实跑：24个契约例、3个语义边界例均符合各自预期。它没有调用模型或OCR，不能作为模型准确率。

- [checker-report.json](checker-report.json)：保留运行器生成的原始输入、预期、响应、退出码、耗时、依赖版本与源码摘要。
- [checker-report.md](checker-report.md)：同次运行的可读报告。
- [案例定义](../../samples/evaluation/cases.json)及[运行方法](../../samples/evaluation/README.md)：重新运行应写入新的状态目录。

两份结果原始名称为 `report.json` / `report.md`，存档仅改文件名，没有改结果。JSON 中 `catalog_sha256` 与 `checker_sha256` 已同此版本代码核对；修改检查器或案例后必须重新运行，不能继续引用旧结果作为新代码证据。完整方法与局限见 [Skills 技术报告](../skills-technical-report.md)。
