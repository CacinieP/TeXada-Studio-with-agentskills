# 当前验证与分发状态

日期：2026-11-04。当前产品入口是本地单用户 Web UI，Python/FastAPI 提供服务、Monaco 在浏览器中编辑。尚未把本次整理声明为正式版本 Release。

## 代码与验证范围

公式修复实现基准为 `ceae9a7`；此前 Skill 与工作区修复包含在其历史中。本轮继续整理文档、仓库首页、CI 与可复核源码包。提交号可从 `git rev-parse HEAD` 和源码包 manifest 核对；GitHub PR 合并后的提交号与原分支实现提交可能不同。

| 验证 | 已取得的证据 |
| --- | --- |
| Python 功能回归 | `ceae9a7`：Harness 123、Web/API 159、脚本 61、LaTeX cleanup 77，共 420 项通过 |
| JavaScript | Studio 交互、LaTeX 编辑器与数学审计三组通过 |
| 检查器契约 | 27/27 合成案例符合声明预期 |
| 公式修复流程 | 20 个合成案例对照；结构组 4/6 → 6/6，原文控制组 5/6 → 6/6，详见[质量记录](formula-repair-quality.md) |
| 实际编译和交付 | 六个修复结果离线编译通过；合成文档经过实际 HTTP 候选生成、审阅记录、保存、PDF 生成与预览 |
| 源码打包 | 新增 8 项临时 Git 仓库回归，覆盖 dirty、排除项、身份/摘要、路径空格与可重复重建；实际提交的三件套再按[打包说明](source-package.md)核验 |
| 当前首页截图 | Chrome、1440×900、合成 `welcome.tex`；源码与中文 PDF 同屏，未使用私人文档或伪造连接状态 |

本轮文档/打包版本使用 Python 3.13 重新运行完整回归：Harness 123、Web/API 159、脚本 69、LaTeX cleanup 77，共 **428 项通过**；三组 JavaScript 回归也通过。新增及更新入口的 326 个本地链接/标题锚点核对通过。实际 CI 结果请查看 [Studio regression](https://github.com/CacinieP/TeXada-Studio-with-agentskills/actions/workflows/regression.yml) 的对应提交；配置或排队不等于已经通过。

## 怎样复现

安装依赖后，按[完整回归命令](local-studio.md#回归测试)运行 Python 和 JavaScript 测试。检查器案例、公式修复 fixture 与显式本机模型对照分别使用其专用 runner，不把 fixture 调用计入模型请求。

离线资源准备见[本地指南](local-studio.md#首次准备与离线使用)。要验证真实候选、编译与导出，请使用合成文档、独立数据目录和新运行目录；保留实际状态、来源哈希和失败记录。

## 保留的边界

- 新规则在上述结构修复组中避免了模型请求，收益是宿主流程改进；after 的零 HTTP 不是模型推理准确率评测。
- 小型合成对照、单次本机 OCR 和页面 smoke 不能推广为数学正确率、任意文档准确率或跨平台验收。
- 当前构建与字体/页面转换核对以 Apple Silicon macOS 为主；Linux CI 验证软件回归，不能替代 Linux 桌面与模型实测。
- 历史 Chrome 与本机 1B 转写记录保留其日期和提交，见[本地验收](local-studio-acceptance.md)、[视觉验收](texada-visual-implementation.md)与[历史验证](validation.md)。

源码 ZIP 只含已提交的 Git tree，附完整提交与文件摘要，不包含 `.git` 历史、CI 配置、运行文档、模型、虚拟环境或本机工具。仓库维护使用完整 checkout；普通源码包使用者按 README 准备运行环境。
