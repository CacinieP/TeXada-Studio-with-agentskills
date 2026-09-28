# 可执行的合成检查案例

这个案例集包含 **27 个合成输入**：10 个公式、17 个表格。它直接运行仓库内的两个确定性检查脚本，验证输入契约、拒绝行为及能力边界，不使用 fixture 修复、不调用模型、OCR 或网络，也不读取真实用户文档。

## 运行与查看结果

在仓库根目录使用已激活的 Python 虚拟环境：

```bash
python -m pip install -r harness/requirements.txt
python scripts/evaluate_cases.py --outdir state/evaluation-01
```

依赖安装可能需要网络；运行器本身没有网络请求。它用当前 `sys.executable` 启动检查器，通过独立 argv 参数或 JSONL 标准输入传递案例，不把文档文本拼成 shell 命令。默认每例超时 15 秒，可通过 `--timeout` 指定大于 0、不超过 120 秒的值。

生成文件：

- `state/evaluation-01/report.json`：每例输入、预期、实际响应、进程状态、原因和耗时，以及脚本 / 案例摘要、Python 与依赖版本。
- `state/evaluation-01/report.md`：分组计数、逐例状态及限制说明。

输出目录必须尚不存在；重跑请选择 `state/evaluation-02` 等新目录。运行器拒绝覆盖已有证据。源码中的 `samples/evaluation/cases.json` 是稳定案例定义，不保存本机运行产物。

| 退出码 | 意义 |
| --- | --- |
| `0` | 本次全部案例匹配各自声明的预期；仍不证明语义正确 |
| `1` | 至少一例未匹配、检查器崩溃、超时、缺环境或输出协议错误；查看报告 |
| `2` | 参数 / 案例文件无效，或不能创建新的输出目录 |

检查器合法返回 `NEEDS_HUMAN` 并不等于运行器崩溃：运行器同时核对结构化状态与退出码。没有 JSON 的崩溃不能算作“成功拒绝非法输入”。缺少 SymPy / ANTLR 属于环境问题，不归因于公式质量。

## 案例覆盖

| ID | 场景 | 预期 |
| --- | --- | --- |
| F01–F03 | 多项式、分数与上下标、配对 `left/right` | `OK` |
| F04–F06 | 尾部运算符、缺失下标、不完整分数 | `RETRY` |
| F07 | 空白公式 | `RETRY` |
| F08 | 可解析但通常算术下不成立的 `1+1=3` | `OK`，仅表示语法可解析 |
| F09–F10 | 损坏的 JSON、非字符串公式 | `NEEDS_HUMAN / bad_input` |
| T01 | Decimal：`0.1+0.2=0.3` | `OK` |
| T02 | 表内合计错误 | `RETRY / sum_mismatch` |
| T03–T04 | 行数不符、列数不符 | `RETRY / shape_mismatch` |
| T05 | 中英文千位分隔符 | `OK` |
| T06 | 非数值单元格 | `RETRY / bad_number` |
| T07–T08 | 行基准通过、列基准不符 | `OK` / `RETRY` |
| T09 | 显式正负号 | `OK` |
| T10、T13 | 超上界或负数基准列索引 | `NEEDS_HUMAN / bad_expectation` |
| T11–T12 | 短合计行、空末行 | `RETRY / shape_mismatch` |
| T14–T15 | 百分比混合、会计括号负数 | `RETRY / bad_number`，不进行隐式换算 |
| T16–T17 | 超过默认 Decimal 精度的大整数：准确合计与相差 1 | `OK` / `RETRY / sum_mismatch` |

`contract` 组有 24 例，检查明确的脚本行为；`semantic-boundary` 组有 F08、T14、T15 共 3 例，展示解析不等于判真、拒绝不等于理解。`known-gap` 分组保留给尚未满足的要求，本版没有把崩溃或不支持功能的错误接受设置成“预期通过”。以后发现新缺口，应保持合理预期并单独分组，而不是把实际错误结果抄成期望。

## 不应从这些结果得出什么

- 匹配数不是模型准确率。运行中没有模型，也没有真实 OCR 标注集、盲测或对照组。
- F08 故意展示语法检查的限制。`OK` 不证明等式成立，不证明下标与原文一致。
- T14、T15 只验证拒绝不支持的格式。系统不负责解释币种、百分比单位、会计符号或四舍五入规则。
- 这不是完整 LaTeX 编译测试，也不覆盖自定义宏、跨页合并表格、完整文档语义或恶意 TeX 的隔离。
- 每例耗时包含独立 Python 进程启动，不是吞吐量、模型延迟或硬件性能基准。

## 维护与运行器回归

每例必须保留稳定 ID、`checker`、`category`、`evaluation_group`、`input`、`expected` 和 `why`。`expected.reason` 可约束固定机器可读原因；解析器生成的自然语言报错不做精确字符串匹配。额外边界写入 `limitation`。改预期前应说明输入契约为何改变，不能为了全绿修改期望。

```bash
python -m unittest discover -s scripts -p test_evaluate_cases.py -v
```

运行器回归覆盖真实表格进程、崩溃与非零退出码、超时、错误原因、分组隔离、重复 ID、非法 catalog 字段、argv NUL 与输出目录保护。它不重复验证所有检查器算法；案例报告仍须单独运行并保存。
