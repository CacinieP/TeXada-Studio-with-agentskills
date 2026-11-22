# 捆绑组件许可审计(macOS 自包含 `.app` 与 Windows 自包含便携包)

本文件列出 `desktop/build_bundle.py`(macOS arm64)与 `desktop/build_windows_bundle.py`(Windows x64)打进自包含桌面发行包的全部第三方组件及其许可证结论。
结论:**均可合法再分发**;GPL 组件以独立进程方式调用(mere aggregation),不与本项目 AGPL-3.0-only 代码产生衍生关系。
本文件副本随包写入 `Resources/licenses/`。

## 1. Python 运行时与库(macOS `py2app` / Windows `PyInstaller` 冻结)

| 组件 | 许可证 | 再分发 |
| --- | --- | --- |
| CPython(macOS framework Python / Windows x64 CPython 3.11+) | PSF License(含 BeOpen/CNRI 历史条款) | 允许,附许可文本 |
| PyInstaller Bootloader(仅 Windows 冻结入口 `TeXada Studio.exe`) | GPL-2.0-or-later with Bootloader Exception | 特殊例外条款明确允许冻结并分发任意许可的程序 |
| fastapi | MIT | 允许 |
| starlette / uvicorn / h11 | BSD-3-Clause | 允许 |
| anyio / sniffio | MIT | 允许 |
| idna | BSD-3-Clause | 允许 |
| pydantic(+pydantic_core,Rust 扩展) | MIT | 允许 |
| sympy / mpmath | BSD | 允许 |
| antlr4-python3-runtime | BSD-3-Clause | 允许 |
| pywebview(含 Windows 端 `WebView2Loader.dll` 再分发库) | BSD-3-Clause(WebView2 Loader 为 Microsoft BSD 风格可再分发许可) | 允许 |
| pyobjc(-core、Cocoa、WebKit、Quartz、Security、UniformTypeIdentifiers;仅 macOS) | MIT | 允许 |
| pythonnet / clr-loader(仅 Windows `pywebview` 桥接) | MIT | 允许 |

来源:各包 PyPI 元数据 License 字段与上游仓库(构建时逐包核对,见 `pip show <pkg>`)。

## 2. TeX 编译器与资源

| 组件 | 许可证 | 说明 |
| --- | --- | --- |
| Tectonic 0.17.0(macOS `aarch64-apple-darwin` / Windows `x86_64-pc-windows-msvc.zip`,SHA256 `f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f`) | MIT | 直接再分发允许;SHA256 与上游官方 Release 一致 |
| TeX 资源缓存(默认 bundle 所需文件,约 68 MiB) | 来源为 TeX Live 各宏包,许可混合:LPPL(多数)、Public Domain、BSD/MIT、部分 GPL | TeX Live 的分发条款允许整体再分发;缓存内含各文件哈希寻址,逐文件许可随 TeX Live 发行 |

注意事项:
- LPPL 大多数版本含"可改名分发"条款;我们按哈希原样分发、未改名、未修改,符合 LPPL 1.3c 的分发条件。
- 若上游 bundle 中个别文件带更严格条款,分发者义务与直接再分发 Tectonic 默认 bundle 相同。构建时按实际复制进应用的缓存现写 `Resources/licenses/tex-cache-manifest.sha256`。完整上游文件名索引不入库,可用 `tectonic -X bundle search --only-cached` 从同一缓存导出。
- 本缓存由 `scripts/prepare-local-tex.py --download-resources` 在构建机上物化,只含固定样本所需资源。

## 3. Poppler(PDF 导入与页面预览)

| 组件 | 许可证 | 调用方式 |
| --- | --- | --- |
| macOS Poppler(Homebrew `pdfinfo`、`libpoppler` 及独立 PNG 渲染程序 `desktop/poppler_render.cpp`) | GPL-2.0-or-later | Studio 通过独立子进程调用;渲染程序链接 `libpoppler-cpp` |
| Windows Poppler(`oschwartz10612/poppler-windows` `v26.09.0-0`,`Release-26.09.0-0.zip`,SHA256 `7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0`) | GPL-2.0-or-later | Studio 仅通过独立命令行子进程调用 `pdfinfo.exe` / `pdftoppm.exe` |
| 其动态库依赖链(freetype、libpng、zlib、libjpeg-turbo、openjpeg、cairo 等) | 各自宽松许可(FTL/BSD/Zlib/MPL/GPL 兼容) | 仅被上述独立可执行程序动态链接 |

结论:GPL 程序以独立进程 + 命令行参数方式使用,属 mere aggregation;AGPL-3.0-only 的 Studio 代码不因此变成 GPL 衍生作品。
再分发义务:随包提供本审计文件、GPL-2.0 许可声明与源码获取途径(见下)。

固定版本的 Poppler 编码数据随包写入:
- macOS:`Resources/poppler-data/`,许可文本存放于 `Resources/licenses/poppler-data/`;
- Windows:`Resources/share/poppler/`,许可与构建说明存放于 `Resources/licenses/poppler-windows/`。

## 4. 其他

| 组件 | 许可证 |
| --- | --- |
| `llama.cpp`(可选:macOS 经 Homebrew 构建;Windows 锁定官方 `llama-b12631-bin-win-cpu-x64.zip`,SHA256 `8b3639c62c6c41b8134797ea9beedd6b6c26caad6a1ed99a3d5a2802262923d7`) | MIT;随包附 `Resources/licenses/llama.cpp-LICENSE.txt`,作为独立进程调用。模型权重由用户在设置面板按需下载 |
| Monaco 0.52.2(已 vendored) | MIT |
| 本项目代码/文档/合成样本 | AGPL-3.0-only(见 LICENSE、THIRD_PARTY_NOTICES.md) |

## 源码获取(written offer)

对应源码的官方来源:
- CPython / PyPI 组件 / PyInstaller:`pip download <pkg>==<version>` 或各项目仓库(https://github.com/pyinstaller/pyinstaller);
- Tectonic:https://github.com/tectonic-typesetting/tectonic (tag `tectonic@0.17.0`);
- TeX 资源:Tectonic 官方 bundle(构建说明见上);
- Poppler 及依赖:上游 https://gitlab.freedesktop.org/poppler/poppler 、https://poppler.freedesktop.org/ 、macOS Homebrew formula(`brew info poppler`)及 Windows 打包配方 https://github.com/oschwartz10612/poppler-windows (tag `v26.09.0-0`);
- `llama.cpp`:https://github.com/ggml-org/llama.cpp (tag `b12631`);
- Homebrew 构建脚本:https://github.com/Homebrew/homebrew-core (各 formula)。

如需完整对应源码包,按上表来源自行获取,或联系维护者索取构建时所用的确切版本清单。
