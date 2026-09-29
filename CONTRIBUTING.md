# 参与贡献

欢迎提交可复现的问题和聚焦的小范围 PR。无需 GPU 也能改进检查器、样本、UI 和文档。

## 开发流程

1. Clone 仓库，创建 `fix/`、`feat/` 或 `docs/` 分支；私有期间需先获得访问权限。
2. 按 [README](README.md)准备虚拟环境，用最小合成输入复现问题。
3. 修改实现并运行相关检查，命令见下表。
4. 运行 `git diff --check`，检查暂存文件后提交 PR。

PR 写清具体问题、修改后的行为和实际运行的验证命令。UI 改动附必要截图；模型行为改动附模型、输入来源和运行结果。私人文档、凭据、模型权重及本机运行产物留在仓库外。安全问题使用 [SECURITY.md](SECURITY.md) 的渠道。

## 按改动选择验证

| 改动 | 验证入口 |
| --- | --- |
| Web API、静态资源 | `python -m unittest discover -s webui -p 'test_*.py' -v` |
| Studio 交互 | `node webui/test_studio.cjs`；布局变更另做浏览器检查 |
| CLI 重试、状态、报告 | `python -m unittest discover -s harness/tests -p 'test_*.py' -v`；重放 fixture 首跑和续跑 |
| 检查器契约 | [27 个案例](samples/evaluation/README.md)，保留新报告 |
| 评估运行器 | `python -m unittest discover -s scripts -p 'test_evaluate_*.py' -v` |
| latex-cleanup | [该模块测试说明](skills/latex-cleanup/tests/CASES.md) |
| 文档 | 核对命令、相对链接和中英文一致性 |

依赖安装和完整测试列表见 [README](README.md#4-测试与评估复现)。当前没有自动 CI，PR 中需记录本地验证结果。

## 样本与文档

新增案例使用稳定 ID，写清来源、输入、预期状态和原因。优先原创合成输入；第三方样本需附可分发的许可。改预期时说明输入契约的变化，并保留能重现原问题的案例。

README 负责上手，模块手册负责参数和细节，实验报告记录一次具体运行。按[文档联动表](docs/index.md#变更时同步哪些文档)更新对应入口；模型结论使用真实运行和复核结果，fixture 用于流程回归。

## 依赖与许可

Monaco 资源按版本和摘要固定。升级时修改 `scripts/vendor_monaco.py` 的版本与包摘要，再重新获取资源并运行静态资源测试。`latex-cleanup` 是导入快照，修改时同步其来源说明；其他第三方依赖也需保留来源、版本和许可证。

贡献沿用本项目 AGPL-3.0-only，作者保留版权；既有第三方许可继续有效。项目不要求 CLA 或固定提交格式。后续任务见[路线图](docs/roadmap.md)。
