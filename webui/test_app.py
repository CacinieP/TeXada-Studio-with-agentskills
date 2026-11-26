"""Configuration and local-document regression tests; no model/compiler required."""

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
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_static_assets import ROOT, studio
from docforensics import vlm


class AppTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.samples = self.base / "samples"
        self.samples.mkdir()
        (self.samples / "example.tex").write_text("synthetic sample")
        self.uploads = self.base / "state" / "documents"
        replacements = dict(TOKEN="test-only-app-token", SAMPLE_DOCS=str(self.samples),
                            STUDIO_DOCS=str(self.uploads), STUDIO_STATE=str(self.base / "build"))
        config = patch.multiple(studio, **replacements)
        config.start()
        self.addCleanup(config.stop)
        self.client = TestClient(studio.app)
        self.addCleanup(self.client.close)
        self.auth = {"token": studio.TOKEN}

    def test_empty_token_fails_startup(self):
        for token in (None, "", "  "):
            with self.subTest(token=token), patch.dict(os.environ, clear=True):
                if token is not None:
                    os.environ["DEMO_TOKEN"] = token
                spec = importlib.util.spec_from_file_location("unconfigured_app", ROOT / "webui/app.py")
                with self.assertRaisesRegex(RuntimeError, "DEMO_TOKEN must be set"):
                    spec.loader.exec_module(importlib.util.module_from_spec(spec))

    def test_repo_resolves_from_source(self):
        self.assertEqual(Path(studio.REPO), ROOT)

    def test_tools_install_requires_token(self):
        response = self.client.post("/api/studio/tools/install")
        self.assertEqual(response.status_code, 401)

    def test_tools_install_installs_tectonic_and_activates_it_in_session(self):
        original = os.environ.get("TECTONIC")
        try:
            fake = {"ok": True, "path": "/tmp/fake-tectonic", "version": "0.17.0", "sha256": "0" * 64}
            with patch.object(studio.tool_fetch, "install_tectonic", return_value=fake):
                response = self.client.post("/api/studio/tools/install", params=self.auth)
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertTrue(result["ok"])
            self.assertEqual(result["version"], "0.17.0")
            self.assertIn("tectonic", result["tools"])
            self.assertEqual(os.environ.get("TECTONIC"), "/tmp/fake-tectonic",
                             "安装后当前会话立即可用编译器")
        finally:
            if original is None:
                os.environ.pop("TECTONIC", None)
            else:
                os.environ["TECTONIC"] = original

    def test_tools_install_maps_fetch_error_to_400(self):
        with patch.object(studio.tool_fetch, "install_tectonic",
                          side_effect=studio.tool_fetch.ToolFetchError("无适配平台")):
            response = self.client.post("/api/studio/tools/install", params=self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertIn("无适配平台", response.text)

    def test_tools_install_poppler_selects_installer_and_unknown_tool_fails(self):
        with patch.object(studio.tool_fetch, "install_poppler",
                          return_value={"ok": True, "tool": "poppler", "method": "homebrew"}) as poppler_install:
            response = self.client.post("/api/studio/tools/install", params=self.auth, json={"tool": "poppler"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(poppler_install.call_count, 1)
        unknown = self.client.post("/api/studio/tools/install", params=self.auth, json={"tool": "unknown"})
        self.assertEqual(unknown.status_code, 400)

    def test_default_model_is_minicpm_and_explicit_environment_override_still_works(self):
        for extra, model, base in (({}, "minicpm-v4.7-35b-a3b-q4", "http://127.0.0.1:18147/v1"),
                                   ({"VLM_MODEL": "other-model", "VLM_BASE_URL": "http://localhost:9000/v1"},
                                    "other-model", "http://localhost:9000/v1")):
            with self.subTest(model=model), patch.dict(os.environ, {"DEMO_TOKEN": "test-only-demo-token", **extra}, clear=True):
                spec = importlib.util.spec_from_file_location("default_profile_app", ROOT / "webui/app.py")
                configured = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(configured)
            self.assertEqual(configured.VLM_MODEL, model)
            self.assertEqual(configured.VLM_BASE_URL, base)
            self.assertEqual(configured.PROVIDER.model, model)

    def test_repair_model_environment_takes_priority_and_flows_to_the_provider(self):
        for index, (extra, expected) in enumerate((
                ({"REPAIR_MODEL": "m-repair", "VLM_MODEL": "m-vlm"}, "m-repair"),
                ({"VLM_MODEL": "m-vlm"}, "m-vlm"),
                ({}, "minicpm-v4.7-35b-a3b-q4"))):
            environment = {"DEMO_TOKEN": "test-only-demo-token",
                           "TEXADA_STUDIO_STATE_DIR": str(self.base / f"routing-{index}"), **extra}
            with self.subTest(expected=expected), patch.dict(os.environ, environment, clear=True):
                spec = importlib.util.spec_from_file_location("repair_model_app", ROOT / "webui/app.py")
                configured = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(configured)
            self.assertEqual(configured.REPAIR_MODEL, expected)
            self.assertEqual(configured.PROVIDER.model, expected)

    def test_model_defaults_stay_in_sync_across_repair_studio_and_ocr_lines(self):
        from docforensics.__main__ import DEFAULT_REPAIR_MODEL
        spec = importlib.util.spec_from_file_location(
            "ocr_extract_contract", ROOT / "skills/doc-ocr-extract/scripts/ocr_extract.py")
        ocr = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, clear=False):
            for name in ("OCR_MODEL", "REPAIR_MODEL", "VLM_MODEL"):
                os.environ.pop(name, None)
            spec.loader.exec_module(ocr)
        self.assertEqual(DEFAULT_REPAIR_MODEL, "minicpm-v4.7-35b-a3b-q4")
        self.assertEqual(studio.DEFAULT_MODEL, DEFAULT_REPAIR_MODEL,
                         "Studio 与 harness 的默认修复模型必须一致")
        self.assertEqual(ocr.DEFAULT_MODEL, "minicpm-ocr:latest")
        self.assertEqual(studio.OCR_MODEL, os.environ.get("OCR_MODEL", "minicpm-ocr:latest"))

    def test_upload_overlays_sample_without_modifying_it(self):
        response = self.client.post("/api/studio/upload", params=self.auth,
                                    json={"name": "example.tex", "content": "user document"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.samples / "example.tex").read_text(), "synthetic sample")
        self.assertEqual((self.uploads / "example.tex").read_text(), "user document")
        self.assertEqual(self.client.get("/api/studio/files", params=self.auth).json()["files"], ["example.tex"])
        response = self.client.get("/api/studio/file", params={**self.auth, "name": "example.tex"})
        self.assertEqual(response.json()["content"], "user document")

    def test_samples_work_before_first_upload(self):
        self.assertFalse(self.uploads.exists())
        self.assertEqual(self.client.get("/api/studio/files", params=self.auth).json()["files"], ["example.tex"])
        response = self.client.get("/api/studio/file", params={**self.auth, "name": "example.tex"})
        self.assertEqual(response.json()["content"], "synthetic sample")

    def test_upload_requires_auth_and_rejects_parent_paths(self):
        body = {"name": "example.tex", "content": "untrusted"}
        self.assertEqual(self.client.post("/api/studio/upload", json=body).status_code, 401)
        for name in ("../outside.tex", "/outside.tex", "data.txt"):
            response = self.client.post("/api/studio/upload", params=self.auth,
                                        json={**body, "name": name})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(self.uploads.exists())
        self.assertEqual((self.samples / "example.tex").read_text(), "synthetic sample")

    def test_missing_compiler_and_timeout_return_actionable_errors(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("tectonic", 240)):
            with self.subTest(error=type(error).__name__), patch.object(studio.subprocess, "run", side_effect=error):
                response = self.client.post("/api/studio/preview", params=self.auth,
                                            json={"name": "example.tex", "content": "synthetic"})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["ok"])
                self.assertIsNone(response.json()["png"])
                self.assertTrue(response.json()["log"])

    def test_timeout_preserves_partial_compiler_diagnostics(self):
        timeout = subprocess.TimeoutExpired("tectonic", 120, output=b"running TeX",
                                            stderr="中文诊断".encode("utf-8") + b"\xff")
        with patch.object(studio.subprocess, "run", side_effect=timeout):
            response = self.client.post("/api/studio/preview", params=self.auth,
                                        json={"name": "example.tex", "content": "synthetic"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["compile_ok"])
        self.assertIn("120 秒", body["log"])
        self.assertIn("running TeX", body["log"])
        self.assertIn("中文诊断\ufffd", body["log"])

    def test_non_utf8_compiler_output_stays_in_the_preview_log(self):
        stderr = ("Runaway argument?\n! File ended while scanning use of \\frac .\n"
                  "\\section {二项式展开}\n").encode("utf-8") + b"\xff"

        def run(command, **kwargs):
            self.assertTrue(kwargs.get("capture_output"))
            self.assertFalse(kwargs.get("text"))
            self.assertFalse(kwargs.get("universal_newlines"))
            self.assertIsNone(kwargs.get("encoding"))
            self.assertIsNone(kwargs.get("errors"))
            return SimpleNamespace(returncode=1, stdout=b"", stderr=stderr)

        with patch.object(studio.subprocess, "run", side_effect=run):
            response = self.client.post("/api/studio/preview", params=self.auth,
                                        json={"name": "example.tex", "content": "synthetic"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertFalse(body["compile_ok"])
        self.assertIn("File ended while scanning use of \\frac", body["log"])
        self.assertIn("二项式展开", body["log"])
        self.assertIn("\ufffd", body["log"])

    def test_compile_location_uses_source_error_before_log_tail(self):
        messages = (b"error: nested/main.tex:1: nested error\n"
                    b"error: main.tex:99: detached line\n"
                    b"error: ./main.tex:2: Missing delimiter\n" + b"long trace\n" * 300)
        compiler = SimpleNamespace(returncode=1, stdout=b"", stderr=messages)
        with patch.object(studio.subprocess, "run", return_value=compiler):
            response = self.client.post("/api/studio/preview", params=self.auth,
                                        json={"name": "example.tex", "content": "one\ntwo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["diagnostic"], {"line": 2, "message": "Missing delimiter"})

    def test_external_file_diagnostic_never_jumps_into_current_document(self):
        compiler = SimpleNamespace(returncode=1, stdout=b"",
                                   stderr=b"error: include.tex:2: undefined macro\nl.2 included text")
        with patch.object(studio.subprocess, "run", return_value=compiler):
            response = self.client.post("/api/studio/preview", params=self.auth,
                                        json={"name": "example.tex", "content": "one\ntwo"})
        self.assertIsNone(response.json()["diagnostic"])
        self.assertIn("include.tex:2", response.json()["log"])

    def test_failed_compile_log_reaches_the_repair_job(self):
        job_id = "e" * 32
        failure = {"ok": False, "compile_ok": False, "log": "! File ended while scanning use of \\frac ."}
        success = {"ok": True, "compile_ok": True, "log": "noise that must stay out of the job log", "png": None}

        class Provider:
            name = "test"
            model = "test-model"

            def fingerprint(self):
                return {"kind": "test"}

        with patch.object(studio, "STUDIO_STATE", str(self.base / "jobs")), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None, "name": "example.tex",
                                                   "created_at": 1, "planner_mode": False, "skill_selection": False}}, clear=True), \
                patch.object(studio, "_new_provider", return_value=Provider()), \
                patch.object(studio, "_apply_fixes", return_value=("synthetic", [])), \
                patch.object(studio, "_analyze", return_value=[]), \
                patch.object(studio, "_studio_compile", side_effect=[failure, success]):
            studio._studio_job("example.tex", "synthetic", job_id)
            loaded = studio._read_job(job_id)
        self.assertIsNone(loaded.get("error"))
        self.assertTrue(loaded["done"])
        self.assertIn("! File ended while scanning use of \\frac .", loaded["log"])
        self.assertNotIn("noise that must stay out of the job log", loaded["log"])
        self.assertNotIn("UnicodeDecodeError", "\n".join(loaded["log"]))

    def test_missing_preview_converter_is_reported(self):
        output = Path(studio.STUDIO_STATE) / "builds" / "example" / "test"
        output.mkdir(parents=True)
        (output / "main.pdf").write_bytes(b"%PDF-synthetic")
        def run(command, **kwargs):
            if command[0] == "pdftoppm":
                raise FileNotFoundError()
            return SimpleNamespace(returncode=0, stdout="Pages: 1\n" if command[0] == "pdfinfo" else "", stderr="")
        with patch.object(studio.subprocess, "run", side_effect=run):
            result = studio._studio_compile("synthetic", "example.tex", "test")
        self.assertFalse(result["ok"])
        self.assertTrue(result["compile_ok"])
        self.assertTrue(result["pdf"])
        self.assertIn("pdftoppm", result["log"])

    def test_nodeinfo_reports_platform_and_model_without_subprocess_probes(self):
        for system, machine in (("Darwin", "arm64"), ("Windows", "AMD64")):
            with self.subTest(system=system), \
                    patch.object(studio.platform, "node", return_value="test-host"), \
                    patch.object(studio.platform, "system", return_value=system), \
                    patch.object(studio.platform, "release", return_value="test-release"), \
                    patch.object(studio.platform, "machine", return_value=machine), \
                    patch.object(studio.subprocess, "run", side_effect=AssertionError("unexpected probe")) as run, \
                    patch.object(studio.subprocess, "Popen", side_effect=AssertionError("unexpected probe")) as popen:
                response = self.client.get("/api/nodeinfo", params=self.auth)
            self.assertEqual(response.status_code, 200)
            info = response.json()
            self.assertEqual(info["host"], "test-host")
            self.assertEqual(info["platform"], f"{system} test-release {machine}")
            self.assertEqual(info["configured_model"], studio.REPAIR_MODEL)
            self.assertEqual(info["model"], studio.REPAIR_MODEL)
            self.assertEqual(info["repair_model"], studio.REPAIR_MODEL)
            self.assertEqual(info["ocr_model"], studio.OCR_MODEL)
            self.assertTrue(info["python"])
            self.assertEqual([info["gpu"], info["mem"], info["models"]], ["", "", ""])
            run.assert_not_called()
            popen.assert_not_called()
        with patch.object(studio.subprocess, "run", side_effect=AssertionError("unexpected probe")) as run, \
                patch.object(studio.subprocess, "Popen", side_effect=AssertionError("unexpected probe")) as popen:
            response = self.client.get("/api/nodeinfo", params=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["platform"])
        run.assert_not_called()
        popen.assert_not_called()

    def test_pipeline_uses_current_python_no_shell_and_keeps_exit_code(self):
        model = "model name; this must stay one argument"
        process = SimpleNamespace(stdout=["failed\n"], returncode=7, wait=lambda: 7)
        with patch.object(studio, "REPAIR_MODEL", model), patch.dict(studio._run, clear=True), \
                patch.object(studio.subprocess, "Popen", return_value=process) as popen, \
                patch.object(studio.threading, "Thread") as thread:
            studio._run_pipeline(fresh=False)
            command = popen.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-m", "docforensics"])
            self.assertEqual(command[-1], model)
            self.assertNotIn("shell", popen.call_args.kwargs)
            thread.call_args.kwargs["target"]()
            self.assertTrue(studio._run["done"])
            self.assertEqual(studio._run["code"], 7)

    def test_cloud_endpoint_and_key_are_shared_by_studio_and_pipeline(self):
        model, base, key = "MiniCPM-V-4.7-1B", "https://api.modelbest.cn/v1", "test-only-api-key"
        process = SimpleNamespace(stdout=[], returncode=0, wait=lambda: 0)
        with patch.multiple(studio, REPAIR_MODEL=model, VLM_MODEL=model, VLM_BASE_URL=base), \
                patch.dict(os.environ, {"VLM_API_KEY": key, "TEXADA_LOCAL_MODE": "0"}), \
                patch.object(studio.subprocess, "Popen", return_value=process) as popen, \
                patch.object(studio.threading, "Thread"):
            provider = studio._new_provider()
            studio._run_pipeline(fresh=False)
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--vlm") + 1], base)
        self.assertEqual(command[command.index("--vlm-model") + 1], model)
        self.assertNotIn(key, " ".join(command))
        self.assertEqual(popen.call_args.kwargs["env"]["VLM_API_KEY"], key)
        with patch.object(vlm.urllib.request, "urlopen", return_value=io.BytesIO(
                b'{"choices":[{"message":{"content":"{\\"latex\\":\\"a_1\\"}"}}]}')) as network:
            self.assertEqual(provider.repair_formula({"data": {"latex": "a_"}}), "a_1")
        request = network.call_args.args[0]
        self.assertEqual(request.full_url, base + "/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + key)
        self.assertEqual(json.loads(request.data)["chat_template_kwargs"], {"enable_thinking": False})

    def test_dynamic_studio_state_isolates_managed_models_and_preserves_explicit_override(self):
        getter = getattr(studio, "_managed_models", None)
        self.assertTrue(callable(getter), "_managed_models() helper must exist")
        state_a = self.base / "isolated-a"
        state_b = self.base / "isolated-b"
        with patch.object(studio, "STUDIO_STATE", str(state_a)):
            manager_a = getter()
            self.assertEqual(manager_a.state, state_a)
            self.assertIsNot(manager_a, studio.managed_models)
        with patch.object(studio, "STUDIO_STATE", str(state_b)):
            manager_b = getter()
            self.assertEqual(manager_b.state, state_b)
            self.assertIsNot(manager_b, manager_a)
        explicit = studio.ManagedModels(self.base / "explicit-override")
        with patch.object(studio, "managed_models", explicit), \
                patch.object(studio, "STUDIO_STATE", str(state_a)):
            self.assertIs(getter(), explicit)

    def test_settings_post_is_idempotent_under_normalization_when_managed_model_active(self):
        active_conn = {"base_url": "http://127.0.0.1:43210/v1", "model": "minicpm-v4.7-1b-q4_k_m"}
        fake_proc = SimpleNamespace(poll=lambda: None, terminate=lambda: None, wait=lambda timeout=None: 0)
        manager = studio.ManagedModels(Path(studio.STUDIO_STATE))
        manager.active = active_conn.copy()
        manager.process = fake_proc
        stop_calls = []
        original_stop = manager.stop

        def record_stop():
            stop_calls.append(True)
            original_stop()

        manager.stop = record_stop
        with patch.object(studio, "managed_models", manager):
            same = self.client.post(
                "/api/studio/settings",
                params=self.auth,
                json={"base_url": "  http://127.0.0.1:43210/  ", "model": " minicpm-v4.7-1b-q4_k_m "},
            )
            self.assertEqual(same.status_code, 200, same.text)
            payload = same.json()
            self.assertEqual(payload["base_url"], active_conn["base_url"])
            self.assertEqual(payload["model"], active_conn["model"])
            self.assertEqual(set(payload["tools"]), {"tectonic", "pdftoppm", "pdfinfo"})
            self.assertFalse((Path(studio.STUDIO_STATE) / "local-runtime.json").exists())
            self.assertEqual(stop_calls, [])
            self.assertEqual(manager.connection(), active_conn)

            changed = self.client.post(
                "/api/studio/settings",
                params=self.auth,
                json={"base_url": "http://127.0.0.1:18147/v1", "model": "custom-local-model"},
            )
            self.assertEqual(changed.status_code, 200, changed.text)
            self.assertTrue((Path(studio.STUDIO_STATE) / "local-runtime.json").is_file())
            self.assertEqual(len(stop_calls), 1)
            self.assertIsNone(manager.connection())

    def test_nodeinfo_reports_active_managed_model_consistently_across_all_model_fields(self):
        active_conn = {"base_url": "http://127.0.0.1:43210/v1", "model": "minicpm-v4.7-1b-q4_k_m"}
        manager = studio.ManagedModels(Path(studio.STUDIO_STATE))
        manager.active = active_conn.copy()
        manager.process = SimpleNamespace(poll=lambda: None)
        for local_flag in ("1", "0"):
            with self.subTest(local_mode=local_flag), \
                    patch.dict(os.environ, {"TEXADA_LOCAL_MODE": local_flag}), \
                    patch.object(studio, "managed_models", manager):
                response = self.client.get("/api/nodeinfo", params=self.auth)
            self.assertEqual(response.status_code, 200)
            info = response.json()
            self.assertEqual(info["configured_model"], active_conn["model"])
            self.assertEqual(info["model"], active_conn["model"])
            self.assertEqual(info["repair_model"], active_conn["model"])
            self.assertEqual(info["ocr_model"], active_conn["model"])

    def test_studio_import_route_uses_active_managed_model_endpoint(self):
        from test_local_runtime import FakeModel, PNG
        import base64

        with FakeModel() as managed_server:
            manager = studio.ManagedModels(Path(studio.STUDIO_STATE))
            manager.active = {"base_url": managed_server.base, "model": "minicpm-v4.7-1b-q4_k_m"}
            manager.process = SimpleNamespace(poll=lambda: None)
            Path(studio.STUDIO_STATE).mkdir(parents=True, exist_ok=True)
            (Path(studio.STUDIO_STATE) / "local-runtime.json").write_text(
                '{"base_url":"http://127.0.0.1:1/v1","model":"offline-saved-model"}', encoding="utf-8"
            )
            with patch.object(studio, "managed_models", manager):
                response = self.client.post(
                    "/api/studio/import",
                    params=self.auth,
                    json={
                        "name": "scan.png",
                        "mime_type": "image/png",
                        "data_base64": base64.b64encode(PNG).decode("ascii"),
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["model"], "minicpm-v4.7-1b-q4_k_m")
            self.assertEqual(len(managed_server.requests), 1)
            self.assertEqual(managed_server.requests[0]["path"], "/v1/chat/completions")

    def test_studio_config_succeeds_when_local_mode_disabled_with_https_endpoint(self):
        with patch.multiple(studio, VLM_BASE_URL="https://api.modelbest.cn/v1", REPAIR_MODEL="MiniCPM-V-4.7-1B"), \
                patch.dict(os.environ, {"TEXADA_LOCAL_MODE": "0", "VLM_BASE_URL": "https://api.modelbest.cn/v1"}):
            for extra in ({}, {"probe": "true"}):
                response = self.client.get("/api/studio/config", params={**self.auth, **extra})
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertFalse(data["local_mode"])
                self.assertEqual(data["base_url"], "https://api.modelbest.cn/v1")
                self.assertEqual(data["model"], "MiniCPM-V-4.7-1B")
                self.assertIn("tectonic", data["tools"])

    def test_csrf_guard_blocks_cross_origin_mutating_requests_and_allows_cli_and_loopback(self):
        body = {"name": "csrf.tex", "content": "safe"}
        for headers in (
            {"Sec-Fetch-Site": "cross-site"},
            {"Origin": "https://evil.example"},
            {"Origin": "http://127.0.0.1.evil.example:8888"},
            {"Origin": "null"},
        ):
            with self.subTest(headers=headers):
                blocked = self.client.post("/api/studio/create", params=self.auth, json=body, headers=headers)
                self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertFalse((self.uploads / "csrf.tex").exists())

        for index, headers in enumerate((
            {},
            {"Origin": "http://127.0.0.1:8888", "Sec-Fetch-Site": "same-origin"},
            {"Origin": "http://localhost:8888"},
            {"Origin": "http://[::1]:8888"},
        )):
            with self.subTest(allowed=headers):
                ok = self.client.post("/api/studio/create", params=self.auth,
                                      json={"name": f"ok-{index}.tex", "content": "safe"}, headers=headers)
                self.assertEqual(ok.status_code, 200, ok.text)

        # Navigating to GET /studio from an external bookmark/link remains allowed.
        nav = self.client.get("/studio", params=self.auth, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(nav.status_code, 200)

    def test_csrf_guard_allows_exact_same_origin_behind_reverse_proxy_only_when_local_mode_disabled(self):
        with TestClient(studio.app, base_url="https://studio.example.com") as proxy_client:
            # In local mode, non-loopback Origin is blocked even if matching request host.
            with patch.dict(os.environ, {"TEXADA_LOCAL_MODE": "1"}):
                blocked_local = proxy_client.post(
                    "/api/studio/create", params=self.auth,
                    json={"name": "proxy-local.tex", "content": "x"},
                    headers={"Origin": "https://studio.example.com", "Sec-Fetch-Site": "same-origin"},
                )
                self.assertEqual(blocked_local.status_code, 403, blocked_local.text)

            with patch.object(studio, "LOCAL_MODE", False):
                ok_attr = proxy_client.post(
                    "/api/studio/create", params=self.auth,
                    json={"name": "proxy-attr.tex", "content": "x"},
                    headers={"Origin": "https://studio.example.com", "Sec-Fetch-Site": "same-origin"},
                )
                self.assertEqual(ok_attr.status_code, 200, ok_attr.text)

            with patch.dict(os.environ, {"TEXADA_LOCAL_MODE": "0"}):
                for idx, origin in enumerate(("https://studio.example.com", "https://studio.example.com:443")):
                    ok = proxy_client.post(
                        "/api/studio/create", params=self.auth,
                        json={"name": f"proxy-ok-{idx}.tex", "content": "x"},
                        headers={"Origin": origin, "Sec-Fetch-Site": "same-origin"},
                    )
                    self.assertEqual(ok.status_code, 200, ok.text)

                for bad_headers in (
                    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
                    {"Origin": "https://evil.example"},
                    {"Origin": "http://studio.example.com"},
                    {"Origin": "https://studio.example.com:8443"},
                    {"Origin": "null"},
                    {"Origin": "https://studio.example.com", "Sec-Fetch-Site": "cross-site"},
                ):
                    with self.subTest(bad_headers=bad_headers):
                        denied = proxy_client.post(
                            "/api/studio/create", params=self.auth,
                            json={"name": "proxy-denied.tex", "content": "x"},
                            headers=bad_headers,
                        )
                        self.assertEqual(denied.status_code, 403, denied.text)

    def test_compile_latex_uses_sandbox_flags_handles_pdftoppm_errors_and_cleans_tmp(self):
        render_dir = self.base / "render-test"
        seen_commands = []

        def fake_run(cmd, **kwargs):
            seen_commands.append((cmd, kwargs))
            if cmd[0] == studio._tectonic_command():
                out_dir = Path(cmd[cmd.index("-o") + 1])
                (out_dir / "f.pdf").write_bytes(b"%PDF-1.4\n")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if cmd[0] == "pdftoppm":
                self.assertEqual(kwargs.get("timeout"), 30)
                raise FileNotFoundError("pdftoppm missing")
            raise AssertionError(f"unexpected command: {cmd}")

        with patch.object(studio, "RENDER", str(render_dir)), \
                patch.object(studio.subprocess, "run", side_effect=fake_run):
            result = studio._compile_latex("x^2", "node-1", "rep")
        self.assertIsNone(result)
        tectonic_cmd = seen_commands[0][0]
        self.assertIn("--untrusted", tectonic_cmd)
        self.assertIn("--only-cached", tectonic_cmd)
        self.assertEqual([p.name for p in render_dir.iterdir() if p.name.startswith("tmp-")], [])

    def test_planned_fixes_preserve_lexical_math_boundary_diagnostics_and_respect_abstention(self):
        for source in ("Prefix $x + 1\n", "\\begin{equation}\nx + 1\n"):
            with self.subTest(source=source), \
                    patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                    patch.object(studio, "_verify_formula", side_effect=AssertionError("unclosed math must not run checker")):
                for flags in ({"planner_mode": True, "skill_selection": False},
                              {"planner_mode": False, "skill_selection": True}):
                    job_id = "a" * 31 + ("1" if flags["planner_mode"] else "2")
                    provider = SimpleNamespace(
                        name="fixture", model="fixture-model", last_trace={"model_calls": 0},
                        fingerprint=lambda: {"kind": "fixture"},
                    )
                    with patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None, **flags}}, clear=True), \
                            patch.object(studio, "_new_provider", return_value=provider):
                        studio._studio_job("unclosed.tex", source, job_id)
                        problems = studio._jobs[job_id]["result"]["problems_after"]
                    self.assertEqual(len(problems), 1, problems)
                    self.assertEqual(problems[0]["id"], "math-boundary-0")
                    self.assertEqual(problems[0]["type"], "formula")
                    self.assertEqual(problems[0]["status"], "NEEDS_HUMAN")
                    self.assertIn("unclosed_math", problems[0]["reason"])

        # Explicit model abstention (assess_candidate(...).get("method") == "unchanged") stops retry immediately.
        for planned in (False, True):
            for trailing, mock_unchanged in (("  ", False), (r"\ ", True)):
                calls = []

                class AbstainingProvider:
                    name = "abstaining"
                    last_trace = {"model_calls": 1, "reason": "ok"}

                    def fingerprint(self):
                        return {"kind": "abstaining"}

                    def repair_formula(self, node, **kwargs):
                        calls.append(node["data"]["latex"])
                        return "  " + node["data"]["latex"] + trailing

                checks = []

                def fake_verify(expr):
                    checks.append(expr)
                    return {"status": "RETRY", "reason": "unclosed_brace"}

                assess_ctx = (
                    patch.object(studio, "assess_candidate",
                                 side_effect=lambda orig, cand: {"allowed": True, "reason": "unchanged_source", "method": "unchanged"})
                    if mock_unchanged else patch.dict(os.environ, {})
                )
                with self.subTest(planned=planned, mock_unchanged=mock_unchanged), \
                        patch.object(studio, "deterministic_candidate", return_value=None), \
                        assess_ctx, \
                        patch.object(studio, "_verify_formula", side_effect=fake_verify):
                    if planned:
                        fixed, edits, _ = studio._apply_planned_fixes(
                            r"$\frac{a}{b$", [], provider=AbstainingProvider(),
                            emit=lambda *a, **k: None, use_model_planner=False)
                    else:
                        fixed, edits = studio._apply_fixes(
                            r"$\frac{a}{b$", [], provider=AbstainingProvider())
                self.assertEqual(fixed, r"$\frac{a}{b$")
                self.assertEqual(edits, [])
                self.assertEqual(len(calls), 1, "abstention must stop without a second VLM attempt")
                self.assertEqual(checks, [r"\frac{a}{b"], "abstained original must not be re-verified")


@unittest.skipUnless(os.name == "posix", "POSIX shell launcher")
class MiniCPMProfileTest(unittest.TestCase):
    def test_example_env_preserves_exported_credentials_and_profile_endpoint_default(self):
        check = (
            "import json, os; print(json.dumps({"
            "'key_preserved': os.environ['VLM_API_KEY'] == 'test-only-api-key',"
            "'token_preserved': os.environ['DEMO_TOKEN'] == 'test-only-demo-token',"
            "'base_unset': 'VLM_BASE_URL' not in os.environ}))")
        environment = {"PATH": os.environ["PATH"], "VLM_API_KEY": "test-only-api-key",
                       "DEMO_TOKEN": "test-only-demo-token", "ENV_EXAMPLE": str(ROOT / ".env.example"),
                       "CHECK_PYTHON": sys.executable, "CHECK_CODE": check}
        result = subprocess.run(["sh", "-c", 'set -a; . "$ENV_EXAMPLE"; set +a; "$CHECK_PYTHON" -c "$CHECK_CODE"'],
                                env=environment, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout),
                         {"key_preserved": True, "token_preserved": True, "base_unset": True})
        self.assertNotIn("test-only-api-key", result.stdout + result.stderr)
        self.assertNotIn("test-only-demo-token", result.stdout + result.stderr)

    def test_launcher_uses_one_model_and_maps_only_environment_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "capture.py"
            capture.write_text(
                "import json, os, sys\n"
                "print(json.dumps({'args': sys.argv[1:], 'model': os.environ['VLM_MODEL'], "
                "'base': os.environ['VLM_BASE_URL'], 'key_matches': os.environ['VLM_API_KEY'] "
                "== os.environ['EXPECTED_TEST_KEY'], 'skill': os.environ['SKILL_MODE']}))\n")
            fake_python = Path(directory) / "python"
            fake_python.write_text('#!/bin/sh\nexec "$CHECK_PYTHON" "$CHECK_CAPTURE" "$@"\n')
            fake_python.chmod(0o700)
            launcher = str(ROOT / "scripts/run-minicpm-v47-studio.sh")
            for extra, key, expected_base in (
                ({"TEXADA_OPENAI_API_KEY": "shared-test-key"}, "shared-test-key", "https://api.modelbest.cn/v1"),
                ({"VLM_API_KEY": "studio-test-key", "TEXADA_OPENAI_API_KEY": "shared-test-key", "VLM_BASE_URL": "http://localhost:9000/v1"},
                 "studio-test-key", "http://localhost:9000/v1"),
            ):
                environment = {"PATH": os.environ["PATH"], "DEMO_TOKEN": "test-only-demo-token",
                               "CHECK_PYTHON": sys.executable, "CHECK_CAPTURE": str(capture),
                               "TEXADA_STUDIO_PYTHON": str(fake_python), "VLM_MODEL": "legacy-model",
                               "EXPECTED_TEST_KEY": key, **extra}
                result = subprocess.run([launcher, "--log-level", "warning"], env=environment,
                                        text=True, capture_output=True, check=True)
                output = json.loads(result.stdout)
                self.assertEqual(output["model"], "MiniCPM-V-4.7-1B")
                self.assertEqual(output["base"], expected_base)
                self.assertTrue(output["key_matches"])
                self.assertEqual(output["skill"], "on")
                self.assertEqual(output["args"][:3], ["-m", "uvicorn", "app:app"])
                self.assertIn("127.0.0.1", output["args"])
                self.assertEqual(output["args"][-2:], ["--log-level", "warning"])
                self.assertNotIn(key, result.stdout + result.stderr)

    def test_launcher_requires_key_and_ui_token_before_start(self):
        launcher = str(ROOT / "scripts/run-minicpm-v47-studio.sh")
        for extra, message in (({}, "VLM_API_KEY"), ({"VLM_API_KEY": "test-only-key"}, "DEMO_TOKEN")):
            with self.subTest(message=message):
                result = subprocess.run([launcher], env={"PATH": os.environ["PATH"], **extra},
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertNotIn("test-only-key", result.stderr)

class VerificationFailureTest(unittest.TestCase):
    @patch.object(studio, "repair_blocker", lambda original: None)
    def test_invalid_cloud_response_cannot_reach_checker_or_change_document(self):
        content = 'Original $a_$ text.\r\n'
        key = "test-only-api-key"
        cases = [('{"latex":"x","latex":"a_1"}', {}),
                 ('{"latex":"a_1"}', {"finish_reason": "length"}),
                 ('{"latex":"test\\u002donly\\u002dapi\\u002dkey"}', {})]
        for candidate, extra in cases:
            body = {"choices": [{"message": {"content": candidate}, **extra}]}
            with self.subTest(candidate=candidate), patch.dict(os.environ, {"VLM_API_KEY": key}):
                provider = vlm.OpenAICompatibleProvider("https://api.modelbest.cn/v1", "MiniCPM-V-4.7-1B")
            problem = {"id": "formula-1", "line": 1, "latex": "a_", "status": "RETRY"}
            events = []
            with patch.object(studio, '_formula_problems', return_value=[problem]), \
                 patch.object(studio, '_verify_formula') as verify, \
                 patch.object(vlm.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(body).encode())) as network:
                fixed, edits = studio._apply_fixes(content, [], provider=provider,
                    emit=lambda action, **fields: events.append({"action": action, **fields}))
            verify.assert_not_called()
            self.assertEqual(network.call_count, 2)
            self.assertEqual(fixed, content)
            self.assertEqual(edits, [])
            self.assertNotIn(key, json.dumps(events))

    def test_verifier_failure_is_not_green(self):
        failures = [SimpleNamespace(returncode=1, stdout='', stderr='crash'),
                    SimpleNamespace(returncode=0, stdout='not json', stderr=''),
                    SimpleNamespace(returncode=0, stdout='{"status":[]}', stderr=''),
                    SimpleNamespace(returncode=0, stdout='{"status":"UNKNOWN"}', stderr='')]
        for result in failures:
            with self.subTest(result=result), patch.object(studio.subprocess, 'run', return_value=result):
                self.assertEqual(studio._formula_problems('$a_$')[0]['status'], 'NEEDS_ENV')
        with patch.object(studio.subprocess, 'run', side_effect=subprocess.TimeoutExpired('verify', 30)):
            self.assertEqual(studio._verify_formula('x')['status'], 'NEEDS_ENV')

    def test_environment_failure_never_calls_model_or_changes_text(self):
        content = 'Original $a_$ text.\n'
        with patch.object(studio, '_verify_formula', return_value={'status': 'NEEDS_ENV'}), \
             patch.object(studio.PROVIDER, 'repair_formula') as repair:
            fixed, edits = studio._apply_fixes(content, [])
        repair.assert_not_called()
        self.assertEqual(fixed, content)
        self.assertEqual(edits, [])

    def test_bad_input_remains_a_human_problem(self):
        result = SimpleNamespace(returncode=1, stdout='{"status":"NEEDS_HUMAN","reason":"bad_input"}')
        with patch.object(studio.subprocess, 'run', return_value=result), \
             patch.object(studio.PROVIDER, 'repair_formula') as repair:
            self.assertEqual(studio._verify_formula('x')['status'], 'NEEDS_HUMAN')
            fixed, edits = studio._apply_fixes('Original $a_$ text.\r\n', [])
        repair.assert_not_called()
        self.assertEqual(fixed, 'Original $a_$ text.\r\n')
        self.assertEqual(edits, [])

    def test_verifier_status_and_exit_code_must_agree(self):
        for status, code in (('OK', 1), ('RETRY', 1), ('NEEDS_HUMAN', 2), ('NEEDS_HUMAN', 0)):
            with self.subTest(status=status, code=code):
                result = SimpleNamespace(returncode=code, stdout='{"status":"' + status + '"}')
                with patch.object(studio.subprocess, 'run', return_value=result):
                    self.assertEqual(studio._verify_formula('x')['status'], 'NEEDS_ENV')
        result = SimpleNamespace(returncode=2, stdout='{"status":"NEEDS_ENV","reason":"missing antlr"}')
        with patch.object(studio.subprocess, 'run', return_value=result):
            self.assertEqual(studio._verify_formula('x')['reason'], 'missing antlr')

    @patch.object(studio, "repair_blocker", lambda original: None)
    def test_candidate_environment_failure_stops_retries(self):
        content = 'Original $a_$ text.\n'
        log = []
        with patch.object(studio, '_verify_formula', side_effect=[
                {'status': 'RETRY'}, {'status': 'NEEDS_ENV', 'reason': 'missing antlr'}]), \
             patch.object(studio.PROVIDER, 'repair_formula', return_value='a_1') as repair:
            fixed, edits = studio._apply_fixes(content, log)
        repair.assert_called_once()
        self.assertEqual(fixed, content)
        self.assertEqual(edits, [])
        self.assertIn('停止尝试', '\n'.join(log))

    def test_invalid_model_response_never_creates_an_edit(self):
        content = 'Original $a_$ text.\n'
        with patch.object(studio, '_verify_formula', return_value={'status': 'RETRY'}), \
             patch.object(studio.PROVIDER, 'repair_formula', return_value={'latex': 'a_1'}):
            fixed, edits = studio._apply_fixes(content, [])
        self.assertEqual(fixed, content)
        self.assertEqual(edits, [])

    @patch.object(studio, "repair_blocker", lambda original: None)
    def test_candidate_environment_failure_also_stops_later_formula_repairs(self):
        content = 'Original $a_$ and $b_$ text.\n'
        problems = [dict(id=f'f-{i}', line=1, latex=value, status='RETRY')
                    for i, value in enumerate(('a_', 'b_'))]
        with patch.object(studio, '_formula_problems', return_value=problems), \
             patch.object(studio, '_verify_formula', return_value={'status': 'NEEDS_ENV'}), \
             patch.object(studio.PROVIDER, 'repair_formula', return_value='a_1') as repair:
            fixed, edits = studio._apply_fixes(content, [])
        repair.assert_called_once()
        self.assertEqual(fixed, content)
        self.assertEqual(edits, [])

    def test_report_total_preserves_table_and_other_cells(self):
        content = (ROOT / 'samples/docs/report-01.tex').read_text()
        with patch.object(studio, '_formula_problems', return_value=[]), \
             patch.object(studio.PROVIDER, 'repair_formula') as repair:
            fixed, edits = studio._apply_fixes(content, [])
        repair.assert_not_called()
        self.assertEqual(fixed, content.replace('650 & 115', '650 & 105'))
        self.assertEqual(len(edits), 1)
        self.assertEqual(studio._table_problems(fixed), [])


class StudioTableAuditTest(unittest.TestCase):
    @staticmethod
    def table(rows, total='0', newline='\n'):
        lines = [r'\begin{tabular}{|l|r|}', r'项目 & 数量 \\', r'\hline']
        lines.extend(label + ' & ' + value + r' \\' for label, value in rows)
        lines.extend(['合计 & ' + total + r' \\', r'\end{tabular}'])
        return newline.join(lines) + newline

    def test_model_deferral_does_not_gate_deterministic_formula_and_table_repairs(self):
        formula = r"$\left(\frac{x+1}{x-1}$"
        content = formula + "\n" + self.table([("A", "20"), ("B", "31")], "50")
        summary = {"executed": 0, "rejected": 1, "nodes": [{"state": "human"}]}
        provider = SimpleNamespace(repair_formula=lambda _: self.fail("Fallback must not call a model"))
        for use_model_planner, skill_selection in ((True, False), (False, True), (True, True)):
            with self.subTest(planner=use_model_planner, selection=skill_selection), \
                    patch.object(studio, "ConstrainedPlanner") as planner, \
                    patch.object(studio, "_verify_formula",
                                 side_effect=lambda latex: {"status": "OK" if r"\right)" in latex else "RETRY"}):
                planner.return_value.run.return_value = ([], summary)
                planner.return_value.remaining_seconds.return_value = 30
                fixed, edits, _ = studio._apply_planned_fixes(
                    content, [], provider=provider, emit=lambda *args, **kwargs: None,
                    use_model_planner=use_model_planner, skill_selection=skill_selection)
                expected = content.replace(formula, formula[:-1] + r"\right)$").replace("合计 & 50", "合计 & 51")
                self.assertEqual(fixed, expected)
                self.assertEqual([edit["skill"] for edit in edits], ["doc-formula-verify", "doc-table-audit"])

    def test_planned_fallback_aligns_shifted_formula_ordinals_and_skips_attempted_nodes(self):
        lines = [
            "$x+$",
            r"$\left(a+b\right)$",
            r"$\left(\frac{u+1}{u-1}$",
            r"$\left(c+d$",
        ]
        content = "\n".join(lines) + "\n"
        nodes = studio.extract_math(content)
        multiline_edit = {
            "line": 1,
            "before": "x+",
            "after": "x\n+1",
            "skill": "doc-formula-verify",
            "start": nodes[0]["body_start"],
            "end": nodes[0]["body_end"],
        }
        summary = {
            "executed": 3,
            "rejected": 0,
            "nodes": [
                {"id": "f-001-1", "kind": "formula", "line": 1, "state": "candidate", "attempts": 1},
                {"id": "f-002-2", "kind": "formula", "line": 2, "state": "ok", "attempts": 0},
                {"id": "f-003-3", "kind": "formula", "line": 3, "state": "human", "attempts": 0,
                 "human_reason": "model_deferred"},
                {"id": "f-004-4", "kind": "formula", "line": 4, "state": "needs_human", "attempts": 1,
                 "human_reason": "repair_rejected"},
            ],
        }
        verified = []

        def fake_verify(latex):
            verified.append(latex)
            if latex == r"\left(\frac{u+1}{u-1}\right)":
                return {"status": "OK"}
            return {"status": "RETRY"}

        provider = SimpleNamespace(repair_formula=lambda *a, **k: self.fail("Fallback must not call model"))
        with patch.object(studio, "ConstrainedPlanner") as planner_cls, \
                patch.object(studio, "_verify_formula", side_effect=fake_verify):
            planner_cls.return_value.run.return_value = ([multiline_edit], summary)
            planner_cls.return_value.remaining_seconds.return_value = 30
            fixed, edits, out_summary = studio._apply_planned_fixes(
                content, [], provider=provider, emit=lambda *a, **k: None
            )

        self.assertIn(r"$\left(\frac{u+1}{u-1}\right)$", fixed)
        self.assertEqual(
            verified,
            [r"\left(\frac{u+1}{u-1}", r"\left(\frac{u+1}{u-1}\right)"],
            "Fallback must skip already-ok and already-attempted formulas",
        )
        self.assertEqual(
            out_summary.get("deterministic_resolved"),
            ["f-003-3"],
            "deterministic_resolved must store only the canonical pre-edit formula ID",
        )
        remaining = studio._planned_problems(out_summary, fixed)
        self.assertEqual(len(remaining), 1, remaining)
        self.assertEqual(remaining[0]["id"], "f-004-4")
        self.assertEqual(remaining[0]["line"], 5, "Shifted post-edit line number must be reported")

        synthetic = studio._planned_problems({"nodes": [
            {"state": "human"},
            {"id": "table-document", "kind": "table", "line": 9, "state": "human"},
        ]})
        self.assertEqual(len(synthetic), 2)
        self.assertEqual(synthetic[1]["type"], "table_total")

    def assert_manual_unchanged(self, content):
        problems = studio._table_problems(content)
        self.assertTrue(problems)
        self.assertTrue(all(p['status'] == 'NEEDS_HUMAN' for p in problems), problems)
        self.assertTrue(all('right' not in p for p in problems), problems)
        with patch.object(studio, '_formula_problems', return_value=[]), \
             patch.object(studio.PROVIDER, 'repair_formula') as repair:
            fixed, edits = studio._apply_fixes(content, [])
        repair.assert_not_called()
        self.assertEqual(fixed, content)
        self.assertEqual(edits, [])

    def test_signed_decimals_and_grouped_numbers_recalculate_exactly(self):
        content = self.table([('A', '+1,000.25'), ('B', '-20.5'), ('C', '.25')], newline='\r\n')
        problems = studio._table_problems(content)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]['right'], '980')
        with patch.object(studio, '_formula_problems', return_value=[]):
            fixed, edits = studio._apply_fixes(content, [])
        self.assertEqual(fixed, content.replace('合计 & 0', '合计 & 980'))
        self.assertEqual(edits, [{'line': 7, 'before': '0', 'after': '980', 'skill': 'doc-table-audit'}])
        self.assertEqual(studio._table_problems(fixed), [])

    def test_decimal_and_large_integer_totals_are_not_rounded(self):
        self.assertEqual(studio._table_problems(self.table([('A', '0.1'), ('B', '0.2')], '0.3')), [])
        value = '123456789012345678901234567890'
        problems = studio._table_problems(self.table([('A', value), ('B', '0.00001')], value))
        self.assertEqual(problems[0]['right'], value + '.00001')

    def test_non_numeric_total_is_manual_without_a_candidate(self):
        self.assert_manual_unchanged(self.table([('A', '1'), ('B', '2')], '—', newline='\r\n'))

    def test_complex_numeric_formats_require_human_review(self):
        for value in ('(20)', r'20\%', '20%', '20 kg', r'\num{20}', '$20', '12,34',
                      '1,234,56', '1.234,50', '1e3', 'NaN', 'Infinity'):
            with self.subTest(value=value):
                self.assert_manual_unchanged(self.table([('A', value), ('B', '2')], '0'))

    def test_mixed_units_are_not_summed_as_plain_numbers(self):
        self.assert_manual_unchanged(self.table([('A', '1 kg'), ('B', '2 g')], '3 kg'))

    def test_non_rectangular_or_short_rows_require_human_review(self):
        content = self.table([('A', '1'), ('B', '2')], '0')
        for replacement in (r'B \\', r'B & 2 & 999 \\', r'B & 2'):
            with self.subTest(replacement=replacement):
                self.assert_manual_unchanged(content.replace(r'B & 2 \\', replacement))

    def test_ambiguous_header_and_subtotal_are_not_automatically_summed(self):
        content = self.table([('A', '1'), ('B', '2')], '0')
        self.assert_manual_unchanged(content.replace(r'项目 & 数量 \\', r'项目 & 99 \\'))
        self.assert_manual_unchanged(content.replace('B & 2', '小计 total & 2'))

    def test_complex_column_spec_and_unclosed_table_require_human_review(self):
        content = self.table([('A', '1'), ('B', '2')], '0')
        self.assert_manual_unchanged(content.replace('{|l|r|}', '{|l|p{3cm}|}'))
        self.assert_manual_unchanged(content.replace(r'\end{tabular}', ''))

    def test_stale_or_invalid_candidates_never_claim_an_edit(self):
        for total, right in (('—', '3'), ('3', '3'), ('0', '3 kg'), ('0', None)):
            with self.subTest(total=total, right=right):
                content = self.table([('A', '1'), ('B', '2')], total)
                problem = {'id': 't-test', 'line': 6, 'col': 1, 'status': 'RETRY',
                           'reason': 'synthetic candidate', 'right': right}
                with patch.object(studio, '_formula_problems', return_value=[]), \
                     patch.object(studio, '_table_problems', return_value=[problem]):
                    fixed, edits = studio._apply_fixes(content, [])
                self.assertEqual(fixed, content)
                self.assertEqual(edits, [])

    def test_formfeed_and_unicode_line_separators_in_comments_never_break_table_audit(self):
        prefix = "% comment with \f and \v and \u2028 and \u2029\n\\begin{verbatim}\nrow\f\u2028\u2029\n\\end{verbatim}\n"
        table = self.table([("A", "10"), ("B", "20")], "0")
        content = prefix + table
        problems = studio._table_problems(content)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["status"], "RETRY")
        self.assertEqual(problems[0]["right"], "30")
        self.assertEqual(problems[0]["line"], 10)
        with patch.object(studio, "_formula_problems", return_value=[]):
            fixed, edits = studio._apply_fixes(content, [])
        self.assertEqual(fixed, prefix + self.table([("A", "10"), ("B", "20")], "30"))
        self.assertEqual(len(edits), 1)
        provider = SimpleNamespace(name="fixture", last_trace={}, fingerprint=lambda: {})
        planned_fixed, planned_edits, _ = studio._apply_planned_fixes(
            content, [], provider=provider, emit=lambda *a, **k: None, use_model_planner=False)
        self.assertEqual(planned_fixed, fixed)
        self.assertEqual(planned_edits, edits)

    def test_comments_and_escaped_ampersands_in_tables_are_parsed_and_replaced_safely(self):
        content = "\n".join([
            r"\begin{tabular}{lr} % budget & summary",
            r"部门 & 金额 \\ % header & note",
            r"\hline % rule",
            r"R\&D & 40 \\ % R&D dept",
            r"Operations & 60 \\ % ops",
            r"合计 & 99 \\ % stale & check",
            r"\end{tabular} % end table",
        ]) + "\n"
        problems = studio._table_problems(content)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(problems[0]["status"], "RETRY")
        self.assertEqual(problems[0]["right"], "100")
        with patch.object(studio, "_formula_problems", return_value=[]):
            fixed, edits = studio._apply_fixes(content, [])
        expected = content.replace("合计 & 99 \\\\ % stale & check", "合计 & 100 \\\\ % stale & check")
        self.assertEqual(fixed, expected)
        self.assertEqual(edits, [{"line": 6, "before": "99", "after": "100", "skill": "doc-table-audit"}])
        provider = SimpleNamespace(name="fixture", last_trace={}, fingerprint=lambda: {})
        planned_fixed, planned_edits, _ = studio._apply_planned_fixes(
            content, [], provider=provider, emit=lambda *a, **k: None, use_model_planner=False)
        self.assertEqual(planned_fixed, expected)
        self.assertEqual(planned_edits, edits)

        # Mid-row % comment hides \\ and any commented & 500 \\: must be NEEDS_HUMAN and never add fake cells.
        mid_comment = "\n".join([
            r"\begin{tabular}{lr}",
            r"项目 & 金额 \\",
            r"A & 40 % & 500 \\",
            r"B & 60 \\",
            r"合计 & 100 \\",
            r"\end{tabular}",
        ]) + "\n"
        self.assert_manual_unchanged(mid_comment)


class RealVerifierTest(unittest.TestCase):
    def test_strict_checker_rejects_partial_parse(self):
        self.assertEqual(studio._verify_formula('x+')['status'], 'RETRY')
        self.assertEqual(studio._verify_formula(r'\frac{1}{2}')['status'], 'OK')
        self.assertEqual(studio._verify_formula(r'\left(a+b\right)')['status'], 'OK')
        self.assertEqual(studio._verify_formula(r'\left(a+b\right')['status'], 'RETRY')

    def test_missing_antlr_is_environment_problem(self):
        spec = importlib.util.spec_from_file_location('formula_verifier', studio.VERIFY)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with patch('sympy.parsing.latex.parse_latex', side_effect=ImportError('antlr unavailable')):
            self.assertEqual(verifier.check('x')[0], 'NEEDS_ENV')


class StudioTrackARepairPipelineTest(unittest.TestCase):
    def test_extra_closing_brace_and_interior_brace_repair_in_ordinary_and_planned_modes(self):
        for source, repaired_latex in (
            (r"Value $\frac1}{2}$ here.", r"\frac{1}{2}"),
            (r"Eq $x^{n+1 + y = 0$ end.", r"x^{n+1} + y = 0"),
        ):
            for planned in (False, True):
                calls = []

                class FormulaProvider:
                    name = "track-a-formula"
                    model = "track-a-model"
                    last_trace = {"model_calls": 1, "reason": "ok"}

                    def fingerprint(self):
                        return {"provider": self.name}

                    def repair_formula(self, node, **kwargs):
                        calls.append((node["data"]["latex"], kwargs.get("loaded_skill")))
                        return repaired_latex

                with self.subTest(source=source, planned=planned):
                    if planned:
                        fixed, edits, report = studio._apply_planned_fixes(
                            source, [], provider=FormulaProvider(),
                            emit=lambda *a, **k: None, use_model_planner=False,
                        )
                        self.assertEqual(report["nodes"][0]["state"], "candidate")
                        self.assertEqual(len(report["nodes"]), 1)
                    else:
                        fixed, edits = studio._apply_fixes(source, [], provider=FormulaProvider())
                    self.assertIn(f"${repaired_latex}$", fixed)
                    self.assertEqual(len(edits), 1)
                    self.assertEqual(edits[0]["skill"], "doc-formula-verify")
                    self.assertEqual(len(calls), 1)

        # Equal-brace-count wrong order (x} + {y) must skip model calls in both modes.
        unrepairable = r"Bad $x} + {y$ math."
        for planned in (False, True):
            provider = SimpleNamespace(
                name="forbid", last_trace={}, fingerprint=lambda: {},
                repair_formula=lambda *a, **k: self.fail("unrepairable extra_closing_brace must not call model"),
            )
            if planned:
                fixed, edits, _ = studio._apply_planned_fixes(
                    unrepairable, [], provider=provider, emit=lambda *a, **k: None, use_model_planner=False)
            else:
                fixed, edits = studio._apply_fixes(unrepairable, [], provider=provider)
            self.assertEqual(fixed, unrepairable)
            self.assertEqual(edits, [])

    def test_studio_table_model_repairs_short_and_blank_totals_and_rejects_data_edits(self):
        short_table = "\n".join([
            r"\begin{tabular}{lrr}",
            r"项目 & 单价 & 数量 \\",
            r"\hline",
            r"A & 12.5 & 2 \\",
            r"B & 7.5 & 3 \\",
            r"合计 \\ % 待补全",
            r"\end{tabular}",
        ]) + "\n"
        blank_table = short_table.replace(r"合计 \\ % 待补全", r"合计 &  &  \\ % 待补全")

        for content in (short_table, blank_table):
            for mode in ("ordinary", "planned", "selected"):
                seen_skills = []

                class TableProvider:
                    name = "track-a-table"
                    model = "track-a-model"
                    last_trace = {"model_calls": 1, "reason": "ok"}

                    def fingerprint(self):
                        return {"provider": self.name}

                    def select_skill(self, snapshot, **kwargs):
                        self.last_trace = {"model_calls": 1, "reason": "ok"}
                        return {"skill_id": "doc-table-audit", "state_rev": snapshot["state_rev"], "reason": "table"}

                    def repair_table(self, node, *, timeout=120, loaded_skill=None):
                        seen_skills.append(loaded_skill)
                        self.last_trace = {"model_calls": 1, "reason": "ok"}
                        return [
                            ["项目", "单价", "数量"],
                            ["A", "12.5", "2"],
                            ["B", "7.5", "3"],
                            ["合计", "20.0", "5"],
                        ]

                events = []
                emit = lambda action, **fields: events.append({"action": action, **fields})
                with self.subTest(content_kind="short" if "合计 \\\\" in content else "blank", mode=mode):
                    if mode == "ordinary":
                        fixed, edits = studio._apply_fixes(content, [], provider=TableProvider(), emit=emit)
                    else:
                        fixed, edits, report = studio._apply_planned_fixes(
                            content, [], provider=TableProvider(), emit=emit,
                            skill_selection=(mode == "selected"), use_model_planner=False,
                        )
                        self.assertEqual(report["nodes"], [{
                            "id": "table-document", "kind": "table", "line": 1,
                            "state": "candidate", "attempts": 1,
                        }])
                        self.assertEqual(report["reserved_model_calls"], 2 if mode == "selected" else 1)
                    self.assertIn(r"合计 & 20.0 & 5 \\ % 待补全", fixed)
                    self.assertIn(r"A & 12.5 & 2 \\", fixed)
                    self.assertEqual(len(edits), 1)
                    self.assertEqual(edits[0]["skill"], "doc-table-audit")
                    self.assertEqual(studio._table_problems(fixed), [])
                    self.assertTrue(any(e["action"] == "CANDIDATE_ACCEPTED" for e in events))
                    if mode == "selected":
                        self.assertEqual(seen_skills[0].name, "doc-table-audit")

        # Reject tampered data cells even if the altered sum matches!
        class TamperingTableProvider:
            name = "tamper"
            last_trace = {"model_calls": 1, "reason": "ok"}
            fingerprint = lambda self: {}

            def repair_table(self, node, **kwargs):
                return [
                    ["项目", "单价", "数量"],
                    ["A", "10.0", "2"],  # tampered from 12.5!
                    ["B", "7.5", "3"],
                    ["合计", "17.5", "5"],
                ]

        fixed, edits = studio._apply_fixes(short_table, [], provider=TamperingTableProvider())
        self.assertEqual(fixed, short_table)
        self.assertEqual(edits, [])

    def test_studio_cleanup_repairs_zero_width_and_unclosed_structures_without_affecting_clean_docs(self):
        # 1) Deterministic zero-width cleanup uses 0 model calls.
        zw_doc = "\ufeff\\section{标题}\n正文\u200b内容 $x+1$。\n"
        forbid_provider = SimpleNamespace(
            name="forbid", last_trace={}, fingerprint=lambda: {},
            repair_cleanup=lambda *a, **k: self.fail("zero-width cleanup must be deterministic"),
        )
        fixed_zw, edits_zw, report_zw = studio._apply_planned_fixes(
            zw_doc, [], provider=forbid_provider, emit=lambda *a, **k: None, use_model_planner=False,
        )
        self.assertEqual(fixed_zw, "\\section{标题}\n正文内容 $x+1$。\n")
        self.assertEqual(len(edits_zw), 2)
        self.assertTrue(all(e["skill"] == "latex-cleanup" for e in edits_zw))
        self.assertEqual(report_zw["reserved_model_calls"], 0)

        # 2) Model cleanup closes unclosed command/environment while preserving prose and math.
        unclosed_doc = "\\documentclass{article}\n\\begin{document}\n\\section{引言\n\\begin{itemize}\n\\item 条目一 $a+b$\n\n总结段落。\n\\end{document}\n"
        repaired_doc = "\\documentclass{article}\n\\begin{document}\n\\section{引言}\n\\begin{itemize}\n\\item 条目一 $a+b$\n\\end{itemize}\n\n总结段落。\n\\end{document}\n"

        for mode in ("ordinary", "selected"):
            seen_skills = []

            class CleanupProvider:
                name = "track-a-cleanup"
                model = "track-a-model"
                last_trace = {"model_calls": 1, "reason": "ok"}

                def fingerprint(self):
                    return {"provider": self.name}

                def select_skill(self, snapshot, **kwargs):
                    self.last_trace = {"model_calls": 1, "reason": "ok"}
                    kind = snapshot["node"]["kind"]
                    skill_map = {"formula": "doc-formula-verify", "table": "doc-table-audit", "cleanup": "latex-cleanup"}
                    return {"skill_id": skill_map[kind], "state_rev": snapshot["state_rev"], "reason": "route"}

                def repair_cleanup(self, node, *, timeout=120, loaded_skill=None):
                    seen_skills.append(loaded_skill)
                    self.last_trace = {"model_calls": 1, "reason": "ok"}
                    return repaired_doc

            with self.subTest(mode=mode):
                if mode == "ordinary":
                    fixed, edits = studio._apply_fixes(unclosed_doc, [], provider=CleanupProvider())
                else:
                    fixed, edits, report = studio._apply_planned_fixes(
                        unclosed_doc, [], provider=CleanupProvider(),
                        emit=lambda *a, **k: None, skill_selection=True, use_model_planner=False,
                    )
                    self.assertEqual(seen_skills[0].name, "latex-cleanup")
                    self.assertTrue(any(s["skill_id"] == "latex-cleanup" for s in report["loaded_skills"]))
                self.assertEqual(fixed, repaired_doc)
                self.assertTrue(any(e["skill"] == "latex-cleanup" for e in edits))
                self.assertEqual(studio._analyze(fixed), [])

    def test_studio_job_combines_formula_table_and_cleanup_skills_with_exact_model_accounting(self):
        combined_source = "\n".join([
            r"\documentclass{article}",
            r"\begin{document}",
            r"\section{综合测试",
            r"公式 $x^{n+1 + y = 0$ 与表格：",
            r"\begin{tabular}{lr}",
            r"项目 & 金额 \\",
            r"A & 15 \\",
            r"B & 25 \\",
            r"合计 \\",
            r"\end{tabular}",
            r"\end{document}",
        ]) + "\n"

        for skill_selection in (False, True):
            job_id = ("c" if skill_selection else "b") * 32

            class AllThreeProvider:
                name = "all-three-provider"
                model = "all-three-model"
                last_trace = {"model_calls": 1, "reason": "ok"}

                def fingerprint(self):
                    return {"provider": self.name}

                def select_skill(self, snapshot, **kwargs):
                    self.last_trace = {"model_calls": 1, "reason": "ok"}
                    mapping = {
                        "formula": "doc-formula-verify",
                        "table": "doc-table-audit",
                        "cleanup": "latex-cleanup",
                    }
                    return {
                        "skill_id": mapping[snapshot["node"]["kind"]],
                        "state_rev": snapshot["state_rev"],
                        "reason": "route",
                    }

                def repair_formula(self, node, **kwargs):
                    self.last_trace = {"model_calls": 1, "reason": "ok"}
                    return "x^{n+1} + y = 0"

                def repair_table(self, node, **kwargs):
                    self.last_trace = {"model_calls": 1, "reason": "ok"}
                    return [["项目", "金额"], ["A", "15"], ["B", "25"], ["合计", "40"]]

                def repair_cleanup(self, node, **kwargs):
                    self.last_trace = {"model_calls": 1, "reason": "ok"}
                    return node["data"]["content"].replace(r"\section{综合测试", r"\section{综合测试}")

            with self.subTest(skill_selection=skill_selection), \
                    tempfile.TemporaryDirectory() as temp_state, \
                    patch.object(studio, "STUDIO_STATE", temp_state), \
                    patch.dict(studio._jobs, {job_id: {
                        "done": False, "log": [], "result": None, "name": "combined.tex",
                        "created_at": 1, "planner_mode": False, "skill_selection": skill_selection,
                    }}, clear=True), \
                    patch.object(studio, "_new_provider", return_value=AllThreeProvider()), \
                    patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}):
                studio._studio_job("combined.tex", combined_source, job_id)
                result = studio._read_job(job_id)["result"]

            self.assertIn(r"\section{综合测试}", result["fixed_content"])
            self.assertIn(r"$x^{n+1} + y = 0$", result["fixed_content"])
            self.assertIn(r"合计 & 40 \\", result["fixed_content"])
            self.assertEqual(result["problems_after"], [])
            self.assertEqual(
                {edit["skill"] for edit in result["edits"]},
                {"doc-formula-verify", "doc-table-audit", "latex-cleanup"},
            )
            # Ordinary: 3 repair calls (note formula tries deterministic first -> 0 calls, then 1 model call).
            # Skill selection: 3 selection calls + 3 repair calls = 6 model calls.
            self.assertEqual(result["model_calls"], 6 if skill_selection else 3)
            self.assertEqual(result["provider"], "all-three-provider")

    def test_planned_cleanup_and_table_with_commented_end_tabular_do_not_collide(self):
        source = "\n".join([
            r"\section{标题",
            r"\begin{center}",
            r"\begin{tabular}{lr}",
            r"项目 & 金额 \\",
            r"A & 1 \\ % fake \end{tabular}",
            r"合计 & 99 \\",
            r"\end{tabular}",
        ]) + "\n"
        bad_candidate = "\n".join([
            r"\section{标题}",
            r"\begin{center}",
            r"\begin{tabular}{lr}",
            r"项目 & 金额 \\",
            r"A & 1 \\ % fake \end{tabular}",
            r"\end{center}",
            r"合计 & 99 \\",
            r"\end{tabular}",
        ]) + "\n"
        good_candidate = "\n".join([
            r"\section{标题}",
            r"\begin{center}",
            r"\begin{tabular}{lr}",
            r"项目 & 金额 \\",
            r"A & 1 \\ % fake \end{tabular}",
            r"合计 & 99 \\",
            r"\end{tabular}",
            r"\end{center}",
        ]) + "\n"

        class Provider:
            name = "combo"
            last_trace = {"model_calls": 1, "reason": "ok"}
            fingerprint = lambda self: {}

            def __init__(self):
                self.replies = iter([bad_candidate, good_candidate])

            def repair_cleanup(self, node, **kwargs):
                self.last_trace = {"model_calls": 1, "reason": "ok"}
                return next(self.replies)

        fixed, edits, report = studio._apply_planned_fixes(
            source, [], provider=Provider(), emit=lambda *a, **k: None, use_model_planner=False,
        )
        self.assertIn(r"\section{标题}", fixed)
        self.assertIn(r"合计 & 1 \\", fixed)
        self.assertTrue(fixed.endswith("\\end{tabular}\n\\end{center}\n"))
        self.assertEqual({e["skill"] for e in edits}, {"latex-cleanup", "doc-table-audit"})
        self.assertEqual(report["reserved_model_calls"], 2)

    def test_mixed_wrong_and_blank_total_row_emits_single_deduplicated_line_edit(self):
        source = "\n".join([
            r"\begin{tabular}{lrr}",
            r"项目 & 单价 & 数量 \\",
            r"A & 10 & 2 \\",
            r"B & 20 & 3 \\",
            r"合计 & 99 &  \\",
            r"\end{tabular}",
        ]) + "\n"

        class TableProvider:
            name = "table-mix"
            last_trace = {"model_calls": 1, "reason": "ok"}
            fingerprint = lambda self: {}

            def repair_table(self, node, **kwargs):
                self.last_trace = {"model_calls": 1, "reason": "ok"}
                return [["项目", "单价", "数量"], ["A", "10", "2"], ["B", "20", "3"], ["合计", "30", "5"]]

        fixed, edits = studio._apply_fixes(source, [], provider=TableProvider())
        self.assertIn(r"合计 & 30 & 5 \\", fixed)
        self.assertEqual(len(edits), 1, edits)
        self.assertEqual(edits[0], {
            "line": 5,
            "before": "合计 & 99 &  ",
            "after": "合计 & 30 & 5 ",
            "skill": "doc-table-audit",
        })

    def test_windows_subprocess_calls_pass_create_no_window_flag(self):
        seen_kwargs = []

        def fake_run(cmd, **kwargs):
            seen_kwargs.append((cmd[0], kwargs))
            if cmd[0] == studio._tectonic_command():
                out_dir = Path(cmd[cmd.index("-o") + 1])
                (out_dir / "main.pdf").write_bytes(b"%PDF-1.4\n")
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            if cmd[0] == "pdfinfo":
                return SimpleNamespace(returncode=0, stdout=b"Pages: 1\n", stderr=b"")
            if cmd[0] == "pdftoppm":
                prefix = Path(cmd[-1])
                prefix.with_suffix(".png").write_bytes(b"\x89PNG\r\n\x1a\n")
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            raise AssertionError(f"unexpected cmd: {cmd}")

        with tempfile.TemporaryDirectory() as temp_state, \
                patch.object(studio, "STUDIO_STATE", temp_state), \
                patch.object(studio._sys, "platform", "win32"), \
                patch.object(studio.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.object(studio.subprocess, "run", side_effect=fake_run):
            res = studio._studio_compile("synthetic", "example.tex", "win-check")
        self.assertTrue(res["ok"])
        self.assertEqual([name for name, _ in seen_kwargs], [studio._tectonic_command(), "pdfinfo", "pdftoppm"])
        for name, kwargs in seen_kwargs:
            with self.subTest(binary=name):
                self.assertEqual(kwargs.get("creationflags"), 0x08000000)

    def test_source_compile_error_matches_windows_drive_and_backslash_paths(self):
        win_source = Path(r"C:\Users\Demo\builds\main.tex")
        for line_text in (
            r"error: C:\Users\Demo\builds\main.tex:12: Undefined control sequence.",
            r"error: c:\users\demo\builds\main.tex:12: Undefined control sequence.",
            r"error: .\main.tex:12: Undefined control sequence.",
            "error: ./main.tex:12: Undefined control sequence.",
        ):
            with self.subTest(line_text=line_text):
                loc = studio._source_compile_error(line_text, win_source, 40)
                self.assertEqual(loc, {"line": 12, "message": "Undefined control sequence."})

    def test_studio_compile_preserves_stdout_diagnostics_when_stderr_has_warnings(self):
        def fake_run(cmd, **kwargs):
            return SimpleNamespace(
                returncode=1,
                stdout=b"error: main.tex:4: Missing $ inserted.\n",
                stderr=b"warning: minor font note\n",
            )

        with tempfile.TemporaryDirectory() as temp_state, \
                patch.object(studio, "STUDIO_STATE", temp_state), \
                patch.object(studio.subprocess, "run", side_effect=fake_run):
            res = studio._studio_compile("a\nb\nc\n$broken\n", "note.tex", "warn-stdout")
        self.assertFalse(res["compile_ok"])
        self.assertIn("warning: minor font note", res["log"])
        self.assertIn("Missing $ inserted.", res["log"])
        self.assertEqual(res["diagnostic"], {"line": 4, "message": "Missing $ inserted."})

    def test_checker_subprocesses_use_utf8_and_windows_no_window_flag(self):
        seen = []

        def fake_run(cmd, **kwargs):
            seen.append((Path(cmd[1]).name, kwargs))
            if Path(cmd[1]).name == "verify.py":
                return SimpleNamespace(returncode=0, stdout='{"id":"argv","status":"OK","reason":""}\n', stderr="")
            return SimpleNamespace(returncode=0, stdout='{"id":"t-studio","status":"OK","reason":""}\n', stderr="")

        with patch.object(studio._sys, "platform", "win32"), \
                patch.object(studio.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.object(studio.subprocess, "run", side_effect=fake_run):
            self.assertEqual(studio._verify_formula("x^2+1")["status"], "OK")
            self.assertEqual(studio._verify_table_grid([["项目", "金额"], ["A", "1"], ["合计", "1"]])["status"], "OK")
        self.assertEqual([name for name, _ in seen], ["verify.py", "audit_table.py"])
        for name, kwargs in seen:
            with self.subTest(script=name):
                self.assertEqual(kwargs.get("encoding"), "utf-8")
                self.assertEqual(kwargs.get("errors"), "replace")
                self.assertEqual(kwargs.get("creationflags"), 0x08000000)

    def test_local_provider_preserves_custom_skill_root(self):
        import local_runtime

        custom_root = Path(ROOT) / "skills"
        provider = local_runtime.make_local_provider(
            "http://127.0.0.1:18081/v1", "minicpm-v4.7-1b-q4_k_m",
            skill_mode="on", skill_root=custom_root,
        )
        self.assertEqual(provider.skill_root, custom_root)

    def test_compile_latex_and_run_pipeline_use_utf8_and_no_window_flag(self):
        with tempfile.TemporaryDirectory() as render_dir, \
                patch.object(studio, "RENDER", render_dir), \
                patch.object(studio._sys, "platform", "win32"), \
                patch.object(studio.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.object(studio.subprocess, "run",
                             return_value=SimpleNamespace(returncode=1, stdout="", stderr="")) as run_mock:
            self.assertIsNone(studio._compile_latex("x+1", "n1", "orig"))
        self.assertEqual(run_mock.call_args.kwargs.get("encoding"), "utf-8")
        self.assertEqual(run_mock.call_args.kwargs.get("errors"), "replace")
        self.assertEqual(run_mock.call_args.kwargs.get("creationflags"), 0x08000000)

        fake_proc = SimpleNamespace(stdout=iter(()), wait=lambda: 0, returncode=0)
        with tempfile.TemporaryDirectory() as state_dir, \
                patch.object(studio, "STATE", state_dir), \
                patch.object(studio._sys, "platform", "win32"), \
                patch.object(studio.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.object(studio.subprocess, "Popen", return_value=fake_proc) as popen_mock:
            studio._run_pipeline(False)
            for _ in range(50):
                if studio._run["done"]:
                    break
                time.sleep(0.01)
        self.assertEqual(popen_mock.call_args.kwargs.get("encoding"), "utf-8")
        self.assertEqual(popen_mock.call_args.kwargs.get("errors"), "replace")
        self.assertEqual(popen_mock.call_args.kwargs.get("creationflags"), 0x08000000)

    def test_cleanup_falls_back_to_deterministic_zero_width_strip_and_forwards_all_cleanup_issues(self):
        source = (
            "\\author{TeXada Studio\n"
            "正文\u200b段落。\n"
            "\\begin{itemize}\n"
            "\\item 第一项\n"
        )
        seen_contexts = []

        class FailingCleanupProvider:
            name = "failing-cleanup"
            last_trace = {"model_calls": 1, "reason": "bad_candidate_json"}
            fingerprint = lambda self: {}

            def repair_cleanup(self, node, **kwargs):
                seen_contexts.append(node["data"]["repair_context"])
                self.last_trace = {"model_calls": 1, "reason": "bad_candidate_json"}
                return None

        fixed, edits = studio._apply_fixes(source, [], provider=FailingCleanupProvider())
        self.assertEqual(len(seen_contexts), 2)
        reason_summary = seen_contexts[0]["checker"]["reason"]
        self.assertIn("zero_width_noise", reason_summary)
        self.assertIn("unclosed_command_brace", reason_summary)
        self.assertIn("unclosed_environment", reason_summary)
        self.assertNotIn("\u200b", fixed)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["skill"], "latex-cleanup")

        planned_fixed, planned_edits, summary = studio._apply_planned_fixes(
            source, [], provider=FailingCleanupProvider(), emit=lambda *a, **k: None, use_model_planner=False,
        )
        self.assertNotIn("\u200b", planned_fixed)
        self.assertEqual([e["skill"] for e in planned_edits], ["latex-cleanup"])
        remaining_kinds = [p["kind"] for p in studio._planned_problems(summary, planned_fixed)]
        self.assertNotIn("zero_width_noise", remaining_kinds)
        self.assertIn("unclosed_command_brace", remaining_kinds)
        self.assertIn("unclosed_environment", remaining_kinds)

        with tempfile.TemporaryDirectory() as temp_state, \
                patch.object(studio, "STUDIO_STATE", temp_state), \
                patch.object(studio, "_is_local_mode", return_value=True):
            studio._local_runtime(managed=False).update_settings({
                "base_url": "http://127.0.0.1:53058/v1",
                "model": studio.PROFILES["1b"].model,
            })
            provider_1b = studio._new_provider()
            self.assertEqual(
                provider_1b.fingerprint()["parameters"].get("planner_response_format"),
                "numbered_json_choice",
            )

    def test_studio_compile_redacts_internal_build_directory_paths_from_logs(self):
        captured_dir = {}

        def fake_run(cmd, **kwargs):
            build_dir = Path(cmd[cmd.index("-o") + 1])
            captured_dir["path"] = build_dir
            msg = (
                f"error: {build_dir / 'main.tex'}:3: Undefined control sequence.\n"
                f"note: Writing `{build_dir / 'main.log'}` (9.0 KiB)\n"
            )
            return SimpleNamespace(returncode=1, stdout=msg.encode("utf-8"), stderr=b"")

        with tempfile.TemporaryDirectory() as temp_state, \
                patch.object(studio, "STUDIO_STATE", temp_state), \
                patch.object(studio.subprocess, "run", side_effect=fake_run):
            res = studio._studio_compile("a\nb\n\\badcmd\n", "secret-doc.tex", "redact-check")
        self.assertFalse(res["compile_ok"])
        self.assertEqual(res["diagnostic"], {"line": 3, "message": "Undefined control sequence."})
        self.assertNotIn(str(captured_dir["path"]), res["log"])
        self.assertIn("main.tex:3: Undefined control sequence.", res["log"])
        self.assertIn("main.log", res["log"])


if __name__ == '__main__':
    unittest.main()
