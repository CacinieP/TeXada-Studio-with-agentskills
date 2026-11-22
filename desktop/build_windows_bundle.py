# 生成 Windows x64 自包含桌面便携包「TeXada Studio/TeXada Studio.exe」。
"""在已完成以下准备的 Windows x64 构建机上运行(全部显式、带 SHA-256 校验)::

    .venv\\Scripts\\pip install -r webui/requirements.txt -r desktop/requirements.txt pyinstaller
    .venv\\Scripts\\python scripts/install_local_tools.py
    .venv\\Scripts\\python -c "import sys; sys.path.insert(0,'webui'); import tool_fetch; tool_fetch.install_poppler()"
    .venv\\Scripts\\python scripts/prepare-local-tex.py --download-resources

然后::

    .venv\\Scripts\\python desktop/build_windows_bundle.py [--output dist-win] [--skip-poppler] [--with-llama-server]

产物 <output>/TeXada Studio 不再依赖仓库、.venv、包管理器或外网(模型权重仍由用户在设置面板按需下载)。
许可合规:desktop/licenses-audit.md 与各组件许可证随包写入 Resources/licenses/。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
TECTONIC = Path.home() / ".texada" / "bin" / "tectonic.exe"
POPPLER_BIN_DEFAULT = Path.home() / ".texada" / "Library" / "bin"

APP_VERSION = "0.1.1"
FILE_VERSION_TUPLE = (0, 1, 1, 0)

LLAMA_WINDOWS_TAG = "b12631"
LLAMA_WINDOWS_ARCHIVE = f"llama-{LLAMA_WINDOWS_TAG}-bin-win-cpu-x64.zip"
LLAMA_WINDOWS_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_WINDOWS_TAG}/{LLAMA_WINDOWS_ARCHIVE}"
LLAMA_WINDOWS_SHA256 = "8b3639c62c6c41b8134797ea9beedd6b6c26caad6a1ed99a3d5a2802262923d7"

BRAND_CANDIDATES = (
    REPO_ROOT / "assets" / "brand" / "studio-icon-master.png",
    REPO_ROOT / "webui" / "static" / "brand" / "texada-studio-source.png",
    REPO_ROOT / "assets" / "texada-studio-icon.png",
)

PY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "test_*.py", "tests", "*.bak*")

COLLECT_ALL_PACKAGES = (
    "webview",
    "fastapi",
    "starlette",
    "uvicorn",
    "anyio",
    "h11",
    "pydantic",
    "pydantic_core",
    "idna",
    "sympy",
    "mpmath",
    "antlr4",
)
STDLIB_HIDDEN_IMPORTS = (
    "csv",
    "decimal",
    "difflib",
    "hmac",
    "plistlib",
    "runpy",
    "secrets",
    "shlex",
    "tarfile",
    "unicodedata",
    "uuid",
    "webbrowser",
    "xml.etree.ElementTree",
    "zipfile",
)
EXCLUDE_MODULES = ("pip", "setuptools", "tkinter", "numpy", "matplotlib", "pytest", "py2app")


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"缺少前置条件:{message}", file=sys.stderr)
        raise SystemExit(2)


def run(argv, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, **kwargs)


def copy_tree(source: Path, target: Path, ignore=PY_IGNORE) -> None:
    shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def _decode_rgba8_png(png: bytes) -> tuple[int, int, bytes] | None:
    if len(png) < 33 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("图标源文件不是合法的 PNG。")
    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    while pos + 8 <= len(png):
        length, ctype = struct.unpack(">I4s", png[pos:pos + 8])
        chunk = png[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _comp, _flt, interlace = struct.unpack(">IIBBBBB", chunk)
        elif ctype == b"IDAT":
            idat.extend(chunk)
        elif ctype == b"IEND":
            break
    if width <= 0 or height <= 0:
        raise ValueError("PNG IHDR 尺寸无效。")
    if bit_depth != 8 or color_type != 6 or interlace != 0:
        return None
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out = bytearray(width * height * 4)
    offset = 0
    for y in range(height):
        flt = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        prev = out[(y - 1) * stride:y * stride] if y > 0 else bytes(stride)
        if flt == 1:
            for i in range(4, stride):
                row[i] = (row[i] + row[i - 4]) & 0xFF
        elif flt == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif flt == 3:
            for i in range(stride):
                left = row[i - 4] if i >= 4 else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif flt == 4:
            for i in range(stride):
                a = row[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = row
    return width, height, bytes(out)


def _encode_rgba8_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I4s", len(payload), tag) + payload + struct.pack(">I", crc)

    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _downsample_square_rgba(width: int, height: int, rgba: bytes, target: int) -> bytes:
    out = bytearray(target * target * 4)
    idx = 0
    for ty in range(target):
        y0 = (ty * height) // target
        y1 = max(y0 + 1, ((ty + 1) * height) // target)
        for tx in range(target):
            x0 = (tx * width) // target
            x1 = max(x0 + 1, ((tx + 1) * width) // target)
            r = g = b = a = count = 0
            for sy in range(y0, y1):
                row_base = sy * width * 4
                for sx in range(x0, x1):
                    p = row_base + sx * 4
                    r += rgba[p]
                    g += rgba[p + 1]
                    b += rgba[p + 2]
                    a += rgba[p + 3]
                    count += 1
            out[idx] = r // count
            out[idx + 1] = g // count
            out[idx + 2] = b // count
            out[idx + 3] = a // count
            idx += 4
    return bytes(out)


def png_to_ico_bytes(png_bytes: bytes) -> bytes:
    """用纯标准库 struct/zlib 将 PNG 封装为合法 Windows Vista+ PNG-in-ICO(帧上限 256x256)。"""
    if len(png_bytes) < 24 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("图标输入必须是 PNG 字节流。")
    width, height = struct.unpack(">II", png_bytes[16:24])
    frames: list[tuple[int, int, bytes]] = []
    if width <= 256 and height <= 256:
        frames.append((width, height, png_bytes))
    else:
        decoded = _decode_rgba8_png(png_bytes)
        if decoded is None:
            raise ValueError("超过 256px 的图标源图必须是 8-bit 非隔行 RGBA PNG。")
        src_w, src_h, rgba = decoded
        for size in (16, 32, 64, 128, 256):
            scaled = _downsample_square_rgba(src_w, src_h, rgba, size)
            frames.append((size, size, _encode_rgba8_png(size, size, scaled)))

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries = []
    payloads = []
    for frame_w, frame_h, payload in frames:
        w_byte = 0 if frame_w >= 256 else frame_w
        h_byte = 0 if frame_h >= 256 else frame_h
        entries.append(struct.pack("<BBBBHHII", w_byte, h_byte, 0, 0, 1, 32, len(payload), offset))
        payloads.append(payload)
        offset += len(payload)
    return b"".join([header, *entries, *payloads])


def _resolve_brand_png(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_file() else None
    return next((candidate for candidate in BRAND_CANDIDATES if candidate.is_file()), None)


def build_icon(workdir: Path, source_png: Path | None = None) -> Path | None:
    src = _resolve_brand_png(source_png)
    if src is None:
        return None
    workdir.mkdir(parents=True, exist_ok=True)
    ico_path = workdir / "AppIcon.ico"
    ico_path.write_bytes(png_to_ico_bytes(src.read_bytes()))
    return ico_path


def write_version_file(workdir: Path) -> Path:
    v1, v2, v3, v4 = FILE_VERSION_TUPLE
    dotted = f"{v1}.{v2}.{v3}.{v4}"
    content = (
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers=({v1}, {v2}, {v3}, {v4}), prodvers=({v1}, {v2}, {v3}, {v4}), "
        "mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable('040904B0', [\n"
        "        StringStruct('CompanyName', 'TeXada Project'),\n"
        "        StringStruct('FileDescription', 'TeXada Studio Local LaTeX Workbench'),\n"
        f"        StringStruct('FileVersion', '{dotted}'),\n"
        "        StringStruct('InternalName', 'TeXada Studio'),\n"
        "        StringStruct('OriginalFilename', 'TeXada Studio.exe'),\n"
        "        StringStruct('ProductName', 'TeXada Studio'),\n"
        f"        StringStruct('ProductVersion', '{APP_VERSION}')\n"
        "      ])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    target = workdir / "version_info.txt"
    target.write_text(content, encoding="utf-8")
    return target


def tex_cache_manifest(cache: Path) -> str:
    lines = []
    for path in sorted(item for item in cache.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(cache).as_posix()}")
    return "\n".join(lines) + ("\n" if lines else "")


def _safe_zip_parts(raw_name: str) -> list[str]:
    if not raw_name or "\x00" in raw_name or raw_name.startswith(("/", "\\")):
        raise ValueError(f"拒绝不安全的压缩包路径:{raw_name!r}")
    parts = [seg for seg in raw_name.replace("\\", "/").split("/") if seg and seg != "."]
    for seg in parts:
        if seg == ".." or ":" in seg:
            raise ValueError(f"拒绝包含路径穿越或盘符的压缩包路径:{raw_name!r}")
    return parts


def _write_flat(directory: Path, filename: str, payload: bytes) -> Path:
    if "/" in filename or "\\" in filename or filename in {"", ".", ".."} or ":" in filename:
        raise ValueError(f"非法目标文件名:{filename!r}")
    resolved_dir = directory.resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    target = (resolved_dir / filename).resolve()
    if target.parent != resolved_dir:
        raise ValueError("目标文件路径超出目录边界。")
    tmp = target.with_name(f".{filename}.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, target)
    return target


LLAMA_FALLBACK_NOTICE = (
    f"llama.cpp ({LLAMA_WINDOWS_TAG})\n"
    "License: MIT License\n"
    f"Pinned binary archive: {LLAMA_WINDOWS_URL}\n"
    f"SHA256: {LLAMA_WINDOWS_SHA256}\n"
    "Upstream repository: https://github.com/ggml-org/llama.cpp\n"
)


def extract_llama_server_zip(
    payload: bytes,
    bin_dir: Path,
    licenses_dir: Path,
    *,
    expected_sha256: str | None = None,
) -> Path:
    target_sha256 = LLAMA_WINDOWS_SHA256 if expected_sha256 is None else expected_sha256
    digest = hashlib.sha256(payload).hexdigest()
    if digest != target_sha256:
        raise ValueError(f"llama-server ZIP SHA-256 校验失败:期望 {target_sha256},实际 {digest}")

    binaries: list[tuple[str, bytes]] = []
    license_bytes: bytes | None = None
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            parts = _safe_zip_parts(info.filename)
            if info.is_dir() or not parts:
                continue
            basename = parts[-1]
            lower = basename.lower()
            if lower == "llama-server.exe" or lower.endswith(".dll"):
                binaries.append((basename, archive.read(info)))
            elif lower.startswith("license") and license_bytes is None:
                license_bytes = archive.read(info)

    if not any(name.lower() == "llama-server.exe" for name, _ in binaries):
        raise ValueError("llama.cpp 压缩包内未找到 llama-server.exe。")

    for basename, data in binaries:
        _write_flat(bin_dir, basename, data)

    _write_flat(
        licenses_dir,
        "llama.cpp-LICENSE.txt",
        license_bytes if license_bytes is not None else LLAMA_FALLBACK_NOTICE.encode("utf-8"),
    )
    return bin_dir / "llama-server.exe"


def stage_llama_server(staging: Path, *, fetch=None, archive_path: Path | None = None) -> Path:
    bin_dir = staging / "bin"
    lic_dir = staging / "licenses"
    env_zip = os.environ.get("TEXADA_LLAMA_SERVER_ZIP", "").strip()
    chosen_zip = archive_path or (Path(env_zip) if env_zip else None)
    if chosen_zip is not None:
        require(chosen_zip.is_file(), f"指定的 llama-server 压缩包不存在:{chosen_zip}")
        return extract_llama_server_zip(chosen_zip.read_bytes(), bin_dir, lic_dir)

    if fetch is None:
        local_tool = shutil.which("llama-server.exe") or shutil.which("llama-server")
        if not local_tool:
            candidate = Path.home() / ".texada" / "bin" / "llama-server.exe"
            if candidate.is_file():
                local_tool = str(candidate)
        if local_tool and Path(local_tool).name.lower() == "llama-server.exe":
            resolved = Path(local_tool).resolve()
            _write_flat(bin_dir, "llama-server.exe", resolved.read_bytes())
            for dll in resolved.parent.glob("*.dll"):
                if dll.is_file():
                    _write_flat(bin_dir, dll.name, dll.read_bytes())
            lic_src = next(
                (parent / name for parent in (resolved.parent, *resolved.parents[:3])
                 for name in ("LICENSE", "LICENSE.txt") if (parent / name).is_file()),
                None,
            )
            _write_flat(
                lic_dir,
                "llama.cpp-LICENSE.txt",
                lic_src.read_bytes() if lic_src is not None else LLAMA_FALLBACK_NOTICE.encode("utf-8"),
            )
            return bin_dir / "llama-server.exe"

    payload = (fetch or _http_get)(LLAMA_WINDOWS_URL)
    return extract_llama_server_zip(payload, bin_dir, lic_dir)


def stage_poppler_windows(staging: Path, *, poppler_bin: Path | None = None) -> None:
    bin_source = poppler_bin
    if bin_source is None:
        fallback_flat = Path.home() / ".texada" / "bin"
        if (POPPLER_BIN_DEFAULT / "pdfinfo.exe").is_file() and (POPPLER_BIN_DEFAULT / "pdftoppm.exe").is_file():
            bin_source = POPPLER_BIN_DEFAULT
        elif (fallback_flat / "pdfinfo.exe").is_file() and (fallback_flat / "pdftoppm.exe").is_file():
            bin_source = fallback_flat
        else:
            found = shutil.which("pdfinfo.exe") or shutil.which("pdfinfo")
            require(found is not None, "未找到 Poppler Windows(pdfinfo.exe);请先调用 tool_fetch.install_poppler()")
            bin_source = Path(found).resolve().parent

    require(
        (bin_source / "pdfinfo.exe").is_file() and (bin_source / "pdftoppm.exe").is_file(),
        f"Poppler 目录缺少 pdfinfo.exe 或 pdftoppm.exe:{bin_source}",
    )
    # Conda-forge win64 poppler.dll resolves CJK maps at <dll_dir>\..\..\share\poppler,
    # so stage Poppler into Resources/Library/bin paired with Resources/share/poppler.
    poppler_target_bin = staging / "Library" / "bin"
    poppler_target_bin.mkdir(parents=True, exist_ok=True)
    for item in bin_source.iterdir():
        if item.is_file() and item.suffix.lower() in {".exe", ".dll"} and item.name.lower() != "tectonic.exe":
            shutil.copy2(item, poppler_target_bin / item.name)

    share_candidates = (
        bin_source.parent / "share" / "poppler",
        bin_source.parent.parent / "share" / "poppler",
    )
    share_src = next((cand for cand in share_candidates if cand.is_dir()), None)
    require(share_src is not None, "未找到 Poppler CJK 字符映射目录(share/poppler)")
    copy_tree(share_src, staging / "share" / "poppler", ignore=shutil.ignore_patterns(".DS_Store"))

    lic_target = staging / "licenses" / "poppler-windows"
    lic_target.mkdir(parents=True, exist_ok=True)
    lic_src = next(
        (cand for cand in (bin_source.parent / "licenses" / "poppler-windows",
                           bin_source.parent.parent / "licenses" / "poppler-windows") if cand.is_dir()),
        None,
    )
    if lic_src is not None:
        for item in lic_src.iterdir():
            if item.is_file():
                shutil.copy2(item, lic_target / item.name)
    else:
        (lic_target / "NOTICE.txt").write_text(
            "Poppler Windows (GPL-2.0-or-later, invoked strictly via separate CLI subprocesses).\n"
            "Upstream: https://github.com/oschwartz10612/poppler-windows and "
            "https://gitlab.freedesktop.org/poppler/poppler\n",
            encoding="utf-8",
        )


def _resolve_tectonic_exe() -> Path:
    override = os.environ.get("TECTONIC", "").strip()
    if override and Path(override).is_file():
        return Path(override).resolve()
    if TECTONIC.is_file():
        return TECTONIC
    which_hit = shutil.which("tectonic.exe") or shutil.which("tectonic")
    if which_hit:
        return Path(which_hit).resolve()
    return TECTONIC


def _resolve_tex_cache() -> Path:
    override = os.environ.get("TECTONIC_CACHE_DIR", "").strip()
    if override and Path(override).is_dir():
        return Path(override).resolve()
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    candidates = (
        local_appdata / "TectonicProject" / "Tectonic" / "Cache",
        local_appdata / "TectonicProject" / "Tectonic" / "cache",
        local_appdata / "TectonicProject" / "Tectonic",
        local_appdata / "Tectonic" / "cache",
        local_appdata / "Tectonic",
    )
    for candidate in candidates:
        if (candidate / "bundles").is_dir():
            return candidate
    return candidates[0]


def minimal_smoke_env() -> dict[str, str]:
    if os.name != "nt":
        return {"PATH": "/usr/bin:/bin"}
    sys_root = os.environ.get("SystemRoot") or r"C:\Windows"
    temp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home())
    return {
        "SystemRoot": sys_root,
        "WINDIR": sys_root,
        "PATH": f"{sys_root}\\System32;{sys_root}",
        "TEMP": temp_dir,
        "TMP": temp_dir,
    }


def stage_resources(
    staging: Path,
    skip_poppler: bool = False,
    with_llama_server: bool = False,
    *,
    fetch=None,
    llama_zip: Path | None = None,
) -> dict[str, int]:
    """把 Windows 自包含包所需源码、编译器、Poppler、可选 llama-server 与预热 TeX 缓存装入 staging。"""
    sizes: dict[str, int] = {}
    copy_tree(REPO_ROOT / "webui", staging / "webui")
    copy_tree(REPO_ROOT / "harness", staging / "harness")
    copy_tree(REPO_ROOT / "skills", staging / "skills")
    copy_tree(REPO_ROOT / "samples" / "docs", staging / "samples" / "docs")
    (staging / "scripts").mkdir(parents=True, exist_ok=True)
    for name in ("run-local-studio.py", "prepare-local-tex.py", "install_local_tools.py", "start-local-studio.bat"):
        src_script = REPO_ROOT / "scripts" / name
        if src_script.is_file():
            shutil.copy2(src_script, staging / "scripts" / name)
    (staging / "desktop").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DESKTOP / "app.py", staging / "desktop" / "app.py")
    (staging / "licenses").mkdir(parents=True, exist_ok=True)
    for doc in ("README.md", "licenses-audit.md"):
        source = DESKTOP / doc
        if source.is_file():
            shutil.copy2(source, staging / "licenses" / doc)

    (staging / "bin").mkdir(parents=True, exist_ok=True)
    tectonic_src = _resolve_tectonic_exe()
    require(tectonic_src.is_file(), "Tectonic 未安装;先运行 scripts/install_local_tools.py")
    shutil.copy2(tectonic_src, staging / "bin" / "tectonic.exe")

    smoke: list[tuple[Path, str]] = [(staging / "bin" / "tectonic.exe", "--version")]
    if not skip_poppler:
        stage_poppler_windows(staging)
        smoke.extend((
            (staging / "Library" / "bin" / "pdfinfo.exe", "-v"),
            (staging / "Library" / "bin" / "pdftoppm.exe", "-v"),
        ))
    if with_llama_server:
        try:
            stage_llama_server(staging, fetch=fetch, archive_path=llama_zip)
        except ValueError as exc:
            require(False, str(exc))
        smoke.append((staging / "bin" / "llama-server.exe", "--version"))

    smoke_env = minimal_smoke_env()
    for exe_path, flag in smoke:
        run([str(exe_path), flag], env=smoke_env, capture_output=True)

    tex_cache = _resolve_tex_cache()
    require(tex_cache.is_dir(), "TeX 资源缓存未准备;先运行 scripts/prepare-local-tex.py --download-resources")
    run(
        [sys.executable, str(REPO_ROOT / "scripts" / "prepare-local-tex.py")],
        env={**os.environ, "TECTONIC": str(tectonic_src), "TECTONIC_CACHE_DIR": str(tex_cache)},
    )
    copy_tree(tex_cache, staging / "tex-cache", ignore=shutil.ignore_patterns("*.lock", ".DS_Store"))
    (staging / "licenses" / "tex-cache-manifest.sha256").write_text(
        tex_cache_manifest(staging / "tex-cache"),
        encoding="utf-8",
    )
    for area in ("webui", "tex-cache", "bin", "Library", "share"):
        path = staging / area
        if path.exists():
            sizes[area] = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return sizes


def _resolve_build_python() -> Path:
    venv_py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return venv_py if venv_py.is_file() else Path(sys.executable).resolve()


def pyinstaller_command(
    python_exe: Path,
    *,
    icon_path: Path,
    version_file: Path,
    dist_dir: Path,
    work_dir: Path,
    spec_dir: Path,
) -> list[str]:
    cmd = [
        str(python_exe),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "TeXada Studio",
        "--icon",
        str(icon_path),
        "--version-file",
        str(version_file),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
    ]
    for pkg in COLLECT_ALL_PACKAGES:
        cmd.extend(("--collect-all", pkg))
    for mod in STDLIB_HIDDEN_IMPORTS:
        cmd.extend(("--hidden-import", mod))
    for excluded in EXCLUDE_MODULES:
        cmd.extend(("--exclude-module", excluded))
    cmd.append(str(DESKTOP / "windows_entry.py"))
    return cmd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建 Windows x64 自包含 TeXada Studio 桌面包")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist-win")
    parser.add_argument("--skip-poppler", action="store_true", help="不捆绑 Poppler Windows")
    parser.add_argument("--with-llama-server", action="store_true", help="捆绑官方固定版本 llama-server.exe")
    parser.add_argument("--llama-zip", type=Path, help="预下载的官方 llama-b12631-bin-win-cpu-x64.zip 路径")
    args = parser.parse_args(argv)
    args.output = args.output.expanduser().resolve()
    require(sys.platform == "win32", "Windows 自包含包必须在 Windows 上构建")

    build_python = _resolve_build_python()
    require(build_python.exists(), "未找到构建用 Python 解释器")
    for module in ("PyInstaller", "webview"):
        probe = subprocess.run([str(build_python), "-c", f"import {module}"], capture_output=True)
        require(probe.returncode == 0, f"Python 环境缺少 {module};请安装 desktop/requirements.txt 与 pyinstaller")

    workdir = args.output / ".bundle-work"
    if workdir.exists():
        shutil.rmtree(workdir)
    staging = workdir / "Resources"
    staging.mkdir(parents=True)

    print("① 生成 Windows 多尺寸图标与版本元数据…")
    icon = build_icon(workdir)
    if icon is None:
        raise SystemExit("无法生成 Studio 图标:未找到品牌源 PNG。")
    version_file = write_version_file(workdir)

    print("② 收集资源(webui/harness/skills/Tectonic/Poppler/TeX 缓存)…")
    sizes = stage_resources(
        staging,
        skip_poppler=args.skip_poppler,
        with_llama_server=args.with_llama_server,
        llama_zip=args.llama_zip,
    )
    for area, size in sizes.items():
        print(f"   {area}: {size / 1_048_576:.1f} MiB")

    print("③ PyInstaller 冻结 Windows 桌面入口…")
    pyi_dist = workdir / "pyi-dist"
    pyi_work = workdir / "pyi-work"
    pyi_spec = workdir / "pyi-spec"
    run(
        pyinstaller_command(
            build_python,
            icon_path=icon,
            version_file=version_file,
            dist_dir=pyi_dist,
            work_dir=pyi_work,
            spec_dir=pyi_spec,
        ),
        cwd=str(workdir),
    )

    produced = pyi_dist / "TeXada Studio"
    require((produced / "TeXada Studio.exe").is_file(), "PyInstaller 未产出 TeXada Studio.exe")
    app_dir = args.output / "TeXada Studio"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    shutil.move(str(produced), str(app_dir))

    print("④ 合入自包含 Resources…")
    shutil.copy2(icon, staging / "AppIcon.ico")
    shutil.move(str(staging), str(app_dir / "Resources"))
    shutil.rmtree(workdir, ignore_errors=True)

    total = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file())
    print(f"完成:{app_dir}({total / 1_048_576:.0f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
