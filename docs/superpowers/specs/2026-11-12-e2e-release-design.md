# TeXada Studio 端到端可用性迭代与公证发行 — 设计文档

日期：2026-11-12（报告日期）；状态：**已批准（2026-11-12，用户确认：版本号 v0.1.0，其余按本文件）**
作者工作方式：本文件是「全量设计」；批准后按 writing-plans 产出实施计划。

## 1. 意图与为什么

把 TeXada Studio 从「回归全绿的开发候选」推进到「端到端真实可用」，并产出**公证安装包**。
用户对「真实可用」的定义（2026-11-12 口头确认）：**端到端流程跑通**——不是收口验收清单，而是从打开真实文档到落稿、重启恢复的完整链路以真实模型、真实编译跑通并留证。

## 2. 目标 / 非目标 / 反目标

**目标**
- G1：E2E-1..5 五条场景全部通过并留证 `docs/evaluation-results/e2e-release-01/`。
- G2：端到端暴露的拦路缺陷以「最小修复 + 测试 + 全量回归」逐个落成小 PR。
- G3：两个在审分支合入：PR #52（#50 SIGTERM 退出）、PR #53（#23 模型契约）。
- G4：版本切面（CHANGELOG 定稿、版本号、tag），经 GitHub Actions `bundle-build` 产出公证 DMG + checksum。
- G5：用户 GUI 终审通过后发布 GitHub Release（附 DMG、checksum）。

**非目标**
- 不做 `.pkg` 安装器（无 Developer ID Installer 证书；DMG 为交付形态）。
- 不做新功能、不做模型质量调优、不强求 #23/#24 的非阻塞打磨项。
- 不支持 macOS ARM 以外的发布平台。

**反目标（即使技术上可行也不做）**
- 不留无证据的「可用」结论：每个验收项都要有可复核记录。
- 不为让 E2E 变绿而放宽或绕过既有测试。
- 不做需要用户反复到场的重复验收轮（自动化优先，用户只做一次终审）。
- 不擅自触发 CI、不在未经批准下合并 PR（沿用既有审批纪律）。

## 3. 约束

- 仓库：AGPL-3.0-only，Python 3.13 venv（`.venv`），macOS ARM。
- E2E-2/3 依赖本机 Ollama（当前在运行，含 `openbmb/minicpm-v4.7`、`minicpm-ocr`）；E2E-1 依赖本机 LaTeX 工具链（CI 已验过本地编译）。
- 发行出包走 GitHub Actions `bundle-build`：secrets 已齐（`MACOS_CERTIFICATE*` + `ASC_KEY_ID/ASC_ISSUER_ID/ASC_KEY_P8`），管线已含签名→公证→装订→DMG→spctl 校验；**触发 workflow 需要用户逐次明确批准**。本机无 notarytool 凭据，不做本地公证。
- 合并 PR 需 CI 全绿 + 用户批准；`fix/sigterm-exit`、`fix/studio-model-routing` 已获推送批准（2026-11-12「继续」）并开出 PR #52/#53。
- CI bundle-build 全程约 45 分钟。

## 4. 方案取舍（对话中已定）

**验收执行方式**
- ✅ **A. 自动化 E2E 为主 + 用户 GUI 终审**（选定）：可重复、可留证、不占用户时间；终审只做一次。
- ✗ B. 纯手工 GUI 验收：每轮需要用户在场，慢、不可重复。
- ✗ C. 只收口现有 issue 清单：没有端到端跑通证据，与用户定义不符。

**出包路线**
- ✅ **GitHub Actions `bundle-build`**（选定）：secrets/管线齐备，产物已含 spctl 校验与 checksum。
- ✗ 本机出包：本机无 notarytool 凭据，需用户另授密钥，且与 CI 产物重复。

**安装包形态**
- ✅ 公证 DMG（拖拽到 Applications），沿用现有管线与现有 Developer ID Application 证书。
- ✗ `.pkg`：需要 Developer ID Installer 证书（用户当前没有），无必要。

## 5. 已定的「怎么做」

### 5.1 验收线（E2E-1..5，与用户确认过的表一致）

| # | 场景 | 通过标准 |
|---|---|---|
| E2E-1 | 打开真实 `.tex` → 编译出 PDF | 真实 LaTeX 编译成功，预览出稿 |
| E2E-2 | 公式修复（真实 MiniCPM） | 真实模型改稿 + checker 复核落稿 |
| E2E-3 | OCR 行→布局（真实 minicpm-ocr） | 真实推理出候选行并落布局 |
| E2E-4 | 状态持久化 | 保存 → 重启恢复不丢 |
| E2E-5 | 打包真机冒烟（.app） | 启动、API 存活、SIGTERM 有界退出 |

### 5.2 E2E 驱动形态

新增 `scripts/e2e_release_check.py`（可重复、无人值守）：
1. **预检**：venv、LaTeX 工具链、Ollama 端点与两个模型就绪；预检失败**立即失败**（发布运行不许跳过；`--skip-model` 仅供日常开发）。
2. **E2E-1..4**：起真实 uvicorn 后端（`webui/app.py` 本地模式），走 HTTP 接口驱动完整链路，使用 `samples/` 既有样本与 evaluation 数据集中既有公式修复用例（不新造语料）。
3. **E2E-5**：对构建产物 `.app` 做冒烟——启动、`/api` 存活、SIGTERM 限期退出（即 #50 修复的真实验证）。
4. **留证**：JSON 结果 + Markdown 摘要写入 `docs/evaluation-results/e2e-release-01/`，含每场景耗时、模型名、退出码。

### 5.3 迭代纪律

- 每个拦路缺陷：先复现 → 最小修复 → 测试（能 TDD 则 TDD）→ 全量回归（harness/webui/scripts/desktop unittest + 四套 JS 套件）→ 小 PR。
- 修复若牵涉大改（超出最小修复范围），**停下来报告**，不擅自扩scope。

### 5.4 发行顺序

1. 合入 PR #52、#53（CI 全绿 + 用户批准）。
2. 开发并跑通 E2E-1..5，修拦路缺陷，全量回归绿。
3. 用户 GUI 终审（阻塞项挡住发行；纯外观问题可延后到下一 patch）。
4. 版本切面：CHANGELOG 定稿、版本号、tag。**版本号 = v0.1.0**（用户定，2026-11-12；CHANGELOG 既有 0.2.0-beta.x 历史条目保留原样，发行 tag/Release/包版本统一用 v0.1.0）。
5. **请示用户批准后**触发 `bundle-build`，下载产物做 Gatekeeper/spctl 复核 + checksum 比对。
6. 建 GitHub Release（附 DMG + checksum.txt），收口 issue 与 CHANGELOG 记录。

## 6. 留给实施者的部分

- E2E 各场景的具体 fixture 选择（`samples/` 与 evaluation 数据集内挑选）、超时/重试参数、证据 JSON 的字段细节。
- GUI 终审清单的具体条目（依据 E2E-1..5 展开为可勾选列表）。
- 预检失败信息的措辞与修复提示。

## 7. 自查（builder check，无子代理工具，自查替代）

以「拿到本文件即可排实施计划的新工程师」视角提问，只列猜错会有后果的：
1. **发行版本号？**——用户已定 **v0.1.0**（2026-11-12）。
2. **PR #52/#53 合并时机？**——已在 §3/§5.4 回答：CI 全绿 + 用户批准。
3. **GUI 终审发现的问题是否挡发行？**——已在 §5.4 回答：阻塞项挡住，外观问题可延后。
4. **发布渠道？**——GitHub Release（公开仓库）；若用户要其他渠道属其拍板项，默认 GitHub。

其余（fixture、超时、证据格式、清单措辞）为 §6 已显式留给实施者的部分，可自决。

## 8. 裁决补记（执行期，2026-11-12）

E2E-2 真跑暴露一个设计级事实：`assess_candidate` 范围门卫原本只放行「原文不动」或
「deterministic 补括号 patch」，系统提示词与 doc-formula-verify SKILL 又明令「never
invent a missing operand or index」——按原设计，模型候选**永远无法落稿**，与本文
「真实 MiniCPM 落稿」的验收语义冲突。三选项呈报后**用户裁决 B**：扩权范围门卫。

**裁决 B 内容**（已实施，详见 CHANGELOG Unreleased/Changed）：

- `assess_candidate` 新增唯一发明通道：`single_token_gap_fill` / `fill_empty_script_token`
  ——仅空 script 槽（`_`/`^` 后无任何可作参数的 token）允许填一个 ≤8 字母数字 token
  （可 `{...}` 包裹）；行尾空槽仍被 `repair_blocker=missing_script_operand` 拦截；
  尾操作数、缺 `\frac` 参数、歧义组等一律保持「不臆造」。
- 修复系统提示词与 MiniCPM few-shot 教该填充（样例 `x^+1`→`x^2+1`，刻意与 E2E fixture
  异形以证明泛化）；doc-formula-verify SKILL v1.2.0（capability.json 同步）教义对齐。
- 落稿编辑仍受人工采纳门约束（`checker_accepted_not_user_adopted`）——「防篡改」语义不变。

真跑证据（2026-11-12）：真 MiniCPM 对 `a_+b` 泛化产出 `a_1+b`（未抄样例），checker 复核 ✓，
门卫 `single_token_gap_fill` 放行，落稿 1 处，`model_calls=1`，E2E-2 通过。
