# 桌面壳的离线测试:只覆盖无 GUI 的会话读取、进程判定与命令行组装。
"""桌面壳测试:无 GUI 覆盖会话/进程/命令行/看门狗;darwin 上另有原生信号集成验证。

运行:python -m unittest discover -s desktop -p 'test_*.py'(无需 pywebview 即可跑全部非集成用例)。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
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

    @unittest.skipUnless(sys.platform == "darwin", "codesign 仅在 macOS 上可用")
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


class TerminateWatchdogTests(unittest.TestCase):
    """看门狗线程体:唤醒后有界等待,随后自行清理并强制退出。"""

    def run_watchdog(self, write_bytes, deadline=0.2):
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        cleaned = []
        exited = []
        state = {"shutdown": lambda: cleaned.append(True)}
        thread = threading.Thread(
            target=desktop_app._terminate_watchdog,
            args=(read_fd, state),
            kwargs={"deadline": deadline, "exiter": lambda code: exited.append(code)},
            daemon=True)
        thread.start()
        for payload in write_bytes:
            os.write(write_fd, payload)
            time.sleep(0.02)
        thread.join(timeout=5)
        os.close(read_fd)
        os.close(write_fd)
        self.assertFalse(thread.is_alive(), "看门狗处理完应退出线程体")
        return cleaned, exited

    def test_cleanup_and_force_exit_after_deadline(self):
        cleaned, exited = self.run_watchdog([b"\x0f"], deadline=0.2)
        self.assertEqual(cleaned, [True], "强制退出前执行已注册的清理")
        self.assertEqual(exited, [0])

    def test_second_signal_skips_waiting_for_the_deadline(self):
        start = time.monotonic()
        cleaned, exited = self.run_watchdog([b"\x0f", b"\x0f"], deadline=10.0)
        self.assertLess(time.monotonic() - start, 5.0, "第二个信号立即强制退出,不等满 deadline")
        self.assertEqual(cleaned, [True])
        self.assertEqual(exited, [0])

    def test_missing_shutdown_hook_still_exits(self):
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        exited = []
        thread = threading.Thread(
            target=desktop_app._terminate_watchdog,
            args=(read_fd, {}),
            kwargs={"deadline": 0.1, "exiter": lambda code: exited.append(code)},
            daemon=True)
        thread.start()
        os.write(write_fd, b"\x0f")
        thread.join(timeout=5)
        os.close(read_fd)
        os.close(write_fd)
        self.assertEqual(exited, [0], "无清理钩子也不能卡死")


class NativeTerminateIntegrationTests(unittest.TestCase):
    """原生集成验证:真实 Cocoa 事件循环中 SIGTERM 必须有界退出(#50)。

    需要 macOS 与 pywebview;无窗口服务时跳过。设 TEXADA_NATIVE_TESTS=0 可关闭。
    """

    @classmethod
    def setUpClass(cls):
        if sys.platform != "darwin":
            raise unittest.SkipTest("原生集成验证仅在 macOS 上运行")
        if os.environ.get("TEXADA_NATIVE_TESTS") == "0":
            raise unittest.SkipTest("TEXADA_NATIVE_TESTS=0 已关闭原生集成验证")
        try:
            import webview  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("未安装 pywebview,跳过原生集成验证")

    def test_sigterm_exits_cocoa_event_loop_with_bounded_wait(self):
        repo = Path(__file__).resolve().parents[1]
        helper = (
            "import importlib.util, json, os, sys, time\n"
            "repo, state, port = sys.argv[1], sys.argv[2], sys.argv[3]\n"
            "os.environ['TEXADA_BUNDLE_DIR'] = repo\n"
            "from pathlib import Path\n"
            "d = Path(state); d.mkdir(parents=True, exist_ok=True)\n"
            "(d / 'session.json').write_text(json.dumps({\n"
            "    'session_id': 'probe', 'pid': os.getpid(),\n"
            "    'url': f'http://127.0.0.1:{port}/studio?token=probe',\n"
            "    'base_url': f'http://127.0.0.1:{port}', 'model_base_url': '',\n"
            "    'model': '', 'owned_model_pid': None,\n"
            "    'created_at': time.time(), 'running': True}))\n"
            "import webview\n"
            "orig = webview.start\n"
            "def start(*args, **kwargs):\n"
            "    print('IN_RUNLOOP', flush=True)\n"
            "    return orig(*args, **kwargs)\n"
            "webview.start = start\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'texada_desktop_app', os.path.join(repo, 'desktop', 'app.py'))\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "sys.modules['texada_desktop_app'] = mod\n"
            "spec.loader.exec_module(mod)\n"
            "code = mod.main(['--port', port, '--state-dir', state])\n"
            "print('MAIN_RETURNED', flush=True)\n"
            "raise SystemExit(code)\n")
        with tempfile.TemporaryDirectory() as tmp:
            helper_path = Path(tmp) / "native_probe.py"
            helper_path.write_text(helper, encoding="utf-8")
            state = Path(tmp) / "state"
            child = subprocess.Popen(
                [sys.executable, str(helper_path), str(repo), str(state), "8893"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                ready = False
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    line = child.stdout.readline()
                    if "IN_RUNLOOP" in line:
                        ready = True
                        break
                    if not line and child.poll() is not None:
                        break
                if not ready:
                    if child.poll() is not None:
                        self.skipTest(f"无法启动窗口(GUI 不可用?):{child.stderr.read()[-300:]}")
                    self.fail("窗口事件循环未就绪")
                time.sleep(0.5)
                child.send_signal(15)  # signal.SIGTERM
                try:
                    code = child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.fail("SIGTERM 后 15 秒仍未退出(Cocoa 事件循环吞掉信号,#50 复现)")
                self.assertEqual(code, 0, "SIGTERM 应作为优雅退出")
                tail = child.stdout.read()
                self.assertIn(
                    "MAIN_RETURNED", tail,
                    "应走信号泵→window_closer 的正常清理路径,而不是看门狗强制退出")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                child.stdout.close()
                child.stderr.close()


if __name__ == "__main__":
    unittest.main()
