# MiniCPM5-2B 公式 Skill 与路由复核（issue #23）

2026-11-11，本机 macOS arm64 / Python 3.11 / Ollama 0.40.16。
基线为 `cb8c78230f03b659349363777180d5907380092c`（beta.3）。
本次不改变 Studio 默认模型、模型服务配置或旧证据。

## 实际运行与结果

本机原先没有加载 Ollama 模型。使用已安装的 `minicpm5-2b:latest`
（2.5B、Q8_0，模型 digest 见 [manifest](run/manifest.json)），
经 `http://127.0.0.1:11434/v1/chat/completions` 顺序发出 **3 次真实请求**。
使用现有 `OpenAICompatibleProvider`，`skill_mode=on`、temperature=0、seed=0、
max_tokens=1024，每次超时上限 30 秒；未增加重试、未覆盖思考参数。

| 合成输入 | 模型候选 | 检查器 | 来源保留审计 | 解释 |
| --- | --- | --- | --- | --- |
| `\frac{a+b}{2` | `\frac{a+b}{2}` | OK | 允许尾括号补全 | 已有确定性路径可完成同一修复，无额外模型收益 |
| `a+b+` | `a+b+` | RETRY | 原文保留 | 不猜缺失操作数；不是成功修复 |
| `a+b` | `a+b` | OK | 原文保留 | 正确对照式，直接 provider 探测不代表 host 会请求模型 |

3/3 请求返回严格 JSON 的非空 `latex` 候选；这只是这三个请求的观察，
不是契约可靠率或数学准确率的估计。completion_tokens 分别为 324、429、357，
包括后端计入的思考预算，不能当作候选文本长度。响应中的思考正文未归档，
仅记录字符数；最终候选、用量、finish_reason 和 Skill/prompt 哈希均保留。
旧的 MiniCPM5-1B 表格截断结果来自另一模型、任务、配置，不能用本次数据覆盖或直接排名。

[results.json](run/results.json) 保存发给后端的 system/user 消息与去除思考正文后的真实响应。
消息包含加载的公式 Skill；参考答案没有进入消息，只在推理完成后用于精确匹配。
提示词、Skill 和实现哈希由 provider 原生 fingerprint/trace 记录。

## 实际 host 与路由

同一组输入再通过真实 `python -m docforensics run`，设置
`REPAIR_MODEL=minicpm5-2b:latest`、`VLM_MODEL=deliberately-not-selected`，不传 `--vlm-model`。
[host-run/report.md](host-run/report.md) 与 [state.jsonl](host-run/state.jsonl) 记录：
**OK=2、NEEDS_HUMAN=1、模型 HTTP 请求=0**。host 用确定性路径补尾括号，
将缺失操作数转人工，正确式不调用模型；没有写回输入。
这与上面的 3 次直接 provider 探测分开计数。

[routing-audit.json](routing-audit.json) 是 **离线参数解析/provider 选择检查**：
REPAIR_MODEL 优先、显式 --vlm-model 优先、空白 REPAIR_MODEL 回退 VLM_MODEL，
3 项均选择预期模型。这份检查本身不发送请求，不是模型调用证据。
现有 `harness/tests/test_model_routing.py` 的 3 项测试也已通过。
Studio 仍是单模型工作台；CLI 的按任务路由不等于 Studio 有两个模型设置位。

## 语义复核与 issue 状态

本次完成的是 **agent 逐例核对 + 检查器/来源策略审计**，结果见 [audit.json](audit.json)。
尾括号候选保留原有分子、分母、变量和运算顺序；后两例逐字保留。
未进行具名独立人工语义复核，[independent-review.csv](independent-review.csv) 留空待审。
因此 #23 的“真实 MiniCPM5 按公式 Skill 协议产出候选”已补证，
**独立人工复核仍未完成，issue 继续开放**。不据此更改默认模型或声称质量达标。

## 复现与核验

无需云凭证；已安装上述模型并运行 Ollama，使用项目 Python 环境。
原始归档不覆盖；在仓库根目录选一个新的输出目录，例如：

```bash
python docs/evaluation-results/minicpm5-routing-01/reproduce.py state/minicpm5-repeat/run
python docs/evaluation-results/minicpm5-routing-01/audit.py state/minicpm5-repeat
python -m unittest discover -s harness/tests -p test_model_routing.py
```

`reproduce.py` 对已存在输出目录报错；`audit.py` 对已存在 host-run 报错，
防止将续跑或历史复用算成新测量。脚本只用合成输入，不读用户文档或凭证。
`SHA256SUMS.json` 覆盖本目录除自身外的全部归档文件。
