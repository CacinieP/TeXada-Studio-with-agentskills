"""Launcher acceptance checks without installing, downloading or loading models."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("studio_local_launcher", ROOT / "scripts/run-local-studio.py")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
READY = {"python": True, "modules": {name: True for name in ("fastapi", "uvicorn", "sympy", "antlr4")},
         "tools": {name: True for name in ("tectonic", "pdftoppm", "pdfinfo")}}


class LocalLauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_prepend_local_bin_puts_texada_bin_first_once(self):
        local = str(launcher.LOCAL_TOOL_BIN)
        self.assertEqual(launcher.prepend_local_bin(""), local)
        self.assertEqual(launcher.prepend_local_bin("/usr/bin"), os.pathsep.join([local, "/usr/bin"]))
        once = launcher.prepend_local_bin(f"/usr/bin{os.pathsep}local")
        self.assertEqual(launcher.prepend_local_bin(once), once, "重复前置不叠加")
        self.assertTrue(once.startswith(local + os.pathsep))

    def args(self, *extra):
        return launcher.parser().parse_args(["--state-dir", str(self.directory), "--no-browser", *extra])

    def test_help_never_requires_app_import_or_services(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/run-local-studio.py"), "--help"],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--no-auto-model", result.stdout)
        self.assertIn("--gguf", result.stdout)
        self.assertIn("--check", result.stdout)

    def test_check_is_read_only_and_does_not_probe_or_start(self):
        with patch.object(launcher, "dependency_status", return_value=READY), \
                patch.object(launcher, "select_service", side_effect=AssertionError("probe")), \
                patch.object(launcher.subprocess, "Popen", side_effect=AssertionError("start")), \
                contextlib.redirect_stdout(io.StringIO()):
            result = launcher.run(self.args("--check", "--base-url", "http://127.0.0.1:18081/v1", "--model", "local"))
        self.assertEqual(result, 0)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_remote_config_and_equal_ports_are_rejected(self):
        for extra in (("--check", "--base-url", "https://api.modelbest.cn/v1"),
                      ("--port", "8888", "--model-port", "8888"),
                      ("--port", "0"), ("--check", "--model", "invalid\nname")):
            with self.subTest(extra=extra), patch.object(launcher, "dependency_status", return_value=READY), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(launcher.main(["--state-dir", str(self.directory), *extra]), 2)

    def test_cloud_environment_credentials_are_removed_but_local_system_settings_remain(self):
        cleaned = launcher.clean_environment({"PATH": "/bin", "HOME": "/example", "TECTONIC": "/tools/tectonic",
                                               "VLM_API_KEY": "private", "TEXADA_OPENAI_API_KEY": "private",
                                               "OPENAI_API_KEY": "private", "HF_TOKEN": "private",
                                               "DEMO_TOKEN": "private", "VLM_BASE_URL": "https://remote"})
        self.assertEqual(cleaned, {"PATH": "/bin", "HOME": "/example", "TECTONIC": "/tools/tectonic"})

    def test_session_file_is_private_and_does_not_print_its_url(self):
        state = {}
        session_file = self.directory / "session.json"

        class Server:
            def __init__(self, config):
                state["config"] = config

            def run(self):
                state["session"] = json.loads(session_file.read_text())
                state["mode"] = os.environ.get("TEXADA_LOCAL_MODE")
                state["has_api_key"] = "VLM_API_KEY" in os.environ

        module = SimpleNamespace(Config=lambda app, **kwargs: {"app": app, **kwargs}, Server=Server)
        capture = io.StringIO()
        with patch.object(launcher, "dependency_status", return_value=READY), \
                patch.object(launcher, "_listen_available", return_value=True), \
                patch.object(launcher, "select_service", return_value="http://127.0.0.1:18081/v1"), \
                patch.object(launcher, "launch_owned_model", side_effect=AssertionError("should reuse")), \
                patch.dict(sys.modules, {"uvicorn": module}), \
                patch.dict(os.environ, {"VLM_API_KEY": "never-inherit-this-key"}), contextlib.redirect_stdout(capture):
            self.assertEqual(launcher.run(self.args("--no-auto-model")), 0)
        self.assertTrue(state["session"]["running"])
        self.assertEqual(state["session"]["pid"], os.getpid())
        self.assertIn("?token=", state["session"]["url"])
        self.assertNotIn("?token=", capture.getvalue())
        self.assertNotIn("never-inherit-this-key", capture.getvalue())
        self.assertEqual(state["mode"], "1")
        self.assertFalse(state["has_api_key"])
        self.assertEqual(state["config"]["host"], "127.0.0.1")
        self.assertEqual(state["config"]["workers"], 1)
        self.assertFalse(state["config"]["access_log"])
        self.assertIsNone(state["session"]["owned_model_pid"])
        self.assertEqual(session_file.stat().st_mode & 0o777, 0o600)
        stopped = json.loads(session_file.read_text())
        self.assertFalse(stopped["running"])
        self.assertIsNone(stopped["url"])
        self.assertFalse((self.directory / "launcher.lock").exists())

    def test_lock_rejects_live_process_and_recovers_stale_process(self):
        path = self.directory / "launcher.lock"
        path.write_text(str(os.getpid()))
        with self.assertRaisesRegex(RuntimeError, "已有 Studio"):
            launcher.acquire_lock(self.directory)
        with patch.object(launcher, "_alive", return_value=False):
            self.assertEqual(launcher.acquire_lock(self.directory), path)
        self.assertEqual(path.read_text(), str(os.getpid()))

    def write_running_session(self, **updates):
        record = {"running": True, "pid": os.getpid(),
                  "url": "http://127.0.0.1:8888/studio?token=private-existing-session-token"}
        record.update(updates)
        path = self.directory / "session.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path, record

    def test_second_launch_reopens_live_profile_without_changing_settings_or_processes(self):
        path, record = self.write_running_session()
        before = path.read_bytes()
        settings = self.directory / "local-runtime.json"
        settings.write_text('{"base_url":"http://127.0.0.1:8080/v1","model":"saved-local-model"}')
        saved_settings = settings.read_bytes()
        args = self.args("--base-url", "http://127.0.0.1:18081/v1", "--model", "new-cli-choice")
        args.no_browser = False
        capture = io.StringIO()
        with patch.object(launcher, "dependency_status", return_value=READY), \
                patch.object(launcher, "_listen_available", side_effect=AssertionError("port check")), \
                patch.object(launcher, "acquire_lock", side_effect=AssertionError("new lock")), \
                patch.object(launcher, "select_service", side_effect=AssertionError("model probe")), \
                patch.object(launcher, "launch_owned_model", side_effect=AssertionError("model start")), \
                patch.object(launcher, "stop_owned_model", side_effect=AssertionError("model stop")), \
                patch.object(launcher.LocalRuntime, "update_settings", side_effect=AssertionError("settings write")), \
                patch.object(launcher.webbrowser, "open", return_value=True) as browser, \
                contextlib.redirect_stdout(capture):
            self.assertEqual(launcher.run(args), 0)
        browser.assert_called_once_with(record["url"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(settings.read_bytes(), saved_settings)
        self.assertNotIn("private-existing-session-token", capture.getvalue())
        self.assertNotIn("?token=", capture.getvalue())

    def test_no_browser_second_launch_reports_existing_profile_without_opening(self):
        path, _ = self.write_running_session()
        before = path.read_bytes()
        capture = io.StringIO()
        with patch.object(launcher, "dependency_status", return_value=READY), \
                patch.object(launcher, "_listen_available", side_effect=AssertionError("port check")), \
                patch.object(launcher.webbrowser, "open", side_effect=AssertionError("browser open")), \
                contextlib.redirect_stdout(capture):
            self.assertEqual(launcher.run(self.args()), 0)
        self.assertIn("已在运行", capture.getvalue())
        self.assertNotIn("private-existing-session-token", capture.getvalue())
        self.assertEqual(path.read_bytes(), before)

    def test_untrusted_or_wrong_port_session_never_opens_a_url(self):
        invalid_urls = ("http://evil.example/studio?token=private", "https://127.0.0.1:8888/studio?token=private",
                        "http://127.0.0.1:9999/studio?token=private", "http://user@127.0.0.1:8888/studio?token=private",
                        "http://127.0.0.1:8888/other?token=private", "http://127.0.0.1:8888/studio?token=private&next=outside",
                        "http://127.0.0.1:8888/studio?token=", "http://127.0.0.1:8888/studio?token=private#fragment")
        for url in invalid_urls:
            with self.subTest(url=url):
                self.write_running_session(url=url)
                with patch.object(launcher, "dependency_status", return_value=READY), \
                        patch.object(launcher, "_listen_available", return_value=False), \
                        patch.object(launcher.webbrowser, "open", side_effect=AssertionError("untrusted URL")), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "端口已被占用"):
                    launcher.run(self.args())

    def test_dead_or_stopped_session_does_not_reopen(self):
        for fields in ({"pid": 12345}, {"running": False}, {"pid": True}):
            with self.subTest(fields=fields):
                self.write_running_session(**fields)
                with patch.object(launcher, "dependency_status", return_value=READY), \
                        patch.object(launcher, "_alive", return_value=False), \
                        patch.object(launcher, "_listen_available", return_value=False), \
                        patch.object(launcher.webbrowser, "open", side_effect=AssertionError("stale session")), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "端口已被占用"):
                    launcher.run(self.args())

    def test_a_different_profile_cannot_reuse_another_profiles_busy_port(self):
        other = self.directory / "other-profile"
        other.mkdir()
        self.write_running_session()
        args = launcher.parser().parse_args(["--state-dir", str(other), "--no-browser"])
        with patch.object(launcher, "dependency_status", return_value=READY), \
                patch.object(launcher, "_listen_available", return_value=False), \
                patch.object(launcher.webbrowser, "open", side_effect=AssertionError("wrong profile")), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "端口已被占用"):
            launcher.run(args)

    def test_default_owned_weights_are_35b_q4(self):
        args = self.args()
        with patch.object(launcher.Path, "home", return_value=self.directory):
            _, gguf, projector = launcher.find_model_files(args)
        self.assertEqual(gguf.name, "MiniCPM-V-4_7-35B-A3B-Q4_K_M.gguf")
        self.assertEqual(projector.name, "mmproj-model-f16.gguf")
        self.assertEqual(launcher.DEFAULT_MODEL, "minicpm-v4.7-35b-a3b-q4")

    def test_model_launch_is_local_bounded_and_shutdown_only_touches_owned_handle(self):
        gguf, mmproj = self.directory / "model.gguf", self.directory / "projector.gguf"
        gguf.write_bytes(b"test weight")
        mmproj.write_bytes(b"test projector")
        args = self.args("--gguf", str(gguf), "--mmproj", str(mmproj))
        process = Mock()
        process.poll.return_value = None
        with patch.object(launcher, "find_model_files", return_value=("/test/llama-server", gguf, mmproj)), \
                patch.object(launcher, "_listen_available", return_value=True), \
                patch.object(launcher.subprocess, "Popen", return_value=process) as popen, \
                contextlib.redirect_stdout(io.StringIO()):
            owned = launcher.launch_owned_model(args, {"model": "MiniCPM-V-4.7-1B"}, self.directory, {"PATH": "/bin"})
        self.assertIs(owned, process)
        command = popen.call_args.args[0]
        for name, expected in (("--host", "127.0.0.1"), ("--port", "18081"), ("--ctx-size", "8192"),
                               ("--parallel", "1"), ("--reasoning", "off")):
            self.assertEqual(command[command.index(name) + 1], expected)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertNotIn("shell", popen.call_args.kwargs)
        launcher.stop_owned_model(None)
        process.terminate.assert_not_called()
        launcher.stop_owned_model(process)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=8)

    def test_reachable_ollama_without_target_model_does_not_block_auto_model(self):
        args = self.args()
        config = {"base_url": launcher.DEFAULT_BASE, "model": launcher.DEFAULT_MODEL}

        def probe(base, model):
            self.assertEqual(model, launcher.DEFAULT_MODEL)
            return {"reachable": base == launcher.DEFAULT_BASE, "available": False}

        with patch.object(launcher, "_probe_service", side_effect=probe):
            self.assertIsNone(launcher.select_service(config, args))
            args.no_auto_model = True
            self.assertEqual(launcher.select_service(config, args), launcher.DEFAULT_BASE)

    def test_auto_mode_reuses_only_a_service_containing_the_target_model(self):
        args = self.args()
        target = f"http://127.0.0.1:{args.model_port}/v1"
        config = {"base_url": launcher.DEFAULT_BASE, "model": launcher.DEFAULT_MODEL}
        with patch.object(launcher, "_probe_service", side_effect=lambda base, _model: {
            "reachable": True, "available": base == target
        }):
            self.assertEqual(launcher.select_service(config, args), target)

    def test_other_model_name_cannot_alias_default_minicpm_weights(self):
        args = self.args("--model", "Gemma-local")
        with patch.object(launcher, "find_model_files", side_effect=AssertionError("default weights selected")), \
                patch.object(launcher.subprocess, "Popen", side_effect=AssertionError("wrong model launched")), \
                contextlib.redirect_stdout(io.StringIO()) as capture:
            result = launcher.launch_owned_model(args, {"model": "Gemma-local"}, self.directory, {})
        self.assertIsNone(result)
        self.assertIn("未自动加载或重命名权重", capture.getvalue())

    def test_explicit_unavailable_endpoint_is_preserved_without_auto_model_or_rerouting(self):
        base = "http://127.0.0.1:19000/v1"
        args = self.args("--base-url", base)
        observed = {}

        class Server:
            def __init__(self, _config):
                pass

            def run(self):
                observed["base"] = os.environ["VLM_BASE_URL"]

        module = SimpleNamespace(Config=lambda *_args, **kwargs: kwargs, Server=Server)
        capture = io.StringIO()
        with patch.object(launcher, "dependency_status", return_value=READY), \
                patch.object(launcher, "_listen_available", return_value=True), \
                patch.object(launcher, "select_service", return_value=None), \
                patch.object(launcher, "launch_owned_model", side_effect=AssertionError("explicit route changed")), \
                patch.dict(sys.modules, {"uvicorn": module}), patch.dict(os.environ, dict(os.environ), clear=True), \
                contextlib.redirect_stdout(capture):
            self.assertEqual(launcher.run(args), 0)
        self.assertEqual(observed["base"], base)
        self.assertEqual(json.loads((self.directory / "local-runtime.json").read_text())["base_url"], base)
        self.assertIsNone(json.loads((self.directory / "session.json").read_text())["owned_model_pid"])
        self.assertIn("没有切换路由或自动启动其他服务", capture.getvalue())

    def test_application_data_default_respects_platform_and_override(self):
        with patch.dict(os.environ, {"TEXADA_STUDIO_STATE_DIR": str(self.directory)}):
            self.assertEqual(launcher.default_state_dir(), self.directory)
        with patch.dict(os.environ, {}, clear=True), patch.object(launcher.sys, "platform", "darwin"), \
                patch.object(launcher.Path, "home", return_value=self.directory):
            self.assertEqual(launcher.default_state_dir(), self.directory / "Library/Application Support/TeXada Studio")


if __name__ == "__main__":
    unittest.main()
