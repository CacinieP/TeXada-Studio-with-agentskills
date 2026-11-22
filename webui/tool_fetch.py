# 本地工具自举:按固定版本与 SHA256 把 Tectonic / Windows Poppler 安装到 ~/.texada。
"""仅在用户显式触发时执行一次下载;不在文档处理过程中自动运行。

入口::

    CLI:.venv/bin/python scripts/install_local_tools.py [--bin-dir DIR]
    UI:设置面板「下载 Tectonic / 安装 Poppler」按钮 → POST /api/studio/tools/install

摘要取自 Tectonic 官方 Release(tectonic@0.17.0)与 poppler-windows 官方 Release(v26.09.0-0)。
Poppler 为 GPL-2.0-or-later 独立命令行工具,仅经子进程调用并随附许可证与源码声明。
"""
from __future__ import annotations

import hashlib
import inspect
import io
import os
import platform as platform_module
import secrets
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

TECTONIC_VERSION = "0.17.0"
RELEASE_TAG = f"tectonic@{TECTONIC_VERSION}"
RELEASE_BASE = "https://github.com/tectonic-typesetting/tectonic/releases/download"
# {平台: (资产文件名, SHA256)}
TECTONIC_ASSETS = {
    "darwin-arm64": ("tectonic-0.17.0-aarch64-apple-darwin.tar.gz",
                     "a3f1cac7c5678f01661a92212f58480ae3b0634115d880dbc59e2953ded45667"),
    "darwin-x86_64": ("tectonic-0.17.0-x86_64-apple-darwin.tar.gz",
                      "f4c887268be8ce443de7b4ccb67d6978fe40113ae8872310957693bb80d07ff4"),
    "linux-x86_64": ("tectonic-0.17.0-x86_64-unknown-linux-musl.tar.gz",
                     "8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7"),
    "linux-aarch64": ("tectonic-0.17.0-aarch64-unknown-linux-musl.tar.gz",
                      "b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8"),
    "win32-x86_64": ("tectonic-0.17.0-x86_64-pc-windows-msvc.zip",
                     "f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f"),
}

POPPLER_WINDOWS_VERSION = "26.09.0-0"
POPPLER_WINDOWS_URL = (
    f"https://github.com/oschwartz10612/poppler-windows/releases/download/"
    f"v{POPPLER_WINDOWS_VERSION}/Release-{POPPLER_WINDOWS_VERSION}.zip"
)
POPPLER_WINDOWS_SHA256 = "7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0"

DEFAULT_BIN_DIR = Path.home() / ".texada" / "bin"


class ToolFetchError(RuntimeError):
    """下载或安装本地工具失败的用户可读原因。"""


def tectonic_binary_name(platform_name=None) -> str:
    """平台对应的 Tectonic 可执行文件名。"""
    effective = platform_name if platform_name is not None else sys.platform
    return "tectonic.exe" if effective == "win32" else "tectonic"


def platform_key(platform_name=None, machine=None):
    """映射到预编译资产键;无适配包的平台返回 None。"""
    platform_name = platform_name if platform_name is not None else sys.platform
    machine = machine if machine is not None else platform_module.machine()
    if platform_name == "darwin":
        return "darwin-arm64" if machine == "arm64" else "darwin-x86_64"
    if platform_name.startswith("linux"):
        return "linux-aarch64" if machine == "aarch64" else "linux-x86_64"
    if platform_name == "win32" and machine.lower() in {"amd64", "x86_64"}:
        return "win32-x86_64"
    return None


def tectonic_download_url(key=None):
    key = key if key is not None else platform_key()
    asset = TECTONIC_ASSETS.get(key)
    if asset is None:
        supported = "、".join(sorted(TECTONIC_ASSETS))
        raise ToolFetchError(f"没有适配当前平台的 Tectonic 预编译包(支持:{supported});请自行安装并置于 PATH。")
    return f"{RELEASE_BASE}/{RELEASE_TAG}/{asset[0]}"


def _http_get(url, progress=None):
    """下载完整文件;progress(downloaded, total) 用于界面进度提示。"""
    with urllib.request.urlopen(url, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        chunks, downloaded = [], 0
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress:
                progress(downloaded, total)
    return b"".join(chunks)


def _call_fetch(fetch, url, progress=None):
    getter = fetch or _http_get
    try:
        params = inspect.signature(getter).parameters
    except (TypeError, ValueError):
        return getter(url, progress)
    positional = [
        p for p in params.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params.values())
    if has_varargs or len(positional) >= 2:
        return getter(url, progress)
    return getter(url)


def _extract_tectonic(payload):
    """从发布包(.tar.gz 或 .zip)提取唯一的 tectonic/tectonic.exe;不做磁盘路径展开。"""
    if payload[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                matches = [
                    info for info in archive.infolist()
                    if not info.is_dir()
                    and info.file_size > 0
                    and info.filename.replace("\\", "/").rsplit("/", 1)[-1].lower() in {"tectonic", "tectonic.exe"}
                ]
                if len(matches) != 1:
                    raise ToolFetchError("发布包内未找到唯一的 tectonic 可执行文件。")
                return archive.read(matches[0])
        except zipfile.BadZipFile as error:
            raise ToolFetchError("Tectonic ZIP 压缩包损坏。") from error

    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                basename = member.name.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if not member.isfile() or basename not in {"tectonic", "tectonic.exe"}:
                    continue
                if member.size <= 0:
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                return handle.read()
    except tarfile.TarError as error:
        raise ToolFetchError("Tectonic 发布包格式不受支持或已损坏。") from error
    raise ToolFetchError("发布包内未找到 tectonic 可执行文件。")


def tectonic_status(bin_dir=None, *, platform_name=None):
    """当前 Tectonic 的可用状态:PATH 中是否可见、本地安装的版本。"""
    bin_dir = Path(bin_dir) if bin_dir else DEFAULT_BIN_DIR
    binary_name = tectonic_binary_name(platform_name)
    target = bin_dir / binary_name
    version = None
    version_file = bin_dir / "tectonic.version"
    if target.exists() and version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip() or None
    return {"in_path": bool(shutil.which(binary_name) or shutil.which("tectonic")),
            "installed_path": str(target) if target.exists() else None,
            "installed_version": version}


def poppler_status():
    """Poppler(pdfinfo/pdftoppm)是否可用,以及本机是否有 Homebrew。"""
    return {"in_path": bool(shutil.which("pdftoppm")) and bool(shutil.which("pdfinfo")),
            "brew": shutil.which("brew")}


def _safe_zip_parts(raw_name: str) -> list[str]:
    """校验 ZIP 成员路径并拆分为安全相对路径段;发现越界特征立即抛 ToolFetchError。"""
    if not raw_name or "\x00" in raw_name or raw_name.startswith(("/", "\\")):
        raise ToolFetchError(f"拒绝不安全的压缩包路径:{raw_name!r}")
    normalized = raw_name.replace("\\", "/")
    parts = [segment for segment in normalized.split("/") if segment and segment != "."]
    for segment in parts:
        if segment == ".." or ":" in segment:
            raise ToolFetchError(f"拒绝包含路径穿越或盘符的压缩包路径:{raw_name!r}")
    return parts


def _atomic_replace_file(target: Path, data: bytes, *, mode: int | None = None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_bytes(data)
        if mode is not None:
            temporary.chmod(mode)
        try:
            os.replace(temporary, target)
        except PermissionError as error:
            if not target.exists():
                raise ToolFetchError("目标工具文件正被占用，请等待当前编译/预览结束后重试。") from error
            backup = target.with_name(f".{target.name}.old-{secrets.token_hex(4)}")
            try:
                os.replace(target, backup)
                os.replace(temporary, target)
            except OSError as retry_error:
                if backup.exists() and not target.exists():
                    try:
                        os.replace(backup, target)
                    except OSError:
                        pass
                raise ToolFetchError("目标工具文件正被占用，请等待当前编译/预览结束后重试。") from retry_error
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass
        except OSError as error:
            raise ToolFetchError(f"无法写入工具文件 {target.name}:{error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def _write_confined(root: Path, relative_parts: list[str], data: bytes) -> Path:
    resolved_root = root.resolve()
    destination = (resolved_root / Path(*relative_parts)).resolve()
    if destination == resolved_root or not destination.is_relative_to(resolved_root):
        raise ToolFetchError("压缩包成员超出目标目录边界。")
    return _atomic_replace_file(destination, data)


def _install_poppler_windows(*, bin_dir=None, fetch=None, progress=None):
    target_bin = (Path(bin_dir) if bin_dir else DEFAULT_BIN_DIR).resolve()
    prefix_root = target_bin.parent.resolve()
    share_poppler = prefix_root / "share" / "poppler"
    license_dir = prefix_root / "licenses" / "poppler-windows"

    payload = _call_fetch(fetch, POPPLER_WINDOWS_URL, progress)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != POPPLER_WINDOWS_SHA256:
        raise ToolFetchError(f"Poppler SHA256 校验失败(得到 {digest});不会安装未校验的文件。")

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            bin_entries: list[tuple[list[str], bytes]] = []
            share_entries: list[tuple[list[str], bytes]] = []
            license_entries: list[tuple[str, bytes]] = []

            for info in archive.infolist():
                parts = _safe_zip_parts(info.filename)
                if info.is_dir() or not parts:
                    continue
                if parts[:2] == ["Library", "bin"] and len(parts) > 2:
                    bin_entries.append((parts[2:], archive.read(info)))
                elif len(parts) > 3 and parts[1:3] == ["Library", "bin"]:
                    bin_entries.append((parts[3:], archive.read(info)))
                elif parts[:3] == ["Library", "share", "poppler"] and len(parts) > 3:
                    share_entries.append((parts[3:], archive.read(info)))
                elif len(parts) > 4 and parts[1:4] == ["Library", "share", "poppler"]:
                    share_entries.append((parts[4:], archive.read(info)))
                else:
                    basename = parts[-1]
                    if basename.upper().startswith(("LICENSE", "COPYING")) and len(parts) <= 3:
                        license_entries.append((basename, archive.read(info)))
    except zipfile.BadZipFile as error:
        raise ToolFetchError("Poppler ZIP 压缩包损坏。") from error

    bin_names = {parts[-1].lower() for parts, _ in bin_entries if len(parts) == 1}
    if not {"pdfinfo.exe", "pdftoppm.exe"}.issubset(bin_names):
        raise ToolFetchError("Poppler 压缩包内未找到 pdfinfo.exe 与 pdftoppm.exe。")

    for rel_parts, data in bin_entries:
        _write_confined(target_bin, rel_parts, data)
    for rel_parts, data in share_entries:
        _write_confined(share_poppler, rel_parts, data)
    for name, data in license_entries:
        _write_confined(license_dir, [name], data)

    notice = (
        f"poppler-windows v{POPPLER_WINDOWS_VERSION}\n"
        f"URL: {POPPLER_WINDOWS_URL}\n"
        f"SHA256: {POPPLER_WINDOWS_SHA256}\n"
        "License: GPL-2.0-or-later (invoked strictly as separate CLI subprocesses: pdfinfo.exe / pdftoppm.exe).\n"
        "Upstream sources: https://github.com/oschwartz10612/poppler-windows and "
        "https://gitlab.freedesktop.org/poppler/poppler\n"
    ).encode("utf-8")
    _write_confined(license_dir, ["NOTICE.txt"], notice)

    return {
        "ok": True,
        "tool": "poppler",
        "method": "github-release",
        "version": POPPLER_WINDOWS_VERSION,
        "path": str(target_bin),
        "sha256": digest,
    }


def install_poppler(run=None, *, bin_dir=None, fetch=None, progress=None, platform_name=None):
    """显式安装 Poppler:macOS 走 Homebrew,Windows 走固定 SHA256 的 poppler-windows 便携包。"""
    effective_platform = platform_name if platform_name is not None else sys.platform
    if effective_platform == "win32":
        return _install_poppler_windows(bin_dir=bin_dir, fetch=fetch, progress=progress)
    if effective_platform != "darwin":
        raise ToolFetchError("此入口仅支持 macOS 与 Windows;Linux 请用系统包管理器安装 poppler-utils。")
    brew = shutil.which("brew")
    if not brew:
        raise ToolFetchError("未找到 Homebrew;请先安装 brew,或手动安装 Poppler 并加入 PATH。")
    runner = run or subprocess.run
    try:
        completed = runner([brew, "install", "poppler"], capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as error:
        raise ToolFetchError("brew install poppler 超时;请手动重试。") from error
    except OSError as error:
        raise ToolFetchError(f"无法运行 brew:{error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-400:]
        raise ToolFetchError(f"brew 安装 Poppler 失败:{detail or '未知错误'}")
    if not poppler_status()["in_path"]:
        raise ToolFetchError("brew 报告成功但未找到 pdfinfo/pdftoppm;请检查 brew 状态。")
    return {"ok": True, "tool": "poppler", "method": "homebrew",
            "version": (completed.stdout or "").strip().splitlines()[-1][:120] if (completed.stdout or "").strip() else ""}


def install_tectonic(bin_dir=None, fetch=None, progress=None, *, platform_name=None, machine=None):
    """下载 → SHA256 校验 → 原子安装到 bin_dir/tectonic(.exe)。

    fetch(url, progress) 可注入替代真实网络,便于离线测试。
    """
    bin_dir = Path(bin_dir) if bin_dir else DEFAULT_BIN_DIR
    key = platform_key(platform_name, machine)
    asset = TECTONIC_ASSETS.get(key)
    if asset is None:
        raise ToolFetchError("没有适配当前平台的 Tectonic 预编译包;请自行安装并置于 PATH。")
    payload = _call_fetch(fetch, tectonic_download_url(key), progress)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset[1]:
        raise ToolFetchError(f"SHA256 校验失败(得到 {digest});不会安装未校验的文件。")
    binary = _extract_tectonic(payload)
    binary_name = tectonic_binary_name(platform_name)
    target = bin_dir / binary_name
    _atomic_replace_file(target, binary, mode=0o755)
    (bin_dir / "tectonic.version").write_text(TECTONIC_VERSION + "\n", encoding="utf-8")
    return {"ok": True, "path": str(target), "version": TECTONIC_VERSION, "sha256": digest}
