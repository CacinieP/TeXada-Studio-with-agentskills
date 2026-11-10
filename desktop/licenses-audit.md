# 捆绑组件许可审计(自包含 .app)

本文件列出 `desktop/build_bundle.py` 打进「TeXada Studio.app」的全部第三方组件及其许可证结论。
结论:**均可合法再分发**;GPL 组件以独立进程方式调用(mere aggregation),不与本项目 AGPL-3.0-only 代码产生衍生关系。
本文件副本随包写入 `Resources/licenses/`。

## 1. Python 运行时与库(py2app 冻结)

| 组件 | 许可证 | 再分发 |
| --- | --- | --- |
| CPython（构建机上的 macOS framework Python。桌面流水线请求 3.11；2026-11-10 本地候选包是 Homebrew CPython 3.13.16） | PSF License(含 BeOpen/CNRI 历史条款) | 允许,附许可文本 |
| fastapi | MIT | 允许 |
| starlette / uvicorn / h11 | BSD-3-Clause | 允许 |
| anyio / sniffio | MIT | 允许 |
| idna | BSD-3-Clause | 允许 |
| pydantic(+pydantic_core,Rust 扩展) | MIT | 允许 |
| sympy / mpmath | BSD | 允许 |
| antlr4-python3-runtime | BSD-3-Clause | 允许 |
| pywebview | BSD-3-Clause | 允许 |
| pyobjc(-core、Cocoa、WebKit、Quartz、Security、UniformTypeIdentifiers) | MIT | 允许 |

来源:各包 PyPI 元数据 License 字段与上游仓库(构建时逐包核对,见 `pip show <pkg>`)。

## 2. TeX 编译器与资源

| 组件 | 许可证 | 说明 |
| --- | --- | --- |
| Tectonic 0.17.0(官方 Release 单文件二进制) | MIT | 直接再分发允许;SHA256 与上游 Release 一致 |
| TeX 资源缓存(默认 bundle 所需文件,约 68 MiB) | 来源为 TeX Live 各宏包,许可混合:LPPL(多数)、Public Domain、BSD/MIT、部分 GPL | TeX Live 的分发条款允许整体再分发;缓存内含各文件哈希寻址,逐文件许可随 TeX Live 发行 |

注意事项:
- LPPL 大多数版本含"可改名分发"条款;我们按哈希原样分发、未改名、未修改,符合 LPPL 1.3c 的分发条件。
- 若上游 bundle 中个别文件带更严格条款,分发者义务与直接再分发 Tectonic 默认 bundle 相同。构建时按实际复制进应用的缓存现写 `Resources/licenses/tex-cache-manifest.sha256`。2026-11-10 本地候选是 `default_bundle_v33`(bundle id `6ffe055852f8faf66c0acbe1a7fb27f87b869a90bad1204f3bf4d9683f597c7c`)的已物化子集,共 335 个文件,与仓库里的 `desktop/tex-cache-manifest.sha256` 一致。完整上游文件名索引不入库,可用 `tectonic -X bundle search --only-cached` 从同一缓存导出。
- 本缓存由 `scripts/prepare-local-tex.py --download-resources` 在构建机上物化,只含固定样本所需资源。

## 3. Poppler(PDF 导入与页面预览)

| 组件 | 许可证 | 调用方式 |
| --- | --- | --- |
| poppler(pdfinfo、pdftoppm,Homebrew 构建) | GPL-2.0-or-later | 独立进程命令行调用,**不链接、不 import** |
| 其依赖链(freetype、libpng、zlib、libjpeg-turbo、openjpeg 等,由构建脚本收集并重写加载路径) | 各自宽松许可(FTL/BSD/Zlib/GPL 兼容) | 仅被上述二进制动态链接 |

结论:GPL 程序以独立进程 + 命令行参数方式使用,属 mere aggregation;AGPL-3.0-only 的 Studio 代码不因此变成 GPL 衍生作品。
再分发义务:随包提供本审计文件、GPL-2.0 文本与源码获取途径(见下)。

## 4. 其他

| 组件 | 许可证 |
| --- | --- |
| Monaco 0.52.2(已 vendored) | MIT |
| 本项目代码/文档/合成样本 | AGPL-3.0-only(见 LICENSE、THIRD_PARTY_NOTICES.md) |

## 源码获取(written offer)

对应源码的官方来源:
- CPython/PyPI 组件:`pip download <pkg>==<version>` 或各项目仓库;
- Tectonic:https://github.com/tectonic-typesetting/tectonic(tag `tectonic@0.17.0`);
- TeX 资源:Tectonic 官方 bundle(构建说明见上);
- Poppler 及依赖:`brew info poppler` 指向的 Homebrew formula 与上游 https://gitlab.freedesktop.org/poppler/poppler;
- Homebrew 构建脚本:https://github.com/Homebrew/homebrew-core(各 formula)。

如需完整对应源码包,按上表来源自行获取,或联系维护者索取构建时所用的确切版本清单。
