# doc-forensics · 选题定稿书

定稿日期：2026-09-28 · 提交截止：2026-09-29 · 决策状态：**已定稿（方案 A）**

## 1. 一句话

把「解析 → 逐项质检 → 不合格自动修复 → 修不好退回重生成 → 断点续跑」封成 Skill 套件，
对扫描件/试卷/论文交付**带置信度与可追溯证据**的结构化文档。

## 2. 问题定义

OCR / 视觉解析管线在扫描件上必然出错，且错误会**沿流水线放大**：版面顺序错 → 表格断行错 → 公式识别错 →
下游数据全部不可信。现有工具（含 Anthropic pdf skill、NVIDIA 官方目录）只做「提取」，**不做版面结构还原与质检**。
谁用得最痛：教育（试卷数字化）、法务财会（扫描凭证）、学术（论文库结构化）。

## 3. 选题依据（四条，均有证据）

1. **资产复用 5/5**：PaddleOCR-VL 端侧部署经验、HunyuanOCR/Chandra 调研、OmniDocBench 认知、
   TeXWizard（文心多模态赛作品）+ CROHME LoRA 微调经验直接迁移公式验证；`TeXada-the-Math-Agent` 同域项目在侧。
2. **闭环工程模式**：解析管线的错误必须被检出、修复、留痕——「每环节先过检查 → 不合格自动修复 →
   修不好退回重新生成 → 中断可续跑」，并叠加「证据链」：每处修改附原始截图，可审计、可回溯。
3. **官方目录空白**：NVIDIA/skills 视觉类只有 VSS 系列（视频流/安防），静态文档/版面/公式/表格方向空缺；
   Anthropic 四件套的 pdf skill 只做提取与填表。训练营第三课（本地视觉 Agent）正对口。
4. **Spark 硬件叙事**：多模型并行仲裁是 24GB 消费卡做不到的，详见 architecture.md 内存预算。

评分记录：既有资产 5 / 赛题契合 5 / Spark 适配 5 / 可演示性 5 = **20/20**（方案 B 18、方案 C 14）。
方案 C（spark-ops）不废弃，降级为本方案内部依赖。

## 4. 方案总览：四个协作 Skill + 一个内部依赖

| Skill | 职责 | 确定性来源 |
| --- | --- | --- |
| `doc-layout-parse` | 版面与阅读顺序还原，输出带 bbox 的结构树 | 本地 VLM（8B 级常驻） |
| `doc-table-audit` | 单元格合并/跨页续表校验；行列数与合计值交叉验算 | `scripts/audit_table.py`（纯计算） |
| `doc-formula-verify` | 公式 SymPy 解析回判；不合法触发带 20% padding 的高分辨率重识别 | `scripts/verify.py` + VLM |
| `doc-report` | 质检报告 + diff 视图，每处修改附原始 crop 证据 | 模板渲染 |
| `spark-ops`（内部依赖） | 内存预算规划、vLLM 启动参数、OOM 诊断与降级、llama-swap 装卸 | 系统读取脚本 |
| `latex-cleanup`（内部依赖） | 修复结果的编译回环：数学审计 + 实际编译验证 + 保守空白清洗 | vendor 自 CacinieP/latex-cleanup v0.2.3（scripts/tests） |

协作协议：`doc-layout-parse` 产出结构树 → 质检 Skill 各自认领节点类型（`formula` / `table`）→
产出 `OK / RETRY / NEEDS_HUMAN` 三态 → 全部决策追加写入 `state.jsonl`（断点续跑）→ `doc-report` 汇总。
公式修复走「SymPy 回判 → 重识别 → `latex-cleanup` 数学审计与编译回环」三级验证（吸收方案 B 的编译回环思路）。
任何节点失败**不得阻塞流水线**。

## 5. 为什么必须在 DGX Spark 上（评审必问，答案前置）

同时常驻：qwen3.8-27B（**最新代原生多模态**，解析/重识别/仲裁三合一，Q4_K_M ~16GB）+ embedding/reranker 0.6B×2，
合计 < 20GB 权重 —— 剩下 ~100GB 统一内存全部作为 **KV cache 并发预算，支持十几路文档流并行质检**。
24GB 消费卡装得下模型却装不下并发，批量文档场景（试卷库/论文库）吞吐差距是数量级的。
仲裁质量靠 **SymPy/精确验算等确定性工具与视觉模型互为校验**（实机已验证拦截 VLM 幻觉），而非堆更大的模型——
所以单流 decode 慢不是短板，并发吞吐与仲裁质量才是叙事。
P1 可选追加 30B 文本 MoE 作仲裁二意见（合计 ~37GB，仍在预算内）。

## 6. 24h 冲刺切片（提交截止 09-29）

- **P0（必交，缺一不可）**
  - `doc-formula-verify` 完整闭环（SymPy 回判 + RETRY 高分辨率重识别 + state.jsonl）
  - `doc-table-audit` 完整闭环（行列数 + 合计值交叉验算）
  - `doc-layout-parse` 薄封装：复用现有 PaddleOCR-VL / HunyuanOCR 部署，只要求产出结构树 JSON
  - `doc-report` 最小可用：Markdown 报告 + diff + 证据截图路径
  - 一键跑通样例包（3 份样本：论文页 / 试卷页 / 含跨页断表的报表）
- **P1（加分）**：`BENCHMARK.md`（有/无 Skill 对照）；`spark-ops` 接入 llama-swap；skill-tools 自检全绿
- **P2（stretch，做不完不羞耻）**：跨页续表自动拼接；推测解码调优

切片原则：P0 全部是「确定性脚本 + 已有模型资产」，无新模型训练；评审最看重的失败处理与断点续跑放在 P0。

## 7. 评测计划

- 每个 Skill 附 `evals/evals.json`，核心是**有 / 无 Skill 对照**：同批样本，度量修复成功率、误改率、
  人工介入率；产出 NVIDIA 验证体系风格的 `BENCHMARK.md`。
- 样本集：OmniDocBench 子集 + 自建错误注入集（公式错 10 例 / 表格错 5 例），标注 ground truth。

## 8. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 算力云节点未获批 / 时间不够自测 Spark | x86 + RTX 开发，容器保 ARM64（NGC 镜像）；脚本层无 GPU 依赖，可先过逻辑 |
| VLM 输出不稳定 | 确定性操作全走 scripts/，VLM 只做重识别；每公式最多 3 次调用 |
| 现场断网 | 全本地断网跑通 + 无剪辑录屏备份 |
| parse_latex 依赖 antlr | requirements 固化；verify.py 对缺依赖显式报 NEEDS_ENV 而非崩溃 |
| 24h 内做不完全部 Skill | 按 P0/P1/P2 切片，宁可少一个 Skill 也不交断链路 |

## 9. 提交物清单

- [ ] 四个 Skill 目录（SKILL.md + references/ + scripts/ + evals/）
- [ ] 一键复现包（README + 部署脚本 + 样本）
- [ ] `BENCHMARK.md`（P1）
- [ ] 3 分钟无剪辑实机演示视频（含一次故意注入的错误与自动修复）
- [ ] 5 分钟路演讲稿（决赛用，10-15 苏州）
