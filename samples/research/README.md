# 公式 Skills 受控对照

对同一批公式运行三组，保留来源、请求配置、每个候选和人工复核表：

| 组 | 检查器 | 模型 | 公式 Skill |
| --- | --- | --- | --- |
| `checker_only` | 相同 | 无 | 无 |
| `model_without_skill` | 相同 | 同一模型 | off |
| `model_with_skill` | 相同 | 同一模型 | on，读取真实指令正文 |

## 先检查运行流程

在仓库根目录、已安装 [`harness/requirements.txt`](../../harness/requirements.txt) 的环境中运行。每次使用新的输出目录。

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-dry-01 --mode dry-run

python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/research-fixture-01 --mode fixture \
  --fixture-repairs samples/research/smoke_repairs.json
```

Dry-run 验证输入与执行计划；fixture 运行真实检查器、读取预设候选。二者模型请求数均为0。Fixture格式为 `{"model_without_skill":{"case-id":["candidate1",null]},"model_with_skill":{...}}`，每例每组最多两个候选。

## 真实模型运行

准备兼容服务，将标签替换为已安装的模型：

```bash
export VLM_MODEL='替换为已安装的完整模型标签'
python scripts/evaluate_skills.py run \
  --cases samples/research/active_calculus_cases.json \
  --outdir work/research-model-01 --mode model \
  --base http://127.0.0.1:11434 --model "$VLM_MODEL" \
  --seed 0 --max-tokens 1024
```

只有显式选择 `--mode model` 并提供 `--base`、`--model` 才请求服务。两个模型组共享 seed、temperature=0、max_tokens 和每例最多两次候选预算；按 case 轮换组顺序。上限为 `样本数 × 2组 × 2次` HTTP尝试，初检 `OK` 会跳过模型。实际服务是否严格复现seed需记录其实现；模型权重digest和服务版本另存到运行目录。

仅初检 `RETRY` 进入候选流程。候选重新检查后，`OK` 成为拟交付文本，其余情况保留原文；环境故障停止该项。参考答案和预期标签不进入模型请求。Skill增加输入token，统一输出上限不代表总token成本相同。

## 输入与来源

| 集合 | 组成 | 用途 |
| --- | --- | --- |
| [smoke_cases.json](smoke_cases.json) | 完全合成，来源文件为[smoke-source.txt](smoke-source.txt) | 运行器流程检查 |
| [active_calculus_cases.json](active_calculus_cases.json) | Active Calculus第二版6条原文、6条人工注入错误 | 小规模受控先导实验 |

开放教材集合从固定提交的三章按源码顺序各取最早两个符合词法条件的唯一公式。注入操作为删去末个右花括号，无右花括号时追加 `+`。许可与定位见 [ACTIVE_CALCULUS_NOTICE.md](ACTIVE_CALCULUS_NOTICE.md)。重建命令会下载固定版本的公开来源：

```bash
python scripts/prepare_open_cases.py \
  --source-dir work/active-calculus-source \
  --out work/active-calculus-rebuilt.json --fetch
```

已有来源文件时省略 `--fetch`，脚本仍验证字节哈希。输出文件须不存在。

新样本遵循 [schema.json](schema.json)，包括稳定ID、来源URL/许可/具体定位/源文件SHA256、`original_latex` 和 `review_status=pending`。`case_kind` 分为原文 `original`、对照 `control` 和注入 `injected`。`expected_syntax` 记录解析器预期；`reference_latex` 供复核者参考。

## 输出与结果解释

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 输入、参数、环境、代码/Skill指纹、执行顺序和文件哈希 |
| `results.jsonl` | 每个组的检查、候选、拒绝原因和请求计数 |
| `report.md` | 语法接受、失败、无候选和输出差异汇总 |
| `blind-review.csv` | 隐去组名、打乱行序的复核表 |

模型请求数统计HTTP尝试，包含超时。环境失败和无候选单列。语义准确率在独立复核前为空；部分复核只统计已审且有确定结论的行。合成数据、人工注入和自然错误应分开解释；这批单教材先导样本用于观察候选差异，不能代表一般文档效果。已有结果见[先导实验解读](../../docs/skills-pilot-analysis.md)。

逐组结果及时落盘。中断后的 `status=running` 目录保留已有结果，需用新目录完整重跑后再导入复核；运行期间代码或样本变化也会使运行无效。

## 导入独立人工复核

将 `blind-review.csv` 和必要来源上下文交给复核者。复制CSV后填写以下列，保留其余列和哈希不变：

- `reviewer`：具名复核者；`independent_review=yes`：独立性声明。
- `verdict`：`correct`、`incorrect`、`uncertain` 或 `unreviewable`。
- `review_seconds` 和 `notes`：按实际情况填写时长和理由。

判定对象是相对来源上下文的拟交付文本，包含原样保留的文本。证据不足选 `uncertain`，无法评阅选 `unreviewable`。

```bash
python scripts/evaluate_skills.py review \
  --run-dir work/research-model-01 \
  --reviews work/completed-review.csv \
  --outdir work/research-review-01
```

可导入部分复核，未填行保留pending；至少一行完成才生成汇总。导入器验证case、输入和候选的哈希绑定，报告覆盖率及各类判定。独立性由复核者声明，相同输出也可能被识别，因此这里提供的是组名盲化。多人分歧与仲裁需另存记录。

后续扩大评测时，先固定来源、抽样规则和指标，按文档划分开发集与评测集，并分别收集原文对照、注入错误和自然错误。
