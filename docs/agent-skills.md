# 当前 AgentSkills 使用指南

Studio 的编辑器是本地 Web UI：Python/FastAPI 提供服务，浏览器中的 Monaco 编辑源码。
文档、OCR 来源与运行记录保存在所选本地数据目录；模型可以通过本机回环服务提供候选。

## 按工作选择 Skill

| 工作 | 入口 | 实际范围 |
| --- | --- | --- |
| 操作 Studio 编辑器 | [texada-studio](../skills/texada-studio/SKILL.md) | 打开与保存、检查、候选审阅、OCR 导入、版本冲突和 PDF 导出 |
| 检查或修复公式语法 | [doc-formula-verify](../skills/doc-formula-verify/SKILL.md) | 公式文本、严格解析、有限候选与人工语义核对 |
| 检查简单表格合计 | [doc-table-audit](../skills/doc-table-audit/SKILL.md) | CLI 网格约束；Studio 对受支持 `tabular` 的确定性重算 |
| 选择文档输入路线 | [doc-layout-parse](../skills/doc-layout-parse/SKILL.md) | Studio 图片/PDF 转写候选，或 CLI 已有 `layout.json`；两种输出不能直接互换 |
| 交付检查证据 | [doc-report](../skills/doc-report/SKILL.md) | 本轮事件、候选与拒绝原因、复用来源及未验证项 |
| 直接清洗磁盘源码 | [latex-cleanup](../skills/latex-cleanup/SKILL.md) | 保留内容含义的 TeX/Markdown 清洗、编译与有来源的 OCR 校订 |

外部 coding agent 可以直接读取目标 Skill，例如：

> 请使用 `skills/texada-studio/SKILL.md` 检查本地 Studio 的当前文档，保留未保存内容，交付问题和可审阅候选。

仓库内的新 Skill 不会自动安装到所有 Agent。支持 Skill 安装的宿主可安装相应目录；
保留其引用的仓库相对路径，或让宿主直接读取完整 checkout。`texada-studio` 的 API 参考按需读取，
普通编辑不需要预先加载全部参考文件。

## Studio 运行时怎样使用 Skill

固定公式修复宿主在 `skill_mode=on` 时加载 `doc-formula-verify/SKILL.md`，
校验白名单和路径，记录正文与请求哈希；`off` 用于保持其他参数相同的对照。
表格候选由确定性规则生成。

公式修复也优先使用本地确定性语法规则。模型候选须同时通过语法与来源修改范围检查；
重试反馈保留原公式、上一候选和拒绝类别。当前保真范围及对照结果见[公式修复质量记录](formula-repair-quality.md)。

独立的“自动选择检查 Skill”实验默认关闭。开启后，宿主先提供公式/表格两种 capability 元数据，
验证适用性、版本和当前 revision，再加载正文；模型选择不赋予任意脚本执行能力。
新加入的 `texada-studio` 是外部 Agent 的操作说明，未加入此运行时工具白名单。
`doc-layout-parse` 和 `doc-report` 也分别是输入准备与证据交付约定，不会因此被自动注入 OCR 或报告请求。

两份运行时 Skill 保留与 `capability.json` 一致的顶层 `version: 1.0.0`。
本次修订更正流程说明，没有改变 capability schema；正文 SHA256 会随修改变化，旧执行上下文不能据此冒充新运行。
研究比较须保存实际正文、模型、输入和请求记录，不能从文字修订直接推断准确率提升。

## 验证与维护

修改前先核对实现和可复现请求，尤其是以下边界：

- 只检查不触发模型或写回；未保存编辑与磁盘版本分别保留。
- 注释、原样环境和宏定义中的公式示例不会被当成普通可修正文。
- 模型故障、检查环境故障、人工拒绝和保存冲突保留来源与失败状态。
- OCR 的已处理页、结构化节点、语法正确、数学正确分别报告。
- 候选采用、保存和重新编译导出是独立动作。

按 [本地指南的回归测试](local-studio.md#回归测试) 运行相应测试；公式/表格正文还应通过实际
`load_skill`、`load_selected_skill` 加载与版本校验。通用 Skill 校验器可能不接受宿主要求的顶层
`version`，不要为迁就它删掉运行时契约。真实模型行为需另做受控验证，fixture 仅验证流程。

当前功能以本页、各 Skill 和 [本地指南](local-studio.md) 为准。
[技术报告](skills-technical-report.md) 与历史实验保留各自日期的设计和结果。
