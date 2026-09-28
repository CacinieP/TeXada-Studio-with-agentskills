# 案例手册：成功、停止与人工判断

下列 Studio、CLI fixture 与检查器案例为仓库原创合成样本，随主项目使用 AGPL-3.0-only；研究集合的来源与许可单独记录。案例文件、步骤、预期和证据必须对应；fixture 不是模型输出，语法通过不是数学判真。深入实现见 [Skills 技术报告](skills-technical-report.md)，全部命令从仓库根目录执行。

## 先选要验证的层次

| 入口 | 数量 / 标识 | 用途 | 环境 |
| --- | --- | --- | --- |
| [检查器案例](../samples/evaluation/README.md) | 27 例，F01–F10、T01–T17 | 验证输入契约、拒绝行为、大整数精度和语义边界 | Python + harness 依赖 |
| Studio 文档 | 5 个 `.tex`，下表 S01–S05 | 用户可操作的成功、正常与人工场景 | Web 依赖；编译 / 模型另装 |
| CLI fixture | exam/paper/report，8 节点 | 状态机、报告、真实网格 diff 和续跑 | 无模型、无需 GPU |
| 故障回归 | E01–E09，下表 | 环境恢复、坏回包、哈希续跑、逐候选记录 | 本地测试，无真实模型 |
| [Skills 研究](../samples/research/README.md) | 有来源与哈希的独立 catalog | 三组执行、保留原文对照、人工复核 | dry-run / fixture 可离线；真实模型需显式启用 |

## Studio 演练

按 [README](../README.md) 启动服务，从文件列表选择样本。先“分析”，需要时运行修复，检查 diff 与剩余问题；采用后导出 `.tex` 和报告。“采用”只更新编辑器，关闭页面前应导出。

公式提取使用逐行美元正则，注释或 verbatim 代码中的相似内容也可能被列为候选。当前没有完整 TeX 上下文保护，审阅时要检查改动是否属于真正的数学公式。

| 案例 | 文件 / 输入 | 预期与审阅要点 | 证据 |
| --- | --- | --- | --- |
| S01 可重算的错误合计 | [report-01.tex](../samples/docs/report-01.tex)：45+60，合计115 | 分析定位1处；候选105；只改合计；仍需确认数据行正确 | 早前实机前后编译均通过；新真实检查器回归保持1处修改、零模型调用 |
| S02 公式候选 | [exam-01.tex](../samples/docs/exam-01.tex)：残缺下标等 | 可请求文本候选；`a_1` 能解析不代表原意就是1；候选可能因模型不同而变化 | 早前录屏3处修改、编译失败→通过；历史演示不替代新版对照实验 |
| S03 正常对照 | [clean-control.tex](../samples/docs/clean-control.tex)：合法多项式、合计105 | 已检出问题0、编辑0、原文逐字不变、零模型调用 | `webui/test_samples.py` 真实检查器验证 |
| S04 语义反例 | [semantic-boundary.tex](../samples/docs/semantic-boundary.tex)：`1+1=3` | 语法可解析，编辑0；人工指出等式不成立。当前界面不会自动识别此数学错误 | F08 + Studio 样本回归；展示已知范围，不计为“纠错成功” |
| S05 必须人工 | [manual-review.tex](../samples/docs/manual-review.tex)：百分比混合、会计括号、缺数字合计 | 3处 `NEEDS_HUMAN`，零编辑、原文不变；不猜单位、不把括号负数当正数、不编造缺失合计 | 真实检查器回归；没有运行模型或编译 |

S03–S05 的样本回归验证分析和候选逻辑，未将它们的 TeX 编译或完整浏览器操作写成已通过。S01/S02 的实机证据是历史运行，详情见 [验证记录](validation.md)。服务升级前，当前运行实例也可能尚未包含新文件。

## 一条命令跑确定性案例

```bash
python scripts/evaluate_cases.py --outdir state/evaluation-01
```

查看 `report.md` 中逐例的 expected / actual，再查看 JSON 原始响应。27 个案例分为 24 个 `contract` 和 3 个 `semantic-boundary`；只有分别理解分组，匹配计数才有意义。本轮实跑存档见 [结果](evaluation-results/checker-report.md)。

代表案例：F04 保证 `x+` 不被部分解析为 `x`；F09/F10 拒绝坏 JSON 与非字符串；T11/T12 拒绝短/空末行；T13 拒绝负索引；T14/T15 不误读百分比和会计格式；T16/T17 区分大整数正确合计与少1的错误合计。正常控制与反例都必须保留，不能只展示能修好的输入。

## CLI：从预设候选到可审阅报告

第一次使用新的状态目录：

```bash
PYTHONPATH=harness python -m docforensics run samples \
  --state state/casebook-01 --fixture-repairs samples/fixture_repairs.json
```

预期 `exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。打开 `state/casebook-01/report.md`，应明确标注 `fixture (offline test double)`，表格候选显示 `original_rows` 与 `candidate_rows` 的实际 diff，待人工项显示原因，缺证据不能伪装为有原图。

再次执行相同命令，匹配的 fixture 终态节点生成 `SKIP`，不重复调用提供方。输入、crop 字节、模型参数、Skill 正文、检查器或依赖发生变化会自动使复用失效；旧日志无哈希也会重新检查。暂时性提供方或检查器故障标记 `resumable:false`，恢复后同目录重跑；独立实验另用新目录。

报告按当前 `run_id` 统计。逐次 `CHECK`、`PROVIDER_START` / `PROVIDER_RESULT`、候选接受/拒绝记录保存在 `state.jsonl`，失败候选不会被最后成功项覆盖。报告中复用项标明来源运行，历史调用不计入本轮。CLI 不改写源文件，检查器接受也不表示使用者采用。

## Skills：从执行证据到人工判定

CLI 真实模型默认 `--skill-mode on`，Studio 默认 `SKILL_MODE=on`。宿主读取白名单公式 Skill 的实际正文并注入系统消息，记录 Skill 和提示哈希；off 模式保留基础提示、检查器及重试流程。Fixture 没有真实加载或模型请求，不能通过安排不同候选来证明 Skill 的收益。

使用[研究运行器](../scripts/evaluate_skills.py)比较仅检查器、模型无 Skill、模型有 Skill 三组。先按[研究协议](../samples/research/README.md)执行 dry-run 或 fixture，核对参数与事件，再使用已授权模型运行。原始来源、正确对照与人工注入错误分别标记；参考公式和错误标签不进入模型请求。输出的 `blind-review.csv` 用于独立复核，未复核前语义准确率为空，单行审阅计时不能直接解释为节省人工时间。

## 故障与恢复案例

以下场景通过隔离测试注入，不需要破坏真实环境：

| 标识 | 触发 | 正确行为 | 可运行证据 |
| --- | --- | --- | --- |
| E01 检查器故障 | 缺 ANTLR、超时、崩溃、非 JSON / 状态退出码不匹配 | 公式 `NEEDS_ENV`，不向模型请求；CLI 终态明确环境原因 | `webui/test_app.py`、`harness/tests/test_pipeline.py` |
| E02 候选回判故障 | 第一次候选产生后检查器变不可用 | 保留原文、停止继续模型请求 | 同上，candidate environment / checker failure 测试 |
| E03 无效模型响应 | 空串、None、无效类型 | 不制造修改；超过预算后仍需人工 | `webui/test_app.py` |
| E04 旧报告兼容 | 旧表格事件没有 before/after 网格 | 能读日志，明确缺差异，不编造候选 | `harness/tests/test_pipeline.py` |
| E05 运行器保护 | 子进程超时、目录已存在、无效案例协议 | 非零退出、保留诊断；不覆盖旧证据 | `scripts/test_evaluate_cases.py` |
| E06 输入与上下文变化 | 同 ID 换输入、crop 字节变化、更换模型/Skill/检查器/依赖 | 同目录重新检查；无哈希旧日志不授权跳过 | `harness/tests/test_resume_trace.py` |
| E07 故障恢复与完整事件 | 提供方超时/协议故障、检查器不可用；失败后恢复 | 暂时故障终态不复用；所有失败与成功候选保留 | `harness/tests/test_resume_trace.py` |
| E08 Studio 服务重启 | 内存任务清空，已保存任务完成或中断 | 已完成结果可按 job_id 读取；中断明确报错并要求新建，不自动继续模型请求 | `webui/test_trace.py` |
| E09 Skill 与研究契约 | on/off 请求、目录越界、复核结果与输出哈希不符 | 验证实际消息差异；非法 Skill 与篡改复核记录被拒绝 | `harness/tests/test_skills_runtime.py`、`harness/tests/test_vlm.py`、`scripts/test_evaluate_skills.py` |

```bash
python -m unittest discover -s harness/tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p 'test_evaluate_*.py' -v
python -m unittest discover -s webui -p 'test_*.py' -v
```

## 下一批 case 怎么选

输入变化、同名 crop 与逐候选回放已进入上述回归。下一步应按来源划分开发与独立评测集合，增加自然发生的错误和正常对照，并保留具名复核及分歧。真实 OCR 案例需先确认再分发授权和原始证据，再独立标注含义；复杂跨页表格与图像重识别仍未实现。研究工具与样本可执行，不代表已经证实泛化效果或节省人工时间。

新增案例时保留稳定 ID、来源授权、原始输入、预期及判断理由，记录依赖与脚本摘要。出现错误应先保留失败报告，再修实现；不能为了让测试全绿而修改预期。
