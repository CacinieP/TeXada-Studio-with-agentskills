# 仓库名称与迁移记录

当前仓库为 [`CacinieP/TeXada-Studio-with-agentskills`](https://github.com/CacinieP/TeXada-Studio-with-agentskills)，显示名为 **TeXada Studio with Agent Skills · 文档质检与修复**，Web 界面沿用 TeXada Studio。名称由维护者指定，现有比赛材料未要求固定仓库前缀或编号。

六个 Skill 的目录与 frontmatter 名称保持原接口，遵循 [Agent Skills 命名规范](https://agentskills.io/specification)；仓库改名未改动这些入口。

## 清理与迁移

| 阶段 | 已完成处理 |
| --- | --- |
| 原仓库教材清理 | 在 `TeXada-WebUI` 私密备份完整 bundle 后，按路径与两个 blob ID 移除 `samples/docs/GTM249-p101-120.tex`。35个提交中重写13个，当前代码 tree 保持一致；遍历可达历史与 Git 完整性检查通过。 |
| 创建独立仓库 | 只推送清理后的可达历史到新仓库，保留 AGPL、Monaco MIT、合成样本和测试。新仓库为独立仓库，未使用 fork。 |
| 后续历史脱敏 | 清理时的45个可达提交全部重写且保留，处理邮件元数据、旧部署端口、制作记录与含节点名图片；实验原始文件保持不变。[详情](security-scan-notes.md) |

原仓库重新 mirror clone 后，教材路径与两个 blob 已不可达，但已登录 API 仍能按旧 SHA 读取对象，因此另建独立仓库。新仓库 mirror clone 不含这些内容，API 查询两个旧 blob 均返回404。原仓库清理时仅有 `main`，无标签、PR、Release 或 fork。

## 迁移后的状态

- 新旧仓库均保持 **PRIVATE**；新仓库已完成推送并核对 `main`。
- 工作目录、`origin`、README、界面源码链接、部署示例和打包名称已切换到新名称。
- 运行数据、私人上传、本地备份及已移除的教材内容未随迁移上传。
- 演示服务的部署与源码仓库分别维护，部署时核对运行版本。

协作者应重新 clone 清理后的仓库，避免将旧历史 merge 或 push 回来。清理前的 bundle 仅作私有恢复备份。Git 引用清理之外的平台缓存和旧副本按[扫描记录](security-scan-notes.md)处理；公开发布按[发布清单](open-source-release.md)执行。
