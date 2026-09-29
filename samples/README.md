# 样本入口

按使用方式选择输入。项目原创文档和合成数据采用 [AGPL-3.0-only](../LICENSE)；开放教材样本单独保留 [CC-BY-SA-4.0](research/ACTIVE_CALCULUS_NOTICE.md)。

| 输入 | 用途 | 运行方式 |
| --- | --- | --- |
| [`docs/*.tex`](docs/)：13份文档 | Studio 编辑、分析、候选审阅 | [启动 Studio](../README.md#2-打开-studio) |
| `paper-01/`、`exam-01/`、`report-01/` 的 `layout.json` | CLI 检查与续跑 | 下方 fixture 命令 |
| [`evaluation/cases.json`](evaluation/cases.json)：27例 | 检查器契约回归 | [检查案例](evaluation/README.md) |
| [`research/`](research/README.md) | 同模型有 / 无 Skill 对照 | [研究协议](research/README.md) |

Studio 的 `.tex` 和 CLI 的 layout 是各自独立的输入；CLI 只扫描含 `layout.json` 的目录。自己的上传文档保存在 `state/studio/documents/`，不加入样本库。

## Studio 数学样本

推荐顺序：`math-clean.tex` → `math-delimiters.tex` → `math-semantics.tex`。先看正常排版，再审阅定界符修复，最后看语法与数学真值的区别。

| ID | 文档 | 提取公式 / 语法问题 | 主要用途 |
| --- | --- | --- | --- |
| S06 | [math-delimiters.tex](docs/math-delimiters.tex) | 2 / 1 | 分式外层缺少 `\right)` |
| S07 | [math-fractions.tex](docs/math-fractions.tex) | 2 / 1 | 分母花括号缺失 |
| S08 | [math-indices.tex](docs/math-indices.tex) | 2 / 1 | 下标分组缺失闭合花括号 |
| S09 | [math-integrals.tex](docs/math-integrals.tex) | 2 / 1 | 积分上限分组缺失闭合花括号 |
| S10 | [math-clean.tex](docs/math-clean.tex) | 4 / 0 | 分式、积分、极限和递推正常对照 |
| S11 | [math-semantics.tex](docs/math-semantics.tex) | 3 / 0 | 积分值故意写错，语法仍合法 |
| S12 | [math-align-boundary.tex](docs/math-align-boundary.tex) | 0 / 0 | 损坏的多行 `align*`，展示提取范围 |
| S13 | [math-references.tex](docs/math-references.tex) | 0 / 0 | `equation`、交叉引用和文献引用边界 |

这8份英文数学讲义为原创合成材料，无需中文字体。另5份原有文档及逐例操作见[案例手册](../docs/casebook.md)。

当前分析器按行提取 `$...$`。因此 S12、S13 的零问题表示未提取到公式；S11 的零问题表示语法接受，数学结论需另外核对。

[studio-cases.json](studio-cases.json) 记录预期检查结果、原文保持要求和4个作者参考修复。参考修复用于离线回归；真实模型候选另行记录。

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_samples.py' -v
```

此命令验证提取与修复契约。8份原稿和4份参考修订的独立编译入口见 [12次编译核验](../docs/evaluation-results/studio-latex/README.md)。

## CLI 样本

| 样本 | 节点 | 注入问题 |
| --- | --- | --- |
| `paper-01/` | 3个公式 | `a_` 下标缺失，fixture给出 `a_1`；另一式花括号失衡，留待人工 |
| `exam-01/` | 1个公式、2个表格 | 定界符缺失；表内合计4.5与数据和4.0不符 |
| `report-01/` | 2个表格 | 行数3与预期4不符；另有干净对照 |

在仓库根目录安装依赖并运行：

```bash
python -m pip install -r harness/requirements.txt
PYTHONPATH=harness python -m docforensics run samples \
  --state state/fixture-check --fixture-repairs samples/fixture_repairs.json
```

预期：`exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。结果在 `state/fixture-check/report.md`。重复同一命令会复用8个输入与上下文一致的终态节点。

layout、占位 crop 和修复表用于检查处理流程。真实模型配置与复用条件见 [Harness 手册](../harness/README.md)，模型效果评估见[研究协议](research/README.md)。
