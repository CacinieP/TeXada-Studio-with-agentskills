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
import io
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
TECTONIC = Path.home() / ".texada" / "bin" / "tectonic"
TEX_CACHE = Path.home() / "Library" / "Caches" / "TectonicProject.Tectonic"
POPPLER_DATA_VERSION = "0.4.12"
POPPLER_DATA_SHA256 = "c835b640a40ce357e1b83666aabd95edffa24ddddd49b8daff63adb851cdab74"
LLAMA_MACOS_TAG = "b12631"
LLAMA_MACOS_ARCHIVE = f"llama-{LLAMA_MACOS_TAG}-bin-macos-arm64.tar.gz"
LLAMA_MACOS_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_MACOS_TAG}/{LLAMA_MACOS_ARCHIVE}"
LLAMA_MACOS_SHA256 = "8de65a20e743b27405f05e6f89c636b879fd040fdd2c9abd4730fc0632ca49a5"
LLAMA_MACOS_FALLBACK_NOTICE = (
    f"llama.cpp ({LLAMA_MACOS_TAG})\n"
    "License: MIT License\n"
    f"Pinned binary archive: {LLAMA_MACOS_URL}\n"
    f"SHA256: {LLAMA_MACOS_SHA256}\n"
    "Upstream repository: https://github.com/ggml-org/llama.cpp\n"
)
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


SYSTEM_PREFIXES = ("/usr/lib", "/System", "/Library/Apple")
_DYLD_LOADED_RE = re.compile(r"^dyld\[\d+\]:\s+<[^>]+>\s+(.+)$", re.M)


def _safe_tar_parts(raw_name: str) -> list[str]:
    if not raw_name or "\x00" in raw_name or raw_name.startswith(("/", "\\")):
        raise ValueError(f"拒绝不安全的归档路径:{raw_name!r}")
    parts = [seg for seg in raw_name.replace("\\", "/").split("/") if seg and seg != "."]
    for seg in parts:
        if seg == ".." or ":" in seg:
            raise ValueError(f"拒绝包含路径穿越的归档路径:{raw_name!r}")
    return parts


def extract_llama_server_tar(
    payload: bytes,
    extract_dir: Path,
    licenses_dir: Path,
    *,
    expected_sha256: str | None = None,
) -> Path:
    """校验官方 llama.cpp macOS 归档 SHA-256 并安全解包 llama-server 及其 dylib。"""
    target_sha256 = LLAMA_MACOS_SHA256 if expected_sha256 is None else expected_sha256
    digest = hashlib.sha256(payload).hexdigest()
    if digest != target_sha256:
        raise ValueError(f"llama-server 归档 SHA-256 校验失败:期望 {target_sha256},实际 {digest}")

    extract_root = extract_dir.resolve()
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)
    licenses_dir.mkdir(parents=True, exist_ok=True)

    license_bytes: bytes | None = None
    symlinks: list[tuple[Path, str]] = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = _safe_tar_parts(member.name)
            if not parts or member.isdir():
                continue
            if not (member.isfile() or member.issym()):
                raise ValueError(f"拒绝非常规归档条目:{member.name!r}")
            dest = Path(os.path.normpath(extract_root.joinpath(*parts)))
            if not dest.is_relative_to(extract_root):
                raise ValueError(f"归档条目越界:{member.name!r}")
            basename = parts[-1]
            if member.issym():
                link = member.linkname
                if not link or "\x00" in link or link.startswith(("/", "\\")):
                    raise ValueError(f"拒绝绝对路径符号链接:{member.name!r} -> {link!r}")
                norm_target = Path(os.path.normpath(dest.parent / link))
                if not norm_target.is_relative_to(extract_root):
                    raise ValueError(f"拒绝越界符号链接:{member.name!r} -> {link!r}")
                if basename.endswith(".dylib"):
                    symlinks.append((dest, link))
                continue
            lower = basename.lower()
            if lower.startswith("license") and license_bytes is None:
                stream = archive.extractfile(member)
                if stream is not None:
                    license_bytes = stream.read()
                continue
            if basename == "llama-server" or basename.endswith(".dylib"):
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(stream.read())
                os.chmod(dest, 0o755)

    for dest, link in symlinks:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(link)

    servers = sorted(extract_root.rglob("llama-server"))
    if not servers:
        raise ValueError("llama.cpp 归档内未找到 llama-server。")
    (licenses_dir / "llama.cpp-LICENSE.txt").write_bytes(
        license_bytes if license_bytes is not None else LLAMA_MACOS_FALLBACK_NOTICE.encode("utf-8")
    )
    return servers[0]


def _uses_external_ggml_plugins(binary: Path) -> bool:
    """检测本机 llama-server 是否依赖 ggml 外部 libexec 动态后端插件(如 Homebrew 构建)。"""
    try:
        dependencies, rpaths = _load_commands(binary)
    except (subprocess.CalledProcessError, OSError):
        return False
    owner_dir = binary.resolve().parent
    ggml_libs = []
    has_direct_backend = False
    for entry in dependencies:
        name = Path(entry).name
        if name.startswith(("libggml-metal", "libggml-cpu", "libggml-blas")):
            has_direct_backend = True
        elif name.startswith("libggml.") or name == "libggml.dylib":
            ggml_libs.append(entry)
    if not ggml_libs:
        return False
    for entry in ggml_libs:
        resolved = _resolve_dep(entry, owner_dir, rpaths=rpaths, bin_dir=owner_dir)
        if resolved and Path(resolved).is_file():
            try:
                if b"/libexec" in Path(resolved).read_bytes():
                    return True
            except OSError:
                pass
    return not has_direct_backend


def _fetch_pinned_llama_tar() -> bytes:
    cache_file = Path.home() / ".texada" / "cache" / LLAMA_MACOS_ARCHIVE
    if cache_file.is_file():
        cached = cache_file.read_bytes()
        if hashlib.sha256(cached).hexdigest() == LLAMA_MACOS_SHA256:
            return cached
    with urllib.request.urlopen(LLAMA_MACOS_URL, timeout=180) as response:
        payload = response.read()
    require(hashlib.sha256(payload).hexdigest() == LLAMA_MACOS_SHA256,
            f"{LLAMA_MACOS_ARCHIVE} 的 SHA-256 校验失败")
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, cache_file)
    except OSError:
        pass
    return payload


def verify_bundled_llama_server(llama_bin: Path, staging: Path) -> None:
    """确认捆绑的 llama-server 具备可用计算后端且绝不越界加载包外(如 /opt/homebrew)动态库。"""
    try:
        listed = subprocess.run(
            [str(llama_bin), "--list-devices"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "DYLD_PRINT_LIBRARIES": "1"},
        )
    except OSError as exc:
        raise SystemExit(f"无法执行捆绑的 llama-server({llama_bin}):{exc}") from None
    stdout = listed.stdout or ""
    stderr = listed.stderr or ""
    combined = stdout + "\n" + stderr
    if listed.returncode != 0 or "Available devices:" not in combined or "(none)" in combined:
        print(combined[-2000:], file=sys.stderr)
        raise SystemExit(
            "捆绑的 llama-server 没有可用计算后端或探测失败；请使用带静态/直连后端的官方 llama.cpp 归档后重试，"
            "或去掉 --with-llama-server。"
        )
    staging_prefix = str(staging.resolve()) + os.sep
    leaked = []
    for raw_path in _DYLD_LOADED_RE.findall(combined):
        loaded = raw_path.strip()
        if loaded.startswith(staging_prefix) or loaded.startswith(SYSTEM_PREFIXES):
            continue
        try:
            resolved_loaded = str(Path(loaded).resolve())
        except OSError:
            resolved_loaded = loaded
        if resolved_loaded.startswith(staging_prefix) or resolved_loaded.startswith(SYSTEM_PREFIXES):
            continue
        leaked.append(loaded)
    if leaked:
        print("\n".join(leaked[:20]), file=sys.stderr)
        raise SystemExit(
            f"捆绑的 llama-server 仍依赖包外动态库({leaked[0]})；已拒绝生成不自包含的安装包。"
        )


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
            queue.append((target, Path(source).resolve().parent))
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


def install_poppler_data(staging: Path) -> None:
    archive_name = f"poppler-data-{POPPLER_DATA_VERSION}"
    url = f"https://poppler.freedesktop.org/{archive_name}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="texada-poppler-") as tmp:
        work = Path(tmp)
        archive = work / "poppler-data.tar.gz"
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as target:
            shutil.copyfileobj(response, target)
        require(hashlib.sha256(archive.read_bytes()).hexdigest() == POPPLER_DATA_SHA256,
                "Poppler 字符映射包的 SHA-256 不匹配")
        run(["tar", "-xzf", str(archive), "-C", str(work)])
        source = work / archive_name
        for directory in ("cMap", "cidToUnicode", "nameToUnicode", "unicodeMap"):
            copy_tree(source / directory, staging / "poppler-data" / directory)
        notices = staging / "licenses" / "poppler-data"
        notices.mkdir()
        for license_file in source.glob("COPYING*"):
            shutil.copy2(license_file, notices)


def stage_poppler(staging: Path) -> dict[str, str]:
    pdfinfo = shutil.which("pdfinfo")
    require(pdfinfo is not None, "未找到 pdfinfo;先 brew install poppler")
    prefix = Path(run(["brew", "--prefix", "poppler"], capture_output=True, text=True).stdout.strip())
    target = staging / "bin" / "pdfinfo"
    shutil.copy2(pdfinfo, target)
    target.chmod(0o755)
    renderer = staging / "bin" / "pdftoppm"
    poppler_cpp_lib = prefix / "lib" / "libpoppler-cpp.dylib"
    run(["xcrun", "clang++", "-std=c++17", "-O2", "-mmacosx-version-min=15.0",
         "-I", str(prefix / "include" / "poppler" / "cpp"),
         str(DESKTOP / "poppler_render.cpp"), str(poppler_cpp_lib),
         "-o", str(renderer)])
    install_poppler_data(staging)
    return {
        str(target): str(Path(pdfinfo).resolve()),
        str(renderer): str(poppler_cpp_lib.resolve()),
    }


def bundle_poppler(staging: Path) -> int:
    return bundle_dylibs(staging / "bin", staging / "tools-lib", stage_poppler(staging))


def stage_resources(staging: Path, skip_poppler: bool, with_llama_server: bool = False) -> dict:
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

    originals: dict[str, str] = {}
    smoke: list[tuple[str, str]] = [("tectonic", "--version")]
    if not skip_poppler:
        originals.update(stage_poppler(staging))
        smoke.extend((("pdfinfo", "-v"), ("pdftoppm", "-v")))
    with tempfile.TemporaryDirectory(prefix="texada-llama-") as llama_tmp:
        if with_llama_server:
            destination = staging / "bin" / "llama-server"
            env_tar = os.environ.get("TEXADA_LLAMA_SERVER_TAR", "").strip()
            tool = None if env_tar else shutil.which("llama-server")
            resolved_tool = Path(tool).resolve() if tool is not None else None
            license_file = (
                next((parent / "LICENSE" for parent in resolved_tool.parents[:3] if (parent / "LICENSE").is_file()), None)
                if resolved_tool is not None else None
            )
            if resolved_tool is not None and license_file is not None and not _uses_external_ggml_plugins(resolved_tool):
                shutil.copy2(resolved_tool, destination)
                os.chmod(destination, 0o755)
                originals[str(destination)] = str(resolved_tool)
                shutil.copy2(license_file, staging / "licenses" / "llama.cpp-LICENSE.txt")
            else:
                if env_tar:
                    tar_path = Path(env_tar).expanduser()
                    require(tar_path.is_file(), f"指定的 llama-server 归档不存在:{tar_path}")
                    payload = tar_path.read_bytes()
                else:
                    if tool is not None:
                        print("   检测到本机 llama-server 使用外部动态后端插件，改用官方自包含归档…")
                    else:
                        print(f"   下载官方自包含 llama-server ({LLAMA_MACOS_TAG})…")
                    payload = _fetch_pinned_llama_tar()
                extracted_bin = extract_llama_server_tar(payload, Path(llama_tmp), staging / "licenses")
                shutil.copy2(extracted_bin, destination)
                os.chmod(destination, 0o755)
                originals[str(destination)] = str(extracted_bin.resolve())
            smoke.append(("llama-server", "--version"))
        if originals:
            count = bundle_dylibs(staging / "bin", staging / "tools-lib", originals)
            print(f"   已捆绑 {count} 个非系统动态库")
    for name, flag in smoke:
        run([str(staging / "bin" / name), flag], env={"PATH": "/usr/bin:/bin"})
    if with_llama_server and sys.platform == "darwin":
        verify_bundled_llama_server(staging / "bin" / "llama-server", staging)

    require(TEX_CACHE.is_dir(), "TeX 资源缓存未准备;先运行 scripts/prepare-local-tex.py --download-resources")
    run([sys.executable, str(REPO_ROOT / "scripts" / "prepare-local-tex.py")],
        env={**os.environ, "TECTONIC": str(TECTONIC)})
    copy_tree(TEX_CACHE, staging / "tex-cache", ignore=shutil.ignore_patterns("*.lock", ".DS_Store"))
    (staging / "licenses" / "tex-cache-manifest.sha256").write_text(
        tex_cache_manifest(staging / "tex-cache"), encoding="utf-8")
    for area in ("webui", "tex-cache", "bin", "tools-lib", "poppler-data"):
        path = staging / area
        if path.exists():
            sizes[area] = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return sizes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建自包含 TeXada Studio.app")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--skip-poppler", action="store_true", help="不捆绑 Poppler(PDF 导入/预览仍需系统安装)")
    parser.add_argument("--with-llama-server", action="store_true", help="捆绑自包含 llama.cpp 运行时")
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

    print("① 生成图标…")
    icon = build_icon(workdir)
    if icon is None:
        raise SystemExit("无法生成 Studio 图标：请检查品牌源图、sips 和 iconutil。")

    print("② 收集资源(webui/harness/编译器/TeX 缓存/Poppler)…")
    sizes = stage_resources(staging, args.skip_poppler, args.with_llama_server)
    for area, size in sizes.items():
        print(f"   {area}: {size / 1_048_576:.1f} MiB")

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
    install_app_icon(app, icon)
    seal_app_bundle(app)
    shutil.rmtree(workdir, ignore_errors=True)

    total = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
    print(f"完成:{app}({total / 1_048_576:.0f} MiB)")
    print("拖入 ~/Applications 使用;模型服务仍走设置面板配置的回环端点。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
