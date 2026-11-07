"""doc-ocr-extract contract tests with a fake Ollama endpoint; no network."""

import base64
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ocr_extract  # noqa: E402

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def endpoint(payload):
    return FakeResponse(json.dumps(payload).encode())


class ExtractTest(unittest.TestCase):
    def ok_body(self, text):
        return {"message": {"role": "assistant", "content": text}, "done": True, "eval_count": 7}

    def call(self, body=None, error=None, image=PNG_1X1, model="minicpm-ocr:latest", raw_response=None):
        calls = {}

        def fake_urlopen(request, timeout=None):
            calls["payload"] = json.loads(request.data.decode())
            if error is not None:
                raise error
            if raw_response is not None:
                return FakeResponse(raw_response)
            return endpoint(body or self.ok_body("Line one\n\nLine two\n"))

        target = "urllib.request.urlopen"
        with patch(target, side_effect=fake_urlopen):
            status, reason, payload = ocr_extract.extract(image, model=model,
                                                          base="http://127.0.0.1:11434",
                                                          prompt="p")
        return status, reason, payload, calls["payload"]

    def test_ok_lines_and_raw_request_shape(self):
        status, reason, payload, sent = self.call()
        self.assertEqual((status, reason), ("OK", ""))
        self.assertEqual(payload["lines"], ["Line one", "Line two"])
        self.assertEqual(sent["model"], "minicpm-ocr:latest")
        self.assertEqual(sent["messages"][0]["images"], [base64.b64encode(PNG_1X1).decode()])
        self.assertFalse(sent["stream"])

    def test_blank_response_is_needs_human_not_env(self):
        status, reason, payload, _ = self.call(body=self.ok_body("   \n \n"))
        self.assertEqual((status, reason), ("NEEDS_HUMAN", "no_text"))
        self.assertEqual(payload["lines"] if "lines" in payload else [], [])

    def test_non_string_content_is_env_error(self):
        status, reason, _, _ = self.call(body={"message": {"content": None}})
        self.assertEqual((status, reason), ("NEEDS_ENV", "bad_response_shape"))

    def test_http_and_network_failures_are_env_errors(self):
        status, reason, _, _ = self.call(error=urllib.error.HTTPError("u", 500, "boom", None, None))
        self.assertEqual((status, reason), ("NEEDS_ENV", "http_error"))
        status, reason, _, _ = self.call(error=urllib.error.URLError("refused"))
        self.assertEqual((status, reason), ("NEEDS_ENV", "timeout_or_network"))

    def test_bad_json_body_is_env_error(self):
        status, reason, _, _ = self.call(raw_response=b"not-json{")
        self.assertEqual((status, reason), ("NEEDS_ENV", "bad_response_json"))

    def test_excerpt_is_bounded_with_flag(self):
        text = "x" * (ocr_extract.RESPONSE_EXCERPT_LIMIT + 10)
        status, _, payload, _ = self.call(body=self.ok_body(text))
        self.assertEqual(status, "OK")
        self.assertTrue(payload["response_truncated"])
        self.assertEqual(len(payload["raw_response"]), ocr_extract.RESPONSE_EXCERPT_LIMIT)
        self.assertEqual(len(payload["lines"]), 1)


class RecordTest(unittest.TestCase):
    def run_record(self, record):
        with patch("urllib.request.urlopen", return_value=endpoint(
                {"message": {"content": "line"}})):
            code = ocr_extract.run_record(record, model="m", base="http://127.0.0.1:11434",
                                          prompt="p")
        return code

    def test_stdin_style_record_ok(self):
        record = {"id": "img-01", "image": base64.b64encode(PNG_1X1).decode()}
        self.assertEqual(self.run_record(record), 0)

    def test_missing_fields_is_needs_human(self):
        self.assertEqual(self.run_record({"id": "x"}), 1)

    def test_bad_base64_is_env_error(self):
        self.assertEqual(self.run_record({"id": "x", "image": "!!!not-b64!!!"}), 2)

    def test_unreadable_file_is_env_error(self):
        self.assertEqual(self.run_record({"id": "x", "image_path": "/nonexistent/a.png"}), 2)


if __name__ == "__main__":
    unittest.main()
