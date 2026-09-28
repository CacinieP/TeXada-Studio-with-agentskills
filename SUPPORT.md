# 使用帮助与反馈

先读 [README](README.md) 的能力范围和 [排错指南](docs/troubleshooting.md)。当前维护的是 `main` 最新提交，尚无正式 Release、付费支持或响应时限承诺。

| 需求 | 入口 | 最少提供的信息 |
| --- | --- | --- |
| 安装失败、界面异常、检查结果不符合预期 | [Bug report](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues/new?template=bug_report.md) | 提交号、环境、预期与实际、最小合成样本 |
| 现有能力未覆盖的使用场景 | [Feature request](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues/new?template=feature_request.md) | 谁遇到什么问题、现有办法、建议验收条件 |
| 使用方式问题 | [Usage question](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues/new?template=question.md) | 已查文档、执行命令、卡住的步骤 |
| 安全漏洞、凭据或隐私问题 | [SECURITY.md](SECURITY.md) | 按私密报告流程联系，勿放入普通 Issue |
| 行为违规 | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | 具体内容的位置，避免再传播个人信息 |

私有阶段只有被授权成员能访问以上仓库入口。没有权限时，请通过你与维护者已有的联系渠道询问访问方式；这里不提供匿名公共演示地址。Discussions 尚未启用，使用问题先统一到 Issues，避免维护多个空频道。

报告时执行 `git rev-parse --short HEAD`，注明使用 Studio 还是 CLI，以及 fixture 还是真实模型。日志只保留相关错误；删去 URL 中的 token、个人文件路径、文档内容和节点访问资料。优先把问题简化成十几行可分发的合成 TeX。

## English

Use GitHub Issues for reproducible bugs, usage questions, or concrete feature requests. Include your commit, environment, entry point (Studio/CLI), fixture vs. real model, and a small synthetic example. The private repository requires access. No support SLA is offered. Report security problems using [SECURITY.md](SECURITY.md), not a public issue.
