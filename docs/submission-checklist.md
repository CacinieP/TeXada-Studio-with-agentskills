# 提交前自检清单（映射 NVIDIA 验证体系）

提交截止 **2026-09-29** · 原则：不压点，提前半天完成提交。

## A. 规范与安全（对应 Scanned）

- [ ] 每个 SKILL.md frontmatter 含 `name` + `description`；description 写清「做什么 + 何时用」
- [ ] 正文 < 5k token；长细节已下沉 references/
- [ ] `npx skill-tools check ./skills/<each>/` 全绿，质量评分 ≥ 80
- [ ] 无硬编码路径、无密钥、无外部 URL 拉取指令
- [ ] 声明与实际行为一致：Skill 不会执行未声明的 shell 操作（防 excessive agency）
- [ ] Skill 不发起任何网络请求；模型端点仅 127.0.0.1

## B. 评测（对应 Evaluated）

- [ ] 每个 Skill 附 `evals/evals.json`，含「有 Skill / 无 Skill」对照设计
- [ ] 产出 `BENCHMARK.md`：修复成功率 / 误改率 / 人工介入率 before-after 表
- [ ] 错误注入集跑通：公式错 ≥ 10 例、表格错 ≥ 5 例

## C. 工程可用性

- [ ] 一键复现：新环境按 README 从零跑通（容器/依赖固化）
- [ ] ARM64 兼容：仅用 NGC 容器或纯 Python 依赖（SymPy/CPU）
- [ ] 断点续跑验证：kill -9 后重跑能跳过已完成节点
- [ ] 断网全流程跑通

## D. 提交材料

- [ ] 代码仓（打包 zip 或按官方要求的 git 形式）
- [ ] 3 分钟无剪辑演示视频（docs/demo-script.md 录制）
- [ ] README + proposal（评审 30 秒能看懂「是什么、为什么需要 Spark」）
- [ ] 队伍信息与成员名单与报名一致

## E. 提交动作（09-29）

- [ ] 上午 10 点前材料冻结
- [ ] 中午前通过官方入口提交，**保存回执/确认页截图**
- [ ] 若晋级：10-15 苏州路演 5 分钟讲稿另行准备

## F. 发布前（git 远端）

- [ ] 人工审阅全部提交历史
- [ ] 建 GitHub **私有**仓后 push（不含样本中的真实文档；确认无个人路径泄漏）

公开发布另见 [开源发布检查](open-source-release.md)；私有仓 push 不代表历史已经适合公开。
