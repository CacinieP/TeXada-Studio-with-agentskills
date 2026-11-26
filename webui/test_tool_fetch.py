# Tectonic 下载/校验/安装的离线测试:不访问网络,用内存中的发布包注入。
"""运行:python -m unittest webui.test_tool_fetch(或 discover -s webui)。"""
from __future__ import annotations

import hashlib
import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tool_fetch


def build_release_archive(members, compression="gz"):
    """构造发布 tar.gz;members 为 {相对路径: 字节}。"""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def build_zip_archive(members):
    """构造内存 .zip 发布包;members 为 {相对路径: 字节}。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


VALID_BINARY = b"#!/bin/sh\necho tectonic-fixture\n"
VALID_WINDOWS_EXE = b"MZ\x90\x00tectonic-windows-fixture"


def valid_payload():
    return build_release_archive({"tectonic-0.17.0-aarch64-apple-darwin/tectonic": VALID_BINARY,
                                  "tectonic-0.17.0-aarch64-apple-darwin/README.md": b"notes"})


class PlatformKeyTests(unittest.TestCase):
    def test_platform_mapping(self):
        self.assertEqual(tool_fetch.platform_key("darwin", "arm64"), "darwin-arm64")
        self.assertEqual(tool_fetch.platform_key("darwin", "x86_64"), "darwin-x86_64")
        self.assertEqual(tool_fetch.platform_key("linux", "x86_64"), "linux-x86_64")
        self.assertEqual(tool_fetch.platform_key("linux", "aarch64"), "linux-aarch64")
        self.assertEqual(tool_fetch.platform_key("win32", "AMD64"), "win32-x86_64")
        self.assertEqual(tool_fetch.platform_key("win32", "x86_64"), "win32-x86_64")
        self.assertIsNone(tool_fetch.platform_key("win32", "ARM64"), "未适配架构返回 None")
        self.assertIsNone(tool_fetch.platform_key("freebsd", "x86_64"), "未适配平台返回 None")

    def test_pinned_windows_constants_and_binary_names(self):
        self.assertEqual(
            tool_fetch.TECTONIC_ASSETS.get("win32-x86_64"),
            (
                "tectonic-0.17.0-x86_64-pc-windows-msvc.zip",
                "f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f",
            ),
        )
        self.assertEqual(tool_fetch.POPPLER_WINDOWS_VERSION, "26.09.0-0")
        self.assertEqual(
            tool_fetch.POPPLER_WINDOWS_URL,
            "https://github.com/oschwartz10612/poppler-windows/releases/download/v26.09.0-0/Release-26.09.0-0.zip",
        )
        self.assertEqual(
            tool_fetch.POPPLER_WINDOWS_SHA256,
            "7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0",
        )
        self.assertEqual(tool_fetch.tectonic_binary_name("win32"), "tectonic.exe")
        self.assertEqual(tool_fetch.tectonic_binary_name("darwin"), "tectonic")
        self.assertEqual(tool_fetch.tectonic_binary_name("linux"), "tectonic")

    def test_download_url_is_pinned_release(self):
        url = tool_fetch.tectonic_download_url("darwin-arm64")
        self.assertIn(tool_fetch.RELEASE_TAG, url)
        self.assertIn("aarch64-apple-darwin", url)
        win_url = tool_fetch.tectonic_download_url("win32-x86_64")
        self.assertIn("x86_64-pc-windows-msvc.zip", win_url)

    def test_download_url_rejects_unsupported_platform(self):
        with self.assertRaises(tool_fetch.ToolFetchError):
            tool_fetch.tectonic_download_url("plan9-arm")


class InstallTectonicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bin_dir = Path(self.temp.name) / "bin"

    def fetch_fixed(self, payload):
        calls = []
        def fetch(url, progress):
            calls.append(url)
            if progress:
                progress(len(payload), len(payload))
            return payload
        return fetch, calls

    def test_install_with_injected_digest(self):
        payload = valid_payload()
        key = tool_fetch.platform_key()
        original = tool_fetch.TECTONIC_ASSETS.get(key)
        self.assertIsNotNone(original, "测试机平台应有预编译资产")
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.dict(tool_fetch.TECTONIC_ASSETS, {key: (original[0], digest)}):
            fetch, calls = self.fetch_fixed(payload)
            progress_seen = []
            result = tool_fetch.install_tectonic(self.bin_dir, fetch=fetch,
                                                 progress=lambda done, total: progress_seen.append((done, total)))
        self.assertEqual(calls, [tool_fetch.tectonic_download_url(key)])
        self.assertTrue(result["ok"])
        self.assertEqual(result["sha256"], digest)
        binary_name = tool_fetch.tectonic_binary_name()
        installed = self.bin_dir / binary_name
        self.assertEqual(installed.read_bytes(), VALID_BINARY)
        self.assertTrue(os.access(installed, os.X_OK), "安装后必须可执行")
        self.assertEqual((self.bin_dir / "tectonic.version").read_text(encoding="utf-8").strip(),
                         tool_fetch.TECTONIC_VERSION)
        self.assertTrue(progress_seen, "进度回调被调用")
        self.assertFalse((self.bin_dir / f".{binary_name}.tmp").exists(), "临时文件已被原子替换")

    def test_install_windows_zip_extracts_tectonic_exe_and_updates_status(self):
        payload = build_zip_archive({
            "tectonic-0.17.0/tectonic.exe": VALID_WINDOWS_EXE,
            "tectonic-0.17.0/README.md": b"windows release notes",
        })
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.object(tool_fetch.sys, "platform", "win32"), \
                mock.patch.object(tool_fetch.platform_module, "machine", return_value="AMD64"), \
                mock.patch.object(tool_fetch.shutil, "which", return_value=None), \
                mock.patch.dict(
                    tool_fetch.TECTONIC_ASSETS,
                    {"win32-x86_64": ("tectonic-0.17.0-x86_64-pc-windows-msvc.zip", digest)},
                ):
            fetch, calls = self.fetch_fixed(payload)
            result = tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)
            status = tool_fetch.tectonic_status(self.bin_dir)

        self.assertEqual(calls, [tool_fetch.tectonic_download_url("win32-x86_64")])
        installed = self.bin_dir / "tectonic.exe"
        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], str(installed))
        self.assertEqual(installed.read_bytes(), VALID_WINDOWS_EXE)
        self.assertEqual(status["installed_path"], str(installed))
        self.assertEqual(status["installed_version"], tool_fetch.TECTONIC_VERSION)

    def test_install_windows_zip_rejects_missing_or_ambiguous_binary(self):
        for members in (
            {"README.txt": b"no exe"},
            {"a/tectonic.exe": VALID_WINDOWS_EXE, "b/tectonic.exe": VALID_WINDOWS_EXE},
        ):
            payload = build_zip_archive(members)
            digest = hashlib.sha256(payload).hexdigest()
            with self.subTest(members=list(members)), \
                    mock.patch.object(tool_fetch.sys, "platform", "win32"), \
                    mock.patch.object(tool_fetch.platform_module, "machine", return_value="AMD64"), \
                    mock.patch.dict(
                        tool_fetch.TECTONIC_ASSETS,
                        {"win32-x86_64": ("tectonic-0.17.0-x86_64-pc-windows-msvc.zip", digest)},
                    ):
                fetch, _ = self.fetch_fixed(payload)
                with self.assertRaisesRegex(tool_fetch.ToolFetchError, "tectonic"):
                    tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)

    def test_install_rejects_digest_mismatch(self):
        payload = valid_payload()
        key = tool_fetch.platform_key()
        original = tool_fetch.TECTONIC_ASSETS.get(key)
        wrong = "0" * 64
        with mock.patch.dict(tool_fetch.TECTONIC_ASSETS, {key: (original[0], wrong)}):
            fetch, _ = self.fetch_fixed(payload)
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "SHA256"):
                tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)
        self.assertFalse((self.bin_dir / tool_fetch.tectonic_binary_name()).exists(), "校验失败不落盘")

    def test_install_rejects_archive_without_binary(self):
        payload = build_release_archive({"tectonic-0.17.0/README.md": b"no binary"})
        key = tool_fetch.platform_key()
        original = tool_fetch.TECTONIC_ASSETS.get(key)
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.dict(tool_fetch.TECTONIC_ASSETS, {key: (original[0], digest)}):
            fetch, _ = self.fetch_fixed(payload)
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "未找到 tectonic"):
                tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)

    def test_install_rejects_unsupported_platform(self):
        with mock.patch.object(tool_fetch, "platform_key", return_value=None):
            with self.assertRaises(tool_fetch.ToolFetchError):
                tool_fetch.install_tectonic(self.bin_dir, fetch=lambda url, progress: b"")

    def test_status_reports_path_and_version(self):
        self.assertFalse(tool_fetch.tectonic_status(self.bin_dir)["installed_path"])
        self.bin_dir.mkdir(parents=True)
        binary = self.bin_dir / tool_fetch.tectonic_binary_name()
        binary.write_bytes(VALID_BINARY)
        (self.bin_dir / "tectonic.version").write_text("0.17.0\n", encoding="utf-8")
        status = tool_fetch.tectonic_status(self.bin_dir)
        self.assertEqual(status["installed_path"], str(binary))
        self.assertEqual(status["installed_version"], "0.17.0")

    def test_install_recovers_locked_target_via_rename_and_maps_persistent_lock_to_tool_fetch_error(self):
        payload = valid_payload()
        key = tool_fetch.platform_key()
        original = tool_fetch.TECTONIC_ASSETS.get(key)
        digest = hashlib.sha256(payload).hexdigest()
        binary_name = tool_fetch.tectonic_binary_name()
        target = self.bin_dir / binary_name
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old-binary")

        real_replace = os.replace
        attempts = []

        def locked_direct_replace(src, dst):
            attempts.append((Path(src).name, Path(dst).name))
            if Path(dst) == target and target.exists():
                raise PermissionError(13, "WinError 5: Access is denied")
            return real_replace(src, dst)

        with mock.patch.dict(tool_fetch.TECTONIC_ASSETS, {key: (original[0], digest)}), \
                mock.patch.object(tool_fetch.os, "replace", side_effect=locked_direct_replace):
            fetch, _ = self.fetch_fixed(payload)
            result = tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)

        self.assertTrue(result["ok"])
        self.assertEqual(target.read_bytes(), VALID_BINARY)
        self.assertEqual(list(self.bin_dir.glob("*.tmp")), [])

        with mock.patch.dict(tool_fetch.TECTONIC_ASSETS, {key: (original[0], digest)}), \
                mock.patch.object(tool_fetch.os, "replace", side_effect=PermissionError(13, "locked")):
            fetch, _ = self.fetch_fixed(payload)
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "占用"):
                tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)
        self.assertEqual(list(self.bin_dir.glob("*.tmp")), [], "失败后必须清理随机临时文件")


class PopplerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "texada-home"
        self.bin_dir = self.root / "bin"

    def test_status_reports_availability_and_brew(self):
        status = tool_fetch.poppler_status()
        self.assertIn("in_path", status)
        self.assertIn("brew", status)

    def test_install_runs_brew_once_and_reports_success(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout="==> Installed poppler\n", stderr="")

        def which(name):
            return f"/opt/homebrew/bin/{name}" if name in {"brew", "pdftoppm", "pdfinfo"} else None

        with mock.patch.object(tool_fetch.sys, "platform", "darwin"), \
             mock.patch.object(tool_fetch.shutil, "which", side_effect=which):
            result = tool_fetch.install_poppler(run=run)
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "homebrew")
        self.assertEqual(calls, [["/opt/homebrew/bin/brew", "install", "poppler"]])

    def test_install_requires_brew(self):
        with mock.patch.object(tool_fetch.sys, "platform", "darwin"), \
             mock.patch.object(tool_fetch.shutil, "which", return_value=None):
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "Homebrew"):
                tool_fetch.install_poppler(run=lambda argv, **kwargs: None)

    def test_find_brew_and_install_poppler_discover_macos_homebrew_outside_launchd_path(self):
        suffix = ".exe" if os.name == "nt" else ""
        empty_sys_bin = self.root / "usr-bin"
        empty_sys_bin.mkdir(parents=True)
        fake_brew_bin = self.root / "opt-homebrew-bin"
        fake_brew_bin.mkdir(parents=True)
        for name in ("brew", "pdftoppm", "pdfinfo"):
            exe = fake_brew_bin / f"{name}{suffix}"
            exe.write_bytes(b"#!/bin/sh\nexit 0\n")
            exe.chmod(0o755)
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout="==> Pouring poppler\n", stderr="")

        with mock.patch.dict(tool_fetch.os.environ, {"PATH": str(empty_sys_bin)}), \
             mock.patch.object(tool_fetch, "MACOS_BREW_PATH", str(fake_brew_bin), create=True):
            status = tool_fetch.poppler_status(platform_name="darwin")
            self.assertFalse(status["in_path"])
            self.assertIsNotNone(status["brew"])
            self.assertEqual(Path(status["brew"]).resolve(), (fake_brew_bin / f"brew{suffix}").resolve())
            result = tool_fetch.install_poppler(run=run, platform_name="darwin")

        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0][0]).resolve(), (fake_brew_bin / f"brew{suffix}").resolve())
        self.assertEqual(calls[0][1:], ["install", "poppler"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "homebrew")
        self.assertEqual(Path(result["path"]).resolve(), fake_brew_bin.resolve())

    def test_install_poppler_returns_existing_when_bundled_tools_ready_without_brew(self):
        suffix = ".exe" if os.name == "nt" else ""
        bundled_bin = self.root / "bundled-bin"
        bundled_bin.mkdir(parents=True)
        for name in ("pdftoppm", "pdfinfo"):
            exe = bundled_bin / f"{name}{suffix}"
            exe.write_bytes(b"#!/bin/sh\nexit 0\n")
            exe.chmod(0o755)
        missing_brew_dir = self.root / "no-homebrew"

        with mock.patch.dict(tool_fetch.os.environ, {"PATH": str(bundled_bin)}), \
             mock.patch.object(tool_fetch, "MACOS_BREW_PATH", str(missing_brew_dir), create=True):
            result = tool_fetch.install_poppler(
                run=lambda *a, **kw: self.fail("bundled Poppler must not invoke brew when brew is absent"),
                platform_name="darwin",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "poppler")
        self.assertEqual(result["method"], "existing")

    def test_install_maps_brew_failure(self):
        def run(argv, **kwargs):
            return SimpleNamespace(returncode=1, stdout="", stderr="Error: offline")

        with mock.patch.object(tool_fetch.sys, "platform", "darwin"), \
             mock.patch.object(tool_fetch.shutil, "which", side_effect=lambda name: "/opt/homebrew/bin/" + name):
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "失败"):
                tool_fetch.install_poppler(run=run)

    def test_install_rejects_non_darwin(self):
        with mock.patch.object(tool_fetch.sys, "platform", "linux"):
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "macOS"):
                tool_fetch.install_poppler(run=lambda argv, **kwargs: None)

    def test_windows_install_poppler_verifies_sha256_and_extracts_bin_data_and_license(self):
        payload = build_zip_archive({
            "poppler-26.09.0/Library/bin/pdfinfo.exe": b"MZ-pdfinfo",
            "poppler-26.09.0/Library/bin/pdftoppm.exe": b"MZ-pdftoppm",
            "poppler-26.09.0/Library/bin/poppler.dll": b"MZ-poppler-dll",
            "poppler-26.09.0/share/poppler/cMap/Adobe-GB1/UniGB-UTF16-H": b"cmap-data",
            "poppler-26.09.0/LICENSE": b"GPL-2.0-or-later license text\n",
        })
        digest = hashlib.sha256(payload).hexdigest()
        seen_urls = []

        def fetch(url, progress=None):
            seen_urls.append(url)
            if progress:
                progress(len(payload), len(payload))
            return payload

        with mock.patch.object(tool_fetch, "POPPLER_WINDOWS_SHA256", digest):
            result = tool_fetch.install_poppler(
                bin_dir=self.bin_dir, fetch=fetch, platform_name="win32"
            )

        self.assertEqual(seen_urls, [tool_fetch.POPPLER_WINDOWS_URL])
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["tool"], "poppler")
        self.assertEqual(result["method"], "github-release")
        self.assertEqual(result["version"], "26.09.0-0")
        poppler_bin = (self.root / "Library" / "bin").resolve()
        self.assertEqual(Path(result["path"]), poppler_bin)
        self.assertEqual((poppler_bin / "pdfinfo.exe").read_bytes(), b"MZ-pdfinfo")
        self.assertEqual((poppler_bin / "pdftoppm.exe").read_bytes(), b"MZ-pdftoppm")
        self.assertEqual((poppler_bin / "poppler.dll").read_bytes(), b"MZ-poppler-dll")
        # poppler.dll (conda-forge win64) resolves CJK maps at <dll_dir>\..\..\share\poppler
        self.assertEqual(
            (poppler_bin.parent.parent / "share" / "poppler" / "cMap" / "Adobe-GB1" / "UniGB-UTF16-H").read_bytes(),
            b"cmap-data",
        )
        license_dir = self.root / "licenses" / "poppler-windows"
        self.assertEqual((license_dir / "LICENSE").read_bytes(), b"GPL-2.0-or-later license text\n")
        self.assertTrue((license_dir / "NOTICE.txt").is_file())

    def test_windows_install_poppler_rejects_archive_missing_share_poppler_maps(self):
        payload = build_zip_archive({
            "poppler-26.09.0/Library/bin/pdfinfo.exe": b"MZ-pdfinfo",
            "poppler-26.09.0/Library/bin/pdftoppm.exe": b"MZ-pdftoppm",
        })
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.object(tool_fetch, "POPPLER_WINDOWS_SHA256", digest):
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "share/poppler"):
                tool_fetch.install_poppler(
                    bin_dir=self.bin_dir, fetch=lambda url, progress=None: payload, platform_name="win32"
                )
        self.assertFalse(self.bin_dir.exists())

    def test_windows_install_poppler_rejects_sha256_mismatch(self):
        payload = build_zip_archive({
            "poppler-26.09.0/Library/bin/pdfinfo.exe": b"MZ-pdfinfo",
            "poppler-26.09.0/Library/bin/pdftoppm.exe": b"MZ-pdftoppm",
        })
        with mock.patch.object(tool_fetch, "POPPLER_WINDOWS_SHA256", "0" * 64):
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "SHA256"):
                tool_fetch.install_poppler(
                    bin_dir=self.bin_dir, fetch=lambda url, progress=None: payload, platform_name="win32"
                )
        self.assertFalse(self.bin_dir.exists())

    def test_windows_install_poppler_blocks_zip_slip_traversal(self):
        outside_sentinel = Path(self.temp.name) / "escape.dll"
        for malicious_member in (
            "poppler-26.09.0/Library/bin/../../../escape.dll",
            "../escape.dll",
            "/abs/escape.dll",
            "C:/Windows/escape.dll",
        ):
            payload = build_zip_archive({
                "poppler-26.09.0/Library/bin/pdfinfo.exe": b"MZ-pdfinfo",
                "poppler-26.09.0/Library/bin/pdftoppm.exe": b"MZ-pdftoppm",
                malicious_member: b"evil",
            })
            digest = hashlib.sha256(payload).hexdigest()
            with self.subTest(member=malicious_member), \
                    mock.patch.object(tool_fetch, "POPPLER_WINDOWS_SHA256", digest):
                with self.assertRaises(tool_fetch.ToolFetchError):
                    tool_fetch.install_poppler(
                        bin_dir=self.bin_dir,
                        fetch=lambda url, progress=None: payload,
                        platform_name="win32",
                    )
            self.assertFalse(outside_sentinel.exists(), "Zip-Slip 成员不得写出目录边界")


if __name__ == "__main__":
    unittest.main()
