# doc-forensics

> 文档解析质检 Skill 套件 · 第三届 NVIDIA DGX Spark 黑客松（Agent Skills 方向）参赛作品

把「文档解析 → 逐项质检 → 不合格自动修复 → 修不好退回重生成 → 断点续跑」封装成一组协作的 Agent Skills，
交付**带置信度与可追溯证据**的结构化文档，覆盖版面、表格、公式三类高错资产域。

## 仓库地图

```
doc-forensics/
├── README.md
├── docs/
│   ├── proposal.md              # 选题定稿书（评审视角，先读这个）
│   ├── architecture.md          # 架构图 + 内存预算 + 为什么需要 DGX Spark
│   ├── research-notes.md        # 调研纪要（含来源链接）
│   ├── demo-script.md           # 3 分钟无剪辑演示脚本（含故意注入错误）
│   └── submission-checklist.md  # 提交前自检清单（映射 NVIDIA 六维验证）
├── skills/
│   ├── doc-layout-parse/        # 版面与阅读顺序还原（调本地 VLM）
│   ├── doc-table-audit/         # 表格跨页/合并/合计值交叉验算
│   ├── doc-formula-verify/      # 公式 SymPy 解析回判 + 高分辨率重识别
│   ├── doc-report/              # 质检报告与 diff 视图（证据链）
│   ├── latex-cleanup/           # 内部依赖：TeX/Markdown 清洗与编译回环（v0.2.3，见其 PROVENANCE.md）
│   └── spark-ops/               # 内部依赖：内存预算与模型装卸（不单独参赛）
├── harness/                     # Agent Harness 说明（模型网关/装卸/断点协议）
├── scripts/
│   └── backup.sh                # git bundle 本地备份
└── state/                       # 运行时状态（断点续跑，不入库）
```

## 快速开始

```bash
# 依赖（目标环境为 DGX Spark / ARM64，本机先验证核心脚本）
pip install sympy antlr4-python3-runtime   # 公式校验
python3 skills/doc-formula-verify/scripts/verify.py '\frac{1}{2}'

# 表格审计
echo '{"rows":[["A","1"],["B","2"]],"expected":{"n_rows":2,"n_cols":2}}' \
  | python3 skills/doc-table-audit/scripts/audit_table.py
```

## 备份

```bash
scripts/backup.sh   # 生成 git bundle 到 ../_backups/doc-forensics/
```

推送远端（GitHub 私有仓）需人工审阅后执行，见 docs/submission-checklist.md 的发布前检查。
