# 调研纪要（2026-09-28 收口）

> 汇总自 Notion「NVIDIA DGX Spark 参赛知识库」05/06/07 页、第二届复盘页与外部核验。
> 结论：选题定稿方案 A `TeXada Agent Skills`。本页只留决策相关证据，完整版在 Notion。

## 一、赛事情报（第三届）

- 全称：NVIDIA DGX Spark 黑客松 · 第三届 —— **Agent Skills 开发挑战赛**（线上训练 + 作品提交，入围赴苏州总决赛）
- 时间线：报名截止 09-19 ｜ 线上训练营 09-20 ｜ **作品提交 09-20–09-29** ｜ 预赛评选 09-30–10-08 ｜ 决赛 10-15（苏州金鸡湖国际会议中心 A 馆 · NVIDIA 中国开发者日）
- 主办：NVIDIA 开发者社区 × StepFun 阶跃星辰 × XSUPERZONE × ASUS；组队 2–5 人，限 100 队，需审核
- 算力：限量 DGX Spark 云节点（审核开通），可自备相近算力 NVIDIA 硬件
- 官方要求：依托 DGX Spark 本地算力打造**完整、可运行**的 Agent 应用，用 Agent Skills 封装专业知识、工具调用与标准工作流
- 来源：HackerTrip 收录页 https://hackertrip.space/hackathon/a2507bbd-e29a-4eae-b7fd-b63a150db1c7 ；知乎训练营公告 zhuanlan.zhihu.com/p/2081347328250795216

## 二、第二届获奖复盘（模式来源）

- 冠军 卡皮巴拉队「Super Idol Master」：数字角色资产流水线 —— 每环节先过检查，不合格自动修复，修不好退回重新生成，中断可续跑；Step 系模型指挥，GPU 重活本地做。GitHub: github.com/SidneyArt/Super-Idol-Master
  → 同样的工程原则应用到文档域，差异化点：证据链（每处修改附原始 crop）+ 置信度
- 亚军 注意力算得队「PLLM」：负载感知推理框架（token 边界让出资源）——启发：spark-ops 的装卸调度叙事
- 季军 树状图设计者队「E-MARS」：三模型分时间尺度决策、权重冻结接入闭环 —— 启发：多模型仲裁分层
- 规模：112 队报名 / 2122 开发者；评委构成偏工程落地

## 三、Agent Skills 规范核验（agentskills.io）

- frontmatter 必需字段仅 `name`、`description`；**两者是 Agent 触发前唯一可见信息** —— description 必须写「何时用」
- 三级渐进披露：L1 元数据 → L2 SKILL.md 正文 → L3 references/scripts/assets 按需加载
- 正文控制 5k token 内，长细节下沉 references/；确定性操作交给 scripts/
- NVIDIA 验证体系（docs.nvidia.com/skills）：Cataloged → Scanned（隐藏指令/提示注入/过度权限）→
  Evaluated（有/无 Skill 对照，产出 BENCHMARK.md）→ Signed（skill.oms.sig）
- 自检工具：`npx skill-tools check ./my-skill/`（20 项规范检查 + 0–100 质量评分）

## 四、生态空白证据（选题依据）

- NVIDIA/skills 视觉类仅 VSS 系列（vss-ask-video 等，面向视频流与安防告警）；**静态文档/版面/公式/表格空缺**
- Anthropic anthropics/skills 四件套（docx/xlsx/pptx/pdf）：pdf skill 只做提取与填表，无结构还原与质检
- 训练营第三课「DGX Spark 本地视觉 Agent 技能开发实战」与本方案正对口

## 五、待核验项（提交前）

- [ ] 官方提交入口与材料格式（以报名确认邮件/官网用户中心为准）
- [ ] 视频时长硬性要求（按 3 分钟准备，宁短勿超）
- [ ] 云节点开通状态；未批则用本地 NVIDIA 卡 + ARM64 NGC 容器
