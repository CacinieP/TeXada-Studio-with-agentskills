# 公式 Skills 受控对照

这一目录定义来源可追溯的公式样本和人工复核协议。它与 [`../evaluation`](../evaluation/README.md) 的检查器契约测试分开：语法契约通过不是语义准确率，合成 smoke 不是独立真实测试集，开放来源加人工注入也不是自然错误样本。

## 样本与来源

每个目录遵循 [`schema.json`](schema.json)。稳定 ID、来源标题/URL/许可、具体公式定位和原始来源文件字节 SHA-256 都必填；`original_latex` 是实际待检查文本。来源字节散列不能用待修公式散列代替。公开来源的出处和许可仍需维护者逐一核实；schema 只能检查字段，无法证明授权或引用正确。

`case_kind` 分为：

- `original`：按来源原样提取，不预设原文有错。
- `control`：保留正确或语法可接受的对照；初检 OK 应跳过模型。
- `injected`：明确记录人工注入变化，不能称为独立收集的真实错误。

`expected_syntax` 可选，只表示当前解析器的预期行为。`reference_latex` 给复核者参考，未获人工确认前不是语义真值。所有来源记录 `review_status=pending`；不能以维护者生成标签替代独立复核。

[`smoke_cases.json`](smoke_cases.json) 完全合成，来源为 [`smoke-source.txt`](smoke-source.txt)。仅用于检查执行器的正例、可修复错误和语法无法证明语义的边界。此集合不能用于发布产品准确率。

## 开放来源先导集合

[`active_calculus_cases.json`](active_calculus_cases.json) 包含 Active Calculus Single Variable 第二版的 6 条来源原文和 6 条明确注入错误，共 12 例。按固定提交下三章的源码顺序取最早两个符合词法条件的唯一公式，不以检查器能否通过筛样；注入规则为删除最后一个右花括号，或在无右花括号时追加 `+`。人工语义复核全部为 pending。

使用 [`prepare_open_cases.py`](../../scripts/prepare_open_cases.py) 从固定来源重建，目录记录精确定位、来源字节散列和 CC-BY-SA-4.0 标识。该先导集合只覆盖一本教材、少量表达式与两类注入，尚不是独立自然错误集，也不构成泛化结论。真实对照运行时将 `--cases` 换成这个文件；许可及署名详见相邻来源说明。

## 三组执行协议

| 组 | 确定性检查 | 模型 | Skill 指令 |
| --- | --- | --- | --- |
| `checker_only` | 是 | 无 | 无 |
| `model_without_skill` | 是 | 同一模型 | off |
| `model_with_skill` | 是 | 同一模型 | on：读取真实 SKILL.md 并注入系统消息 |

三组使用相同输入和检查器。两个模型组共享模型、seed、temperature=0、max_tokens，以及每例每组最多两次候选的预算。相同 max_tokens 是相同输出上限，Skill 增加输入 token，不能称作相同总 token 成本。每个 case 的组顺序循环轮换，减少永远先跑某组的顺序偏差；不能据此声称已消除所有负载或缓存影响。服务端可能不支持严格 seed 重现，应保留其实际实现信息。

仅初检 RETRY 请求模型。初检 OK、NEEDS_ENV、NEEDS_HUMAN 均不请求；候选 NEEDS_ENV 立即停止。参考公式、错误标签和预期状态不进入请求。模型候选再次检查通过后才成为拟交付文本，其余情况保留原文；这只是语法接受，仍需要人工判断。runner 保留每次候选和拒绝原因，不只保留最终成功项。

## 运行

在已安装 [`harness/requirements.txt`](../../harness/requirements.txt) 的 Python 环境中，从仓库根运行。每次输出目录必须不存在，避免覆盖证据。

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-dry-01 --mode dry-run
```

`dry-run` 不执行检查器、不请求网络，仅检验输入、计划、报告与复核空表。`fixture` 执行真实检查器，但候选来自明确指定的 JSON 测试替身，模型请求数永远为零：

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-fixture-01 --mode fixture \
  --fixture-repairs samples/research/smoke_repairs.json
```

Fixture 文件是 `{"model_without_skill":{"case-id":["candidate1",null]},"model_with_skill":{...}}`，最多两个候选。两个组可以相同，也可以不同；区别由测试作者预设，不能证明 Skill 效果。

只有显式指定 `--mode model --base --model` 才请求网络。请替换成已授权端点与实际模型标识，预算上限为 `case 数 × 2 组 × 2 次请求`，实际请求数会因初检通过、无候选或错误而减少：

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-model-01 --mode model \
  --base http://127.0.0.1:11434 --model YOUR_INSTALLED_MODEL \
  --seed 0 --max-tokens 300
```

先用 smoke 检查流程，再指定另行核实的开放来源集合。模型标签不等于权重摘要；同标签更换权重需要另存 digest 并创建新运行。一个来源、少量样本、人工注入的先导实验不能说明广泛泛化，更不能替代随机或预先约定的独立样本。

模型请求数是 HTTP 尝试数，包含超时或 HTTP 错误，并不等于已确认完成推理的次数。两个模型组的相同配置在开始前通过 fingerprint 验证；配置不匹配则拒绝运行。

输出包括 `manifest.json`（配置、来源、代码/Skill 指纹和哈希）、`results.jsonl`（逐项过程）、`report.md` 和 `blind-review.csv`。报告区分真实模型请求、测试替身调用、环境失败、无候选及最终输出差异。未复核时语义准确率为 null。逐组结果及时追加写入，进程中断时已有证据保留，但 `status=running` 的未完成运行不能导入复核。运行前后检查程序哈希；期间发生代码变化则返回非零并拒绝后续复核，固定实现后重跑。

## 独立人工复核

仅把 `blind-review.csv` 和必要来源上下文交给独立复核者，不同时提供分组结果。CSV 隐去组名、固定散列打乱行序，但相同输出可能仍可辨认；这是基本的组名盲化，不是严格临床式双盲。

不要更改前十列。填写 `verdict=correct|incorrect|uncertain|unreviewable`、具名 `reviewer`、`independent_review=yes`；可填实际 `review_seconds` 和理由。`correct` 表示相对于来源上下文，当前拟交付文本语义成立且没有误改；`incorrect` 包含未纠正错误或引入错误；信息不足用 uncertain，超出自身知识或证据不可得用 unreviewable。原样输出也按同一标准判断。不能根据“解析器通过”替人工判定。

```bash
python scripts/evaluate_skills.py review \
  --run-dir work/research-model-01 \
  --reviews work/completed-review.csv \
  --outdir work/research-review-01
```

允许部分复核，未填或未交回行保留 pending。完成的行必须具名、声明独立且给出判定；没有任何完成行则拒绝生成准确率。导入验证 case/原文/拟交付文本哈希与不可变字段，防止把其他版本的判定混入。工具只记录独立性声明，无法验证复核者与作者的关系。

汇总列出总量、覆盖率、pending、uncertain、unreviewable，并只对已审且确定的 correct/incorrect 行给出正确比例。即使比例很高，也不能外推到未审样本；fixture/dry-run 的复核不能变成真实模型实验。逐行计时没有人工从零修复基线，不能推出节省时长。

## 下一阶段采样

先固定来源、抽样规则、错误类型和主要指标，再运行三个组。按来源或文档划分开发集与评测集，避免用展示 case 反复调提示。保留原文对照以记录误改；注入实验与自然错误分表。多人复核时另行保留分歧和仲裁记录，不覆盖原始判定；当前导入器每行只接受一条具名判定，尚不实现多人一致率计算。
