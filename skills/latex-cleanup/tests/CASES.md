# 回归样例

`fixtures/` 的 TeX 原始内容和 PNG 来自用户 2026-09-09 提供的 latex-cleanup 测试报告对应样例。
`semantics` 增加两处普通源码行尾空格，确保清洗实际发生；保留引用、数学符号和 TODO。
`multifile` 保留原始子文件、跨文件引用、book / misc 文献条目及注释内引用。
`basic-error` 保留原始错误；`basic-repaired` 是本次按上下文修复环境、图引用及图片容器宽度的结果，
不是空白脚本自动修复的结果。此 PNG 在本次 Tectonic 下按完整容器宽度仍溢出 1.29237 pt，
因此仅在该样例使用 `0.98\linewidth`；这不是技能的通用规则。

```sh
python3 -m unittest discover -s tests -v
python3 tests/run_integration.py --outdir /path/to/work/integration-01 --offline
```

单元测试验证文件保护和脚本操作结果，编译进程管理部分使用测试用子进程，不依赖完整 TeX 环境。
Markdown 用例要求 `markdown-it-py`；没有依赖会明确显示 skipped，不算已验收。
数学环境回归涵盖行内/展示 `array`、嵌套环境、公式前后的正文清理、代码中的 TeX 示例、
未闭合公式、货币与转义定界符，以及公式旁边的原始 TeX 块保护。GTM 实际样段仅在本地
做副本回归，不随源码发布；单元测试使用自构造文本复现其结构。

集成测试需要已有 Tectonic，复用上述真实案例在输出目录生成清洗前后源码、编译结果和备份。
可选的 pdftotext 检查会记录执行或未执行状态。语义及多文件案例必须成功编译且没有未定义引用，
基础错误和只改图片扩展名的探针必须失败。所有子进程有超时，不安装依赖。

以上验证的是脚本和已实现的修复样例。独立 agent 的端到端执行另见
[行为测试](behavioral/CASES.md)；单次案例通过不能推断跨模型触发率。

`test_verified_edits.py` 检验精确补丁：默认不写、源哈希过期、重复或重叠匹配、证据字段、
备份、并发变更、BOM/CRLF、文件权限和删除。它不验证证据的内容或 OCR 数学正确性。

`test_ocr_corpus.py` 检验批量副本、状态保留、原件变化检测、片段覆盖和文本补丁回放；
`node tests/test_audit_math.cjs` 检验公式探针的代码保护、偏移、哈希和输出目录保护。
完整 50 本的实际运行和可重放例子见 [GTM 语料](../examples/gtm-corpus/README.md)。
