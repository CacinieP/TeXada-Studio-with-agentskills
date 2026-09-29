# 案例手册

所有命令从仓库根目录执行，使用 Python 3.11+ 虚拟环境。安装与 Studio 启动见 [README](../README.md)，实现契约见 [Skills 技术报告](skills-technical-report.md)。

## 选择入口

| 要验证什么 | 输入 | 入口 |
| --- | --- | --- |
| 检查器的已定义行为 | 27例，F01–F10、T01–T17 | `scripts/evaluate_cases.py` |
| 编辑、候选和人工采用 | `samples/docs/` 中13份 `.tex` | Studio 文件列表 |
| 节点状态、报告和续跑 | exam/paper/report 的8个布局节点 | `python -m docforensics run` |
| Skill 指令对照 | 研究 catalog | `scripts/evaluate_skills.py` |
| 故障和恢复 | 隔离测试 | 本页末尾测试命令 |

Studio、CLI fixture 和27例检查输入为原创合成样本，使用 AGPL-3.0-only。开放教材研究集合的来源和许可[单独记录](../samples/research/ACTIVE_CALCULUS_NOTICE.md)。预设候选用于验证程序，真实模型输出另存实机记录。

## 先运行检查器与 CLI

```bash
python -m pip install -r harness/requirements.txt
python scripts/evaluate_cases.py --outdir state/evaluation-01
PYTHONPATH=harness python -m docforensics run samples \
  --state state/casebook-01 --fixture-repairs samples/fixture_repairs.json
```

检查报告在 `state/evaluation-01/report.md`：27例应全部匹配预期，分为24个契约例与3个语义边界例。F04 检查 `x+` 的完整解析，F09/F10 覆盖非法 JSON 和类型，T11–T13 覆盖表格形状与索引，T14/T15 覆盖复杂数字格式，T16/T17 区分大整数正确合计和少1。[已保存结果](evaluation-results/checker-report.md)

CLI 首次预期为 `exam-01 OK=3`、`paper-01 OK=2 NEEDS_HUMAN=1`、`report-01 OK=2`。打开 `state/casebook-01/report.md`，检查 fixture 标识、表格前后网格 diff 和人工项原因。事件位于同目录的 `state.jsonl`，原文件保持不变。

再次执行相同 CLI 命令，8个匹配节点应生成 `SKIP`。输入、已有 crop 字节、执行程序、模型参数、Skill 或依赖变化后重新检查；暂时故障恢复后也会重试。每轮报告单独计数，复用项标明来源。CLI 读取 `layout.json`，Studio 的 `.tex` 文件请使用下一节入口。

## Studio：从分析到导出

从文件列表选择样本，点击分析并查看定位；需要修复时生成候选，检查 diff、编译结果和剩余问题。点击采用只更新编辑器，关闭页面前导出 `.tex` 和报告。

当前公式提取限于同一行的 `$...$`；注释或 verbatim 中的美元内容可能被误提取，多行数学环境及引用需另查。阅读结果时同时看抽取数和问题数。语法与编译结果用于判断结构，数学含义结合原文人工核对。

| ID | 文件与输入 | 预期及审阅重点 |
| --- | --- | --- |
| S01 | [report-01.tex](../samples/docs/report-01.tex)：45+60，合计115 | 1处规则候选105，0次模型请求；核对数据行 |
| S02 | [exam-01.tex](../samples/docs/exam-01.tex)：缺失下标等 | 查看候选、拒绝原因及编译结果；缺失下标的原意需要上下文 |
| S03 | [clean-control.tex](../samples/docs/clean-control.tex)：合法公式与合计 | 0问题、0编辑、0请求，原文保留 |
| S04 | [semantic-boundary.tex](../samples/docs/semantic-boundary.tex)：`1+1=3` | 语法接受，0编辑；等式错误由人工指出 |
| S05 | [manual-review.tex](../samples/docs/manual-review.tex)：百分比、会计括号、无数字合计 | 3个人工项，0编辑，原文保留 |
| S06 | [math-delimiters.tex](../samples/docs/math-delimiters.tex)：缺少配对定界符 | 抽取2式，1个 `RETRY`；参考候选只补 `\right)` |
| S07 | [math-fractions.tex](../samples/docs/math-fractions.tex)：分母缺闭合花括号 | 抽取2式，1个 `RETRY`；核对分母内容未改 |
| S08 | [math-indices.tex](../samples/docs/math-indices.tex)：下标组缺闭合花括号 | 抽取2式，1个 `RETRY`；参考候选恢复分组 |
| S09 | [math-integrals.tex](../samples/docs/math-integrals.tex)：积分上限缺闭合花括号 | 抽取2式，1个 `RETRY`；核对上下限及积分原意 |
| S10 | [math-clean.tex](../samples/docs/math-clean.tex)：分式、积分、极限与递推 | 抽取4式均 `OK`，0编辑、0请求 |
| S11 | [math-semantics.tex](../samples/docs/math-semantics.tex)：从0到1的 x 积分写成1 | 抽取3式均 `OK`，可编译；正确积分值为1/2 |
| S12 | [math-align-boundary.tex](../samples/docs/math-align-boundary.tex)：`align*` 内定界符错误 | 抽取0式、0问题，编译失败；抽取范围外案例 |
| S13 | [math-references.tex](../samples/docs/math-references.tex)：缺失标签和文献键 | 抽取0式、0问题，编译退出0；日志有未定义引用提示 |

[机器可读清单](../samples/studio-cases.json)记录 S06–S13 的原文、抽取结果和作者参考修订。新增8份共抽取15个公式、报告4个语法问题。参考修订用于离线回判和未改区域测试。

最新真实演示选择 S06：1次模型请求只补 `\right)`，形成1处编辑，编译失败转通过；使用者采用并下载 PDF、TeX 和报告。[动态演示及事件](dynamic-demo.md)另有正常讲义、积分反例和代表样本操作。S02 的一次下标候选失败保存在[历史记录](evaluation-results/studio-earlier/README.md)。

## 验证 Studio 样本与编译

```bash
python -m pip install -r webui/requirements-test.txt
python -m unittest discover -s webui -p 'test_samples.py' -v
```

样本测试使用真实检查器、预设提供方，模型请求数为0，也不调用编译器。检查内容包括清单与文件一致、实际抽取与状态、声明区间外文本不变，以及无候选时的调用预算和原文保留。

编译单独复现，准备 Tectonic 后按[编译记录与步骤](evaluation-results/studio-latex/README.md)执行。该入口验证8份原稿与4份作者参考修订，逐份保存日志、PDF 和报告。已保存的12次结果均符合预期：7次生成 PDF，5次预期失败。S11 的错误等式仍可生成 PDF，S13 则需要进一步阅读引用警告。

## 验证 Skill 对照与人工复核

真实公式请求默认加载 `doc-formula-verify/SKILL.md`，将其加入系统消息；off 保留基础提示、检查器及重试流程。先运行三组流程的离线验证：

```bash
python scripts/evaluate_skills.py run \
  --cases samples/research/smoke_cases.json \
  --outdir work/casebook-skills-01 --mode fixture \
  --fixture-repairs samples/research/smoke_repairs.json
```

查看三组结果、逐次候选和 `blind-review.csv`。真实模型实验需要显式使用 `--mode model`；命令、固定参数与现有结果见[先导实验分析](skills-pilot-analysis.md)，人工复核字段见[研究协议](../samples/research/README.md)。当前先导实验的语义复核尚未完成。

## 故障与恢复

以下场景通过测试注入，无需破坏真实环境或请求模型。

| 标识 | 触发与预期 | 测试位置 |
| --- | --- | --- |
| E01 | 检查器缺依赖、超时、崩溃或协议异常：报告环境故障并停止模型请求 | `webui/test_app.py`、`harness/tests/test_pipeline.py` |
| E02 | 候选回判时检查器故障：保留原文并停止后续请求 | 同上 |
| E03 | 空候选、None 或无效类型：不产生修改，按预算结束 | `webui/test_app.py` |
| E04 | 旧表格事件缺少前后网格：仍可读取，标记差异缺失 | `harness/tests/test_pipeline.py` |
| E05 | 子进程超时、输出目录已存在、案例协议无效：返回诊断且保留旧证据 | `scripts/test_evaluate_cases.py` |
| E06 | 同 ID 的输入、crop 或执行上下文变化：重新检查 | `harness/tests/test_resume_trace.py` |
| E07 | 提供方或检查器故障后恢复：重试暂时故障，保留全部候选事件 | `harness/tests/test_resume_trace.py` |
| E08 | Studio 重启：按 ID 读取完成结果，中断任务需新建 | `webui/test_trace.py` |
| E09 | Skill on/off、路径越界、复核哈希不匹配：核对请求差异并拒绝无效输入 | `harness/tests/test_skills_runtime.py`、`harness/tests/test_vlm.py`、`scripts/test_evaluate_skills.py` |

```bash
python -m unittest discover -s harness/tests -p 'test_*.py' -v
python -m unittest discover -s scripts -p 'test_evaluate_*.py' -v
python -m unittest discover -s webui -p 'test_*.py' -v
```

新增案例请保留稳定 ID、来源与许可、原始输入、预期和判断理由，并同时加入正常对照。发现缺陷先保存失败输入和报告，再修实现。下一批优先增加自然发生的公式错误与 TeX 上下文提取案例，按来源划分开发集和评测集，保留人工复核及分歧。
