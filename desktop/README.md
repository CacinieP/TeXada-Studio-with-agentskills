# TeXada Studio 桌面端(macOS)

两种形态,按需选择:

| 形态 | 命令 | 依赖 | 适用 |
| --- | --- | --- | --- |
| **自包含应用包**(推荐) | `.venv/bin/python desktop/build_bundle.py` | 构建机需一次准备(见下);**产物零依赖** | 日常使用;可拖到 ~/Applications,不依赖仓库/venv/brew/网络 |
| 薄壳(仓库模式) | `.venv/bin/python desktop/build_app.py` | 始终需要仓库检出 + `.venv` | 开发调试;跟仓库代码同步 |

两者都提供独立窗口(WKWebView)+ Dock 图标,复用已有会话或自启后端,窗口退出回收资源。

## 自包含应用包

### 构建机一次性准备

```bash
.venv/bin/pip install py2app pywebview            # desktop/requirements.txt + py2app
.venv/bin/python scripts/install_local_tools.py    # Tectonic → ~/.texada/bin(SHA256 校验)
brew install poppler
.venv/bin/python scripts/prepare-local-tex.py --download-resources   # TeX 资源缓存(~68 MiB)
```

### 构建与使用

```bash
.venv/bin/python desktop/build_bundle.py           # 产物 dist/TeXada Studio.app(约 280 MiB)
```

也可以不在本机构建:[`.github/workflows/bundle-build.yml`](../.github/workflows/bundle-build.yml) 会在 GitHub Actions 的 macOS arm64 runner 上完成同一流程(安装固定版 Tectonic → brew 装 Poppler → 准备 TeX 缓存 → 构建 → **隔离冒烟**〔剥离 PATH/HOME 下直测三个二进制并用捆绑缓存编译出 PDF〕→ ditto 打包并上传 artifact `TeXada-Studio-macOS-arm64`,附 SHA256)。触发方式:改动相关路径的 PR、`v*` 标签,或在 Actions 页手动 `workflow_dispatch`。

包内嵌:Python 运行时与全部服务端依赖、Tectonic、TeX 资源缓存、Poppler(pdfinfo/pdftoppm 及其动态库,重签名后自包含)、webui/harness/skills 源码与示例。**许可合规**见 [licenses-audit.md](licenses-audit.md)(副本随包分发)。

行为:
- 首次运行把包内 TeX 缓存种子到用户缓存目录;编译/预览全离线。
- 后端以进程内线程运行:窗口退出(Cmd+Q/关窗)即整进程退出,无孤儿;被强杀时残留会话由 pid 存活检查自愈。
- 模型服务仍是可选的外部回环端点(如 Ollama),在设置面板配置;不配置也可编辑、检查、编译。

### 已知限制

- 构建产物绑定构建时的代码版本;更新仓库后重新构建。
- 未做公证(notarization):分发给他人时 Gatekeeper 需右键打开;自用无碍。
- 仅 macOS;Windows/Linux 用浏览器入口。

## 薄壳(仓库模式)

```bash
.venv/bin/pip install -r desktop/requirements.txt
.venv/bin/python desktop/build_app.py
```

细节见仓库历史文档;`TEXADA_EXIT_WHEN_ORPHANED=1` 的孤儿回收机制只在仓库模式(子进程启动器)生效。

## 测试

```bash
.venv/bin/python -m unittest discover -s desktop -p 'test_*.py'
```

覆盖会话读取(回环/凭据校验)、存活判定、PATH 前置、TeX 缓存种子、命令行与环境组装、两种包结构生成;不启动 GUI、不联网。
