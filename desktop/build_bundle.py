# 生成自包含「TeXada Studio.app」:内嵌 Python 运行时、服务端依赖、Tectonic、TeX 资源缓存与 Poppler。
"""在已完成以下准备的机器上运行(全部显式、一次)::

    .venv/bin/pip install py2app pywebview            # 构建依赖
    .venv/bin/python scripts/install_local_tools.py    # Tectonic → ~/.texada/bin
    brew install poppler                               # Poppler(动态库由内置收集器捆绑并重签名)
    .venv/bin/python scripts/prepare-local-tex.py --download-resources   # TeX 缓存

然后::

    .venv/bin/python desktop/build_bundle.py [--output dist] [--skip-poppler]

产物 <output>/TeXada Studio.app 不再依赖仓库、venv、brew 或网络(模型服务仍为可选的外部回环端)。
许可合规:desktop/licenses-audit.md 列出全部捆绑组件;其副本随包写入 Resources/licenses/。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
TECTONIC = Path.home() / ".texada" / "bin" / "tectonic"
TEX_CACHE = Path.home() / "Library" / "Caches" / "TectonicProject.Tectonic"
BRAND_SOURCE = REPO_ROOT / "webui" / "static" / "brand" / "texada-studio-source.png"

PY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "test_*.py", "tests", "*.bak*")


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"缺少前置条件:{message}", file=sys.stderr)
        raise SystemExit(2)


def run(argv, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, **kwargs)


def copy_tree(source: Path, target: Path, ignore=PY_IGNORE) -> None:
    shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)


ICONSET_SPECS = (
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
)


def build_icon(workdir: Path) -> Path | None:
    iconset, icns = workdir / "AppIcon.iconset", workdir / "AppIcon.icns"
    if shutil.which("sips") is None or shutil.which("iconutil") is None or not BRAND_SOURCE.exists():
        return None
    iconset.mkdir(parents=True, exist_ok=True)
    for size, filename in ICONSET_SPECS:
        run(["sips", "-z", str(size), str(size), str(BRAND_SOURCE), "--out", str(iconset / filename)],
            capture_output=True)
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], capture_output=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return icns if icns.exists() else None


def install_app_icon(app: Path, icon: Path) -> None:
    """Point the bundle at the brand icon. py2app leaves CFBundleIconFile on PythonApplet."""
    resources = app / "Contents" / "Resources"
    resources.mkdir(parents=True, exist_ok=True)
    destination = resources / "AppIcon.icns"
    if icon.resolve() != destination.resolve():
        shutil.copy2(icon, destination)
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    plist["CFBundleIconFile"] = "AppIcon"
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle)


def seal_app_bundle(app: Path) -> None:
    """合入资源并改写 Info.plist 后,py2app 的签名失效,ad-hoc 重签整包。"""
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", "--timestamp=none", str(app)],
        check=True,
    )


SYSTEM_PREFIXES = ("/usr/lib", "/System")


def _otool(argv: list) -> str:
    return subprocess.run(["otool", *argv], check=True, capture_output=True, text=True).stdout


def _load_commands(binary: Path):
    """返回 (依赖列表, rpath 列表);解析 otool -L 与 LC_RPATH(path 在 cmd 的后续行)。"""
    dependencies, rpaths = [], []
    for line in _otool(["-L", str(binary)]).splitlines()[1:]:
        entry = line.strip().split(" (compatibility")[0].strip()
        if not entry or entry == str(binary):
            continue
        dependencies.append(entry)
    lines = _otool(["-l", str(binary)]).splitlines()
    for index, line in enumerate(lines):
        if "cmd LC_RPATH" not in line:
            continue
        for follow in lines[index + 1:index + 5]:
            if " path " in follow:
                rpaths.append(follow.strip().split("path ", 1)[1].split(" (offset")[0])
                break
    return dependencies, rpaths


def _resolve_dep(
    entry: str,
    owner_source_dir: Path,
    rpaths: list | None = None,
    bin_dir: Path | None = None,
) -> str | None:
    owner_dir = Path(owner_source_dir)
    if entry.startswith("@rpath/"):
        rel = entry.removeprefix("@rpath/")
        for rpath in rpaths or ():
            expanded = rpath.replace("@loader_path", str(owner_dir))
            if bin_dir is not None:
                expanded = expanded.replace("@executable_path", str(bin_dir))
            candidate = (Path(expanded) / rel).resolve()
            if candidate.exists():
                return str(candidate)
        return None
    if entry.startswith("@loader_path/"):
        candidate = (owner_dir / entry.removeprefix("@loader_path/")).resolve()
        return str(candidate) if candidate.exists() else None
    if entry.startswith(("@executable_path", "@loader_path")):
        return None
    candidate = Path(entry)
    return str(candidate.resolve()) if candidate.exists() else None


def bundle_dylibs(bin_dir: Path, lib_dir: Path, originals: dict | None = None) -> int:
    """递归收集非系统动态库到 lib_dir,并把引用重写为 @executable_path/../<lib_dir 名>。

    替代 dylibbundler(其对 Homebrew rpath 链会死循环):otool 发现 + install_name_tool 重写。
    @rpath 与 @loader_path 按**原始二进制**目录展开(@executable_path 按捆绑 bin);
    originals 提供 {staging 副本: 原始路径},缺省用副本自身位置。
    """
    lib_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"@executable_path/../{lib_dir.name}/"
    originals = originals or {}
    relocated: dict[str, Path] = {}

    def is_system(path: str) -> bool:
        return path.startswith(SYSTEM_PREFIXES)

    def re_sign(binary: Path) -> None:
        # install_name_tool 改写会使原签名失效,macOS 会 SIGKILL;ad-hoc 重签恢复可执行。
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(binary)],
                       check=True, capture_output=True)

    queue = [(item, Path(originals.get(str(item), str(item))).resolve().parent) for item in bin_dir.iterdir()
             if item.is_file() and not item.name.endswith((".txt", ".version"))]
    processed: set[str] = set()
    seen_sources: set[str] = set()
    while queue:
        binary, loader_dir = queue.pop()
        if str(binary) in processed:
            continue
        processed.add(str(binary))
        try:
            dependencies, rpaths = _load_commands(binary)
        except subprocess.CalledProcessError:
            continue  # 非 Mach-O(脚本等)
        for entry in dependencies:
            source = _resolve_dep(entry, loader_dir, rpaths=rpaths, bin_dir=bin_dir)
            if source is None or is_system(source) or source in seen_sources:
                continue
            seen_sources.add(source)
            target = lib_dir / Path(source).name
            if not target.exists():
                shutil.copy2(source, target)
                os.chmod(target, 0o755)
            relocated[source] = target
            queue.append((target, Path(source).parent))
        for entry in dependencies:
            source = _resolve_dep(entry, loader_dir, rpaths=rpaths, bin_dir=bin_dir)
            if source is None or is_system(source):
                continue
            target = relocated.get(source) or lib_dir / Path(source).name
            new_name = prefix + target.name
            if entry != new_name:
                subprocess.run(["install_name_tool", "-change", entry, new_name, str(binary)],
                               check=True, capture_output=True)
        if lib_dir == binary.parent:
            subprocess.run(["install_name_tool", "-id", prefix + binary.name, str(binary)],
                           check=True, capture_output=True)
        re_sign(binary)
    return len(relocated)


def tex_cache_manifest(cache: Path) -> str:
    """按实际打进应用的缓存现写 SHA256 清单,避免换机器后沿用另一份缓存的记录。"""
    lines = []
    for path in sorted(item for item in cache.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(cache).as_posix()}")
    return "\n".join(lines) + ("\n" if lines else "")


def stage_resources(staging: Path, skip_poppler: bool) -> dict:
    """把运行所需源码与数据放进 staging(其后整体合并进 .app/Contents/Resources)。"""
    sizes = {}
    copy_tree(REPO_ROOT / "webui", staging / "webui")
    copy_tree(REPO_ROOT / "harness", staging / "harness")
    copy_tree(REPO_ROOT / "skills", staging / "skills")
    copy_tree(REPO_ROOT / "samples" / "docs", staging / "samples" / "docs")
    (staging / "scripts").mkdir(parents=True)
    for name in ("run-local-studio.py", "prepare-local-tex.py", "install_local_tools.py"):
        shutil.copy2(REPO_ROOT / "scripts" / name, staging / "scripts" / name)
    (staging / "desktop").mkdir(parents=True)
    shutil.copy2(DESKTOP / "app.py", staging / "desktop" / "app.py")
    (staging / "licenses").mkdir(parents=True, exist_ok=True)
    for doc in ("README.md", "licenses-audit.md"):
        source = DESKTOP / doc
        if source.exists():
            shutil.copy2(source, staging / "licenses" / doc)

    (staging / "bin").mkdir()
    require(TECTONIC.exists(), "Tectonic 未安装;先运行 scripts/install_local_tools.py")
    shutil.copy2(TECTONIC, staging / "bin" / "tectonic")
    os.chmod(staging / "bin" / "tectonic", 0o755)

    if not skip_poppler:
        originals = {}
        for name in ("pdfinfo", "pdftoppm"):
            tool = shutil.which(name)
            require(tool is not None, f"未找到 {name};先 brew install poppler")
            shutil.copy2(tool, staging / "bin" / name)
            os.chmod(staging / "bin" / name, 0o755)
            originals[str(staging / "bin" / name)] = str(Path(tool).resolve())
        count = bundle_dylibs(staging / "bin", staging / "tools-lib", originals)
        print(f"   已捆绑 {count} 个非系统动态库")

    require(TEX_CACHE.is_dir(), "TeX 资源缓存未准备;先运行 scripts/prepare-local-tex.py --download-resources")
    copy_tree(TEX_CACHE, staging / "tex-cache", ignore=shutil.ignore_patterns("*.lock", ".DS_Store"))
    (staging / "licenses" / "tex-cache-manifest.sha256").write_text(
        tex_cache_manifest(staging / "tex-cache"), encoding="utf-8")
    for area in ("webui", "tex-cache", "bin", "tools-lib"):
        path = staging / area
        if path.exists():
            sizes[area] = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return sizes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建自包含 TeXada Studio.app")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--skip-poppler", action="store_true", help="不捆绑 Poppler(PDF 导入/预览仍需系统安装)")
    args = parser.parse_args(argv)
    args.output = args.output.expanduser().resolve()  # py2app 子进程以 desktop/ 为 cwd,必须绝对路径
    require(sys.platform == "darwin", "自包含包仅支持 macOS")
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    require(venv_python.exists(), "未找到 .venv;请先准备虚拟环境与依赖")
    for module in ("py2app", "webview"):
        probe = subprocess.run([str(venv_python), "-c", f"import {module}"], capture_output=True)
        require(probe.returncode == 0, f".venv 缺少 {module};pip install -r desktop/requirements.txt 与 py2app")

    probe = subprocess.run([str(venv_python), "-c",
                            "import zlib; assert getattr(zlib, '__file__', None)"], capture_output=True)
    require(probe.returncode == 0,
            "当前 Python 的 zlib 是内置模块,与 py2app 不兼容;请用 Homebrew/官方 framework Python 创建 .venv 后重试")

    workdir = args.output / ".bundle-work"
    if workdir.exists():
        shutil.rmtree(workdir)
    staging = workdir / "Resources"
    staging.mkdir(parents=True)

    print("① 收集资源(webui/harness/编译器/TeX 缓存/Poppler)…")
    sizes = stage_resources(staging, args.skip_poppler)
    for area, size in sizes.items():
        print(f"   {area}: {size / 1_048_576:.1f} MiB")

    print("② 生成图标…")
    icon = build_icon(workdir)
    if icon is None:
        print("   跳过(sips/iconutil 或源图缺失)")

    print("③ py2app 冻结程序部分(首次较慢)…")
    py2app_dist = workdir / "py2app-dist"
    py2app_build = workdir / "py2app-build"
    run([str(venv_python), str(DESKTOP / "setup_bundle.py"), "py2app",
         "--bdist-base", str(py2app_build),
         "--dist-dir", str(py2app_dist), "--no-strip"], cwd=str(DESKTOP))
    produced = next(path for path in py2app_dist.iterdir() if path.suffix == ".app")
    app = args.output / "TeXada Studio.app"
    if app.exists():
        shutil.rmtree(app)
    produced.rename(app)

    print("④ 合入资源…")
    resources = app / "Contents" / "Resources"
    for item in staging.iterdir():
        shutil.move(str(item), str(resources / item.name))
    if icon is not None:
        install_app_icon(app, icon)
    seal_app_bundle(app)
    shutil.rmtree(workdir, ignore_errors=True)

    total = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
    print(f"完成:{app}({total / 1_048_576:.0f} MiB)")
    print("拖入 ~/Applications 使用;模型服务仍走设置面板配置的回环端点。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
