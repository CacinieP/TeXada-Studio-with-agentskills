# TeXada Studio 桌面端(macOS 与 Windows)

桌面端提供跨平台的原生窗口壳(`desktop/app.py`,在 macOS 使用 WKWebView,在 Windows 10/11 使用系统内置 Edge WebView2)与双平台自包含打包构建器:

| 平台与形态 | 命令 | 依赖 | 适用 |
| --- | --- | --- | --- |
| **macOS 自包含应用包**(推荐) | `.venv/bin/python desktop/build_bundle.py` | 构建机需一次准备;**产物零依赖** | 日常使用;拖入 `~/Applications`,不依赖仓库/venv/brew/网络 |
| **Windows x64 自包含便携包**(推荐) | `.venv\Scripts\python.exe desktop\build_windows_bundle.py` | 构建机需一次准备;**产物零依赖**(Windows 10/11 自带 WebView2) | 解压后双击 `TeXada Studio\TeXada Studio.exe` 即用 |
| macOS 薄壳(仓库模式) | `.venv/bin/python desktop/build_app.py` | 始终需要仓库检出 + `.venv` | 开发调试;跟仓库代码同步 |
| 直接窗口启动(macOS / Windows / Linux) | `python desktop/app.py` | 仓库检出 + `.venv` + `pywebview` | 本地开发调试 |

两者都复用已有同端口回环会话或自启后端,关闭窗口只回收自己拉起的服务进程。

## 1. Windows x64 自包含便携包

### 构建机一次性准备(PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r webui\requirements.txt
.venv\Scripts\python.exe -m pip install -r desktop\requirements.txt pyinstaller
.venv\Scripts\python.exe scripts\install_local_tools.py
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'webui'); import tool_fetch; print(tool_fetch.install_poppler())"
$env:PATH = "$HOME\.texada\bin;$env:PATH"
$env:TECTONIC_CACHE_DIR = "$env:LOCALAPPDATA\TectonicProject\Tectonic\Cache"
.venv\Scripts\python.exe scripts\prepare-local-tex.py --download-resources
```

### 构建与验证

```powershell
.venv\Scripts\python.exe desktop\build_windows_bundle.py --output dist-win --with-llama-server
```

产物位于 `dist-win\TeXada Studio\`,双击 `TeXada Studio.exe` 启动:
- 纯标准库从品牌 PNG 生成多尺寸 `AppIcon.ico`(16–256 px Vista+ PNG-in-ICO)并写入可执行版本 `0.1.1.0`;
- `Resources\` 内含 `webui`、`harness`、`skills`、`samples\docs`、`tex-cache\`、`bin\tectonic.exe`、Poppler Windows(`pdfinfo.exe`、`pdftoppm.exe`、动态库与 `share\poppler` CJK 字形映射)、可选 `llama-server.exe`(`b12631` CPU x64,SHA-256 锁定校验)与 `licenses\`;
- 首次启动自动将 `Resources\tex-cache` 种子到 `%LOCALAPPDATA%\TectonicProject\Tectonic\Cache` 并设置 `TECTONIC_CACHE_DIR`,日常编译与预览全离线;
- `desktop/windows_entry.py` 同时承接包内 `[TeXada Studio.exe, verify.py, ...]` 检查器子进程调用,机器无需预装系统 Python。

CI 工作流 [`.github/workflows/windows-bundle.yml`](../.github/workflows/windows-bundle.yml) 在 `windows-latest` 上自动执行上述构建与**隔离冒烟测试**(空白 `USERPROFILE` / `LOCALAPPDATA`、仅保留 `C:\Windows\System32;C:\Windows` 的最小 `PATH` 下验证 `tectonic.exe` 中文 `ctexart` 离线编译、`pdftoppm.exe` 中文 vs `\phantom` 非空白像素校验、冻结检查器调用与 `llama-server.exe --version`),产出 `TeXada-Studio-Windows-x64.zip` 与 `checksum-windows.txt`。配置可选仓库 Secrets `WINDOWS_CERTIFICATE`(PFX 的 base64)与 `WINDOWS_CERTIFICATE_PWD` 时自动调用 `signtool.exe` 完成 SHA-256 Authenticode 时间戳签名;未配置时跳过签名直接产出便携包。

## 2. macOS arm64 自包含应用包

### 构建机一次性准备

```bash
.venv/bin/pip install py2app pywebview            # desktop/requirements.txt + py2app
.venv/bin/python scripts/install_local_tools.py    # Tectonic → ~/.texada/bin(SHA256 校验)
brew install poppler
.venv/bin/python scripts/prepare-local-tex.py --download-resources   # TeX 资源缓存(~68 MiB)
```

### 构建与公证 DMG

```bash
.venv/bin/python desktop/build_bundle.py --with-llama-server   # 产物 dist/TeXada Studio.app
```

[`.github/workflows/bundle-build.yml`](../.github/workflows/bundle-build.yml) 在 `macos-15` runner 上执行安装、构建、隔离冒烟测试与打包。未配置签名凭据时产出未签名 zip(`…-unsigned`);配置以下 secrets 后产出**签名 + 公证 + 装订(staple)的 DMG**(`…-notarized`):

| Secret | 内容 | 获取方式 |
| --- | --- | --- |
| `MACOS_CERTIFICATE` | **Developer ID Application** 证书 `.p12` 的 base64 | developer.apple.com → Certificates 创建;钥匙串导出(含私钥)后 `base64 -i 证书.p12 \| pbcopy` |
| `MACOS_CERTIFICATE_PWD` | 导出 `.p12` 时设置的密码 | 自定 |
| `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_P8` | App Store Connect API 密钥(公证推荐) | appstoreconnect.apple.com → 用户与访问 → 密钥;`.p8` 原文存 `ASC_KEY_P8` |
| (备选)`APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD` / `APPLE_TEAM_ID` | Apple ID + 专用密码公证 | appleid.apple.com 生成 App 专用密码 |

包内全部第三方组件的许可证审计见 [licenses-audit.md](licenses-audit.md)(副本随包分发)。

### 构建解释器注意(macOS)

macOS 自包含包请使用 Homebrew 或 python.org 的 framework Python 创建 `.venv`(部分 uv standalone Python 将 `zlib` 静态内置会导致 `py2app` 报错;脚本会在构建前检测并提示)。

## 3. 测试

```bash
.venv/bin/python -m unittest discover -s desktop -p 'test_*.py'
```

在 macOS、Linux 与 Windows(`windows-latest` CI 矩阵)上离线覆盖会话读取、跨平台进程存活判定(POSIX 信号 0 与 Win32 `SYNCHRONIZE` 句柄探测)、PATH 前置、TeX 缓存种子、PNG-in-ICO 生成、资源暂存与 PyInstaller / py2app 外部构建目录隔离。
