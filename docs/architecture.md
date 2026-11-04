# 架构与数据流

TeXada Studio 是在本机浏览器运行的 WebUI：Monaco 编辑器连接本机 FastAPI 服务，服务负责文档、检查、模型请求与编译。它不是桌面原生编辑器，也不把单个 `.tex` 自动扩展成多文件工程。另一个入口是读取已有 `layout.json` 的 CLI；它不解析 PDF，也不提供编辑器。

```text
本地 Studio
  Monaco 编辑 / 明确保存 → DocumentStore（版本检查、历史副本）
  当前源码 → TeX 上下文扫描 → 公式检查 / 简单 tabular 检查
           → 确定性保真语法候选 / 表格 Decimal 重算
           → 必要时请求有界文本模型候选 → 语法与修改范围回判
           → 独立候选、编译结果与 diff → 人工采用或拒绝
           → 采用只更新编辑器 → 再保存 / 编译预览 / 导出

本地图片 / PDF 导入
  来源文件 → 文件与页数检查 → PDF 页面转换（需要时）
           → 配置的本机视觉模型 → 转写候选与来源记录
           → 人工核对 → 新建文档；不覆盖已有原文

CLI
  layout.json → 按节点检查 → 确定性公式候选 / 有界提供方候选
              → state.jsonl → 本轮 report.md
              → 仅输入与执行上下文匹配的终态可续跑复用
```

## 公式与表格宿主

[TeX 扫描器](../harness/docforensics/tex_context.py)保留精确来源范围，识别 `$...$`、`$$...$$`、`\(...\)`、`\[...\]` 和常见数学环境。它跳过注释、常见原样环境与常规命令定义；复杂对齐、未知宏、改变类别码和不可靠的边界保留人工检查。它不做完整 TeX 宏展开。CLI 布局树已经提供公式文本，不复用 Studio 的源码抽取步骤。

公式文本交给 [SymPy 检查器](../skills/doc-formula-verify/scripts/verify.py)检查。`RETRY` 才能进入修复；`NEEDS_ENV` 和不合法的输入协议不触发模型猜测。Studio 与 CLI 共用 [formula_repair.py](../harness/docforensics/formula_repair.py)：先闭合可确定的尾部 `}` 或已支持的单个 `\left/\right` 配对，保留已有内容，再用同一检查器验证。缺少操作数、歧义下标及已知解析器覆盖边界保留原文。

模型候选除语法回判外，还需通过修改范围校验。当前规则只授权不变内容或已知确定性规则的同一个结果，不允许数字、变量、运算符、项或既有分组被改写。拒绝反馈随下一次请求提交，最多两次模型请求；重复候选和环境故障会停止继续尝试。这是保守的来源保真约束，不是数学等价证明，详见[公式修复质量记录](formula-repair-quality.md)。

表格路径分开实现：Studio 检查受支持的简单 `tabular`，用 Decimal 为末行合计生成候选；CLI 检查布局树网格和显式形状、合计约束，真实模型提供方不实现表格重提取。两者都不从单位或表达式中猜取数字；表格候选假设数据行正确，仍需与来源核对。

## 模型、OCR 与 Skill

本地启动器只接受 HTTP 回环模型地址，复用已有服务或启动本机已准备的权重。它不下载模型、不读取或发送云 API Key，也不自动回退到云端。图片/PDF 导入调用本地视觉能力，与公式修复的文本请求分开；一个端点列出模型名不代表已经验证其视觉能力。安装、连接和离线资源准备见[本地使用指南](local-studio.md)。

CLI 的通用 OpenAI-compatible 提供方和显式选择的[旧云入口](../deploy/README.md#旧云-api-兼容入口)可使用授权的云服务。它们不继承本地启动器的回环限制，不能把对应记录当作本地推理结果。

默认固定流程在 `skill_mode=on` 时，通过[白名单加载器](../harness/docforensics/skills_runtime.py)验证并读取公式 `SKILL.md`，将正文加入模型 system 消息；公式和有界反馈放在独立的 user JSON 中。`off` 省去 Skill 正文，保留基础参数。fixture 是预设候选，确定性公式与表格工具不调用模型；它们的成功不能记为模型推理成功。

[受限规划](studio-constrained-planner.md)和[Skill 选择](studio-skill-selection.md)是两个独立、默认关闭的实验开关。选择先读取 capability 元信息，验证种类、版本和当前状态后才加载正文；宿主仍控制动作、参数、预算、检查和候选构造。服务间使用普通 HTTP；这些流程不依赖 MCP，也不允许模型任意执行 Skill 文件。可选[Math Agent 交接](studio-formula-handoff.md)需要另外运行对应服务，普通本地工作流不依赖它。

## 存储、版本与审阅

本地启动器默认使用系统用户数据目录，或由 `--state-dir` 指定。直接启动 WebUI 时，未配置 `TEXADA_STUDIO_STATE_DIR` 才回退到仓库 `state/studio/`。数据位置与恢复方法见[本地数据与恢复](local-studio.md#本地数据与恢复)。

- `documents/` 保存用户文档，`.history/` 与 `.trash/` 保留历史或删除副本。保存、改名和删除检查来源版本；同名导入和其他窗口的修改不会被静默覆盖。仓库样本保留为素材，保存时建立用户副本。
- `jobs/<id>/` 保存任务、事件、候选及采用/拒绝决定。界面历史能重开完成任务；采用时仍需匹配来源内容。中断任务不伪装成成功，执行需要重新发起。
- `imports/<id>/` 保存 OCR 来源与逐页候选；模型设置仅保存本机地址与模型名。`session.json` 含当前私密访问入口，不是可公开分发的报告。
- 编译在独立产物目录运行 Tectonic `--untrusted --only-cached`，Poppler 按需生成页面图。每次预览拥有独立 URL，避免旧页面缓存混入新 PDF。编辑内容变化后，界面要求重新编译当前 PDF。

CLI 事件逐条追加到 `state.jsonl`，本轮 `report.md` 只统计对应 `run_id`。复用绑定文档、节点 ID、节点/crop 内容以及程序、修复策略、检查器、依赖、提供方和 Skill 的哈希。暂时故障不可永久复用，恢复后会重查；同一状态目录仅供一个写入进程。具体协议见[CLI 手册](../harness/README.md#续跑)。

## 运行与验证范围

当前面向本地单用户，使用一个 Uvicorn worker。API 使用显式访问 token；Monaco 静态资源使用限定路径的签名 Cookie。默认本地启动器生成会话 token，并关闭访问日志，私密 URL 不打印。它不提供多用户隔离或共享文档协作；对外部署须遵循[安全说明](../SECURITY.md)与[部署手册](../deploy/README.md)。

Monaco 0.52.2 随源码提供并保留 MIT 许可。模型、Python 依赖、字体和 TeX 缓存需要提前准备；正常本地文档处理不会隐式下载 TeX 资源。旧仪表盘 `/` 与 Studio `/studio` 是不同界面，前者仍有 KaTeX CDN 依赖。

截至 `ceae9a7` 的本轮回归记录为 420 项 Python 测试通过，另有前端 JavaScript 检查、27 个检查器契约案例及 20 个公式保真合成案例。测试数量是回归覆盖记录，不是 OCR、数学或跨平台准确率。小型本机模型对照、局限与复现入口见[公式修复质量记录](formula-repair-quality.md)；较早的[本地验收](local-studio-acceptance.md)和[历史验证](validation.md)保留各自日期与环境。
