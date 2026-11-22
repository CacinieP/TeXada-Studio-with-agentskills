# 桌面壳的离线测试:只覆盖无 GUI 的会话读取、进程判定与命令行组装。
"""桌面壳测试:无 GUI 覆盖会话/进程/命令行/看门狗;darwin 上另有原生信号集成验证。

运行:python -m unittest discover -s desktop -p 'test_*.py'(无需 pywebview 即可跑全部非集成用例)。
"""
from __future__ import annotations

import json
import os
import shutil
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
            "import http.server, importlib.util, json, os, sys, threading, time\n"
            "repo, state = sys.argv[1], sys.argv[2]\n"
            "os.environ['TEXADA_BUNDLE_DIR'] = repo\n"
            "class Handler(http.server.BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
            "    def log_message(self, *args): pass\n"
            "httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)\n"
            "port = str(httpd.server_address[1])\n"
            "threading.Thread(target=httpd.serve_forever, daemon=True).start()\n"
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
                [sys.executable, str(helper_path), str(repo), str(state)],
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


def _parse_icns_chunks(icns_bytes: bytes) -> set[str]:
    if len(icns_bytes) < 8 or icns_bytes[:4] != b"icns":
        return set()
    total = int.from_bytes(icns_bytes[4:8], "big")
    pos = 8
    chunks: set[str] = set()
    while pos + 8 <= min(total, len(icns_bytes)):
        tag = icns_bytes[pos:pos + 4].decode("latin1")
        size = int.from_bytes(icns_bytes[pos + 4:pos + 8], "big")
        if size < 8:
            break
        chunks.add(tag)
        pos += size
    return chunks


class BundledBackendHygieneTests(unittest.TestCase):
    """Issue #66 (1): 捆绑后端占口拦截、零 token 泄露与 SystemExit 捕获。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        self._saved_path = list(sys.path)
        self._saved_env = dict(os.environ)

    def tearDown(self):
        sys.path[:] = self._saved_path
        os.environ.clear()
        os.environ.update(self._saved_env)
        self.tmp.cleanup()

    def test_port_available_detects_occupied_and_free_loopback_port(self):
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            self.assertFalse(desktop_app._port_available(port))
        finally:
            sock.close()
        self.assertTrue(desktop_app._port_available(port))

    def test_occupied_port_never_hits_foreign_server_or_leaks_token(self):
        import http.server
        import io
        import types

        received_paths: list[str] = []

        class ForeignHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                received_paths.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"foreign-server")

            def log_message(self, *args):
                pass

        foreign = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ForeignHandler)
        port = foreign.server_address[1]
        foreign_thread = threading.Thread(target=foreign.serve_forever, daemon=True)
        foreign_thread.start()

        fake_webview = types.SimpleNamespace(
            windows=[],
            create_window=unittest.mock.MagicMock(),
            start=unittest.mock.MagicMock(),
        )
        stderr = io.StringIO()
        try:
            with unittest.mock.patch.object(desktop_app, "BUNDLE_DIR", desktop_app.REPO_ROOT), \
                 unittest.mock.patch.dict(sys.modules, {"webview": fake_webview}), \
                 unittest.mock.patch("sys.stderr", stderr):
                code = desktop_app.main(["--port", str(port), "--state-dir", str(self.state), "--timeout", "1.0"])
        finally:
            foreign.shutdown()
            foreign.server_close()

        self.assertEqual(code, 1)
        self.assertEqual(received_paths, [], "严禁向占用端口的外部进程发起携带 DEMO_TOKEN 的请求")
        fake_webview.create_window.assert_not_called()
        self.assertIn(str(port), stderr.getvalue())
        session_file = self.state / "session.json"
        if session_file.exists():
            saved = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertFalse(saved.get("running"))
            self.assertIsNone(saved.get("url"))

    def test_worker_system_exit_captured_scrubs_session_and_fails_fast(self):
        import io
        import socket
        import types

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        class CrashingServer:
            def __init__(self, _config):
                self.started = False
                self.should_exit = False

            def run(self):
                raise SystemExit(1)

        fake_uvicorn = types.SimpleNamespace(
            Config=lambda *a, **kw: ("cfg", a, kw),
            Server=CrashingServer,
        )
        fake_webview = types.SimpleNamespace(
            windows=[],
            create_window=unittest.mock.MagicMock(),
            start=unittest.mock.MagicMock(),
        )
        orig_wait_http = desktop_app.wait_for_http

        def bounded_wait_http(url, timeout=1.2, **kwargs):
            return orig_wait_http(url, timeout=min(timeout, 1.2), **kwargs)

        stderr = io.StringIO()
        start = time.monotonic()
        with unittest.mock.patch.object(desktop_app, "BUNDLE_DIR", desktop_app.REPO_ROOT), \
             unittest.mock.patch.object(desktop_app, "seed_tex_cache", return_value=False), \
             unittest.mock.patch.object(desktop_app, "wait_for_http", side_effect=bounded_wait_http), \
             unittest.mock.patch.dict(sys.modules, {"uvicorn": fake_uvicorn, "webview": fake_webview}), \
             unittest.mock.patch("sys.stderr", stderr):
            code = desktop_app.main(["--port", str(port), "--state-dir", str(self.state), "--timeout", "1.5"])
        elapsed = time.monotonic() - start

        self.assertEqual(code, 1)
        self.assertLess(elapsed, 0.5, "后端线程 SystemExit(1) 时应在 0.5s 内快速失败,不能死等超时")
        self.assertIn("SystemExit(1)", stderr.getvalue())
        fake_webview.create_window.assert_not_called()
        session_file = self.state / "session.json"
        self.assertTrue(session_file.exists())
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertIs(saved.get("running"), False)
        self.assertIsNone(saved.get("url"))

    def test_write_session_is_atomic_0600_from_birth_and_lock_is_reentrant(self):
        created_modes: list[int] = []
        real_os_open = os.open

        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            if ".tmp" in str(path):
                created_modes.append(mode)
            return real_os_open(path, flags, mode, *args, **kwargs)

        with unittest.mock.patch.object(desktop_app.os, "open", side_effect=spy_open):
            desktop_app._write_session(self.state, {"running": False, "url": None})

        self.assertEqual(created_modes, [0o600], "_write_session 必须以 0o600 原子创建临时文件再替换")
        session_path = self.state / "session.json"
        self.assertEqual(session_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.state.glob("*tmp*")), [])

        import socket
        import types

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        class QuickServer:
            def __init__(self, _cfg):
                self.started = False
                self.should_exit = False

            def run(self):
                self.started = True
                while not self.should_exit:
                    time.sleep(0.02)

        fake_uvicorn = types.SimpleNamespace(Config=lambda *a, **kw: None, Server=QuickServer)
        box = {}
        with unittest.mock.patch.object(desktop_app, "BUNDLE_DIR", desktop_app.REPO_ROOT), \
             unittest.mock.patch.object(desktop_app, "seed_tex_cache", return_value=False), \
             unittest.mock.patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            desktop_app.start_backend_thread(self.state, port, box)
            try:
                self.assertIsInstance(box.get("lock"), type(threading.RLock()))
            finally:
                desktop_app.stop_backend_thread(box, self.state)


class StartupLifecycleTests(unittest.TestCase):
    """Issue #66 (2): 启动等待窗口期 SIGTERM 清理、子进程秒退与旧会话校验。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_wait_for_entry_returns_immediately_when_child_exits_early(self):
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(2)"])
        try:
            child.wait(timeout=5)
            start = time.monotonic()
            result = desktop_app.wait_for_entry(self.state, timeout=10.0, child=child)
            elapsed = time.monotonic() - start
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        self.assertIsNone(result)
        self.assertLess(elapsed, 0.5, "启动器子进程已退出时不应继续睡满 timeout")

    def test_sigterm_during_startup_wait_terminates_child_and_scrubs_session(self):
        repo = Path(__file__).resolve().parents[1]
        fake_launcher = Path(self.tmp.name) / "fake_launcher.py"
        child_pid_file = Path(self.tmp.name) / "child.pid"
        fake_launcher.write_text(
            "import json, os, sys, time\n"
            "from pathlib import Path\n"
            "state = Path(sys.argv[sys.argv.index('--state-dir') + 1])\n"
            "state.mkdir(parents=True, exist_ok=True)\n"
            f"Path({str(child_pid_file)!r}).write_text(str(os.getpid()), encoding='utf-8')\n"
            "(state / 'session.json').write_text(json.dumps({\n"
            "    'session_id': 'startup-wait',\n"
            "    'pid': os.getpid(),\n"
            "    'url': 'http://127.0.0.1:19876/studio?token=startup-secret',\n"
            "    'running': True,\n"
            "}), encoding='utf-8')\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )
        driver = Path(self.tmp.name) / "driver.py"
        driver.write_text(
            "import importlib.util, os, sys, time, types\n"
            "repo, state, launcher = sys.argv[1], sys.argv[2], sys.argv[3]\n"
            "os.environ.pop('TEXADA_BUNDLE_DIR', None)\n"
            "spec = importlib.util.spec_from_file_location('texada_app', os.path.join(repo, 'desktop', 'app.py'))\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "mod.LAUNCHER = launcher\n"
            "orig_wait = mod.wait_for_entry\n"
            "def slow_wait(state_dir, timeout, *args, **kwargs):\n"
            "    deadline = time.monotonic() + timeout\n"
            "    while time.monotonic() < deadline:\n"
            "        if (state_dir / 'session.json').exists():\n"
            "            print('IN_STARTUP_WAIT', flush=True)\n"
            "        time.sleep(0.1)\n"
            "    return None\n"
            "mod.wait_for_entry = slow_wait\n"
            "sys.modules['webview'] = types.SimpleNamespace(\n"
            "    windows=[], create_window=lambda *a, **kw: None, start=lambda *a, **kw: None)\n"
            "raise SystemExit(mod.main(['--state-dir', state, '--timeout', '30']))\n",
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [sys.executable, str(driver), str(repo), str(self.state), str(fake_launcher)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        spawned_child_pid = None
        try:
            ready = False
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if "IN_STARTUP_WAIT" in line:
                    ready = True
                    break
                if not line and proc.poll() is not None:
                    break
            self.assertTrue(ready, f"驱动进程未进入启动等待:{proc.stderr.read()}")
            spawned_child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
            proc.send_signal(15)  # SIGTERM
            proc.wait(timeout=10)

            saved = json.loads((self.state / "session.json").read_text(encoding="utf-8"))
            self.assertIs(saved.get("running"), False, "启动等待阶段收到 SIGTERM 必须擦除 running=True")
            self.assertIsNone(saved.get("url"), "启动等待阶段收到 SIGTERM 必须擦除私密 token URL")

            child_alive = True
            for _ in range(20):
                try:
                    os.kill(spawned_child_pid, 0)
                    time.sleep(0.05)
                except OSError:
                    child_alive = False
                    break
            self.assertFalse(child_alive, "启动等待阶段收到 SIGTERM 必须终止已拉起的启动器子进程")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if spawned_child_pid is not None:
                try:
                    os.kill(spawned_child_pid, 9)
                except OSError:
                    pass
            proc.stdout.close()
            proc.stderr.close()

    def test_sigterm_during_bundled_wait_for_http_scrubs_session(self):
        import socket

        repo = Path(__file__).resolve().parents[1]
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        driver = Path(self.tmp.name) / "bundled_driver.py"
        driver.write_text(
            "import importlib.util, os, sys, time, types\n"
            "repo, state, port = sys.argv[1], sys.argv[2], sys.argv[3]\n"
            "os.environ['TEXADA_BUNDLE_DIR'] = repo\n"
            "class FakeServer:\n"
            "    def __init__(self, _cfg):\n"
            "        self.started = False\n"
            "        self.should_exit = False\n"
            "    def run(self):\n"
            "        self.started = True\n"
            "        while not self.should_exit:\n"
            "            time.sleep(0.05)\n"
            "sys.modules['uvicorn'] = types.SimpleNamespace(\n"
            "    Config=lambda *a, **kw: None, Server=FakeServer)\n"
            "sys.modules['webview'] = types.SimpleNamespace(\n"
            "    windows=[], create_window=lambda *a, **kw: None, start=lambda *a, **kw: None)\n"
            "spec = importlib.util.spec_from_file_location('texada_app', os.path.join(repo, 'desktop', 'app.py'))\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "mod.seed_tex_cache = lambda *a, **kw: False\n"
            "orig_wait_http = mod.wait_for_http\n"
            "def notify_wait_http(url, timeout=30.0, **kwargs):\n"
            "    print('IN_WAIT_HTTP', flush=True)\n"
            "    return orig_wait_http(url, timeout=timeout, **kwargs)\n"
            "mod.wait_for_http = notify_wait_http\n"
            "raise SystemExit(mod.main(['--port', port, '--state-dir', state, '--timeout', '30']))\n",
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [sys.executable, str(driver), str(repo), str(self.state), str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            ready = False
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if "IN_WAIT_HTTP" in line:
                    ready = True
                    break
                if not line and proc.poll() is not None:
                    break
            self.assertTrue(ready, f"捆绑驱动未进入 wait_for_http:{proc.stderr.read()}")
            proc.send_signal(15)  # SIGTERM
            proc.wait(timeout=10)
            saved = json.loads((self.state / "session.json").read_text(encoding="utf-8"))
            self.assertIs(saved.get("running"), False)
            self.assertIsNone(saved.get("url"))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def test_main_does_not_reuse_previous_session_when_explicit_port_differs(self):
        import types

        write_session(self.state, {
            "url": "http://127.0.0.1:8888/studio?token=old-port-token",
            "pid": os.getpid(),
            "running": True,
        })
        fake_child = unittest.mock.MagicMock()
        fake_child.poll.return_value = 0
        fake_webview = types.SimpleNamespace(
            windows=[],
            create_window=unittest.mock.MagicMock(),
            start=unittest.mock.MagicMock(),
        )
        with unittest.mock.patch.object(desktop_app, "BUNDLE_DIR", None), \
             unittest.mock.patch.object(desktop_app.subprocess, "Popen", return_value=fake_child) as popen_mock, \
             unittest.mock.patch.object(desktop_app, "wait_for_entry", return_value={
                 "url": "http://127.0.0.1:9001/studio?token=new-port-token",
                 "pid": 43210,
                 "running": True,
             }), \
             unittest.mock.patch.dict(sys.modules, {"webview": fake_webview}):
            code = desktop_app.main(["--port", "9001", "--state-dir", str(self.state), "--timeout", "1.0"])

        self.assertEqual(code, 0)
        popen_mock.assert_called_once()
        fake_webview.create_window.assert_called_once()
        self.assertIn(":9001/", fake_webview.create_window.call_args.args[1])

    def test_main_falls_back_to_fresh_launch_when_previous_session_http_unreachable(self):
        import types

        dead_url = "http://127.0.0.1:8899/studio?token=recycled-pid"
        fresh_url = "http://127.0.0.1:8899/studio?token=fresh-session"
        write_session(self.state, {
            "url": dead_url,
            "pid": os.getpid(),
            "running": True,
        })
        fake_child = unittest.mock.MagicMock()
        fake_child.poll.return_value = 0
        fake_webview = types.SimpleNamespace(
            windows=[],
            create_window=unittest.mock.MagicMock(),
            start=unittest.mock.MagicMock(),
        )
        probed_urls: list[tuple[str, float]] = []

        def fake_wait_http(url, timeout=30.0, **kwargs):
            probed_urls.append((url, timeout))
            return url != dead_url

        with unittest.mock.patch.object(desktop_app, "BUNDLE_DIR", None), \
             unittest.mock.patch.object(desktop_app, "wait_for_http", side_effect=fake_wait_http), \
             unittest.mock.patch.object(desktop_app.subprocess, "Popen", return_value=fake_child) as popen_mock, \
             unittest.mock.patch.object(desktop_app, "wait_for_entry", return_value={
                 "url": fresh_url,
                 "pid": 54321,
                 "running": True,
             }), \
             unittest.mock.patch.dict(sys.modules, {"webview": fake_webview}):
            code = desktop_app.main(["--port", "8899", "--state-dir", str(self.state), "--timeout", "1.0"])

        self.assertEqual(code, 0)
        self.assertIn((dead_url, 3.0), probed_urls, "复用旧会话前必须用 3s 超时探测 HTTP 可达性")
        popen_mock.assert_called_once()
        self.assertEqual(fake_webview.create_window.call_args.args[1], fresh_url)


class BundleAndIconHygieneTests(unittest.TestCase):
    """Issue #66 (3): Retina icns 槽位、@loader_path 解析、去重拷贝与 py2app 外部构建目录。"""

    @unittest.skipUnless(
        sys.platform == "darwin" and shutil.which("sips") is not None
        and shutil.which("iconutil") is not None,
        "需要 macOS sips 与 iconutil",
    )
    def test_build_icon_generates_retina_chunks_in_both_builders(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icns_app = root / "AppIcon-thin.icns"
            ok = build_app.build_icon(root / "thin.iconset", icns_app)
            self.assertTrue(ok)
            self.assertFalse((root / "thin.iconset" / "icon_64x64.png").exists(), "不应生成无效的 icon_64x64.png")
            thin_chunks = _parse_icns_chunks(icns_app.read_bytes())
            self.assertTrue(
                {"ic10", "ic13", "ic14"}.issubset(thin_chunks),
                f"build_app 生成的 icns 缺少 Retina 块: {thin_chunks}",
            )

            icns_bundle = build_bundle.build_icon(root / "bundle-work")
            self.assertIsNotNone(icns_bundle)
            bundle_chunks = _parse_icns_chunks(icns_bundle.read_bytes())
            self.assertTrue(
                {"ic10", "ic13", "ic14"}.issubset(bundle_chunks),
                f"build_bundle 生成的 icns 缺少 Retina 块: {bundle_chunks}",
            )

    def test_resolve_dep_resolves_loader_path_against_owner_source_dir(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            cellar = Path(tmp) / "cellar"
            poppler_lib = cellar / "poppler" / "lib"
            glib_lib = cellar / "glib" / "lib"
            poppler_lib.mkdir(parents=True)
            glib_lib.mkdir(parents=True)
            sibling = poppler_lib / "libpoppler-cpp.0.dylib"
            sibling.write_bytes(b"macho")
            cousin = glib_lib / "libglib-2.0.0.dylib"
            cousin.write_bytes(b"macho")

            self.assertEqual(
                build_bundle._resolve_dep("@loader_path/libpoppler-cpp.0.dylib", poppler_lib),
                str(sibling.resolve()),
            )
            self.assertEqual(
                build_bundle._resolve_dep("@loader_path/../../glib/lib/libglib-2.0.0.dylib", poppler_lib),
                str(cousin.resolve()),
            )
            self.assertIsNone(build_bundle._resolve_dep("@loader_path/missing.dylib", poppler_lib))

    def test_bundle_dylibs_resolves_loader_path_and_deduplicates_shared_sources(self):
        import shutil as real_shutil
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cellar = root / "cellar"
            opt_dir = cellar / "poppler" / "lib"
            sub_dir = opt_dir / "sub"
            sub_dir.mkdir(parents=True)
            bin_dir = root / "staging" / "bin"
            lib_dir = root / "staging" / "tools-lib"
            bin_dir.mkdir(parents=True)

            exe = bin_dir / "pdftoppm"
            exe.write_bytes(b"exe")
            lib_a = opt_dir / "libA.dylib"
            lib_b = opt_dir / "libB.dylib"
            lib_shared = sub_dir / "libShared.dylib"
            for item in (lib_a, lib_b, lib_shared):
                item.write_bytes(b"dylib")

            graph = {
                "pdftoppm": ([str(lib_a), str(lib_b)], []),
                "libA.dylib": (["@loader_path/sub/libShared.dylib"], []),
                "libB.dylib": (["@loader_path/sub/libShared.dylib"], []),
                "libShared.dylib": (["/usr/lib/libSystem.B.dylib"], []),
            }
            copied_sources: list[str] = []
            rewrites: list[list[str]] = []
            orig_copy2 = real_shutil.copy2

            def tracking_copy2(src, dst, *a, **kw):
                copied_sources.append(Path(src).name)
                return orig_copy2(src, dst, *a, **kw)

            def fake_subproc_run(argv, **kwargs):
                if argv[0] == "install_name_tool":
                    rewrites.append(argv)
                return subprocess.CompletedProcess(argv, 0, "", "")

            with unittest.mock.patch.object(build_bundle, "_load_commands",
                                            side_effect=lambda p: graph[Path(p).name]), \
                 unittest.mock.patch.object(build_bundle.shutil, "copy2", side_effect=tracking_copy2), \
                 unittest.mock.patch.object(build_bundle.subprocess, "run", side_effect=fake_subproc_run):
                count = build_bundle.bundle_dylibs(
                    bin_dir, lib_dir, {str(exe): str(cellar / "poppler" / "bin" / "pdftoppm")}
                )

            self.assertEqual(count, 3)
            self.assertTrue((lib_dir / "libShared.dylib").exists(), "@loader_path 依赖必须被收集到 tools-lib")
            self.assertEqual(copied_sources.count("libShared.dylib"), 1, "共享传递依赖只应拷贝一次")
            shared_changes = [
                cmd for cmd in rewrites
                if "-change" in cmd and "@loader_path/sub/libShared.dylib" in cmd
            ]
            self.assertEqual(len(shared_changes), 2, "libA 与 libB 的 @loader_path 引用都必须重写")

    def test_bundle_dylibs_resolves_symlinked_root_binary_loader_path(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brew_bin = root / "opt" / "homebrew" / "bin"
            cellar_bin = root / "opt" / "homebrew" / "Cellar" / "poppler" / "24.0" / "bin"
            cellar_lib = root / "opt" / "homebrew" / "Cellar" / "poppler" / "24.0" / "lib"
            brew_bin.mkdir(parents=True)
            cellar_bin.mkdir(parents=True)
            cellar_lib.mkdir(parents=True)

            real_tool = cellar_bin / "pdftoppm"
            real_tool.write_bytes(b"exe")
            symlink_tool = brew_bin / "pdftoppm"
            symlink_tool.symlink_to(os.path.relpath(real_tool, brew_bin))

            keg_dylib = cellar_lib / "libpoppler.140.dylib"
            keg_dylib.write_bytes(b"dylib")

            bin_dir = root / "staging" / "bin"
            lib_dir = root / "staging" / "tools-lib"
            bin_dir.mkdir(parents=True)
            staged = bin_dir / "pdftoppm"
            staged.write_bytes(b"exe")

            graph = {
                "pdftoppm": (["@rpath/libpoppler.140.dylib"], ["@loader_path/../lib"]),
                "libpoppler.140.dylib": (["/usr/lib/libSystem.B.dylib"], []),
            }
            with unittest.mock.patch.object(build_bundle, "_load_commands",
                                            side_effect=lambda p: graph[Path(p).name]), \
                 unittest.mock.patch.object(build_bundle.subprocess, "run",
                                            return_value=subprocess.CompletedProcess([], 0, "", "")):
                count = build_bundle.bundle_dylibs(bin_dir, lib_dir, {str(staged): str(symlink_tool)})

            self.assertEqual(count, 1, "符号链接入口工具必须先 resolve 到真实 Cellar/bin 再展开 @loader_path/../lib")
            self.assertTrue((lib_dir / "libpoppler.140.dylib").exists())

    def test_build_bundle_passes_out_of_tree_bdist_base_to_py2app(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "dist-out"
            py2app_calls: list[list[str]] = []

            def fake_run(argv, **kwargs):
                if any("setup_bundle.py" in str(part) for part in argv):
                    py2app_calls.append([str(part) for part in argv])
                    dist_idx = argv.index("--dist-dir") + 1
                    dummy_app = Path(argv[dist_idx]) / "TeXada Studio.app"
                    (dummy_app / "Contents" / "Resources").mkdir(parents=True)
                return subprocess.CompletedProcess(argv, 0, "", "")

            def fake_probe(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, "", "")

            with unittest.mock.patch.object(build_bundle.sys, "platform", "darwin"), \
                 unittest.mock.patch.object(Path, "exists", autospec=True,
                                            side_effect=lambda self: True if str(self).endswith(".venv/bin/python")
                                            else os.path.exists(self)), \
                 unittest.mock.patch.object(build_bundle.subprocess, "run", side_effect=fake_probe), \
                 unittest.mock.patch.object(build_bundle, "stage_resources", return_value={}), \
                 unittest.mock.patch.object(build_bundle, "build_icon", return_value=None), \
                 unittest.mock.patch.object(build_bundle, "seal_app_bundle"), \
                 unittest.mock.patch.object(build_bundle, "run", side_effect=fake_run):
                code = build_bundle.main(["--output", str(out_dir), "--skip-poppler"])

            self.assertEqual(code, 0)
            self.assertEqual(len(py2app_calls), 1)
            cmd = py2app_calls[0]
            self.assertIn("--bdist-base", cmd, "py2app 必须显式指定外部 --bdist-base,防止污染 desktop/build/")
            bdist_val = cmd[cmd.index("--bdist-base") + 1]
            expected_bdist = str(out_dir.resolve() / ".bundle-work" / "py2app-build")
            self.assertEqual(bdist_val, expected_bdist)
            self.assertFalse((build_bundle.DESKTOP / "build").exists())


if __name__ == "__main__":
    unittest.main()
