# Tectonic 下载/校验/安装的离线测试:不访问网络,用内存中的发布包注入。
"""运行:python -m unittest webui.test_tool_fetch(或 discover -s webui)。"""
from __future__ import annotations

import hashlib
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tool_fetch


def build_release_archive(members, compression="gz"):
    """构造发布 tar.gz;members 为 {相对路径: 字节}。"""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=f"w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


VALID_BINARY = b"#!/bin/sh\necho tectonic-fixture\n"


def valid_payload():
    return build_release_archive({"tectonic-0.17.0-aarch64-apple-darwin/tectonic": VALID_BINARY,
                                  "tectonic-0.17.0-aarch64-apple-darwin/README.md": b"notes"})


class PlatformKeyTests(unittest.TestCase):
    def test_platform_mapping(self):
        self.assertEqual(tool_fetch.platform_key("darwin", "arm64"), "darwin-arm64")
        self.assertEqual(tool_fetch.platform_key("darwin", "x86_64"), "darwin-x86_64")
        self.assertEqual(tool_fetch.platform_key("linux", "x86_64"), "linux-x86_64")
        self.assertEqual(tool_fetch.platform_key("linux", "aarch64"), "linux-aarch64")
        self.assertIsNone(tool_fetch.platform_key("win32", "AMD64"), "未适配平台返回 None")

    def test_download_url_is_pinned_release(self):
        url = tool_fetch.tectonic_download_url("darwin-arm64")
        self.assertIn(tool_fetch.RELEASE_TAG, url)
        self.assertIn("aarch64-apple-darwin", url)

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
        installed = self.bin_dir / "tectonic"
        self.assertEqual(installed.read_bytes(), VALID_BINARY)
        self.assertTrue(os.access(installed, os.X_OK), "安装后必须可执行")
        self.assertEqual((self.bin_dir / "tectonic.version").read_text().strip(),
                         tool_fetch.TECTONIC_VERSION)
        self.assertTrue(progress_seen, "进度回调被调用")
        self.assertFalse((self.bin_dir / ".tectonic.tmp").exists(), "临时文件已被原子替换")

    def test_install_rejects_digest_mismatch(self):
        payload = valid_payload()
        key = tool_fetch.platform_key()
        original = tool_fetch.TECTONIC_ASSETS.get(key)
        wrong = "0" * 64
        with mock.patch.dict(tool_fetch.TECTONIC_ASSETS, {key: (original[0], wrong)}):
            fetch, _ = self.fetch_fixed(payload)
            with self.assertRaisesRegex(tool_fetch.ToolFetchError, "SHA256"):
                tool_fetch.install_tectonic(self.bin_dir, fetch=fetch)
        self.assertFalse((self.bin_dir / "tectonic").exists(), "校验失败不落盘")

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
        binary = self.bin_dir / "tectonic"
        binary.write_bytes(VALID_BINARY)
        (self.bin_dir / "tectonic.version").write_text("0.17.0\n")
        status = tool_fetch.tectonic_status(self.bin_dir)
        self.assertEqual(status["installed_path"], str(binary))
        self.assertEqual(status["installed_version"], "0.17.0")


if __name__ == "__main__":
    unittest.main()
