# py2app 构建脚本(仅 desktop/build_bundle.py 调用;产物是自包含 .app 的程序部分)。
"""在 desktop/ 目录下运行::

    .venv/bin/python desktop/setup_bundle.py py2app --dist-dir <dir>

资源(编译器、TeX 缓存、webui/harness 源码等)由 build_bundle.py 在构建后合入 Resources。
"""
import sys

sys.setrecursionlimit(20000)  # modulegraph 扫描 sympy/pydantic 深类型图需要更高上限

from setuptools import setup

APP = ["bundle_entry.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "TeXada Studio",
        "CFBundleDisplayName": "TeXada Studio",
        "CFBundleIdentifier": "local.texada.studio",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "2",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
    },
    # webview 连带 pyobjc 各 framework;服务端框架整包冻结,避免运行期动态导入被 modulegraph 漏掉。
    "packages": ["webview", "fastapi", "starlette", "uvicorn", "anyio", "h11", "pydantic",
                 "idna", "sympy", "mpmath", "antlr4"],
    "excludes": ["pip", "setuptools", "tkinter", "py2app", "macholib", "modulegraph", "altgraph",
                 "httpx", "pylsp", "numpy", "matplotlib"],
}

setup(app=APP, name="TeXada Studio", options={"py2app": OPTIONS})
