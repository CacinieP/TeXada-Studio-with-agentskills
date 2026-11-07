# 公式修复质量：保留原文与有界语法修补

本轮参考 [TeXada Math Agent](https://github.com/CacinieP/TeXada-the-Math-Agent/tree/a4a0f434fa483a5951e371f934b9837447aedaae) 的确定性修复及 mutation-scope 策略，改进本地 Studio 与 CLI 的公式修复宿主。没有更换模型或连接云服务。

## 当前修复策略

1. 保留权威原文和精确源码范围，先用同一语法检查器检查。
2. 对缺失的尾部 `}`、受支持的单个 `\left` 配对、末尾 `\right` 缺匹配定界符，生成保留原文的确定性候选，再回判。成功时无需模型。
3. 缺操作数、缺下标、重复上下标、未知宏、复杂结构与已知解析器覆盖边界保留人工项。有效连等式和 evaluation-bar 记号不会因为 SymPy 的覆盖限制被删改。
4. 模型候选同时经过语法与来源修改范围检查。当前保真规则只授权原样内容或已知确定性规则的同一个结果；数字、变量、运算符、项和既有分组不能被模型擅自改写。
5. 有界重试将检查器结果、上一候选和拒绝原因放入用户数据 JSON 的 `repair_context`；原公式保持权威。重复候选停止，环境故障不转成继续猜测。
6. CLI、普通 Studio 和可选 planner 共用规则。事件区分确定性修复、语法检查、scope 判定、真实 HTTP 请求与使用者审阅；策略和扫描器哈希参与续跑身份。

该策略是保守的修改授权，不是数学等价证明。模型 fallback 当前不能扩大已授权的可修复集合；无法确定的改动会保留原文供人工处理。一次语法成功不意味着任意 TeX 宏都能编译，编译、转写忠实度与数学结论分别验证。

实现入口：[formula_repair.py](../harness/docforensics/formula_repair.py)、[Studio 宿主](../webui/app.py)、[CLI 宿主](../harness/docforensics/pipeline.py)。
Agent 参考依据：[确定性工具](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/a4a0f434fa483a5951e371f934b9837447aedaae/src/texada/core/repair.py)、[来源修改范围](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/a4a0f434fa483a5951e371f934b9837447aedaae/src/texada/agent/mutation_scope.py)、[失败上下文](https://github.com/CacinieP/TeXada-the-Math-Agent/blob/a4a0f434fa483a5951e371f934b9837447aedaae/src/texada/agent/failure_context.py)。Studio 的规则范围更小，未引入 Agent 的 KaTeX raw AST 或 CAS 等价能力。

## 可重放的 20 个合成案例

| 组 | 数量 | 评分 |
| --- | ---: | --- |
| R：结构错误 | 6 | 分数、根号、上下标、定界符等修复与明确参考是否精确匹配 |
| C：正确原文 | 6 | 是否逐字保留，是否产生无谓 provider 请求；包括数学不成立但语法合法的 `1+1=3` |
| A：危险候选 | 6 | 改数字、变量、符号、删项等候选是否造成非参考改写 |
| U：歧义输入 | 2 | `x+`、`a_` 是否保留原文，而非编造操作数或索引 |

R/A 部分输入刻意重复，用来分别测试正常候选与攻击候选；这不是独立随机抽样的准确率数据集。参考答案仅供评分，不能进入模型提示。精确匹配失败也不能自动推断数学错误，需要查看逐例输出。

从仓库根目录运行：

```bash
.venv/bin/python scripts/evaluate_formula_repairs.py \
  --mode fixture --outdir state/formula-quality-fixture-01

.venv/bin/python scripts/evaluate_formula_repairs.py \
  --mode local-model --base-url http://127.0.0.1:18081/v1 \
  --model MiniCPM-V-4.7-1B --skill-mode on --seed 0 --max-tokens 300 \
  --outdir state/formula-quality-local-01
```

输出目录须为新目录。本机模式必须显式选择 HTTP 回环端点和模型，不读取云 API Key。
报告记录案例、源码与提供方指纹、输入/预期/输出、事件、调用数和失败状态。
fixture 用预设候选验证宿主；没有请求 provider 的案例不能声称候选被实际注入并经 guard 拒绝。

## 2026-11-04 本机对照

修改前冻结版本为 `4168899`，参考 Agent 固定在上述提交。模型配置保持 MiniCPM-V 4.7 1B Q4、本机回环服务、Skill on、seed 0、max_tokens 300、最多两次请求。

| 指标 | 原流程 | 新流程 |
| --- | ---: | ---: |
| R 组正确结构修复 | 4/6 | 6/6 |
| C 组正确输入逐字保留 | 5/6 | 6/6 |
| U 组歧义输入保留 | 2/2 | 2/2 |
| 这 20 例的 HTTP 尝试 | 22 | 0 |

原流程曾删去 C04 的 `AV_{[0.5,0.75]}` 前缀；新流程保留该连等式并提示人工核对解析器覆盖边界。新流程的 R 组收益来自确定性规则，after 的零 HTTP 结果衡量同配置工作流的变化，不是对模型推理准确率的测量。

fixture 对照中，原流程实际接受了 6/6 个危险改写。新流程在这六例请求候选前完成确定性修复，所以危险候选未被注入；不能把这六例写成“guard 拒绝 6/6”。直接 scope 单元测试另覆盖被替换数字、变量、运算符、上下标与删项的拒绝。

该小型合成对照不能推广成任意公式、OCR 文档或数学正确率。原始本地报告位于本次 checkout 的 `work/formula-quality-before-*` 与 `work/formula-quality-after-*`；该目录不随源码包分发。复现时保留新报告，并记录源码哈希，历史模型结果可能因服务实现和权重版本变化而不同。
