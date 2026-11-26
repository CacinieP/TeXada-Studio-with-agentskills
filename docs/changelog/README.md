# 版本发布与变更日志总览

本目录集中维护 TeXada Studio 的历次发行记录与变更流水账。

- 面向日常使用的功能介绍与安装说明见 **[用户手册（README）](../../README.md)**。
- 按时间倒序排列的完整技术变更流水账见 **[CHANGELOG.md](CHANGELOG.md)**。
- 各版本独立打包说明、校验指引与验收范围见 [`docs/releases/`](../releases/)。

## 正式发行版本矩阵

| 版本 | 发布日期 | 支持平台与构建号 | 核心变更摘要 | 发布说明 |
| --- | --- | --- | --- | --- |
| **v0.1.4**（最新） | 2026-11-26 | macOS arm64（`0.1.4` / build `9`，Apple 公证 DMG）<br>Windows x64（`0.1.4.0` 自包含 ZIP） | 修复孤立 `\]` 遮蔽未闭合命令与混合零宽字符清洗；补齐 MiniCPM 1B 自动选 Skill 编号约束与结构闭合选项；脱敏编译日志宿主路径；升级协商缓存、过期 Diff 自动清理、`⌘/Ctrl+Z` 状态同步与命令面板键盘直达 | [v0.1.4 发布说明](../releases/v0.1.4.md) |
| **v0.1.3** | 2026-11-25 | macOS arm64（`0.1.3` / build `8`）<br>Windows x64（`0.1.3.0`） | 自包含捆绑官方 `llama.cpp` 计算后端并拦截包外动态库泄漏；模型缺失或中断连续两次失败即早停并展示脱敏警告；离线缓存扩展至 30+ 常用宏包；加固 Windows 非 UTF-8 子进程解码 | [v0.1.3 发布说明](../releases/v0.1.3.md) |
| **v0.1.2** | 2026-11-24 | macOS arm64（`0.1.2` / build `7`）<br>Windows x64（`0.1.2.0`） | 原生导出保存对话框、持久化 WebView 偏好、未保存关闭拦截与 macOS 原生菜单撤销/重做；5 套内置模板与离线样本零误报编译；修复清洗诊断分类与模型选择器同步 | [v0.1.2 发布说明](../releases/v0.1.2.md) |
| **v0.1.1** | 2026-11-22 | macOS arm64（`0.1.1` / build `6`）<br>Windows x64（`0.1.1.0` 首发） | 落地三大 AgentSkills 来源保护修复管线（公式结构补全、残缺表格合计行补全、`latex-cleanup` 文档清洗）；新增 Windows x64 全栈自包含桌面包与双平台 CI 矩阵 | [v0.1.1 发布说明](../releases/v0.1.1.md) |
| **v0.1.0** | 2026-11-22 | macOS arm64（`0.1.0` / build `5` 首发） | 内置「本地模型」一键按需下载与托管 MiniCPM-V 4.7（1B / 35B-A3B）；捆绑 `poppler-cpp` 与 `poppler-data` 实现纯离线中文 PDF 预览；支持采纳后撤销/重做、编译报错行跳转与 PDF 拆页续批导入 | [v0.1.0 发布说明](../releases/v0.1.0.md) |

## 内置 AgentSkills 与子模块版本记录

Studio 运行时白名单能力包与独立导入子模块各自维护语义化版本号：

| 模块 / Skill | 当前版本 | 职责说明 | 契约与变更记录 |
| --- | --- | --- | --- |
| `doc-formula-verify` | `1.4.0` | 行内公式、矩阵与 `cases` 语法核验、定界符修复与防篡改回判 | [SKILL.md](../../skills/doc-formula-verify/SKILL.md) · [capability.json](../../skills/doc-formula-verify/capability.json) |
| `doc-table-audit` | `1.0.0` | 简单三线表末行合计确定性重算与残缺合计行补全回判 | [SKILL.md](../../skills/doc-table-audit/SKILL.md) · [capability.json](../../skills/doc-table-audit/capability.json) |
| `latex-cleanup` | `0.2.3` | 零宽格式噪声剥离与非数学命令/正文环境保守闭合 | [SKILL.md](../../skills/latex-cleanup/SKILL.md) · **[独立版本记录（0.0.1–0.2.3）](../../skills/latex-cleanup/CHANGELOG.md)** |
| `doc-ocr-extract` | 独立 CLI | 扫描页/图像行级候选提取与结构化复核信号标注 | [SKILL.md](../../skills/doc-ocr-extract/SKILL.md) · [REVIEW_SIGNALS.md](../../skills/doc-ocr-extract/REVIEW_SIGNALS.md) |
| `doc-layout-parse` / `doc-report` | CLI 契约 | CLI 布局节点输入协议与审计报告导出约定 | [doc-layout-parse](../../skills/doc-layout-parse/SKILL.md) · [doc-report](../../skills/doc-report/SKILL.md) |
| `texada-studio` | 操作契约 | 供外部本地 Agent 通过回环接口驱动工作区的操作约定 | [SKILL.md](../../skills/texada-studio/SKILL.md) · [本地接口说明](../../skills/texada-studio/references/local-api.md) |

> 说明：`skills/latex-cleanup/CHANGELOG.md` 作为导入快照自身的组件记录随包保留在 [`skills/latex-cleanup/`](../../skills/latex-cleanup/) 目录内（详见 [PROVENANCE.md](../../skills/latex-cleanup/PROVENANCE.md)），本页统一汇总其入口。

## 早期预发布与历史归档

以下文档记录正式 `v0.1.0` 定版前的阶段性验收与草案，仅作历史留档，不代表当前发行版边界：

- **[v0.2.0-beta.4 预发布说明](../releases/v0.2.0-beta.4.md)**（2026-11-11）：OCR 审阅行转布局、像素区域绑定与实机冒烟归档（详见 [beta.4 验收记录](../evaluation-results/beta4-acceptance-01/README.md)）。
- **[v0.2.0-beta.2 发布草案](../releases/v0.2.0-beta.2-draft.md)** 与 **[v0.1.0-alpha.1 早期草案](../releases/v0.1.0-alpha.1-draft.md)**：早期开源准备阶段的说明草稿。
- **[历史验证记录](../validation.md)** 与 **[当前验证记录](../current-validation.md)**：各阶段自动化测试规模与实机复核基线。
