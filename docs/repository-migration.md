# 参赛名称与仓库迁移

## 名称

- 作品显示名：**TeXada Studio with Agent Skills · 文档质检与修复**。
- GitHub 仓库：`CacinieP/TeXada-Studio-with-agentskills`。
- Web 界面：TeXada Studio。

现有本地比赛材料没有记录固定仓库名前缀、队名拼接或编号格式；不能把本仓库名描述为组委会指定格式。仓库名由维护者指定为 `TeXada-Studio-with-agentskills`，保留 TeXada / Studio 标识，并标明 Agent Skills 参赛方向。

已核验的 [Agent Skills 官方规范](https://agentskills.io/specification)要求 Skill 的 `name` 为 1–64 字符、小写字母 / 数字 / 连字符，不能首尾或连续使用连字符，并与父目录名一致。这是 **Skill 名称** 的要求，并非比赛强制仓库命名规则。当前六个 Skill 的目录名与 frontmatter 保持一致，不因仓库改名而改动其接口名称。

报名系统或组委会若另有团队专属命名要求，以正式通知为准；队伍名称与报名信息不在本仓库中臆造。

## 迁移范围

从原仓库 `CacinieP/TeXada-WebUI` 的清理后历史创建独立仓库，不使用 GitHub fork、导入旧 bundle 或镜像旧远端的全部对象。

保留可达开发历史、AGPL-3.0-only 许可证、Monaco MIT 声明、合成样本和现有测试。此前移除的教材文件、两个历史 blob、运行数据、私人上传和本地备份不随迁移上传。

原仓库作为私有旧入口保留；新仓库也保持私有。新的工作目录和 `origin` 指向 `TeXada-Studio-with-agentskills`。在线演示服务器没有因本次 Git 迁移自动搬迁或重启。

## 核验清单

- [x] 新仓库为独立仓库（不是 fork），可见性为 PRIVATE。
- [x] 已完成首次推送并核对远端 `main`。
- [x] 从新远端 mirror clone 后，所有可达历史不含教材路径与两个旧 blob。
- [x] GitHub API 在新仓库中查询两个旧 blob 均返回 404。
- [x] README、页面源码链接、部署路径和打包名称均使用新仓库名。

不得从原仓库的旧 clone merge 或 push 回新仓库。公开发布需由维护者另行决定，见 [发布清单](open-source-release.md)。
