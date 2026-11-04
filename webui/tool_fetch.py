# 本地工具自举:按固定版本与 SHA256 把单文件 Tectonic 下载到 ~/.texada/bin。
"""仅在用户显式触发时执行一次下载;不在文档处理过程中自动运行。

入口::

    CLI:.venv/bin/python scripts/install_local_tools.py [--bin-dir DIR]
    UI:设置面板「下载 Tectonic」按钮 → POST /api/studio/tools/install

摘要取自 Tectonic 官方 Release(tectonic@0.17.0)的资产元数据。
Poppler(pdftoppm/pdfinfo)不是单文件分发,仍需系统包管理器安装。
"""
from __future__ import annotations

import hashlib
import io
import os
import platform as platform_module
import shutil
import sys
import tarfile
import urllib.request
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
}
DEFAULT_BIN_DIR = Path.home() / ".texada" / "bin"


class ToolFetchError(RuntimeError):
    """下载或安装本地工具失败的用户可读原因。"""


def platform_key(platform_name=None, machine=None):
    """映射到预编译资产键;无适配包的平台返回 None。"""
    platform_name = platform_name if platform_name is not None else sys.platform
    machine = machine if machine is not None else platform_module.machine()
    if platform_name == "darwin":
        return "darwin-arm64" if machine == "arm64" else "darwin-x86_64"
    if platform_name.startswith("linux"):
        return "linux-aarch64" if machine == "aarch64" else "linux-x86_64"
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


def _extract_tectonic(payload):
    """从发布包提取名为 tectonic 的单个可执行文件;忽略其余成员,不做路径展开。"""
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or os.path.basename(member.name) != "tectonic":
                continue
            if member.size <= 0:
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            return handle.read()
    raise ToolFetchError("发布包内未找到 tectonic 可执行文件。")


def tectonic_status(bin_dir=None):
    """当前 Tectonic 的可用状态:PATH 中是否可见、本地安装的版本。"""
    bin_dir = Path(bin_dir) if bin_dir else DEFAULT_BIN_DIR
    target = bin_dir / "tectonic"
    version = None
    version_file = bin_dir / "tectonic.version"
    if target.exists() and version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip() or None
    return {"in_path": bool(shutil.which("tectonic")),
            "installed_path": str(target) if target.exists() else None,
            "installed_version": version}


def install_tectonic(bin_dir=None, fetch=None, progress=None):
    """下载 → SHA256 校验 → 原子安装到 bin_dir/tectonic。

    fetch(url, progress) 可注入替代真实网络,便于离线测试。
    """
    bin_dir = Path(bin_dir) if bin_dir else DEFAULT_BIN_DIR
    key = platform_key()
    asset = TECTONIC_ASSETS.get(key)
    if asset is None:
        raise ToolFetchError("没有适配当前平台的 Tectonic 预编译包;请自行安装并置于 PATH。")
    payload = (fetch or _http_get)(tectonic_download_url(key), progress)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset[1]:
        raise ToolFetchError(f"SHA256 校验失败(得到 {digest});不会安装未校验的文件。")
    binary = _extract_tectonic(payload)
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "tectonic"
    temporary = target.with_name(".tectonic.tmp")
    temporary.write_bytes(binary)
    temporary.chmod(0o755)
    os.replace(temporary, target)
    (bin_dir / "tectonic.version").write_text(TECTONIC_VERSION + "\n", encoding="utf-8")
    return {"ok": True, "path": str(target), "version": TECTONIC_VERSION, "sha256": digest}
