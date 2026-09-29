# Skill 指令先导实验

本次比较仅检查器、同模型 Skill off、同模型 Skill on 三组。12条输入生成36条分组结果；两个模型组各接受5个语法候选，最终文本完全相同。独立人工语义复核待完成，语义准确率保留为 null。

## 输入与控制条件

输入来自 Active Calculus Single Variable 第二版：按固定提交下三个章节的源码顺序，各取最早两个符合词法条件的唯一公式，得到6条原文。每条另生成一个注入版本：删除最后一个右花括号，或在无右花括号时追加 `+`。共12条输入，来源位置、字节摘要与 CC-BY-SA-4.0 署名见[来源声明](../samples/research/ACTIVE_CALCULUS_NOTICE.md)。

模型实际标签为 `qwen3.8:27b-q4_K_M`，[运行环境](evaluation-results/skills-pilot/model-environment.json)保存 digest 和服务版本。检查器在本机执行，文本请求经 SSH 转发到 Spark；本实验不运行 OCR 或 TeX 编译。两模型组均为 temperature=0、seed=0、max_tokens=1024，每例最多两次候选，逐例轮换组顺序。

计划内的指令差异只有系统消息是否加载完整公式 Skill。基础提示、检查器和输出预算相同，Skill 内容额外消耗输入 token。仅初检 `RETRY` 请求模型；参考公式、预期和注入标签不进入请求。初检共5条 `OK`、7条 `RETRY`，其中原文1条、注入6条进入候选流程。

## 结果与失败

| 组 | HTTP 尝试 | 语法接受候选 | 最终文本改动 | 环境失败 | 无候选 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 仅检查器 | 0 | 0 | 0 | 0 | 0 |
| 同模型 / Skill off | 9 | 5 | 5 | 0 | 0 |
| 同模型 / Skill on | 8 | 5 | 5 | 1 | 1 |

所有组均保留6条原文和6条注入输入。两模型组的5处改动全部来自注入输入，6条原文均原样保留。HTTP 尝试包括超时，环境失败和无候选两列存在重叠。

| 未解决项 | 组 | 结果 |
| --- | --- | --- |
| AC02-original | Skill on | 请求超时，保留原文 |
| AC02-original | Skill off | 两次候选均未通过回判 |
| AC02-injected | Skill off、Skill on | 各两次候选均未通过回判 |

AC02 原文为连等式 `AV_{[0.5, 0.75]} = -16 - 16(0.25) = -20`，它触发了当前解析器的覆盖边界。因此原文对照需要保留，避免将解析失败直接归因于源文错误。重复请求仍发送原公式，种子相同，也没有上次失败反馈。[逐次候选与原始响应](evaluation-results/skills-pilot/results.jsonl)

| 模型组 | 有 usage 的请求 / 全部尝试 | 已知输入 tokens | 已知输出 tokens |
| --- | ---: | ---: | ---: |
| Skill off | 9 / 9 | 1138 | 2567 |
| Skill on | 7 / 8 | 6564 | 1562 |

超时请求缺少 usage，所以上表只统计已知用量。实验只运行一次，且启动前没有已加载模型记录；耗时留在原始报告中，不作性能比较。

## 复现与人工复核

使用 Python 3.11+，在仓库根目录安装 `harness/requirements.txt`。先检查运行器，不发起模型请求：

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/pilot-dry-01 --mode dry-run
```

`dry-run` 只生成计划、报告和复核空表。准备好兼容端点与模型后，可按本次参数重新运行；将 `YOUR_INSTALLED_MODEL` 替换为实际标签，输出目录须为新目录：

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/active_calculus_cases.json \
  --outdir work/pilot-model-01 --mode model \
  --base http://127.0.0.1:11434 --model YOUR_INSTALLED_MODEL \
  --seed 0 --max-tokens 1024
```

运行输出 `manifest.json`、`results.jsonl`、`report.md` 和 `blind-review.csv`。核对配置与模型 digest，再比较逐例结果；模型服务的数值实现可能影响重复运行输出。

将复核 CSV 和必要的来源上下文交给独立复核者，分组结果单独保留。填写 `verdict`、具名 `reviewer` 和 `independent_review=yes`，保留前十列的输入及候选绑定字段。无法判断时填 `uncertain` 或 `unreviewable`。导入已完成的复核：

```bash
python scripts/evaluate_skills.py review \
  --run-dir work/pilot-model-01 --reviews work/completed-review.csv \
  --outdir work/pilot-review-01
```

当前存档的[复核表](evaluation-results/skills-pilot/blind-review.csv)仍待填写；原始[报告](evaluation-results/skills-pilot/report.md)和[运行清单](evaluation-results/skills-pilot/manifest.json)保持原样。完整字段与导入检查见[研究协议](../samples/research/README.md)。

## 结论与下一步

本次没有观察到 Skill 改善最终输出。它验证了同一宿主中的指令对照、逐候选记录和复核交付流程。样本仅来自一本教材的6条公式及简单注入，且只有一次运行，现阶段适合定位流程和解析覆盖问题。

下一步先完成独立语义复核，再增加跨来源自然错误和正常对照，按文档划分开发与评测集合。评测分别记录修复正确性、误改和人工介入；若评估节省时间，需补充人工从零修复的对照。
