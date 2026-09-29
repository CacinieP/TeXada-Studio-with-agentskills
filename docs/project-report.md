# TeXada Studio with Agent Skills 项目报告

团队：LinguistsWantTech　队长：邓一纯　队员：刘丰华

方向：科研与教育中的 LaTeX 文档质检　更新：2026-09-29

[项目仓库](https://github.com/CacinieP/TeXada-Studio-with-agentskills) · [B站实机演示](https://www.bilibili.com/video/BV16Kan6rEGv/) · [Skills 技术报告](skills-technical-report.md)

原创部分采用 AGPL-3.0-only，第三方资源保留各自许可。

## 要解决的问题

写 LaTeX 时，漏掉一个定界符就可能让整篇文档编译失败；把积分结果写错，却可能得到排版正常的 PDF。TeXada 将公式语法、表格合计、编译结果和源码差异放在同一个工作台，让使用者从问题位置查看候选，核对后采用并导出。

面向教师、科研写作者和文档整理人员，Studio 处理单个 `.tex`。另有 CLI 处理已有的 `layout.json`，适合批量检查节点、生成报告和续跑。当前交付是供可信用户使用的原型。

## 一次完整使用

在 `math-delimiters.tex` 中，分式外层的 `\left(` 缺少闭合符。Studio 定位到第20行，向本地文本模型请求候选；这次候选只在末尾补上 `\right)`。回判通过，文档由编译失败变为成功。使用者在 diff 中确认分子、分母和原文条件未变，点击采用，随后下载 PDF、TeX 和质检报告。

这次运行共1次模型请求、1处编辑。[真实动态录屏](dynamic-demo.md)保存完整操作与等待过程，[逐候选事件](dynamic-demo-trace.json)可核对请求和检查结果。另一个样本 `math-semantics.tex` 将从0到1的 x 积分写成1，仍通过语法检查和编译；正确值为二分之一。数学含义由使用者结合原文判断。

## 实现与关键选择

Studio 的执行顺序是源码提取、规则检查、必要的公式候选生成、回判、前后编译、diff 和人工采用。采用只更新浏览器编辑器，使用者通过导出保留结果。CLI 共用公式检查器和模型提供方，将每个节点的检查与候选写入事件日志。

三个选择决定了这条流程的行为：

- **先区分内容问题与环境故障。** 语法失败可以请求候选；检查器缺依赖、超时或异常时保留原文，先处理环境。
- **能够复算的合计直接计算。** 简单表格使用 Decimal，按输入位数设置精度；格式不支持时列为人工项。重算以数据行正确为前提。
- **每次候选都留记录。** 原检查、请求、被拒绝的候选和失败原因按序保存。CLI 依据输入及执行上下文哈希复用结果，内容或配置变化就重新检查。

公式模型请求默认读取并校验 `doc-formula-verify/SKILL.md`，把完整文件内容加入系统消息，公式数据放在独立的用户消息中。`off` 模式保留基础提示、模型参数、检查器和调用预算，供对照实验使用。Python 负责节点选择、工具执行和最多两次候选尝试；模型负责返回文本候选。六个 Skill 的实际入口见[技术报告](skills-technical-report.md)，整体数据流见[架构](architecture.md)。

Monaco 0.52.2 资源由本站提供。修复候选先进入差异视图；文档切换会清理旧 diff 并拦截过期结果。Studio 为各任务分别保存事件、结果及编译目录，重启后可按任务 ID 读取完成结果；中断任务需要新建。

## 验证结果

| 验证 | 可复现材料 | 入口 |
| --- | --- | --- |
| 确定性检查 | 27例全部符合预期：24个契约例、3个语义边界例 | [逐例结果](evaluation-results/checker-report.md) |
| Studio 样本 | 共13份文档；新增8份覆盖4类语法缺陷、正常对照、语义、抽取与引用边界 | [案例手册](casebook.md)、[清单](../samples/studio-cases.json) |
| 独立编译 | 8份原稿和4份作者参考修订，12次均符合预期：7次生成 PDF，5次预期失败 | [编译记录与复现](evaluation-results/studio-latex/README.md) |
| 工程回归 | Web 55项、Harness 57项、两套评测运行器35项通过；另有 Studio JavaScript 回归 | [验证记录](validation.md) |
| Skill 对照 | 仅检查器、同模型 Skill off / on 三组；提供运行器、逐次候选和复核表 | [配置、结果与复核状态](skills-pilot-analysis.md) |

这些材料对应不同的复现任务：检查案例验证规则行为，原稿与作者参考修订用于比较编译结果，实机记录展示模型候选从生成到采用的完整操作。读者可从一份样本开始，核对源码、候选差异和生成文件；失败的下标修复也保留在[历史记录](evaluation-results/studio-earlier/README.md)中。

## 本地复现

按 [README](../README.md) 创建 Python 3.11+ 虚拟环境，然后在仓库根目录执行：

```bash
python -m pip install -r harness/requirements.txt
python scripts/evaluate_cases.py --outdir state/project-checks-01
PYTHONPATH=harness python -m docforensics run samples \
  --state state/project-report-01 --fixture-repairs samples/fixture_repairs.json
```

第一条运行命令生成27例检查报告；CLI 使用预设候选，首次预期7个 `OK`、1个 `NEEDS_HUMAN`。再次执行相同 CLI 命令，8个匹配节点应为 `SKIP`。报告在 `state/project-report-01/report.md`，事件在同目录的 `state.jsonl`。这些步骤无需模型或 GPU；独立评测使用新的输出目录。

Studio 的安装、Tectonic、Poppler、字体、模型和认证设置见 [README](../README.md)。浏览器操作、样本测试及编译复现集中在[案例手册](casebook.md)。

## 当前范围与下一步

公式提取目前只覆盖同一行的 `$...$`，注释和 verbatim 中的相似文本也可能被误提取；多行公式、`align`、引用和文献键需另行检查。表格只处理简单结构与明确数字格式。产品采用共享令牌、单 worker 和进程内调度；自动 PDF/OCR、整项目上传、多用户隔离与可靠作业队列列入后续开发。

下一步围绕 TeX 上下文提取、更多来源的修复评测和持久任务队列推进，具体任务与验收标准见[路线图](roadmap.md)。

源码、报告和B站演示已提供公开入口。微信公众号征文待作者审核后手动发布；提交材料与后续安排见[提交清单](submission-checklist.md)及[文档导航](index.md)。
