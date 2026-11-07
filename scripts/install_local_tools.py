# 显式安装本地工具:目前支持把固定版本的 Tectonic 下载到 ~/.texada/bin(带 SHA256 校验)。
"""用法::

    .venv/bin/python scripts/install_local_tools.py [--bin-dir DIR] [--status]

仅在显式运行时下载一次;Studio 界面中的「下载 Tectonic」按钮调用同一逻辑。
Poppler(pdfinfo/pdftoppm)仍需系统包管理器安装(macOS:brew install poppler)。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webui"))

import tool_fetch  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="安装 TeXada Studio 的本地工具(当前:Tectonic)")
    parser.add_argument("--bin-dir", type=Path, default=tool_fetch.DEFAULT_BIN_DIR,
                        help="安装目录(默认 ~/.texada/bin)")
    parser.add_argument("--status", action="store_true", help="只查看当前状态,不下载")
    args = parser.parse_args(argv)

    status = tool_fetch.tectonic_status(args.bin_dir)
    if args.status:
        print(f"PATH 可见:{'是' if status['in_path'] else '否'}")
        print(f"本地安装:{status['installed_path'] or '无'}")
        print(f"本地版本:{status['installed_version'] or '无'}")
        return 0

    key = tool_fetch.platform_key()
    print(f"平台:{key or '不受支持'} · 目标目录:{args.bin_dir}")
    print(f"下载 Tectonic {tool_fetch.TECTONIC_VERSION}(官方 Release,SHA256 固定)…")

    def progress(done, total):
        if total:
            print(f"\r已下载 {done // 1024} / {total // 1024} KiB", end="", flush=True)

    try:
        result = tool_fetch.install_tectonic(args.bin_dir, progress=progress)
    except tool_fetch.ToolFetchError as error:
        print(f"\n失败:{error}", file=sys.stderr)
        return 1
    print(f"\n完成:{result['path']}(版本 {result['version']},SHA256 已校验)")
    print("提示:由 run-local-studio.py 启动的 Studio 会自动把该目录加入 PATH;")
    print("      其他环境请自行加入 PATH 或设置 TECTONIC 环境变量。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
