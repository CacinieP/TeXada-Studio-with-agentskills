# 使用帮助与反馈

安装与启动见 [README](README.md)，常见错误见 [排错指南](docs/troubleshooting.md)。反馈请附 `main` 上实际使用的提交号。

| 需求 | 入口 | 最少提供的信息 |
| --- | --- | --- |
| 安装失败、界面异常、检查结果不符合预期 | [Bug report](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues/new?template=bug_report.md) | 提交号、环境、预期与实际、最小合成样本 |
| 现有能力未覆盖的使用场景 | [Feature request](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues/new?template=feature_request.md) | 谁遇到什么问题、现有办法、建议验收条件 |
| 使用方式问题 | [Usage question](https://github.com/CacinieP/TeXada-Studio-with-agentskills/issues/new?template=question.md) | 已查文档、执行命令、卡住的步骤 |
| 安全漏洞、凭据或隐私问题 | [SECURITY.md](SECURITY.md) | 按私密报告流程联系，勿放入普通 Issue |
| 行为违规 | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | 具体内容的位置，避免再传播个人信息 |

仓库私有期间，以上入口需要访问权限；没有权限时，通过与维护者已有的联系渠道反馈。使用问题统一提交到 Issues。

执行 `git rev-parse --short HEAD` 获取提交号，注明 Studio / CLI 和 fixture / 真实模型。提供可复现的小型合成 TeX、实际命令及相关错误；删去 token、个人路径、私人文档和节点访问资料。

## English

Use GitHub Issues for bugs, usage questions and feature requests. Include the commit, environment, Studio/CLI entry point, fixture/real-model mode, command and a small synthetic example. Repository access is required while private. Follow [SECURITY.md](SECURITY.md) for vulnerability reports.
