# Skill 指令先导实验：结果与限制

本次完成12条输入的三组运行，共36条拟交付文本记录。输入来自6条开放教材公式及各自的注入变体；36条不是36个独立样本。独立人工复核尚未完成，语义准确率仍为 null。

## 固定条件

模型使用实际安装标签 `qwen3.8:27b-q4_K_M`；完整 digest 和观察到的服务版本见[运行环境](evaluation-results/skills-pilot/model-environment.json)。检查器在本机运行，文本模型请求经SSH转发到Spark节点；没有OCR、图像或TeX编译。temperature=0、seed=0、max_tokens=1024、每例每模型组最多两次候选。

唯一计划内指令差异是是否在系统消息中提供完整公式 Skill。两组基础提示、工具和输出上限一致；Skill 增加输入 token，不能称为相同总成本。只有初检 RETRY 请求模型；参考原文与注入标签没有进入请求。每例组顺序固定轮换。

初检只计12条输入一次：5条 OK，7条 RETRY。来源、抽样规则、原文件摘要和CC-BY-SA-4.0署名见[来源声明](../samples/research/ACTIVE_CALCULUS_NOTICE.md)。

## 保留失败的结果

| 组 | 原文 / 注入 | HTTP尝试 | 语法接受候选 | 拟交付文本改动 | 环境失败 | 无候选 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 仅检查器 | 6 / 6 | 0 | 0 | 0 | 0 | 0 |
| 同模型 / Skill off | 6 / 6 | 9 | 5 | 5 | 0 | 0 |
| 同模型 / Skill on | 6 / 6 | 8 | 5 | 5 | 1 | 1 |

请求是HTTP尝试次数，包含超时，不证明服务端完成了推理。环境失败与无候选可以重叠；所有条目保留，没有因失败缩小分母。语法接受仅指解析器接受候选。

| 组与来源类型 | 条目 | 初检RETRY | 接受候选 | 输出变化 |
| --- | ---: | ---: | ---: | ---: |
| 仅检查器 / original | 6 | 1 | 0 | 0 |
| 仅检查器 / injected | 6 | 6 | 0 | 0 |
| 同模型 / Skill off / original | 6 | 1 | 0 | 0 |
| 同模型 / Skill off / injected | 6 | 6 | 5 | 5 |
| 同模型 / Skill on / original | 6 | 1 | 0 | 0 |
| 同模型 / Skill on / injected | 6 | 6 | 5 | 5 |

## 请求成本与可观察失败

| 模型组 | 有usage的请求 / 全部尝试 | 已知输入tokens | 已知输出tokens |
| --- | ---: | ---: | ---: |
| 同模型 / Skill off | 9 / 9 | 1138 | 2567 |
| 同模型 / Skill on | 7 / 8 | 6564 | 1562 |

缺失usage的超时请求没有可确认token用量，上表是已知部分，不能记作完整成本。实验启动前服务没有已加载模型记录，且只运行一次；总耗时和组间耗时不用于性能或显著性结论。

教材原文中的连等式 `AV_{[0.5, 0.75]} = -16 - 16(0.25) = -20` 触发了当前解析器的 RETRY。它说明“原检查失败”可能来自解析覆盖范围，不能自动判定源文写错。保留原文组因此很重要。逐次候选和原始响应见[结果JSONL](evaluation-results/skills-pilot/results.jsonl)。

| 发生失败或未解决的模型组条目 | 结果 | 提供方原因序列 |
| --- | --- | --- |
| AC02-original / 同模型 / Skill on | environment_failure | timeout |
| AC02-original / 同模型 / Skill off | unresolved | ok, ok |
| AC02-injected / 同模型 / Skill off | unresolved | ok, ok |
| AC02-injected / 同模型 / Skill on | unresolved | ok, ok |

提供方原因 ok 仅表示返回了合法候选JSON；unresolved 表示候选仍未通过语法回判。
两个模型组最终文本不同的案例数为 0 / 12；这只是文本差异，不表示哪一组语义更准确。重复请求仍使用原公式、相同seed且没有失败反馈，可能重复相同候选，并不构成自我修正。

## 人工复核与结论边界

将[盲审CSV](evaluation-results/skills-pilot/blind-review.csv)与来源上下文交给独立复核者，避免同时提供带分组的结果。填写verdict、reviewer、independent_review=yes；不确定项保留uncertain或unreviewable。之后按[导入协议](../samples/research/README.md)导入；不要改绑定输入和候选的前十列。

本次能够验证：实际Skill加载、相同宿主里的三组执行、调用与候选证据，以及人工待审流程。尚不能验证：语义正确率提高、误改率下降、人工时间节省、自然OCR修复效果或跨来源泛化。单一教材、六条来源公式、一次种子和简单注入还可能与模型预训练材料重叠，需要多来源自然错误与独立人工判定继续检验。

原始[运行报告](evaluation-results/skills-pilot/report.md)与[manifest](evaluation-results/skills-pilot/manifest.json)按运行器原样保存，文件摘要已核对，运行期间代码与目录均未改变。SHA256用于版本对应，不是外部公证。未改动提示或预算重跑以替换不理想结果。
