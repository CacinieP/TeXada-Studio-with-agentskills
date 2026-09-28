# Skills 受控对照运行

运行模式：**model**；数据集：`active-calculus-pilot-v1`（open-source）。

dry-run / fixture 只验证执行器；只有 model 模式记录真实模型请求。语法通过不等于语义正确；pending 人工复核不参与正确率。

三组共享同一输入、检查器、模型配置、seed、temperature=0 和每例每组最多两次候选预算；case 间轮换执行顺序。初检 OK 不调用模型。模型端点是否严格遵守 seed 由其实现决定，本工具不保证位级确定性。

| 组 | 条目 | 模型请求 | 测试替身调用 | 语法接受候选 | 输出变化 | 环境失败 | 无候选 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| checker_only | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| model_without_skill | 12 | 9 | 0 | 5 | 5 | 0 | 0 |
| model_with_skill | 12 | 8 | 0 | 5 | 5 | 1 | 1 |

执行中代码发生变化：False；样本目录发生变化：False；对照配置校验：True。代码变化的运行不可导入人工复核，应固定实现后重跑。
模型请求计数是 HTTP 尝试数，包含超时或 HTTP 错误，不等于确认完成推理的次数。环境失败包括检查器不可用及端点/网络异常；这些情况也可能计入无候选，两个计数不是互斥分类。

两个模型组最终输出不同的案例：0。该数值只能证明文本差异，不能证明一组更准确。

## 人工复核

`blind-review.csv` 隐去组名、按固定散列顺序排列，每一行绑定完整 case、原文和最终拟交付文本的 SHA-256。原始返回和被拒绝候选保存在 results.jsonl，不应向盲审人员同时提供分组结果。

填写 verdict（correct / incorrect / uncertain / unreviewable）、非空 reviewer、independent_review=yes 和实际 review_seconds；最后一项可留空，但不能据此估计人工节省时间。未填写行继续 pending。review 导入时验证不可变字段和全部绑定哈希；独立性是复核者声明，工具无法证实人员独立性。

原样保留的输出同样需要按原来源上下文判断。reference_latex 只提供来源参照，未经人工确认，不是自动真值。只对已完成且 verdict 为 correct / incorrect 的行计算正确比例，同时披露复核覆盖率；不能外推到 pending 行。

## 可复核文件

- manifest.json：配置、来源记录、程序/Skill 指纹、顺序、统计及文件哈希。
- results.jsonl：逐组检查、每次候选、拒绝原因及实际模型请求数。
- blind-review.csv：人工复核空表，不含虚构结论。

本实验仅覆盖公式文本与当前解析器支持范围，不测试 OCR、表格、用户工时节约或跨来源泛化。开放来源提取加人工注入错误也不等于自然发生错误的独立数据集。
