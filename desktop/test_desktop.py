# 桌面壳的离线测试:只覆盖无 GUI 的会话读取、进程判定与命令行组装。
"""运行:python -m unittest discover -s desktop -p 'test_*.py'(无需 pywebview)。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as desktop_app  # noqa: E402
import build_app  # noqa: E402


def write_session(directory: Path, payload) -> None:
    (directory / "session.json").write_text(json.dumps(payload), encoding="utf-8")


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, pid=None, running=True, url="http://127.0.0.1:8888/studio?token=abc"):
        return {"url": url, "pid": pid, "running": running}

    def test_read_entry_accepts_loopback_session(self):
        write_session(self.state, {"url": "http://127.0.0.1:8888/studio?token=abc",
                                   "pid": 42, "running": True})
        entry = desktop_app.read_entry(self.state)
        self.assertEqual(entry["url"], "http://127.0.0.1:8888/studio?token=abc")
        self.assertEqual(entry["pid"], 42)
        self.assertTrue(entry["running"])

    def test_read_entry_rejects_missing_or_foreign(self):
        self.assertIsNone(desktop_app.read_entry(self.state / "missing"))
        write_session(self.state, {"url": "http://example.com/studio?token=abc", "pid": 1, "running": True})
        self.assertIsNone(desktop_app.read_entry(self.state), "非回环入口不接受")
        write_session(self.state, {"url": "http://127.0.0.1:8888/studio", "pid": 1, "running": True})
        self.assertIsNone(desktop_app.read_entry(self.state), "缺 token 不接受")
        write_session(self.state, {"url": "http://user:pw@127.0.0.1:8888/studio?token=abc", "pid": 1, "running": True})
        self.assertIsNone(desktop_app.read_entry(self.state), "带凭据的入口不接受")
        (self.state / "session.json").write_text("{broken", encoding="utf-8")
        self.assertIsNone(desktop_app.read_entry(self.state))

    def test_entry_alive_checks_running_flag_and_pid(self):
        self.assertFalse(desktop_app.entry_alive(None))
        self.assertFalse(desktop_app.entry_alive(self.entry(pid=None)))
        self.assertFalse(desktop_app.entry_alive(self.entry(pid=9_999_999)), "不存在的进程视为未运行")
        self.assertFalse(desktop_app.entry_alive(self.entry(pid=os.getpid(), running=False)))
        self.assertTrue(desktop_app.entry_alive(self.entry(pid=os.getpid())))

    def test_wait_for_entry_times_out_on_stale_record(self):
        write_session(self.state, {"url": "http://127.0.0.1:8888/studio?token=abc",
                                   "pid": 9_999_999, "running": True})
        self.assertIsNone(desktop_app.wait_for_entry(self.state, 0.2))

    def test_wait_for_entry_returns_fresh_record(self):
        write_session(self.state, {"url": "http://127.0.0.1:8888/studio?token=abc",
                                   "pid": os.getpid(), "running": True})
        entry = desktop_app.wait_for_entry(self.state, 2)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pid"], os.getpid())


class LauncherTests(unittest.TestCase):
    def test_argv_always_disables_browser(self):
        argv = desktop_app.launcher_argv(desktop_app.DEFAULT_STATE_DIR)
        self.assertEqual(argv[1:], [str(desktop_app.LAUNCHER), "--no-browser"])

    def test_argv_passes_port_and_custom_state_dir(self):
        argv = desktop_app.launcher_argv(Path("/tmp/custom-state"), port=9001)
        self.assertIn("--port", argv)
        self.assertEqual(argv[argv.index("--port") + 1], "9001")
        self.assertIn("--state-dir", argv)
        self.assertEqual(argv[argv.index("--state-dir") + 1], "/tmp/custom-state")

    def test_launcher_env_marks_orphan_exit_without_dropping_existing_values(self):
        env = desktop_app.launcher_env({"PATH": "/bin", "HOME": "/tmp"})
        self.assertEqual(env["TEXADA_EXIT_WHEN_ORPHANED"], "1")
        self.assertEqual(env["PATH"], desktop_app.prepend_dirs("/bin", desktop_app.tool_bin_dirs()))
        self.assertEqual(env["HOME"], "/tmp")

    def test_prepend_dirs_is_idempotent_and_ordered(self):
        first = desktop_app.prepend_dirs("/usr/bin", ["/a", "/b"])
        self.assertEqual(first, os.pathsep.join(["/a", "/b", "/usr/bin"]))
        self.assertEqual(desktop_app.prepend_dirs(first, ["/a", "/b"]), first, "重复前置不叠加")
        self.assertEqual(desktop_app.prepend_dirs("", [Path("/x")]), "/x")

    def test_tool_bin_dirs_prepend_bundle_bin_when_bundled(self):
        import importlib
        with unittest.mock.patch.dict(os.environ, {"TEXADA_BUNDLE_DIR": "/tmp/fake-bundle"}):
            refreshed = importlib.reload(desktop_app)
            dirs = refreshed.tool_bin_dirs()
        importlib.reload(desktop_app)
        self.assertEqual(str(dirs[0]), str(Path("/tmp/fake-bundle").resolve() / "bin"))
        self.assertIn(str(Path.home() / ".texada" / "bin"), [str(item) for item in dirs])

    def test_seed_tex_cache_copies_only_when_target_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "src", Path(tmp) / "dst"
            source.mkdir()
            (source / "bundles").mkdir()
            (source / "bundles" / "x").write_bytes(b"1")
            copied = []

            def copier(s, t):
                copied.append((s, t))
                Path(t).mkdir()

            self.assertTrue(desktop_app.seed_tex_cache(source, target, copier=copier), "目标缺失时种子缓存")
            self.assertFalse(desktop_app.seed_tex_cache(source, target, copier=copier), "目标已存在不重复种子")
            self.assertFalse(desktop_app.seed_tex_cache(Path(tmp) / "missing", target, copier=copier))
            self.assertEqual(copied, [(str(source), str(target))])


class BuildTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "应用包生成仅支持 macOS")
    def test_build_creates_bundle_without_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = build_app.main(["--output", tmp, "--skip-icon", "--allow-missing-venv"])
            self.assertEqual(code, 0)
            app = Path(tmp) / "TeXada Studio.app"
            shim = app / "Contents" / "MacOS" / "TeXadaStudio"
            plist = app / "Contents" / "Info.plist"
            self.assertTrue(shim.exists() and plist.exists())
            self.assertTrue(os.access(shim, os.X_OK), "可执行位已设置")
            self.assertIn(str(build_app.REPO_ROOT), shim.read_text(encoding="utf-8"))
            self.assertIn("local.texada.studio", plist.read_text(encoding="utf-8"))

    def test_install_app_icon_replaces_py2app_default(self):
        import plistlib
        import build_bundle
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "TeXada Studio.app"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            plist_path = app / "Contents" / "Info.plist"
            plist_path.write_bytes(plistlib.dumps({"CFBundleIconFile": "PythonApplet"}))
            icon = Path(tmp) / "brand.icns"
            icon.write_bytes(b"icns-bytes")
            build_bundle.install_app_icon(app, icon)
            saved = plistlib.loads(plist_path.read_bytes())
            self.assertEqual(saved["CFBundleIconFile"], "AppIcon")
            self.assertEqual((resources / "AppIcon.icns").read_bytes(), b"icns-bytes")

    def test_seal_app_bundle_restores_signature_after_plist_edit(self):
        import plistlib
        import subprocess
        import build_bundle
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "TeXada Studio.app"
            macos = app / "Contents" / "MacOS"
            macos.mkdir(parents=True)
            binary = macos / "TeXada Studio"
            binary.write_bytes(Path("/bin/echo").read_bytes())
            binary.chmod(0o755)
            plist_path = app / "Contents" / "Info.plist"
            plist = {"CFBundleExecutable": "TeXada Studio", "CFBundleIconFile": "PythonApplet"}
            plist_path.write_bytes(plistlib.dumps(plist))
            subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True, capture_output=True)
            plist["CFBundleIconFile"] = "AppIcon"
            plist_path.write_bytes(plistlib.dumps(plist))
            broken = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True)
            self.assertNotEqual(broken.returncode, 0)
            build_bundle.seal_app_bundle(app)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True, capture_output=True)

    def test_tex_cache_manifest_hashes_only_copied_files(self):
        import hashlib
        import build_bundle
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "tex-cache"
            nested = cache / "bundles"
            nested.mkdir(parents=True)
            (nested / "a.tex").write_bytes(b"alpha")
            (cache / "b.fmt").write_bytes(b"beta")
            text = build_bundle.tex_cache_manifest(cache)
            lines = text.splitlines()
            self.assertEqual([line.split("  ", 1)[1] for line in lines], ["b.fmt", "bundles/a.tex"])
            self.assertEqual(lines[0].split("  ", 1)[0], hashlib.sha256(b"beta").hexdigest())
            self.assertTrue(text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
