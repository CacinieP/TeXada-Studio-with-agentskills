# 可复核源码包

在已提交的 checkout 中运行：

```bash
bash scripts/package.sh
```

需要 Git、Bash 和 Python 3 标准库。可用 `TEXADA_PACKAGE_PYTHON` 指定 Python 可执行文件。脚本固定本次 `HEAD` 的完整提交号，拒绝工作区和暂存区中的已跟踪文件修改；未跟踪文件不进入包。

`dist/` 下生成同名三件套，文件名包含至少 12 位的 Git 提交缩写：

- `TeXada-Studio-with-agentskills-<rev>.zip`：`git archive` 源码快照，保留一个顶层目录。
- `TeXada-Studio-with-agentskills-<rev>.manifest.json`：完整提交号、Git tree、ZIP 摘要，以及每个包内文件的相对路径、字节数和 SHA256。
- `TeXada-Studio-with-agentskills-<rev>.SHA256SUMS`：ZIP 和 manifest 的 SHA256 清单。

生成过程中会核对 ZIP 提交标记、成员 CRC、路径和必需源码入口，拒绝常见运行数据、凭据文件、模型、缓存、原生运行程序或符号链接。`.gitattributes` 还会从归档中排除 `.github/` 和 `state/`。验证失败时不会留下本次的最终三件套；同一提交重建会替换同名产物，不会混入未提交修改。

收到文件后，把三件套放在同一目录。在 macOS 中执行：

```bash
shasum -a 256 -c TeXada-Studio-with-agentskills-<rev>.SHA256SUMS
```

Linux 可使用 `sha256sum -c`。将 manifest 中的完整 `commit` 与所选 Git 提交比对；其逐文件摘要可用于核对解压内容。校验和用于检查文件是否一致，不代替发布者签名或提交来源核验。路径检查也不是任意源码内容的密钥扫描，提交前仍需审阅实际文件。

这是源码分发包，不含 Python 虚拟环境、模型权重、本机编译器或运行数据，也不是独立应用安装包。安装和启动继续使用[本地指南](local-studio.md)；本命令不创建 tag、GitHub Release 或上传附件。
