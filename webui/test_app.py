"""Configuration and local-document regression tests; no model/compiler required."""

import importlib.util
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

    def test_upload_overlays_sample_without_modifying_it(self):
        response = self.client.post("/api/studio/upload", params=self.auth,
                                    json={"name": "example.tex", "content": "user document"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.samples / "example.tex").read_text(), "synthetic sample")
        self.assertEqual((self.uploads / "example.tex").read_text(), "user document")
        self.assertEqual(self.client.get("/api/studio/files", params=self.auth).json(),
                         {"files": ["example.tex"]})
        response = self.client.get("/api/studio/file", params={**self.auth, "name": "example.tex"})
        self.assertEqual(response.json()["content"], "user document")

    def test_samples_work_before_first_upload(self):
        self.assertFalse(self.uploads.exists())
        self.assertEqual(self.client.get("/api/studio/files", params=self.auth).json(),
                         {"files": ["example.tex"]})
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

    def test_missing_preview_converter_is_reported(self):
        with patch.object(studio.subprocess, "run", side_effect=[
            SimpleNamespace(returncode=0, stdout="", stderr=""), FileNotFoundError()
        ]):
            result = studio._studio_compile("synthetic", "example.tex", "test")
        self.assertFalse(result["ok"])
        self.assertIn("pdftoppm", result["log"])

    def test_nodeinfo_without_gpu_or_ollama(self):
        with patch.object(studio.subprocess, "run", side_effect=FileNotFoundError()):
            response = self.client.get("/api/nodeinfo", params=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["gpu"], "")
        self.assertEqual(response.json()["model"], studio.VLM_MODEL)

    def test_pipeline_uses_current_python_no_shell_and_keeps_exit_code(self):
        model = "model name; this must stay one argument"
        process = SimpleNamespace(stdout=["failed\n"], returncode=7, wait=lambda: 7)
        with patch.object(studio, "VLM_MODEL", model), patch.dict(studio._run, clear=True), \
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


if __name__ == "__main__":
    unittest.main()
