# 桌面壳的离线测试:只覆盖无 GUI 的会话读取、进程判定与命令行组装。
"""桌面壳测试:无 GUI 覆盖会话/进程/命令行/看门狗;darwin 上另有原生信号集成验证。

运行:python -m unittest discover -s desktop -p 'test_*.py'(无需 pywebview 即可跑全部非集成用例)。
"""
from __future__ import annotations

import json
import os
import shutil
import signal
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
        custom = Path("/tmp/custom-state")
        argv = desktop_app.launcher_argv(custom, port=9001)
        self.assertIn("--port", argv)
        self.assertEqual(argv[argv.index("--port") + 1], "9001")
        self.assertIn("--state-dir", argv)
        self.assertEqual(argv[argv.index("--state-dir") + 1], str(custom))

    def test_launcher_env_marks_orphan_exit_without_dropping_existing_values(self):
        env = desktop_app.launcher_env({"PATH": "/bin", "HOME": "/tmp"})
        self.assertEqual(env["TEXADA_EXIT_WHEN_ORPHANED"], "1")
        self.assertEqual(env["PATH"], desktop_app.prepend_dirs("/bin", desktop_app.tool_bin_dirs()))
        self.assertEqual(env["HOME"], "/tmp")

    def test_prepend_dirs_is_idempotent_and_ordered(self):
        first = desktop_app.prepend_dirs("/usr/bin", ["/a", "/b"])
        self.assertEqual(first, os.pathsep.join(["/a", "/b", "/usr/bin"]))
        self.assertEqual(desktop_app.prepend_dirs(first, ["/a", "/b"]), first, "重复前置不叠加")
        self.assertEqual(desktop_app.prepend_dirs("", [Path("/x")]), str(Path("/x")))

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

    def test_seed_tex_cache_adds_missing_files_to_existing_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source", Path(tmp) / "target"
            relative = Path("bundles") / "data" / ("a" * 64)
            for root in (source, target):
                (root / relative).mkdir(parents=True)
            (source / relative / "cmmi5.pfb").write_bytes(b"new font")
            (source / relative / "other").write_bytes(b"bundled copy")
            (target / relative / "other").write_bytes(b"already cached")
            self.assertTrue(desktop_app.seed_tex_cache(source, target))
            self.assertEqual((target / relative / "cmmi5.pfb").read_bytes(), b"new font")
            self.assertEqual((target / relative / "other").read_bytes(), b"already cached")
            self.assertFalse(desktop_app.seed_tex_cache(source, target))

    def test_seed_tex_cache_seeds_missing_index_hashes_and_formats_into_existing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source", Path(tmp) / "target"
            digest = "b" * 64
            (source / "bundles" / "data" / digest).mkdir(parents=True)
            (source / "bundles" / "hashes").mkdir(parents=True)
            (source / "formats").mkdir(parents=True)
            (source / "bundles" / "data" / digest / "tikz.sty").write_bytes(b"tikz")
            (source / "bundles" / "data" / f"{digest}.index").write_bytes(b"index-data")
            (source / "bundles" / "data" / "bundle.prefetch").write_bytes(b"prefetch-data")
            (source / "bundles" / "hashes" / "default_bundle").write_bytes(b"hash-data")
            (source / "formats" / f"{digest}-latex-33.fmt").write_bytes(b"fmt-data")

            # Simulate an already-existing incomplete cache directory (e.g. failed prior run).
            target.mkdir()
            (target / "formats").mkdir()
            (target / "formats" / f"{digest}-latex-33.fmt").write_bytes(b"existing-fmt")

            self.assertTrue(desktop_app.seed_tex_cache(source, target))
            self.assertEqual((target / "bundles" / "data" / digest / "tikz.sty").read_bytes(), b"tikz")
            self.assertEqual((target / "bundles" / "data" / f"{digest}.index").read_bytes(), b"index-data")
            self.assertEqual((target / "bundles" / "data" / "bundle.prefetch").read_bytes(), b"prefetch-data")
            self.assertEqual((target / "bundles" / "hashes" / "default_bundle").read_bytes(), b"hash-data")
            self.assertEqual((target / "formats" / f"{digest}-latex-33.fmt").read_bytes(), b"existing-fmt")
            self.assertFalse(desktop_app.seed_tex_cache(source, target))


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
    """看门狗线程体:跨平台 socketpair 唤醒后有界等待,随后自行清理并强制退出。"""

    def run_watchdog(self, write_bytes, deadline=0.2):
        import socket

        read_sock, write_sock = socket.socketpair()
        read_sock.setblocking(False)
        write_sock.setblocking(False)
        cleaned = []
        exited = []
        state = {"shutdown": lambda: cleaned.append(True)}
        thread = threading.Thread(
            target=desktop_app._terminate_watchdog,
            args=(read_sock, state),
            kwargs={"deadline": deadline, "exiter": lambda code: exited.append(code)},
            daemon=True)
        thread.start()
        try:
            for payload in write_bytes:
                write_sock.sendall(payload)
                time.sleep(0.02)
            thread.join(timeout=5)
        finally:
            read_sock.close()
            write_sock.close()
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
        import socket

        read_sock, write_sock = socket.socketpair()
        read_sock.setblocking(False)
        write_sock.setblocking(False)
        exited = []
        thread = threading.Thread(
            target=desktop_app._terminate_watchdog,
            args=(read_sock, {}),
            kwargs={"deadline": 0.1, "exiter": lambda code: exited.append(code)},
            daemon=True)
        thread.start()
        try:
            write_sock.sendall(b"\x0f")
            thread.join(timeout=5)
        finally:
            read_sock.close()
            write_sock.close()
        self.assertEqual(exited, [0], "无清理钩子也不能卡死")

    def test_pre_wakeup_select_oserror_returns_without_shutdown_or_exit(self):
        import socket

        read_sock, write_sock = socket.socketpair()
        cleaned = []
        exited = []
        state = {"shutdown": lambda: cleaned.append(True)}
        try:
            with unittest.mock.patch.object(
                desktop_app.select,
                "select",
                side_effect=OSError(10038, "An operation was attempted on something that is not a socket"),
            ):
                desktop_app._terminate_watchdog(
                    read_sock, state, deadline=0.1, exiter=lambda code: exited.append(code)
                )
        finally:
            read_sock.close()
            write_sock.close()
        self.assertEqual(cleaned, [], "未收到唤醒字节前的 select 错误严禁触发 shutdown")
        self.assertEqual(exited, [], "未收到唤醒字节前的 select 错误严禁触发 os._exit(0)")

    def test_closed_wakeup_socket_eof_returns_without_shutdown_or_exit(self):
        import socket

        read_sock, write_sock = socket.socketpair()
        cleaned = []
        exited = []
        state = {"shutdown": lambda: cleaned.append(True)}
        thread = threading.Thread(
            target=desktop_app._terminate_watchdog,
            args=(read_sock, state),
            kwargs={"deadline": 0.1, "exiter": lambda code: exited.append(code)},
            daemon=True,
        )
        thread.start()
        write_sock.close()
        thread.join(timeout=2)
        read_sock.close()
        self.assertEqual(cleaned, [])
        self.assertEqual(exited, [])

    def test_post_wakeup_normal_teardown_keeps_finalization_safety_net_without_early_preempt(self):
        import socket

        read_sock, write_sock = socket.socketpair()
        read_sock.setblocking(False)
        write_sock.setblocking(False)
        cleaned = []
        exited = []
        state = {"shutdown": lambda: cleaned.append(True), "wakeup_sockets": (read_sock, write_sock)}
        thread = threading.Thread(
            target=desktop_app._terminate_watchdog,
            args=(read_sock, state),
            kwargs={"deadline": 0.25, "exiter": lambda code: exited.append(code)},
            daemon=True,
        )
        thread.start()
        try:
            write_sock.sendall(b"\x0f")
            time.sleep(0.05)
            # 模拟主线程已完成清理进入 finally:置空 shutdown 并调用非强制 _close_terminate_watchdog
            state["shutdown"] = None
            desktop_app._close_terminate_watchdog(state)
            # 非强制关闭不得立刻关 socket 抢跑 os._exit(0),让 main() 有充足时间返回并刷出缓冲
            self.assertEqual(exited, [], "finally 期间严禁因提前关闭 socket 立即抢跑 os._exit(0)")
            # 若解释器/WebKit 析构随后卡死,deadline 到期后看门狗仍必须兜底退出
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(cleaned, [], "shutdown 已由主线程完成置空,不应重复执行")
            self.assertEqual(exited, [0], "deadline 到期后仍应兜底保证进程退出")
        finally:
            desktop_app._close_terminate_watchdog(state, force=True)

    def test_install_and_close_terminate_watchdog_uses_socketpair(self):
        state = {}
        installed = desktop_app._install_terminate_watchdog(state, deadline=0.1, os_name="nt")
        try:
            self.assertTrue(installed)
            self.assertIn("wakeup_sockets", state)
            self.assertEqual(len(state["wakeup_sockets"]), 2)
        finally:
            desktop_app._close_terminate_watchdog(state)
        self.assertNotIn("wakeup_sockets", state)


class TerminateFallbackTests(unittest.TestCase):
    """SIGTERM 在窗口建立前的启动窗口也必须有界 code=0（E2E-5 发行契约）。

    抓什么：SIGTERM 落在「nodeinfo 就绪但 window_closer 未注册」的窗口期时，
    曾走 SIG_DFL 重抛（-15）违反契约；必须跑清理钩子后以 0 退出。
    """

    def test_sigterm_without_window_closer_cleans_up_and_exits_zero(self):
        calls = []
        state = {"window_closer": None, "shutdown": lambda: calls.append("cleanup")}
        desktop_app._terminate_action(
            signal.SIGTERM, state, exiter=lambda code: calls.append(("exit", code)))
        self.assertEqual(calls, ["cleanup", ("exit", 0)])

    def test_sigterm_window_closer_failure_still_exits_zero(self):
        calls = []

        def broken():
            calls.append("closer")
            raise RuntimeError("boom")

        state = {"window_closer": broken, "shutdown": lambda: calls.append("cleanup")}
        desktop_app._terminate_action(
            signal.SIGTERM, state, exiter=lambda code: calls.append(("exit", code)))
        self.assertEqual(calls, ["closer", "cleanup", ("exit", 0)])

    def test_windowed_sigterm_keeps_normal_cleanup_path(self):
        calls = []
        state = {"window_closer": lambda: calls.append("closer"),
                 "shutdown": lambda: calls.append("cleanup")}
        desktop_app._terminate_action(
            signal.SIGTERM, state, exiter=lambda code: calls.append(("exit", code)))
        self.assertEqual(calls, ["closer"], "窗口路径不强制退出，主循环走正常收尾")

    def test_close_shown_windows_skips_unshown_window_and_falls_back_to_shutdown(self):
        import types

        unshown = types.SimpleNamespace(
            events=types.SimpleNamespace(shown=threading.Event()),
            destroy=unittest.mock.MagicMock(),
        )
        cleaned: list[str] = []
        exits: list[int] = []
        desktop_app._terminate_action(
            signal.SIGTERM,
            {
                "window_closer": lambda: desktop_app._close_shown_windows([unshown]),
                "shutdown": lambda: cleaned.append("shutdown"),
            },
            exiter=exits.append,
        )
        unshown.destroy.assert_not_called()
        self.assertEqual(cleaned, ["shutdown"])
        self.assertEqual(exits, [0])

        shown_event = threading.Event()
        shown_event.set()
        shown = types.SimpleNamespace(
            events=types.SimpleNamespace(shown=shown_event),
            destroy=unittest.mock.MagicMock(),
        )
        cleaned.clear()
        exits.clear()
        desktop_app._terminate_action(
            signal.SIGTERM,
            {
                "window_closer": lambda: desktop_app._close_shown_windows([shown]),
                "shutdown": lambda: cleaned.append("shutdown"),
            },
            exiter=exits.append,
        )
        shown.destroy.assert_called_once()
        self.assertEqual(cleaned, [])
        self.assertEqual(exits, [])


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
            "orig_create = webview.create_window\n"
            "def create_window(*args, **kwargs):\n"
            "    win = orig_create(*args, **kwargs)\n"
            "    def on_shown():\n"
            "        from PyObjCTools import AppHelper\n"
            "        AppHelper.callAfter(lambda: print('IN_RUNLOOP', flush=True))\n"
            "    win.events.shown += on_shown\n"
            "    return win\n"
            "webview.create_window = create_window\n"
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
        if os.name == "posix":
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

    @unittest.skipUnless(os.name == "posix", "POSIX SIGTERM subprocess delivery required")
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
            if not ready:
                self.fail(f"驱动进程未进入启动等待:{proc.stderr.read()}")
            spawned_child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
            proc.send_signal(15)  # SIGTERM
            code = proc.wait(timeout=10)
            self.assertEqual(code, 0, "启动等待阶段收到 SIGTERM 必须有界以退出码 0 结束")

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

    @unittest.skipUnless(os.name == "posix", "POSIX SIGTERM subprocess delivery required")
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
            if not ready:
                self.fail(f"捆绑驱动未进入 wait_for_http:{proc.stderr.read()}")
            proc.send_signal(15)  # SIGTERM
            code = proc.wait(timeout=10)
            self.assertEqual(code, 0, "捆绑模式 wait_for_http 阶段收到 SIGTERM 必须有界以退出码 0 结束")
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
        import plistlib
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "dist-out"
            fake_icon = Path(tmp) / "fake.icns"
            fake_icon.write_bytes(b"icns")
            py2app_calls: list[list[str]] = []

            def fake_run(argv, **kwargs):
                if any("setup_bundle.py" in str(part) for part in argv):
                    py2app_calls.append([str(part) for part in argv])
                    dist_idx = argv.index("--dist-dir") + 1
                    dummy_app = Path(argv[dist_idx]) / "TeXada Studio.app"
                    (dummy_app / "Contents" / "Resources").mkdir(parents=True)
                    (dummy_app / "Contents" / "Info.plist").write_bytes(
                        plistlib.dumps({"CFBundleIconFile": "PythonApplet"})
                    )
                return subprocess.CompletedProcess(argv, 0, "", "")

            def fake_probe(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, "", "")

            with unittest.mock.patch.object(build_bundle.sys, "platform", "darwin"), \
                 unittest.mock.patch.object(Path, "exists", autospec=True,
                                            side_effect=lambda self: True if self.as_posix().endswith(".venv/bin/python")
                                            else os.path.exists(self)), \
                 unittest.mock.patch.object(build_bundle.subprocess, "run", side_effect=fake_probe), \
                 unittest.mock.patch.object(build_bundle, "stage_resources", return_value={}), \
                 unittest.mock.patch.object(build_bundle, "build_icon", return_value=fake_icon), \
                 unittest.mock.patch.object(build_bundle, "seal_app_bundle"), \
                 unittest.mock.patch.object(build_bundle, "run", side_effect=fake_run):
                code = build_bundle.main(["--output", str(out_dir), "--skip-poppler"])
                with unittest.mock.patch.object(build_bundle, "build_icon", return_value=None):
                    with self.assertRaises(SystemExit):
                        build_bundle.main(["--output", str(out_dir), "--skip-poppler"])

            self.assertEqual(code, 0)
            self.assertEqual(len(py2app_calls), 1)
            cmd = py2app_calls[0]
            self.assertIn("--bdist-base", cmd, "py2app 必须显式指定外部 --bdist-base,防止污染 desktop/build/")
            bdist_val = cmd[cmd.index("--bdist-base") + 1]
            expected_bdist = str(out_dir.resolve() / ".bundle-work" / "py2app-build")
            self.assertEqual(bdist_val, expected_bdist)
            self.assertFalse((build_bundle.DESKTOP / "build").exists())

    def test_bundle_poppler_forwards_resolved_pdfinfo_and_renderer_origins(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brew_bin = root / "opt" / "homebrew" / "bin"
            opt_poppler = root / "opt" / "homebrew" / "opt" / "poppler"
            cellar_poppler = root / "opt" / "homebrew" / "Cellar" / "poppler" / "25.0"
            (cellar_poppler / "bin").mkdir(parents=True)
            (cellar_poppler / "lib").mkdir(parents=True)
            brew_bin.mkdir(parents=True)
            opt_poppler.parent.mkdir(parents=True, exist_ok=True)
            opt_poppler.symlink_to(
                os.path.relpath(cellar_poppler, opt_poppler.parent),
                target_is_directory=True,
            )

            real_pdfinfo = cellar_poppler / "bin" / "pdfinfo"
            real_pdfinfo.write_bytes(b"pdfinfo")
            symlink_pdfinfo = brew_bin / "pdfinfo"
            symlink_pdfinfo.symlink_to(os.path.relpath(real_pdfinfo, brew_bin))

            real_cpp_lib = cellar_poppler / "lib" / "libpoppler-cpp.0.dylib"
            real_cpp_lib.write_bytes(b"dylib")
            (cellar_poppler / "lib" / "libpoppler-cpp.dylib").symlink_to("libpoppler-cpp.0.dylib")

            staging = root / "staging"
            (staging / "bin").mkdir(parents=True)
            captured_originals = {}

            def fake_run(argv, **kwargs):
                if argv[:3] == ["brew", "--prefix", "poppler"]:
                    return subprocess.CompletedProcess(argv, 0, str(opt_poppler) + "\n", "")
                if argv[0] == "xcrun":
                    out_idx = argv.index("-o") + 1
                    Path(argv[out_idx]).write_bytes(b"renderer")
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return subprocess.CompletedProcess(argv, 0, "", "")

            def fake_bundle_dylibs(bin_dir, lib_dir, originals=None):
                captured_originals.update(originals or {})
                return 2

            with unittest.mock.patch.object(build_bundle.shutil, "which", return_value=str(symlink_pdfinfo)), \
                 unittest.mock.patch.object(build_bundle, "run", side_effect=fake_run), \
                 unittest.mock.patch.object(build_bundle, "install_poppler_data"), \
                 unittest.mock.patch.object(build_bundle, "bundle_dylibs", side_effect=fake_bundle_dylibs):
                count = build_bundle.bundle_poppler(staging)

            self.assertEqual(count, 2)
            self.assertEqual(
                captured_originals,
                {
                    str(staging / "bin" / "pdfinfo"): str(real_pdfinfo.resolve()),
                    str(staging / "bin" / "pdftoppm"): str(real_cpp_lib.resolve()),
                },
            )

    def test_stage_resources_merges_poppler_and_llama_server_into_single_bundle_dylibs_pass(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brew_bin = root / "opt" / "homebrew" / "bin"
            opt_poppler = root / "opt" / "homebrew" / "opt" / "poppler"
            cellar_poppler = root / "opt" / "homebrew" / "Cellar" / "poppler" / "25.0"
            cellar_llama = root / "opt" / "homebrew" / "Cellar" / "llama.cpp" / "12000"
            (cellar_poppler / "bin").mkdir(parents=True)
            (cellar_poppler / "lib").mkdir(parents=True)
            (cellar_llama / "libexec" / "bin").mkdir(parents=True)
            brew_bin.mkdir(parents=True)
            opt_poppler.parent.mkdir(parents=True, exist_ok=True)
            opt_poppler.symlink_to(
                os.path.relpath(cellar_poppler, opt_poppler.parent),
                target_is_directory=True,
            )

            real_pdfinfo = cellar_poppler / "bin" / "pdfinfo"
            real_pdfinfo.write_bytes(b"pdfinfo")
            symlink_pdfinfo = brew_bin / "pdfinfo"
            symlink_pdfinfo.symlink_to(os.path.relpath(real_pdfinfo, brew_bin))

            real_cpp_lib = cellar_poppler / "lib" / "libpoppler-cpp.0.dylib"
            real_cpp_lib.write_bytes(b"dylib")
            (cellar_poppler / "lib" / "libpoppler-cpp.dylib").symlink_to("libpoppler-cpp.0.dylib")

            real_llama = cellar_llama / "libexec" / "bin" / "llama-server"
            real_llama.write_bytes(b"llama")
            symlink_llama = brew_bin / "llama-server"
            symlink_llama.symlink_to(os.path.relpath(real_llama, brew_bin))
            (cellar_llama / "LICENSE").write_text("MIT License - llama.cpp\n", encoding="utf-8")

            fake_tectonic = root / "tectonic"
            fake_tectonic.write_bytes(b"tectonic")
            fake_tex_cache = root / "tex-cache"
            fake_tex_cache.mkdir()
            (fake_tex_cache / "sample.fmt").write_bytes(b"fmt")

            staging = root / "staging"
            staging.mkdir()
            bundle_calls: list[dict[str, str]] = []
            smoke_cmds: list[tuple[str, str]] = []

            def fake_which(name):
                if name == "pdfinfo":
                    return str(symlink_pdfinfo)
                if name == "llama-server":
                    return str(symlink_llama)
                return None

            def fake_run(argv, **kwargs):
                if argv[:3] == ["brew", "--prefix", "poppler"]:
                    return subprocess.CompletedProcess(argv, 0, str(opt_poppler) + "\n", "")
                if argv[0] == "xcrun":
                    out_idx = argv.index("-o") + 1
                    Path(argv[out_idx]).write_bytes(b"renderer")
                    return subprocess.CompletedProcess(argv, 0, "", "")
                if len(argv) == 2 and Path(argv[0]).parent == staging / "bin":
                    smoke_cmds.append((Path(argv[0]).name, argv[1]))
                return subprocess.CompletedProcess(argv, 0, "", "")

            def fake_bundle_dylibs(bin_dir, lib_dir, originals=None):
                bundle_calls.append(dict(originals or {}))
                return 3

            with unittest.mock.patch.object(build_bundle, "TECTONIC", fake_tectonic), \
                 unittest.mock.patch.object(build_bundle, "TEX_CACHE", fake_tex_cache), \
                 unittest.mock.patch.object(build_bundle, "copy_tree",
                                            side_effect=lambda src, dst, ignore=None: dst.mkdir(parents=True, exist_ok=True)), \
                 unittest.mock.patch.object(build_bundle.shutil, "which", side_effect=fake_which), \
                 unittest.mock.patch.object(build_bundle, "run", side_effect=fake_run), \
                 unittest.mock.patch.object(build_bundle, "install_poppler_data"), \
                 unittest.mock.patch.object(build_bundle, "verify_bundled_llama_server"), \
                 unittest.mock.patch.object(build_bundle, "bundle_dylibs", side_effect=fake_bundle_dylibs):
                build_bundle.stage_resources(staging, skip_poppler=False, with_llama_server=True)

            self.assertEqual(len(bundle_calls), 1, "bundle_dylibs must run in a single combined pass")
            self.assertEqual(
                bundle_calls[0],
                {
                    str(staging / "bin" / "pdfinfo"): str(real_pdfinfo.resolve()),
                    str(staging / "bin" / "pdftoppm"): str(real_cpp_lib.resolve()),
                    str(staging / "bin" / "llama-server"): str(real_llama.resolve()),
                },
            )
            self.assertEqual(
                (staging / "licenses" / "llama.cpp-LICENSE.txt").read_text(encoding="utf-8"),
                "MIT License - llama.cpp\n",
            )
            self.assertEqual(
                smoke_cmds,
                [
                    ("tectonic", "--version"),
                    ("pdfinfo", "-v"),
                    ("pdftoppm", "-v"),
                    ("llama-server", "--version"),
                ],
            )

    def test_extract_llama_server_tar_verifies_sha256_and_rejects_unsafe_entries(self):
        import hashlib
        import io
        import tarfile
        import build_bundle

        def make_tar(entries):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tf:
                for name, kind, payload in entries:
                    info = tarfile.TarInfo(name=name)
                    if kind == "symlink":
                        info.type = tarfile.SYMTYPE
                        info.linkname = payload
                        tf.addfile(info)
                    else:
                        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
                        info.size = len(data)
                        info.mode = 0o755
                        tf.addfile(info, io.BytesIO(data))
            return buf.getvalue()

        valid_bytes = make_tar([
            ("llama-b12631/llama-server", "file", b"\xcf\xfa\xed\xfe-server"),
            ("llama-b12631/libggml-metal.1.0.0.dylib", "file", b"\xcf\xfa\xed\xfe-metal"),
            ("llama-b12631/libggml-metal.1.dylib", "symlink", "libggml-metal.1.0.0.dylib"),
            ("llama-b12631/LICENSE", "file", "MIT License - llama.cpp\n"),
        ])
        valid_sha = hashlib.sha256(valid_bytes).hexdigest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                build_bundle.extract_llama_server_tar(
                    valid_bytes, root / "bad", root / "lic", expected_sha256="0" * 64
                )
            extracted_bin = build_bundle.extract_llama_server_tar(
                valid_bytes, root / "ok", root / "lic", expected_sha256=valid_sha
            )
            self.assertTrue(extracted_bin.is_file())
            self.assertEqual((extracted_bin.parent / "libggml-metal.1.dylib").resolve(),
                             (extracted_bin.parent / "libggml-metal.1.0.0.dylib").resolve())
            self.assertIn("MIT License", (root / "lic" / "llama.cpp-LICENSE.txt").read_text(encoding="utf-8"))

            traversal_bytes = make_tar([("../outside", "file", b"bad")])
            with self.assertRaises(ValueError):
                build_bundle.extract_llama_server_tar(
                    traversal_bytes, root / "trav", root / "lic2",
                    expected_sha256=hashlib.sha256(traversal_bytes).hexdigest(),
                )

            escape_link_bytes = make_tar([
                ("llama-b12631/llama-server", "file", b"ok"),
                ("llama-b12631/libbad.dylib", "symlink", "../../etc/passwd"),
            ])
            with self.assertRaises(ValueError):
                build_bundle.extract_llama_server_tar(
                    escape_link_bytes, root / "esc", root / "lic3",
                    expected_sha256=hashlib.sha256(escape_link_bytes).hexdigest(),
                )

    def test_verify_bundled_llama_server_rejects_backendless_or_homebrew_leaking_binary(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp) / "Resources"
            llama_bin = staging / "bin" / "llama-server"
            llama_bin.parent.mkdir(parents=True)
            llama_bin.write_bytes(b"stub")

            def fake_run_output(stdout_text, stderr_text=""):
                return subprocess.CompletedProcess([str(llama_bin), "--list-devices"], 0, stdout_text, stderr_text)

            with unittest.mock.patch.object(
                build_bundle.subprocess, "run",
                return_value=fake_run_output("Available devices:\n  (none)\n"),
            ):
                with self.assertRaisesRegex(SystemExit, "没有可用计算后端"):
                    build_bundle.verify_bundled_llama_server(llama_bin, staging)

            with unittest.mock.patch.object(
                build_bundle.subprocess, "run",
                side_effect=OSError("Exec format error"),
            ):
                with self.assertRaises(SystemExit):
                    build_bundle.verify_bundled_llama_server(llama_bin, staging)

            with unittest.mock.patch.object(
                build_bundle.subprocess, "run",
                return_value=subprocess.CompletedProcess([str(llama_bin), "--list-devices"], -6, "", "GGML_ASSERT failed\n"),
            ):
                with self.assertRaises(SystemExit):
                    build_bundle.verify_bundled_llama_server(llama_bin, staging)

            leaked_stderr = (
                f"dyld[99]: <UUID> {staging.resolve()}/tools-lib/libggml.1.0.0.dylib\n"
                "dyld[99]: <UUID> /opt/homebrew/Cellar/ggml/1.0.0/libexec/libggml-metal.so\n"
            )
            with unittest.mock.patch.object(
                build_bundle.subprocess, "run",
                return_value=fake_run_output("Available devices:\n  MTL0: Apple M5\n", leaked_stderr),
            ):
                with self.assertRaisesRegex(SystemExit, "包外动态库"):
                    build_bundle.verify_bundled_llama_server(llama_bin, staging)

            clean_stderr = (
                f"dyld[99]: <UUID> {staging.resolve()}/bin/llama-server\n"
                f"dyld[99]: <UUID> {staging.resolve()}/tools-lib/libggml-metal.1.0.0.dylib\n"
                "dyld[99]: <UUID> /System/Library/Frameworks/Metal.framework/Versions/A/Metal\n"
                "dyld[99]: <UUID> /usr/lib/libSystem.B.dylib\n"
            )
            with unittest.mock.patch.object(
                build_bundle.subprocess, "run",
                return_value=fake_run_output("Available devices:\n  MTL0: Apple M5\n  BLAS: Accelerate\n", clean_stderr),
            ):
                build_bundle.verify_bundled_llama_server(llama_bin, staging)

    def test_uses_external_ggml_plugins_detects_dynamic_backend_loader(self):
        import build_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brew_bin = root / "bin" / "llama-server"
            brew_bin.parent.mkdir(parents=True)
            brew_bin.write_bytes(b"macho")
            ggml_lib = root / "lib" / "libggml.1.dylib"
            ggml_lib.parent.mkdir(parents=True)
            ggml_lib.write_bytes(b"header /opt/homebrew/Cellar/ggml/1.0.0/libexec footer")

            with unittest.mock.patch.object(
                build_bundle, "_load_commands",
                return_value=([str(ggml_lib)], []),
            ):
                self.assertTrue(build_bundle._uses_external_ggml_plugins(brew_bin))

            with unittest.mock.patch.object(
                build_bundle, "_load_commands",
                return_value=(["@rpath/libggml.1.dylib", "@rpath/libggml-metal.1.dylib", "@rpath/libggml-cpu.1.dylib"], ["@loader_path"]),
            ):
                self.assertFalse(build_bundle._uses_external_ggml_plugins(brew_bin))

    def test_desktop_bundle_version_metadata_is_synchronized(self):
        import plistlib
        import build_app
        import build_windows_bundle

        plist = plistlib.loads(build_app.INFO_PLIST.encode("utf-8"))
        short_ver = plist["CFBundleShortVersionString"]
        setup_text = (build_windows_bundle.DESKTOP / "setup_bundle.py").read_text(encoding="utf-8")
        self.assertIn(f'"CFBundleShortVersionString": "{short_ver}"', setup_text)
        self.assertEqual(build_windows_bundle.APP_VERSION, short_ver)
        expected_tuple = (*map(int, short_ver.split(".")), 0)
        self.assertEqual(build_windows_bundle.FILE_VERSION_TUPLE, expected_tuple)


class WindowsDesktopAppTests(unittest.TestCase):
    """Windows 进程存活探测、解释器路径、状态目录与 Tectonic 缓存目录契约。"""

    def test_entry_alive_uses_win32_synchronize_without_os_kill(self):
        import ctypes
        import types

        closed = []
        fake_kernel32 = types.SimpleNamespace(
            OpenProcess=unittest.mock.MagicMock(return_value=99),
            WaitForSingleObject=unittest.mock.MagicMock(return_value=0x00000102),
            CloseHandle=unittest.mock.MagicMock(side_effect=lambda h: closed.append(h) or 1),
        )
        fake_windll = types.SimpleNamespace(kernel32=fake_kernel32)
        with unittest.mock.patch.object(desktop_app.os, "name", "nt"), \
             unittest.mock.patch.object(desktop_app.os, "kill", side_effect=AssertionError("os.kill forbidden on Windows")), \
             unittest.mock.patch.object(ctypes, "windll", fake_windll, create=True), \
             unittest.mock.patch.object(ctypes, "get_last_error", return_value=0, create=True):
            self.assertTrue(desktop_app.entry_alive({"pid": 4321, "running": True, "url": "http://127.0.0.1:8888/studio?token=a"}))
            fake_kernel32.OpenProcess.assert_called_once_with(0x00100000, False, 4321)
            fake_kernel32.WaitForSingleObject.assert_called_once_with(99, 0)
            self.assertEqual(closed, [99])

            closed.clear()
            fake_kernel32.WaitForSingleObject.return_value = 0
            self.assertFalse(desktop_app.entry_alive({"pid": 4321, "running": True, "url": "http://127.0.0.1:8888/studio?token=a"}))
            self.assertEqual(closed, [99])

            fake_kernel32.OpenProcess.return_value = 0
            with unittest.mock.patch.object(ctypes, "get_last_error", return_value=5, create=True):
                self.assertTrue(desktop_app.entry_alive({"pid": 7777, "running": True, "url": "http://127.0.0.1:8888/studio?token=a"}))
            with unittest.mock.patch.object(ctypes, "get_last_error", return_value=87, create=True):
                self.assertFalse(desktop_app.entry_alive({"pid": 7777, "running": True, "url": "http://127.0.0.1:8888/studio?token=a"}))
            self.assertFalse(desktop_app.entry_alive({"pid": True, "running": True, "url": "http://127.0.0.1:8888/studio?token=a"}))
            fake_kernel32.OpenProcess.reset_mock()
            self.assertFalse(
                desktop_app.entry_alive({"pid": (1 << 32) + 4321, "running": True, "url": "http://127.0.0.1:8888/studio?token=a"}),
                "超过 32 位无符号范围的 PID 必须直接拒绝,不得经 c_uint32 回绕",
            )
            fake_kernel32.OpenProcess.assert_not_called()

    def test_windows_and_linux_platform_paths(self):
        fake_repo = Path("C:/repo")
        fake_home = Path("C:/Profiles/tester")
        self.assertEqual(
            desktop_app._default_venv_python(fake_repo, os_name="nt"),
            fake_repo / ".venv" / "Scripts" / "python.exe",
        )
        self.assertEqual(
            desktop_app._default_venv_python(fake_repo, os_name="posix"),
            fake_repo / ".venv" / "bin" / "python",
        )
        self.assertEqual(
            desktop_app._default_state_dir(
                platform_name="win32",
                os_name="nt",
                env={"LOCALAPPDATA": str(fake_home / "AppData" / "Local")},
                home=fake_home,
            ),
            fake_home / "AppData" / "Local" / "TeXada Studio",
        )
        self.assertEqual(
            desktop_app._default_state_dir(
                platform_name="linux",
                os_name="posix",
                env={"XDG_DATA_HOME": "/var/tmp/xdg"},
                home=Path("/home/tester"),
            ),
            Path("/var/tmp/xdg") / "texada-studio",
        )
        self.assertEqual(
            desktop_app._default_tex_cache_target(
                platform_name="win32",
                os_name="nt",
                env={"LOCALAPPDATA": str(fake_home / "AppData" / "Local")},
                home=fake_home,
            ),
            fake_home / "AppData" / "Local" / "TectonicProject" / "Tectonic" / "Cache",
        )


class WindowsBundleBuilderTests(unittest.TestCase):
    """离线单测:覆盖 ICO 生成、资源暂存、llama-server ZIP 校验/防越界、PyInstaller 外部目录隔离与冻结入口分发。"""

    def _make_rgba_png(self, width: int, height: int) -> bytes:
        import struct
        import zlib

        def chunk(tag: bytes, payload: bytes) -> bytes:
            crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
            return struct.pack(">I4s", len(payload), tag) + payload + struct.pack(">I", crc)

        raw = b"".join(b"\x00" + (b"\x10\x40\x90\xff" * width) for _ in range(height))
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )

    def _make_zip(self, members: dict[str, bytes]) -> bytes:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_build_icon_generates_valid_vista_png_in_ico_from_master_and_small_png(self):
        import struct
        import build_windows_bundle

        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            ico_path = build_windows_bundle.build_icon(workdir)
            self.assertIsNotNone(ico_path)
            raw = ico_path.read_bytes()
            reserved, ico_type, count = struct.unpack("<HHH", raw[:6])
            self.assertEqual((reserved, ico_type), (0, 1), "ICO 头部魔数必须为 00 00 01 00")
            self.assertGreaterEqual(count, 1)
            for idx in range(count):
                entry = raw[6 + idx * 16: 6 + (idx + 1) * 16]
                w_b, h_b, _cc, _res, planes, bpp, size, offset = struct.unpack("<BBBBHHII", entry)
                self.assertEqual(planes, 1)
                self.assertEqual(bpp, 32)
                frame = raw[offset: offset + size]
                self.assertEqual(frame[:8], b"\x89PNG\r\n\x1a\n", "ICO 帧必须内嵌合法 PNG")
                png_w, png_h = struct.unpack(">II", frame[16:24])
                self.assertLessEqual(png_w, 256, "Windows user32 图标帧不得超过 256px")
                self.assertLessEqual(png_h, 256)
                self.assertEqual(w_b, 0 if png_w == 256 else png_w)
                self.assertEqual(h_b, 0 if png_h == 256 else png_h)

            small_png = workdir / "small.png"
            small_bytes = self._make_rgba_png(32, 32)
            small_png.write_bytes(small_bytes)
            small_ico = build_windows_bundle.build_icon(workdir / "small-out", source_png=small_png)
            self.assertIsNotNone(small_ico)
            small_raw = small_ico.read_bytes()
            self.assertEqual(small_raw[:4], b"\x00\x00\x01\x00")
            self.assertIn(small_bytes, small_raw)

    def test_extract_llama_server_zip_verifies_sha256_extracts_dlls_and_blocks_zip_slip(self):
        import hashlib
        import build_windows_bundle

        self.assertEqual(
            build_windows_bundle.LLAMA_WINDOWS_SHA256,
            "8b3639c62c6c41b8134797ea9beedd6b6c26caad6a1ed99a3d5a2802262923d7",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            lic_dir = root / "licenses"
            payload = self._make_zip({
                "build/bin/llama-server.exe": b"MZ-llama-server",
                "build/bin/llama.dll": b"MZ-llama-dll",
                "build/bin/mtmd.dll": b"MZ-mtmd-dll",
                "build/LICENSE": b"MIT License - ggml-org/llama.cpp\n",
            })
            digest = hashlib.sha256(payload).hexdigest()

            with self.assertRaises(ValueError):
                build_windows_bundle.extract_llama_server_zip(
                    payload, bin_dir, lic_dir, expected_sha256="0" * 64
                )
            self.assertFalse((bin_dir / "llama-server.exe").exists())

            exe = build_windows_bundle.extract_llama_server_zip(
                payload, bin_dir, lic_dir, expected_sha256=digest
            )
            self.assertEqual(exe, bin_dir / "llama-server.exe")
            self.assertEqual((bin_dir / "llama-server.exe").read_bytes(), b"MZ-llama-server")
            self.assertEqual((bin_dir / "llama.dll").read_bytes(), b"MZ-llama-dll")
            self.assertEqual((bin_dir / "mtmd.dll").read_bytes(), b"MZ-mtmd-dll")
            self.assertEqual(
                (lic_dir / "llama.cpp-LICENSE.txt").read_text(encoding="utf-8"),
                "MIT License - ggml-org/llama.cpp\n",
            )

            evil_zip = self._make_zip({
                "llama-server.exe": b"MZ-llama",
                "../../escape.dll": b"evil",
            })
            evil_digest = hashlib.sha256(evil_zip).hexdigest()
            with self.assertRaises(ValueError):
                build_windows_bundle.extract_llama_server_zip(
                    evil_zip, root / "sub" / "bin", lic_dir, expected_sha256=evil_digest
                )
            self.assertFalse((root / "escape.dll").exists())

    def test_stage_resources_and_main_isolate_pyinstaller_workdirs_outside_repo(self):
        import hashlib
        import build_windows_bundle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_home = root / "home"
            texada_bin = fake_home / ".texada" / "bin"
            poppler_share = fake_home / ".texada" / "share" / "poppler" / "cMap"
            poppler_lic = fake_home / ".texada" / "licenses" / "poppler-windows"
            tex_cache = root / "tex-cache"
            for d in (texada_bin, poppler_share, poppler_lic, tex_cache / "bundles"):
                d.mkdir(parents=True)

            (texada_bin / "tectonic.exe").write_bytes(b"MZ-tectonic")
            (texada_bin / "pdfinfo.exe").write_bytes(b"MZ-pdfinfo")
            (texada_bin / "pdftoppm.exe").write_bytes(b"MZ-pdftoppm")
            (texada_bin / "poppler.dll").write_bytes(b"MZ-poppler-dll")
            (poppler_share / "Identity-H").write_bytes(b"cmap")
            (poppler_lic / "LICENSE").write_text("GPL-2.0-or-later\n", encoding="utf-8")
            (tex_cache / "bundles" / "a.txt").write_bytes(b"cached-tex")

            llama_zip_bytes = self._make_zip({
                "llama-server.exe": b"MZ-llama-server",
                "ggml.dll": b"MZ-ggml-dll",
            })
            llama_digest = hashlib.sha256(llama_zip_bytes).hexdigest()

            staging = root / "staging"
            staging.mkdir()
            smoke_seen: list[tuple[str, str]] = []

            def fake_run(argv, **kwargs):
                cmd0 = Path(argv[0])
                if len(argv) == 2 and cmd0.parent in (staging / "bin", staging / "Library" / "bin"):
                    smoke_seen.append((cmd0.name, argv[1]))
                return subprocess.CompletedProcess(argv, 0, "", "")

            with unittest.mock.patch.object(build_windows_bundle, "TECTONIC", texada_bin / "tectonic.exe"), \
                 unittest.mock.patch.object(build_windows_bundle, "POPPLER_BIN_DEFAULT", texada_bin), \
                 unittest.mock.patch.object(build_windows_bundle, "_resolve_tex_cache", return_value=tex_cache), \
                 unittest.mock.patch.object(build_windows_bundle, "LLAMA_WINDOWS_SHA256", llama_digest), \
                 unittest.mock.patch.object(build_windows_bundle, "copy_tree",
                                            side_effect=lambda src, dst, ignore=None: (
                                                shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)
                                                if src in (tex_cache, fake_home / ".texada" / "share" / "poppler")
                                                else dst.mkdir(parents=True, exist_ok=True)
                                            )), \
                 unittest.mock.patch.object(build_windows_bundle, "run", side_effect=fake_run):
                build_windows_bundle.stage_resources(
                    staging,
                    skip_poppler=False,
                    with_llama_server=True,
                    fetch=lambda _url: llama_zip_bytes,
                )

            self.assertEqual(
                smoke_seen,
                [
                    ("tectonic.exe", "--version"),
                    ("pdfinfo.exe", "-v"),
                    ("pdftoppm.exe", "-v"),
                    ("llama-server.exe", "--version"),
                ],
            )
            self.assertTrue((staging / "Library" / "bin" / "poppler.dll").is_file())
            self.assertTrue((staging / "bin" / "ggml.dll").is_file())
            self.assertTrue((staging / "share" / "poppler" / "cMap" / "Identity-H").is_file())
            self.assertTrue((staging / "licenses" / "tex-cache-manifest.sha256").is_file())
            self.assertTrue((staging / "licenses" / "llama.cpp-LICENSE.txt").is_file())
            self.assertTrue((staging / "scripts" / "start-local-studio.bat").is_file())

            out_dir = root / "dist-win"
            pyi_calls: list[list[str]] = []

            def fake_main_run(argv, **kwargs):
                if "-m" in argv and "PyInstaller" in argv:
                    pyi_calls.append([str(part) for part in argv])
                    dist_idx = argv.index("--distpath") + 1
                    produced = Path(argv[dist_idx]) / "TeXada Studio"
                    (produced / "_internal").mkdir(parents=True)
                    (produced / "TeXada Studio.exe").write_bytes(b"MZ-frozen-app")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with unittest.mock.patch.object(build_windows_bundle.sys, "platform", "win32"), \
                 unittest.mock.patch.object(build_windows_bundle, "_resolve_build_python", return_value=Path(sys.executable)), \
                 unittest.mock.patch.object(build_windows_bundle.subprocess, "run",
                                            return_value=subprocess.CompletedProcess([], 0, "", "")), \
                 unittest.mock.patch.object(build_windows_bundle, "stage_resources",
                                            side_effect=lambda stg, **_kw: (stg / "webui").mkdir(parents=True) or {}), \
                 unittest.mock.patch.object(build_windows_bundle, "run", side_effect=fake_main_run):
                rc = build_windows_bundle.main(["--output", str(out_dir), "--skip-poppler"])

            self.assertEqual(rc, 0)
            self.assertEqual(len(pyi_calls), 1)
            cmd = pyi_calls[0]
            for flag in ("--noconfirm", "--onedir", "--windowed", "--distpath", "--workpath", "--specpath"):
                self.assertIn(flag, cmd)
            work_root = str((out_dir.resolve() / ".bundle-work"))
            for path_flag in ("--distpath", "--workpath", "--specpath", "--icon"):
                val = cmd[cmd.index(path_flag) + 1]
                self.assertTrue(val.startswith(work_root), f"{path_flag}={val} 必须位于外部 .bundle-work 内")
            self.assertTrue((out_dir / "TeXada Studio" / "TeXada Studio.exe").is_file())
            self.assertTrue((out_dir / "TeXada Studio" / "Resources" / "webui").is_dir())
            self.assertFalse((out_dir / ".bundle-work").exists(), "构建完成后应清理临时目录")
            self.assertFalse((build_windows_bundle.DESKTOP / "build").exists())

    def test_windows_entry_resolves_bundle_dir_and_dispatches_python_scripts(self):
        import windows_entry

        with tempfile.TemporaryDirectory() as tmp:
            bundle_app = Path(tmp) / "TeXada Studio"
            res = bundle_app / "Resources"
            (res / "desktop").mkdir(parents=True)
            (res / "desktop" / "app.py").write_text(
                "def main(argv=None):\n    return 0\n",
                encoding="utf-8",
            )
            fake_exe = bundle_app / "TeXada Studio.exe"
            fake_exe.write_bytes(b"MZ")
            self.assertEqual(windows_entry.resolve_bundle_dir(executable=fake_exe), res.resolve())

            probe_script = Path(tmp) / "verify_probe.py"
            out_file = Path(tmp) / "probe_out.txt"
            probe_script.write_text(
                "import sys\nfrom pathlib import Path\n"
                f"Path({str(out_file)!r}).write_text('|'.join(sys.argv[1:]), encoding='utf-8')\n",
                encoding="utf-8",
            )
            saved_env = dict(os.environ)
            saved_argv = list(sys.argv)
            saved_stdout, saved_stderr = sys.stdout, sys.stderr
            try:
                os.environ.pop("TEXADA_BUNDLE_DIR", None)
                os.environ.pop("PYTHONUTF8", None)
                os.environ.pop("PYTHONIOENCODING", None)
                rc = windows_entry.run_entry([str(fake_exe), str(probe_script), "x^2+1"], executable=fake_exe)
                self.assertEqual(rc, 0)
                self.assertEqual(out_file.read_text(encoding="utf-8"), "x^2+1")
                self.assertEqual(os.environ.get("TEXADA_BUNDLE_DIR"), str(res.resolve()))
                self.assertEqual(os.environ.get("PYTHONUTF8"), "1")
                self.assertEqual(os.environ.get("PYTHONIOENCODING"), "utf-8")

                os.environ.pop("PYTHONUTF8", None)
                sys.stdout = None
                sys.stderr = None
                rc_dash_c = windows_entry.run_entry(
                    [str(fake_exe), "-c", "import os, sys; sys.stdout.write('ok'); assert os.environ['PYTHONUTF8'] == '1'"],
                    executable=fake_exe,
                )
                self.assertEqual(rc_dash_c, 0)
                self.assertIsNotNone(sys.stdout)
                self.assertIsNotNone(sys.stderr)
            finally:
                for stream, orig in ((sys.stdout, saved_stdout), (sys.stderr, saved_stderr)):
                    if stream is not None and stream is not orig:
                        try:
                            stream.close()
                        except Exception:
                            pass
                sys.stdout, sys.stderr = saved_stdout, saved_stderr
                os.environ.clear()
                os.environ.update(saved_env)
                sys.argv[:] = saved_argv


class DesktopExportPersistenceAndMenuTests(unittest.TestCase):
    """Issue #81 & #54: 桌面版导出桥接、持久化存储、未保存关窗保护、macOS 原生撤销/重做与 POSIX 管道回收。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_desktop_bridge_save_file_writes_atomically_overwrites_and_rejects_unsafe_inputs(self):
        import base64
        import types

        target = Path(self.tmp.name) / "exported.tex"
        target.write_text("stale content", encoding="utf-8")

        fake_window = types.SimpleNamespace(
            confirm_close=False,
            get_current_url=lambda: "http://127.0.0.1:8888/studio?token=abc",
            create_file_dialog=unittest.mock.MagicMock(return_value=str(target)),
        )
        fake_webview = types.SimpleNamespace(FileDialog=types.SimpleNamespace(SAVE=30))
        bridge = desktop_app._DesktopBridge(fake_webview)
        bridge._attach(fake_window)

        public_attrs = [name for name in dir(bridge) if not name.startswith("_")]
        self.assertEqual(sorted(public_attrs), ["save_file", "set_edit_state"],
                         "js_api 仅可暴露 save_file 与 set_edit_state，不得泄露内部窗口对象")

        payload = "\\documentclass{article}\n\\begin{document}你好\\end{document}\n".encode("utf-8")
        res = bridge.save_file("paper.tex", base64.b64encode(payload).decode("ascii"))
        self.assertEqual(res, {"saved": True, "cancelled": False, "name": "exported.tex"})
        self.assertEqual(target.read_bytes(), payload)
        fake_window.create_file_dialog.assert_called_once_with(30, save_filename="paper.tex")

        # 用户取消保存返回 cancelled=True 且不写盘
        fake_window.create_file_dialog.return_value = None
        cancelled = bridge.save_file("paper.pdf", base64.b64encode(b"%PDF-1.4").decode("ascii"))
        self.assertEqual(cancelled, {"saved": False, "cancelled": True})

        # 非法路径、非法后缀、非法 base64 与非回环来源必须拒绝
        for bad_name in ("../evil.tex", "a/b.tex", "a\\b.tex", "script.sh", ""):
            with self.subTest(bad_name=bad_name), self.assertRaises(ValueError):
                bridge.save_file(bad_name, base64.b64encode(b"x").decode("ascii"))
        with self.assertRaises(ValueError):
            bridge.save_file("ok.md", "not-valid-base64!!!")
        fake_window.get_current_url = lambda: "https://example.com/studio"
        with self.assertRaises(RuntimeError):
            bridge.save_file("ok.tex", base64.b64encode(b"x").decode("ascii"))

    def test_desktop_bridge_syncs_confirm_close_and_sigterm_clears_it(self):
        import types

        shown = threading.Event()
        shown.set()
        fake_window = types.SimpleNamespace(
            confirm_close=False,
            events=types.SimpleNamespace(shown=shown),
            destroy=unittest.mock.MagicMock(),
        )
        bridge = desktop_app._DesktopBridge()
        bridge._attach(fake_window)
        bridge.set_edit_state(dirty=True, can_undo=True, can_redo=False)
        self.assertTrue(fake_window.confirm_close)
        self.assertTrue(bridge._history_enabled("undo"))
        self.assertFalse(bridge._history_enabled("redo"))

        # SIGTERM 路径必须清除 confirm_close 并立即销毁窗口（保持 #50 有界退出）
        state = {
            "bridge": bridge,
            "window_closer": lambda: desktop_app._close_shown_windows([fake_window]),
            "shutdown": lambda: None,
        }
        desktop_app._terminate_action(signal.SIGTERM, state, exiter=lambda _c: None)
        self.assertFalse(fake_window.confirm_close)
        fake_window.destroy.assert_called_once()
        # 终止中不可被异步 JS 回调重新开启 confirm_close
        bridge.set_edit_state(dirty=True, can_undo=True, can_redo=True)
        self.assertFalse(fake_window.confirm_close)

    def test_main_enables_downloads_persistent_storage_and_bridge(self):
        from collections.abc import MutableMapping
        import types

        class MutableSettings(MutableMapping):
            def __init__(self, data):
                self._data = dict(data)
            def __getitem__(self, key): return self._data[key]
            def __setitem__(self, key, value): self._data[key] = value
            def __delitem__(self, key): del self._data[key]
            def __iter__(self): return iter(self._data)
            def __len__(self): return len(self._data)

        fake_settings = MutableSettings({"ALLOW_DOWNLOADS": False})
        fake_window = types.SimpleNamespace(
            confirm_close=False,
            events=types.SimpleNamespace(shown=types.SimpleNamespace()),
        )
        fake_webview = types.SimpleNamespace(
            settings=fake_settings,
            windows=[],
            create_window=unittest.mock.MagicMock(return_value=fake_window),
            start=unittest.mock.MagicMock(),
        )
        fake_child = unittest.mock.MagicMock()
        fake_child.poll.return_value = 0
        with unittest.mock.patch.object(desktop_app, "BUNDLE_DIR", None), \
             unittest.mock.patch.object(desktop_app.subprocess, "Popen", return_value=fake_child), \
             unittest.mock.patch.object(desktop_app, "wait_for_entry", return_value={
                 "url": "http://127.0.0.1:8888/studio?token=persist-tok",
                 "pid": 22222,
                 "running": True,
             }), \
             unittest.mock.patch.dict(sys.modules, {"webview": fake_webview}):
            code = desktop_app.main(["--port", "8888", "--state-dir", str(self.state), "--timeout", "1.0"])

        self.assertEqual(code, 0)
        self.assertTrue(fake_settings["ALLOW_DOWNLOADS"], "必须开启 ALLOW_DOWNLOADS（兼容 ImmutableDict）")
        create_kwargs = fake_webview.create_window.call_args.kwargs
        self.assertIsInstance(create_kwargs.get("js_api"), desktop_app._DesktopBridge)
        start_kwargs = fake_webview.start.call_args.kwargs
        self.assertIs(start_kwargs.get("private_mode"), False)
        expected_storage = self.state / "webview-storage"
        self.assertEqual(start_kwargs.get("storage_path"), str(expected_storage))
        self.assertTrue(expected_storage.is_dir())
        self.assertIn("global.quitConfirmation", start_kwargs.get("localization", {}))

        # 符号链接 webview-storage 必须拒绝
        if os.name == "posix":
            sym_state = Path(self.tmp.name) / "sym-state"
            sym_state.mkdir()
            (sym_state / "webview-storage").symlink_to(self.tmp.name)
            with self.assertRaises(RuntimeError):
                desktop_app._prepare_webview_storage(sym_state)

    def test_macos_edit_history_menu_injects_undo_redo_and_validates_state(self):
        class FakeMenuItem:
            def __init__(self, title="", action="", key="", separator=False):
                self._title = title
                self._action = action
                self._key = key
                self._mask = 0
                self._target = None
                self._submenu = None
                self._separator = separator

            @classmethod
            def alloc(cls):
                return cls()

            def initWithTitle_action_keyEquivalent_(self, title, action, key):
                self._title, self._action, self._key = title, action, key
                return self

            @classmethod
            def separatorItem(cls):
                return cls(separator=True)

            def setTarget_(self, target): self._target = target
            def setKeyEquivalentModifierMask_(self, mask): self._mask = mask
            def setSubmenu_(self, sub): self._submenu = sub
            def submenu(self): return self._submenu
            def action(self): return self._action
            def title(self): return self._title

        class FakeMenu:
            def __init__(self, title=""):
                self._title = title
                self._items = []
            def title(self): return self._title
            def itemArray(self): return list(self._items)
            def addItem_(self, item): self._items.append(item)
            def insertItem_atIndex_(self, item, idx): self._items.insert(idx, item)

        class FakeAppKit:
            NSObject = object
            NSMenuItem = FakeMenuItem
            NSEventModifierFlagCommand = 1 << 20
            NSEventModifierFlagShift = 1 << 17

        edit_sub = FakeMenu("Edit")
        edit_sub.addItem_(FakeMenuItem("Copy", "copy:", "c"))
        edit_top = FakeMenuItem("Edit")
        edit_top.setSubmenu_(edit_sub)
        main_menu = FakeMenu("Main")
        main_menu.addItem_(edit_top)
        fake_app = unittest.mock.MagicMock()
        fake_app.mainMenu.return_value = main_menu

        bridge = desktop_app._DesktopBridge()
        dispatched = []
        ok1 = desktop_app._install_macos_edit_history_menu(
            object(), bridge, app=fake_app, appkit=FakeAppKit, dispatcher=lambda _w, d: dispatched.append(d)
        )
        ok2 = desktop_app._install_macos_edit_history_menu(
            object(), bridge, app=fake_app, appkit=FakeAppKit, dispatcher=lambda _w, d: dispatched.append(d)
        )
        self.assertTrue(ok1 and ok2)
        items = edit_sub.itemArray()
        self.assertEqual(len(items), 4, "重复安装必须幂等")
        undo_item, redo_item, sep_item, copy_item = items
        self.assertEqual((undo_item._action, undo_item._key), ("texadaUndo:", "z"))
        self.assertEqual(undo_item._mask, FakeAppKit.NSEventModifierFlagCommand)
        self.assertEqual((redo_item._action, redo_item._key), ("texadaRedo:", "Z"))
        self.assertEqual(redo_item._mask, FakeAppKit.NSEventModifierFlagCommand | FakeAppKit.NSEventModifierFlagShift)
        self.assertTrue(sep_item._separator)
        self.assertEqual(copy_item._action, "copy:")

        target = undo_item._target
        self.assertFalse(target.validateMenuItem_(undo_item))
        self.assertFalse(target.validateMenuItem_(redo_item))
        bridge.set_edit_state(dirty=True, can_undo=True, can_redo=False)
        self.assertTrue(target.validateMenuItem_(undo_item))
        self.assertFalse(target.validateMenuItem_(redo_item))
        bridge.set_edit_state(dirty=False, can_undo=False, can_redo=False, native_editable=True)
        self.assertTrue(target.validateMenuItem_(undo_item))
        self.assertTrue(target.validateMenuItem_(redo_item))
        target.texadaUndo_(undo_item)
        target.texadaRedo_(redo_item)
        self.assertEqual(dispatched, ["undo", "redo"])

    @unittest.skipUnless(sys.platform == "darwin", "真实 AppKit 菜单校验仅在 macOS 上运行")
    def test_macos_real_appkit_edit_menu_validates_and_dispatches_cmd_z_and_shift_cmd_z(self):
        try:
            import AppKit
        except ImportError:
            self.skipTest("未安装 PyObjC AppKit")
        AppKit.NSApplication.sharedApplication()
        main_menu = AppKit.NSMenu.alloc().init()
        edit_top = AppKit.NSMenuItem.alloc().init()
        edit_sub = AppKit.NSMenu.alloc().initWithTitle_("编辑")
        edit_sub.addItemWithTitle_action_keyEquivalent_("拷贝", "copy:", "c")
        edit_top.setSubmenu_(edit_sub)
        main_menu.addItem_(edit_top)

        class _FakeApp:
            def mainMenu(self):
                return main_menu

        bridge = desktop_app._DesktopBridge()
        called = []
        self.assertTrue(
            desktop_app._install_macos_edit_history_menu(
                object(), bridge, app=_FakeApp(), dispatcher=lambda _w, d: called.append(d)
            )
        )
        items = list(edit_sub.itemArray())
        edit_sub.update()
        self.assertFalse(items[0].isEnabled())
        self.assertFalse(items[1].isEnabled())

        bridge.set_edit_state(dirty=True, can_undo=True, can_redo=True)
        edit_sub.update()
        self.assertTrue(items[0].isEnabled())
        self.assertTrue(items[1].isEnabled())

        ev_undo = AppKit.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            AppKit.NSEventTypeKeyDown, (0, 0), AppKit.NSEventModifierFlagCommand, 0.0, 0, None, "z", "z", False, 6
        )
        ev_redo = AppKit.NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            AppKit.NSEventTypeKeyDown, (0, 0),
            AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagShift,
            0.0, 0, None, "Z", "Z", False, 6
        )
        self.assertTrue(main_menu.performKeyEquivalent_(ev_undo))
        self.assertTrue(main_menu.performKeyEquivalent_(ev_redo))
        self.assertEqual(called, ["undo", "redo"])

    @unittest.skipUnless(os.name == "posix", "POSIX 管道回收仅在 POSIX 运行")
    def test_posix_terminate_watchdog_stores_and_closes_wakeup_pipe(self):
        state = {}
        installed = desktop_app._install_terminate_watchdog(state, deadline=0.1, os_name="posix")
        self.assertTrue(installed)
        self.assertIn("wakeup_pipe", state)
        read_fd, write_fd = state["wakeup_pipe"]
        desktop_app._close_terminate_watchdog(state)
        self.assertNotIn("wakeup_pipe", state)
        for fd in (read_fd, write_fd):
            with self.assertRaises(OSError):
                os.fstat(fd)


if __name__ == "__main__":
    unittest.main()
