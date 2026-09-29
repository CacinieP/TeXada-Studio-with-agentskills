# 新增 LaTeX 样本的编译记录

`compilation.json` 保存8份原创输入与4份作者参考修订的独立 Tectonic 结果，带每份实际编译源码的 SHA256。清单来自 [Studio 数学样本目录](../../../samples/studio-cases.json)。作者参考修订由清单明确给出，不是模型响应，也没有进入真实模型请求。

12项预期全部匹配：7份生成PDF，5份按预期编译失败。其中4个语法缺陷及1个未被行内抽取器覆盖的 `align*` 缺陷编译失败；正常讲义、错误积分等式和未解析引用文档均能生成PDF。引用样本的完整TeX日志确认存在未定义引用或引文警告，退出码0并不说明引用有效。数学等式能编译也不代表它成立。

复现单个原始样本（需要已安装 Tectonic；初次运行可能下载TeX资源）：

```bash
mkdir -p state/studio-tex/math-clean
tectonic --keep-logs --outdir state/studio-tex/math-clean samples/docs/math-clean.tex
```

替换文件名即可核对其他原始输入。四个作者参考版需在临时副本中按清单的 `reference_edits` 替换对应公式；不要覆盖故意损坏的原样本。测试命令见 [案例手册](../../casebook.md)，它使用真实语法检查器但不调用模型或编译器。

真实模型的主视频结果单列于 [演示证据](../../demo-evidence.json) 与 [逐候选轨迹](../../demo-trace.json)，不得把这里的4个作者参考版称为模型修复成功数。原有8个CLI fixture节点和12条开放来源先导实验未因新增Studio文件改变。
