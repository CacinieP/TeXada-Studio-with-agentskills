import hashlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
import urllib.request
from unittest.mock import MagicMock, patch

import managed_models
from managed_models import ManagedModels, ModelFile, ModelProfile, PROFILES, _download, find_llama_server


class SourceResponse:
    def __init__(self, payload, status, content_range=None, url=None):
        self.payload = payload
        self.status = status
        self.headers = {"Content-Range": content_range}
        if url is not None:
            self.url = url
        self.closed_flag = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.closed_flag = True

    def read(self, _):
        data, self.payload = self.payload, b""
        return data


class ManagedDownloadTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.data = b"fixture-gguf"
        self.file = ModelFile("model.gguf", len(self.data), hashlib.sha256(self.data).hexdigest())
        self.profile = ModelProfile("Example", "example", "openbmb/example", "revision", (self.file,))
        self.path = self.root / self.file.name
        self.part = self.path.with_suffix(f".gguf.{self.file.sha256}.part")
        self.closed = threading.Event()

    def test_resume_checks_range_and_promotes_verified_file(self):
        self.part.write_bytes(self.data[:4])
        response = SourceResponse(self.data[4:], 206, f"bytes 4-{len(self.data)-1}/{len(self.data)}")
        with patch("managed_models.urllib.request.urlopen", return_value=response) as urlopen:
            _download(self.profile, self.file, self.path, lambda _: None, self.closed)
        self.assertEqual(urlopen.call_args.args[0].headers["Range"], "bytes=4-")
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertFalse(self.part.exists())

    def test_bad_hash_never_becomes_an_installed_model(self):
        response = SourceResponse(b"x" * len(self.data), 200)
        with patch("managed_models.urllib.request.urlopen", return_value=response), \
                self.assertRaisesRegex(ValueError, "SHA-256"):
            _download(self.profile, self.file, self.path, lambda _: None, self.closed)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.part.exists())

    def test_profiles_have_separate_projectors_and_disk_directories(self):
        manager = ManagedModels(self.root)
        self.assertEqual({p["id"] for p in manager.status()["profiles"]}, {"1b", "35b"})
        self.assertNotEqual(PROFILES["1b"].files[1].sha256, PROFILES["35b"].files[1].sha256)
        self.assertNotEqual(manager._paths("1b")[1], manager._paths("35b")[1])

    def test_clean_model_environment_strips_credentials_and_proxies_in_start(self):
        clean_fn = getattr(managed_models, "_clean_model_environment", None)
        self.assertTrue(callable(clean_fn), "_clean_model_environment must exist")
        dirty_env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "OPENAI_API_KEY": "secret-openai-key",
            "vlm_api_key": "secret-vlm-key",
            "HF_TOKEN": "secret-hf-token",
            "DEMO_TOKEN": "secret-demo-token",
            "CLIENT_SECRET": "secret-client",
            "VLM_BASE_URL": "https://api.example.invalid/v1",
            "VLM_MODEL": "remote-model",
            "TEXADA_OPENAI_BASE_URL": "https://api.example.invalid/v1",
            "HTTP_PROXY": "http://127.0.0.1:8080",
            "https_proxy": "http://127.0.0.1:8080",
            "ALL_PROXY": "socks5://127.0.0.1:1080",
            "no_proxy": "localhost",
        }
        cleaned = clean_fn(dirty_env)
        self.assertEqual(cleaned, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})

        state = self.root / "runtime-state"
        manager = ManagedModels(state)
        paths = (self.root / "w.gguf", self.root / "mmproj.gguf")
        for item in paths:
            item.write_bytes(b"stub")
        fake_proc = SimpleNamespace(poll=lambda: None, terminate=lambda: None, wait=lambda timeout=None: 0)
        with patch.dict(os.environ, dirty_env, clear=True), \
                patch("managed_models.find_llama_server", return_value="/usr/bin/llama-server"), \
                patch("managed_models.subprocess.run",
                      return_value=SimpleNamespace(stdout="version: 12000\n", stderr="")) as run_mock, \
                patch("managed_models.subprocess.Popen", return_value=fake_proc) as popen_mock, \
                patch("managed_models.local_json_request",
                      return_value={"data": [{"id": self.profile.model}]}):
            manager._start(self.profile, paths)

        for call_name, mock_obj in (("run", run_mock), ("Popen", popen_mock)):
            passed_env = mock_obj.call_args.kwargs.get("env")
            self.assertIsNotNone(passed_env, f"{call_name} must receive explicit sanitized env")
            self.assertEqual(passed_env, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})

    @unittest.skipUnless(os.name == "posix", "POSIX file mode semantics required")
    def test_download_and_start_enforce_private_directory_and_log_permissions(self):
        state = self.root / "private-state"
        manager = ManagedModels(state)
        with patch("managed_models._matches", return_value=True):
            manager.job = {"profile": "1b", "action": "download", "state": "running", "bytes": 0, "total": 1}
            manager._run("download", "1b")
        model_dir = state / "models" / "1b"
        self.assertEqual(model_dir.stat().st_mode & 0o777, 0o700)

        start_state = self.root / "permissive-state"
        start_state.mkdir(mode=0o755)
        log_path = start_state / "model-server.log"
        log_path.write_bytes(b"old log\n")
        os.chmod(log_path, 0o644)
        manager2 = ManagedModels(start_state)
        paths = (self.root / "w.gguf", self.root / "mmproj.gguf")
        fake_proc = SimpleNamespace(poll=lambda: None, terminate=lambda: None, wait=lambda timeout=None: 0)
        with patch("managed_models.find_llama_server", return_value="/usr/bin/llama-server"), \
                patch("managed_models.subprocess.run",
                      return_value=SimpleNamespace(stdout="version: 12000\n", stderr="")), \
                patch("managed_models.subprocess.Popen", return_value=fake_proc), \
                patch("managed_models.local_json_request",
                      return_value={"data": [{"id": self.profile.model}]}):
            manager2._start(self.profile, paths)
        self.assertEqual(log_path.stat().st_mode & 0o777, 0o600)

        fresh_state = self.root / "fresh-start-state"
        manager3 = ManagedModels(fresh_state)
        with patch("managed_models.find_llama_server", return_value="/usr/bin/llama-server"), \
                patch("managed_models.subprocess.run",
                      return_value=SimpleNamespace(stdout="version: 12000\n", stderr="")), \
                patch("managed_models.subprocess.Popen", return_value=fake_proc), \
                patch("managed_models.local_json_request",
                      return_value={"data": [{"id": self.profile.model}]}):
            manager3._start(self.profile, paths)
        self.assertEqual(fresh_state.stat().st_mode & 0o777, 0o700)
        self.assertEqual((fresh_state / "model-server.log").stat().st_mode & 0o777, 0o600)

    def test_https_redirect_handler_allows_https_cdn_and_blocks_scheme_downgrade(self):
        handler_cls = getattr(managed_models, "_HttpsOnlyRedirectHandler", None)
        self.assertIsNotNone(handler_cls, "_HttpsOnlyRedirectHandler must exist")
        handler = handler_cls()
        req = urllib.request.Request("https://huggingface.co/openbmb/example/resolve/main/model.gguf")
        cdn_req = handler.redirect_request(
            req, io.BytesIO(b""), 302, "Found", {}, "https://cdn-lfs.hf.co/repos/model.gguf"
        )
        self.assertEqual(cdn_req.full_url, "https://cdn-lfs.hf.co/repos/model.gguf")

        for bad_url in ("http://cdn-lfs.hf.co/repos/model.gguf", "file:///tmp/model.gguf", "https:///no-host"):
            fp = MagicMock()
            with self.subTest(bad_url=bad_url), self.assertRaisesRegex(ValueError, "HTTPS"):
                handler.redirect_request(req, fp, 302, "Found", {}, bad_url)
            fp.close.assert_called_once()

        downgraded = SourceResponse(self.data, 200, url="http://cdn-lfs.hf.co/repos/model.gguf")
        with patch("managed_models.urllib.request.urlopen", return_value=downgraded), \
                self.assertRaisesRegex(ValueError, "HTTPS"):
            _download(self.profile, self.file, self.path, lambda _: None, self.closed)
        self.assertTrue(downgraded.closed_flag)
        self.assertFalse(self.path.exists())

    def test_connection_handles_missing_or_exited_process_without_attribute_error(self):
        manager = ManagedModels(self.root)
        manager.active = {"base_url": "http://127.0.0.1:19000/v1", "model": "example"}
        manager.process = None
        self.assertIsNone(manager.connection())
        self.assertIsNone(manager.active)

        manager.active = {"base_url": "http://127.0.0.1:19000/v1", "model": "example"}
        manager.process = SimpleNamespace(poll=lambda: 1)
        self.assertIsNone(manager.connection())
        self.assertIsNone(manager.active)
        self.assertIsNone(manager.process)

    def test_find_llama_server_prefers_bundled_executable_over_system_path(self):
        bundle_dir = self.root / "bundle"
        bundled_bin = bundle_dir / "bin" / "llama-server"
        bundled_bin.parent.mkdir(parents=True)
        bundled_bin.write_text("#!/bin/sh\nexit 0\n")
        bundled_bin.chmod(0o755)

        system_bin = self.root / "sysbin" / "llama-server"
        system_bin.parent.mkdir(parents=True)
        system_bin.write_text("#!/bin/sh\nexit 0\n")
        system_bin.chmod(0o755)

        with patch.dict(os.environ, {"TEXADA_BUNDLE_DIR": str(bundle_dir)}), \
                patch("managed_models.shutil.which", return_value=str(system_bin)):
            self.assertEqual(find_llama_server(), str(bundled_bin.resolve()))

        empty_bundle = self.root / "empty-bundle"
        empty_bundle.mkdir()
        with patch.dict(os.environ, {"TEXADA_BUNDLE_DIR": str(empty_bundle)}), \
                patch("managed_models.shutil.which", return_value=str(system_bin)):
            self.assertEqual(find_llama_server(), str(system_bin))


if __name__ == "__main__":
    unittest.main()
