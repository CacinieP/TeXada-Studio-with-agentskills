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

也可以不在本机构建:[`.github/workflows/bundle-build.yml`](../.github/workflows/bundle-build.yml) 会在 GitHub Actions 的 macOS arm64 runner 上完成同一流程(安装固定版 Tectonic → brew 装 Poppler → 准备 TeX 缓存 → 构建 → **隔离冒烟**〔剥离 PATH/HOME 下直测三个二进制并用捆绑缓存编译出 PDF〕→ 打包上传,附 SHA256)。触发方式:改动相关路径的 PR、`v*` 标签,或在 Actions 页手动 `workflow_dispatch`。

### 公证 DMG(可选,配置仓库 secrets 后自动启用)

未配置凭据时产出未签名 zip(`…-unsigned`,使用需右键打开)。配置以下 secrets 后,同一工作流会改为产出**签名 + 公证 + 装订(staple)的 DMG**(`…-notarized`,双击即装):

| Secret | 内容 | 获取方式 |
| --- | --- | --- |
| `MACOS_CERTIFICATE` | **Developer ID Application** 证书 `.p12` 的 base64 | developer.apple.com → Certificates 创建;钥匙串导出(含私钥)后 `base64 -i 证书.p12 \| pbcopy` |
| `MACOS_CERTIFICATE_PWD` | 导出 `.p12` 时设置的密码 | 自定 |
| `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_P8` | App Store Connect API 密钥(公证推荐) | appstoreconnect.apple.com → 用户与访问 → 密钥;`.p8` 原文存 `ASC_KEY_P8` |
| (备选)`APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD` / `APPLE_TEAM_ID` | Apple ID + 专用密码公证 | appleid.apple.com 生成 App 专用密码 |

设置(在本机仓库目录):`gh secret set MACOS_CERTIFICATE < 证书.p12.base64` 等;随后 `gh workflow run "Desktop bundle"` 或打 `v*` 标签即可产出公证 DMG。流程:导入临时钥匙串 → `sign_bundle.py` 逐个签名全部 Mach-O（含 Resources 内工具与扩展），再由内到外签名 bundle → 公证并 staple 应用 → 制作含 `/Applications` 符号链接的 UDZO DMG → 签名 DMG → 公证 + staple + `spctl` 验证。

> 注意:Apple Development 证书(本机开发用)不能用于分发签名;需要付费 Apple Developer Program 账号创建 **Developer ID Application** 证书。

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
