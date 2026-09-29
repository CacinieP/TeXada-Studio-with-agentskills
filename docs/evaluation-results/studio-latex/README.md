# Studio 样本编译

[compilation.json](compilation.json) 记录 Tectonic 0.16.9 对8份原稿、4份作者参考修订的编译结果。12项均符合预期：7份生成PDF，5份编译失败。各项输入 SHA256 保存在报告中。

| 输入 | 预期 |
| --- | --- |
| S06–S09 的原稿 | 编译失败：缺失定界符或分组括号 |
| S06–S09 的作者参考修订 | 编译成功 |
| S10 正常讲义、S11 错误积分等式 | 编译成功；S11用于区分排版与数学含义 |
| S12 `align*` 缺陷 | 编译失败 |
| S13 未定义引用 | 生成PDF，日志包含引用或引文警告 |

## 复现全部12项

在仓库根目录执行，需要 Python 3.11+ 和 PATH 中的 Tectonic。也可通过 `TECTONIC` 指定编译器路径；首次编译可能下载TeX资源。

```bash
"${TECTONIC:-tectonic}" --version
python scripts/compile_studio_cases.py --outdir state/studio-compile-01
```

预期末行：`12/12 expectations matched`。每项的源码副本、编译输出、TeX日志和生成的PDF位于独立子目录；汇总在 `state/studio-compile-01/report.json`。重跑时换一个输出目录。

脚本读取 [样本清单](../../../samples/studio-cases.json) 中的 `reference_edits` 生成4份参考副本，核对输入摘要、退出码与PDF产物；负例还须出现对应语法诊断，S13须保留未定义引用警告。原始样本保持完整。参考修订是作者给定输入，模型修复结果见[动态演示证据](../../dynamic-demo-evidence.json)。

只检查一份原稿时：

```bash
mkdir -p state/studio-single
"${TECTONIC:-tectonic}" --keep-logs --outdir state/studio-single samples/docs/math-clean.tex
```
