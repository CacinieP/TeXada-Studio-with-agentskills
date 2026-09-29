# 检查器案例

27个合成输入直接调用公式和表格检查器：10个公式、17个表格。用于复现输入契约、数字处理和已知边界，运行时无需模型或网络。

## 运行

在仓库根目录、已激活的 Python 环境中执行：

```bash
python -m pip install -r harness/requirements.txt
python scripts/evaluate_cases.py --outdir state/evaluation-01
```

输出目录须不存在；再次运行换用 `state/evaluation-02` 等新目录。

| 产物 | 内容 |
| --- | --- |
| `report.json` | 逐例输入、预期、响应、进程状态、原因与耗时，以及案例/脚本摘要和环境版本 |
| `report.md` | 分组计数和逐例结果 |

默认每例超时15秒，`--timeout` 可设为大于0且不超过120的秒数。案例文件由 `--cases` 指定，默认 [`cases.json`](cases.json)。

| 退出码 | 意义 |
| --- | --- |
| `0` | 全部案例符合声明的预期 |
| `1` | 有案例不匹配，或发生超时、环境、进程、协议错误 |
| `2` | 参数、案例文件或输出目录无效 |

## 覆盖内容

| ID | 内容 |
| --- | --- |
| F01–F03 | 多项式、分数、上下标和配对定界符 |
| F04–F07 | 尾部运算符、缺下标、不完整分数、空白公式 |
| F08 | `1+1=3`：语法可解析，算术不成立 |
| F09–F10 | 损坏JSON、非字符串公式 |
| T01–T02 | Decimal合计通过与不符 |
| T03–T04、T11–T12 | 行列形状、短合计行和空末行 |
| T05–T09 | 千位分隔符、非数字、行列基准和正负号 |
| T10、T13 | 非法基准列索引 |
| T14–T15 | 百分比混合、会计括号负数的拒绝处理 |
| T16–T17 | 超过默认Decimal精度的大整数合计 |

精确状态和原因以 [`cases.json`](cases.json) 的 `expected` 为准。24例归入 `contract`，F08/T14/T15归入 `semantic-boundary`；`known-gap` 用于记录后续发现的未满足要求。

报告中的匹配数衡量检查器与输入契约的一致性。语义边界案例解释 `OK` 的含义和格式支持范围；模型效果、TeX编译和数学判真分别使用对应评估。每例耗时包含启动Python子进程。

## 维护

保留稳定 `id`、`checker`、`category`、`evaluation_group`、`input`、`expected` 和 `why`，必要时补充 `limitation`。固定原因用 `expected.reason`，解析器自然语言报错不作逐字匹配。变更预期时说明契约为何改变。

```bash
python -m unittest discover -s scripts -p 'test_evaluate_cases.py' -v
```

回归覆盖输出协议、退出码、超时、分组和目录保护。实际案例结果由上面的评估命令另行生成。
