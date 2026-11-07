"""Local transcription transport tests; all HTTP is a loopback test double."""

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from local_runtime import (LocalRuntime, LocalRuntimeError, MAX_FILE_BYTES,
                           _candidate_text, local_json_request, make_local_provider, validate_base_url,
                           validate_image)


def png(width=1, height=1):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


PNG = png()


class FakeModel:
    def __init__(self, response=None, status=200, redirect=None):
        owner = self
        self.requests = []
        self.status, self.redirect = status, redirect
        self.response = response if response is not None else {
            "model": "MiniCPM-V-4.7-1B", "choices": [{"message": {"content": "$x^2$"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4}}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.reply()

            def do_POST(self):
                self.reply()

            def reply(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                owner.requests.append({"path": self.path, "headers": dict(self.headers),
                                       "body": json.loads(raw) if raw else None})
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                if owner.redirect:
                    self.send_header("Location", owner.redirect)
                self.end_headers()
                response = owner.response if isinstance(owner.response, bytes) else json.dumps(owner.response).encode()
                self.wfile.write(response)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class LocalRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def image_body(self, **extra):
        return {"name": "formula.png", "mime_type": "image/png", "data_base64": base64.b64encode(PNG).decode(), **extra}

    def test_endpoint_accepts_only_loopback_http_api_roots(self):
        for value, expected in (("http://localhost:8080", "http://localhost:8080/v1"),
                                ("http://127.0.0.1:11434/v1/", "http://127.0.0.1:11434/v1"),
                                ("http://[::1]:8080", "http://[::1]:8080/v1")):
            with self.subTest(value=value):
                self.assertEqual(validate_base_url(value), expected)
        for value in ("https://api.modelbest.cn/v1", "http://example.com", "http://127.0.0.1.evil.test",
                      "http://2130706433", "http://127.1", "file:///tmp/test", "http://user:secret@127.0.0.1",
                      "http://localhost/v1?token=value", "http://localhost/v1#x", "http://localhost/other",
                      "http://localhost:0", "http://localhost:65536"):
            with self.subTest(value=value), self.assertRaises(LocalRuntimeError):
                validate_base_url(value)

    def test_settings_persist_without_a_request_or_credentials(self):
        runtime = LocalRuntime(self.root)
        with patch("local_runtime.local_json_request", side_effect=AssertionError("unexpected model request")):
            config = runtime.get_config()
            self.assertIsNone(config["model_available"])
            self.assertTrue(config["offline"])
            runtime.update_settings({"base_url": "http://127.0.0.1:9000", "model": "local-vision"})
            restored = LocalRuntime(self.root).get_config()
        self.assertEqual(restored["model"], "local-vision")
        self.assertEqual(restored["base_url"], "http://127.0.0.1:9000/v1")
        stored = json.loads(runtime.settings_path.read_text())
        self.assertEqual(set(stored), {"base_url", "model"})
        self.assertEqual(runtime.settings_path.stat().st_mode & 0o777, 0o600)
        for body in ({"base_url": "http://localhost", "model": "x", "api_key": "not-accepted"},
                     {"base_url": "http://remote.test", "model": "x"}):
            with self.assertRaises(LocalRuntimeError):
                runtime.update_settings(body)
        self.assertEqual(LocalRuntime(self.root).get_config()["model"], "local-vision")

    def test_unsaved_connection_probe_never_changes_saved_settings(self):
        runtime = LocalRuntime(self.root)
        runtime.update_settings({"base_url": "http://127.0.0.1:8080/v1", "model": "saved-model"})
        previous = runtime.settings_path.read_bytes()
        with patch("local_runtime.local_json_request", return_value={"data": [{"id": "candidate-model"}]}):
            result = runtime.probe({"base_url": "http://127.0.0.1:9000/v1", "model": "candidate-model"})
        self.assertTrue(result["model_available"])
        self.assertEqual(runtime.settings_path.read_bytes(), previous)
        self.assertEqual(runtime.get_config()["model"], "saved-model")

    def test_corrupt_persisted_settings_fail_closed(self):
        runtime = LocalRuntime(self.root)
        runtime.settings_path.write_text('{"base_url":"http://remote.test","model":"x"}')
        with self.assertRaisesRegex(LocalRuntimeError, "配置无法读取"):
            runtime.get_config()

    def test_probe_lists_actual_models_and_reports_missing_model(self):
        with FakeModel({"data": [{"id": "local-vision"}, {"id": "other"}]}) as model:
            runtime = LocalRuntime(self.root, base_url=model.base, model="local-vision")
            config = runtime.probe()
            self.assertTrue(config["model_available"])
            self.assertEqual(config["models"], ["local-vision", "other"])
            runtime.update_settings({"base_url": model.base, "model": "missing"})
            self.assertEqual(runtime.probe()["error"], "configured_model_not_found")
        self.assertTrue(all(request["path"] == "/v1/models" for request in model.requests))

    def test_no_listener_reports_unavailable_without_claiming_success(self):
        # Reserve then close a local ephemeral port, without probing user services.
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        config = LocalRuntime(self.root, base_url=f"http://127.0.0.1:{port}").probe()
        self.assertFalse(config["model_available"])
        self.assertEqual(config["error"], "local_model_unavailable")

    def test_multimodal_request_bypasses_proxy_and_never_forwards_keys(self):
        with FakeModel() as model, patch.dict(os.environ, {
            "HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1",
            "http_proxy": "http://127.0.0.1:1", "VLM_API_KEY": "private-environment-key"}):
            runtime = LocalRuntime(self.root, base_url=model.base)
            result = runtime.import_document(self.image_body())
        request = model.requests[0]
        self.assertEqual(request["path"], "/v1/chat/completions")
        self.assertNotIn("Authorization", request["headers"])
        body = request["body"]
        self.assertEqual(body["model"], "minicpm-v4.7-35b-a3b-q4")
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        image = body["messages"][1]["content"][1]
        self.assertEqual(image["type"], "image_url")
        self.assertEqual(image["image_url"]["url"], "data:image/png;base64," + base64.b64encode(PNG).decode())
        self.assertTrue(result["requires_review"])
        self.assertIn("\\begin{document}", result["content"])
        self.assertIn("$x^2$", result["content"])
        self.assertEqual(result["source_sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(result["imported_pages"], 1)
        self.assertFalse(result["has_more_pages"])
        self.assertEqual((self.root / "imports" / result["id"] / "source.png").read_bytes(), PNG)
        record = json.loads((self.root / "imports" / result["id"] / "candidate.json").read_text())
        self.assertEqual(record["pages"][0]["raw_response"], "$x^2$")
        self.assertNotIn("private-environment-key", json.dumps(result))

    def test_redirect_is_blocked_without_contacting_target(self):
        with FakeModel() as target, FakeModel(status=302, redirect=target.base + "/models") as model:
            with self.assertRaises(LocalRuntimeError) as error:
                local_json_request(model.base + "/models")
            self.assertEqual(error.exception.code, "redirect_blocked")
            self.assertEqual(target.requests, [])
            self.assertEqual(len(model.requests), 1)

    def test_existing_formula_provider_uses_local_transport_and_records_fingerprint(self):
        harness = str(Path(__file__).resolve().parents[1] / "harness")
        response = {"choices": [{"message": {"content": '{"latex":"a_1"}'}, "finish_reason": "stop"}]}
        with FakeModel(response) as model, patch.object(sys, "path", [harness, *sys.path]), \
                patch.dict(os.environ, {"VLM_API_KEY": "ignored\ncredential"}):
            provider = make_local_provider(model.base, "MiniCPM-V-4.7-1B", skill_mode="off")
            self.assertEqual(provider.repair_formula({"data": {"latex": "a_"}}), "a_1")
            self.assertEqual(provider.name, "local-openai-compatible")
            self.assertIn("local_runtime_sha256", provider.fingerprint())
        self.assertNotIn("Authorization", model.requests[0]["headers"])
        self.assertEqual(provider.last_trace["model_calls"], 1)
        self.assertEqual(provider.last_trace["reason"], "ok")

    def test_invalid_http_and_response_shapes_are_explicit(self):
        for response, status, expected in ((b"not json", 200, "invalid_model_response"),
                                           ([], 200, "invalid_model_response"),
                                           ({"error": "private detail"}, 500, "local_model_http_error")):
            with self.subTest(expected=expected), FakeModel(response, status=status) as model:
                with self.assertRaises(LocalRuntimeError) as error:
                    local_json_request(model.base + "/models")
                self.assertEqual(error.exception.code, expected)
                self.assertNotIn("private detail", error.exception.message)

    def test_bad_images_and_ranges_never_call_a_model(self):
        runtime = LocalRuntime(self.root)
        invalid = [self.image_body(data_base64="invalid?"),
                   self.image_body(data_base64=base64.b64encode(b"not a PNG").decode()),
                   self.image_body(mime_type="image/jpeg"),
                   self.image_body(max_pages=0), self.image_body(max_pages=6),
                   self.image_body(max_pages=True), self.image_body(page_start=0),
                   self.image_body(name="../outside.png"), self.image_body(mime_type="image/svg+xml")]
        with patch("local_runtime.local_json_request", side_effect=AssertionError("model called")):
            for body in invalid:
                with self.subTest(body={k: v for k, v in body.items() if k != "data_base64"}), self.assertRaises(LocalRuntimeError):
                    runtime.import_document(body)
            with self.assertRaises(LocalRuntimeError) as error:
                validate_image(png(15000, 15000), "image/png")
            self.assertEqual(error.exception.code, "image_dimensions_exceeded")

    def test_png_crc_damage_is_rejected_before_model_request(self):
        damaged = bytearray(PNG)
        damaged[-15] ^= 0xFF
        with self.assertRaises(LocalRuntimeError) as error:
            validate_image(bytes(damaged), "image/png")
        self.assertEqual(error.exception.code, "invalid_image")

    def test_file_size_limit_precedes_decode_and_model_calls(self):
        with self.assertRaises(LocalRuntimeError) as error:
            LocalRuntime(self.root).import_document(self.image_body(data_base64="a" * (((MAX_FILE_BYTES + 2) // 3) * 4 + 1)))
        self.assertEqual(error.exception.status, 413)

    def test_hidden_reasoning_and_incomplete_outputs_are_not_imported(self):
        self.assertEqual(_candidate_text("<think>secret scratch</think>\n```latex\n$x$\n```"), "$x$")
        self.assertEqual(_candidate_text("```tex\n$x$\n```"), "$x$")
        for text in ("<think>only reasoning", "<think>reasoning</think>", "", "text\x00"):
            with self.subTest(text=text), self.assertRaises(LocalRuntimeError):
                _candidate_text(text)
        for reason, message in (("length", {"content": "$x"}), ("content_filter", {"content": ""}),
                                ("stop", {"content": "", "refusal": "declined"}), ("stop", {})):
            with self.subTest(reason=reason), FakeModel({"choices": [{"message": message, "finish_reason": reason}]}) as model:
                with self.assertRaises(LocalRuntimeError):
                    LocalRuntime(self.root, base_url=model.base).import_document(self.image_body())
        self.assertFalse((self.root / "imports").exists())

    def test_pdf_requires_header_and_available_renderer(self):
        runtime = LocalRuntime(self.root)
        body = {"name": "test.pdf", "mime_type": "application/pdf", "data_base64": base64.b64encode(b"not pdf").decode()}
        with self.assertRaises(LocalRuntimeError) as error:
            runtime.import_document(body)
        self.assertEqual(error.exception.code, "invalid_pdf")
        body["data_base64"] = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode()
        with patch("local_runtime.shutil.which", return_value=None), self.assertRaises(LocalRuntimeError) as error:
            runtime.import_document(body)
        self.assertEqual(error.exception.code, "pdf_tools_unavailable")

    def test_pdf_selected_pages_are_rendered_and_source_page_numbers_are_preserved(self):
        runtime = LocalRuntime(self.root)
        commands = []

        def run(command, **kwargs):
            commands.append(command)
            self.assertNotIn("shell", kwargs)
            if command[0] == "pdfinfo":
                return SimpleNamespace(returncode=0, stdout="Pages:          9\n")
            Path(command[-1] + ".png").write_bytes(PNG)
            return SimpleNamespace(returncode=0)

        with FakeModel() as model, patch("local_runtime.shutil.which", return_value="/test/tool"), \
                patch("local_runtime.subprocess.run", side_effect=run):
            runtime.update_settings({"base_url": model.base, "model": "MiniCPM-V-4.7-1B"})
            result = runtime.import_document({"name": "my scan.pdf", "mime_type": "application/pdf",
                                               "data_base64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode(),
                                               "page_start": 3, "max_pages": 2})
        self.assertEqual(result["source_pages"], 9)
        self.assertEqual([page["page"] for page in result["pages"]], [3, 4])
        self.assertEqual(result["imported_pages"], 2)
        self.assertTrue(result["has_more_pages"])
        self.assertIn("Source page 3", result["content"])
        self.assertIn("\\clearpage", result["content"])
        self.assertEqual(len(model.requests), 2)
        self.assertEqual([command[command.index("-f") + 1] for command in commands[1:]], ["3", "4"])

    def test_unexpected_route_and_remote_url_are_rejected_before_connect(self):
        for url in ("http://remote.test/v1/models", "http://localhost/v1/models?x=1", "http://localhost/v1/other"):
            with self.subTest(url=url), patch("local_runtime.urllib.request.build_opener", side_effect=AssertionError("network")), \
                    self.assertRaises(LocalRuntimeError):
                local_json_request(url)


if __name__ == "__main__":
    unittest.main()
