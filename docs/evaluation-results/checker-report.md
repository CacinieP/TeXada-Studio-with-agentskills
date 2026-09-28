# 合成检查器案例报告

本报告检查确定性脚本的输入契约和边界行为。没有调用模型、OCR 或网络；预期匹配不代表数学语义正确，也不是模型准确率。

生成时间：2026-09-28T09:02:25.387429+00:00 · Python 3.13.13。

Catalog SHA-256：`9db03d5d5df5e062d93c116dbed3f0470c67ccd2c846c48b9d374f46be94a30d`。

## 分组结果

| 分组 | 案例 | 匹配 | 未匹配 |
| --- | ---: | ---: | ---: |
| contract | 24 | 24 | 0 |
| semantic-boundary | 3 | 3 | 0 |
| known-gap | 0 | 0 | 0 |

`contract` 检查声明的确定性行为；`semantic-boundary` 展示语法或支持范围边界；`known-gap` 单独保留尚未满足的要求，不计入契约匹配成绩。任何一组出现未匹配，命令均返回非零。

## 逐例结果

| ID | 分类 / 分组 | 预期状态 | 实际状态 / 进程结果 | 匹配 |
| --- | --- | --- | --- | --- |
| F01 | positive / contract | OK | OK | 是 |
| F02 | positive / contract | OK | OK | 是 |
| F03 | positive / contract | OK | OK | 是 |
| F04 | negative / contract | RETRY | RETRY | 是 |
| F05 | negative / contract | RETRY | RETRY | 是 |
| F06 | negative / contract | RETRY | RETRY | 是 |
| F07 | invalid-input / contract | RETRY | RETRY | 是 |
| F08 | semantic-boundary / semantic-boundary | OK | OK | 是 |
| F09 | invalid-input / contract | NEEDS_HUMAN | NEEDS_HUMAN | 是 |
| F10 | invalid-input / contract | NEEDS_HUMAN | NEEDS_HUMAN | 是 |
| T01 | positive / contract | OK | OK | 是 |
| T02 | negative / contract | RETRY | RETRY | 是 |
| T03 | negative / contract | RETRY | RETRY | 是 |
| T04 | negative / contract | RETRY | RETRY | 是 |
| T05 | positive / contract | OK | OK | 是 |
| T06 | negative / contract | RETRY | RETRY | 是 |
| T07 | positive / contract | OK | OK | 是 |
| T08 | negative / contract | RETRY | RETRY | 是 |
| T09 | positive / contract | OK | OK | 是 |
| T10 | invalid-input / contract | NEEDS_HUMAN | NEEDS_HUMAN | 是 |
| T11 | invalid-input / contract | RETRY | RETRY | 是 |
| T12 | invalid-input / contract | RETRY | RETRY | 是 |
| T13 | invalid-input / contract | NEEDS_HUMAN | NEEDS_HUMAN | 是 |
| T14 | unsupported-format / semantic-boundary | RETRY | RETRY | 是 |
| T15 | unsupported-format / semantic-boundary | RETRY | RETRY | 是 |
| T16 | positive / contract | OK | OK | 是 |
| T17 | negative / contract | RETRY | RETRY | 是 |

## 解释与限制

### F01 · 完整多项式

完整的支持范围内代数表达式应通过语法解析。

### F02 · 分数与上下标

分子、分母与上下标均完整，检查组合语法。

### F03 · 配对的伸缩定界符

先验证原始定界符，再归一化尺寸命令，完整配对应通过。

### F04 · 尾部运算符

严格解析不能仅接受前缀 x 并忽略缺少右操作数的加号。

### F05 · 缺失下标

下标操作符后没有内容，应请求修复而不是推测原意。

### F06 · 缺少分母右花括号

不完整的分数结构不能通过语法检查。

### F07 · 空白公式

脚本显式约定空公式为 RETRY。

### F08 · 语法完整的错误等式

等式语法可解析；预期 OK 仅断言解析器接受输入，不断言等式成立。

限制：1+1=3 在通常算术下不成立；语法检查不能代替数学判真或原文核对。

### F09 · 损坏的 JSON 输入

JSONL 入口必须受控拒绝损坏的 JSON 或非字符串公式字段，并返回 NEEDS_HUMAN / bad_input。

### F10 · 公式字段类型错误

JSONL 入口必须受控拒绝损坏的 JSON 或非字符串公式字段，并返回 NEEDS_HUMAN / bad_input。

### T01 · Decimal 小数精确相加

0.1+0.2 应与 0.3 精确相等，避免二进制浮点误差。

### T02 · 表内合计不一致

数据行和为 4.0，声明合计 4.5 不一致。

### T03 · 声明行数不一致

显式声明 3 行而实际只有 2 行，应先报告 shape_mismatch。

### T04 · 声明列数下的短行

n_cols=2 的契约下，短行应受控地报告 shape_mismatch。

### T05 · 中英文千位分隔符

合法千位分组在归一化后按 Decimal 精确相加，合计应为 3000.30。

### T06 · 数据单元格无数值

合计列的数据行无法提取数值，应返回 bad_number。

### T07 · 行基准合计

row:1 从第二个单元格起相加，与独立提供的基准 3.5 比较。

### T08 · 列基准合计不一致

没有合计行也应按 expected.totals 比对数据行和 3.5。

### T09 · 带符号数值

明确的正负号在支持范围内，合计应为 1.00。

### T10 · 超出范围的基准列

基准指向不存在的列，当前接口明确使用 bad_expectation。

### T11 · 合计行缺少单元格

网格存在缺失单元格或空行，应受控返回 RETRY / shape_mismatch，不能中断进程。

### T12 · 空的末行

网格存在缺失单元格或空行，应受控返回 RETRY / shape_mismatch，不能中断进程。

### T13 · 负数基准列索引

列索引契约应是有效的非负下标；非法基准应报告 bad_expectation。

### T14 · 百分比与普通数混合

数值必须符合支持的完整单元格格式；百分比、混合单位和会计括号不能静默取首个数字，应返回 RETRY / bad_number。

限制：本例验证拒绝不支持的数字格式，不证明系统能换算百分比、币种或会计负数。需要人工解释原文或显式归一化后重新检查。

### T15 · 会计括号负数

数值必须符合支持的完整单元格格式；百分比、混合单位和会计括号不能静默取首个数字，应返回 RETRY / bad_number。

限制：本例验证拒绝不支持的数字格式，不证明系统能换算百分比、币种或会计负数。需要人工解释原文或显式归一化后重新检查。

### T16 · 超出默认 Decimal 精度的正确合计

求和精度应随输入位数扩展，不能把大整数低位的差异舍入成相等。

### T17 · 大整数合计少 1

求和精度应随输入位数扩展，不能把大整数低位的差异舍入成相等。
