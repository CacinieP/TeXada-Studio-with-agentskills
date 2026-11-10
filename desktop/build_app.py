# 在本机生成「TeXada Studio.app」:绑定当前仓库检出与 .venv,不打包 Python/模型/TeX 资源。
"""生成本地 macOS 应用包(纯标准库)::

    .venv/bin/python desktop/build_app.py [--output PATH] [--skip-icon] [--allow-missing-venv]

产物是一个薄壳 .app:可执行文件回指**当前仓库检出**与其 ``.venv``;
移动仓库或重建虚拟环境后需重新生成。图标用 ``iconutil/sips`` 从
``webui/static/brand/texada-studio-source.png`` 生成,非 macOS 或缺工具时用 ``--skip-icon``。
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAND_SOURCE = REPO_ROOT / "webui" / "static" / "brand" / "texada-studio-source.png"
APP_NAME = "TeXada Studio"
BUNDLE_ID = "local.texada.studio"

INFO_PLIST = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
    <key>CFBundleExecutable</key><string>TeXadaStudio</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundleName</key><string>{APP_NAME}</string>
    <key>CFBundleDisplayName</key><string>{APP_NAME}</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSSupportsAutomaticTermination</key><false/>
    <key>NSSupportsSuddenTermination</key><false/>
</dict>
</plist>
"""

SHIM_TEMPLATE = """#!/bin/bash
# 由 desktop/build_app.py 生成;绑定构建时的仓库检出,移动仓库后请重新生成。
REPO_DIR={repo_shell}
PYTHON="$REPO_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  osascript -e 'display alert "TeXada Studio" message "未找到 .venv/bin/python。请在仓库内执行 python3 -m venv .venv 并安装依赖后重试。" as critical' >/dev/null 2>&1
  exit 1
fi
exec "$PYTHON" "$REPO_DIR/desktop/app.py" "$@"
"""


def build_icon(iconset_dir: Path, icns_path: Path) -> bool:
    """用 sips+iconutil 生成 icns;工具缺失时返回 False。"""
    if not BRAND_SOURCE.exists():
        return False
    if shutil.which("sips") is None or shutil.which("iconutil") is None:
        return False
    iconset_dir.mkdir(parents=True)
    for size in (16, 32, 64, 128, 256, 512):
        subprocess.run(["sips", "-z", str(size), str(size), str(BRAND_SOURCE),
                        "--out", str(iconset_dir / f"icon_{size}x{size}.png")],
                       check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
                   check=True, capture_output=True)
    return True


def build(output: Path, skip_icon: bool, allow_missing_venv: bool) -> int:
    if sys.platform != "darwin":
        print("应用包生成仅支持 macOS;其他平台请直接运行 scripts/run-local-studio.py。", file=sys.stderr)
        return 1
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists() and not allow_missing_venv:
        print(f"未找到 {venv_python};请先创建虚拟环境并安装依赖。", file=sys.stderr)
        return 1

    app = output / f"{APP_NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    macos_dir = app / "Contents" / "MacOS"
    resources_dir = app / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")

    shim = macos_dir / "TeXadaStudio"
    shim.write_text(SHIM_TEMPLATE.format(repo_shell=shlex.quote(str(REPO_ROOT))), encoding="utf-8")
    shim.chmod(0o755)

    icon_ready = False
    if not skip_icon:
        try:
            icon_ready = build_icon(resources_dir / "AppIcon.iconset", resources_dir / "AppIcon.icns")
        except subprocess.CalledProcessError:
            icon_ready = False
        finally:
            iconset = resources_dir / "AppIcon.iconset"
            if iconset.exists():
                shutil.rmtree(iconset)
    if not icon_ready:
        print("提示:未生成图标(缺 sips/iconutil 或源图);应用将使用默认图标。")

    print(f"已生成:{app}")
    print("使用:双击打开,或拖入 ~/Applications;/Applications 需管理员权限。")
    print("注意:该应用绑定当前仓库位置与 .venv;移动仓库或重建环境后重新运行本脚本。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 TeXada Studio 本地应用包")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist", help="输出目录(默认 <repo>/dist)")
    parser.add_argument("--skip-icon", action="store_true", help="跳过 icns 图标生成")
    parser.add_argument("--allow-missing-venv", action="store_true", help="允许 .venv 缺失(供测试)")
    args = parser.parse_args(argv)
    return build(args.output, args.skip_icon, args.allow_missing_venv)


if __name__ == "__main__":
    raise SystemExit(main())
