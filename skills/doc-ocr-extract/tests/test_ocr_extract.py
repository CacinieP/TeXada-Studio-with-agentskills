"""doc-ocr-extract contract tests with a fake endpoint; no network.

Both transports must honor the same candidate contract: openai
(/v1/chat/completions + image_url data URL, default, unified with the repair
line) and ollama (native /api/chat + images fallback).
"""

import base64
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ocr_extract  # noqa: E402

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
BASE = "http://127.0.0.1:11434"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def openai_body(text, tokens=9):
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": tokens, "total_tokens": 19}}


def ollama_body(text):
    return {"message": {"role": "assistant", "content": text}, "done": True, "eval_count": 7}


def endpoint(payload):
    return FakeResponse(json.dumps(payload).encode())


class ExtractTest(unittest.TestCase):
    def call(self, body=None, transport="openai", error=None,
             raw_response=None, text="Line one\n\nLine two\n"):
        calls = {"url": None}

        def fake_urlopen(request, timeout=None):
            calls["url"] = request.full_url
            calls["payload"] = json.loads(request.data.decode())
            if error is not None:
                raise error
            if raw_response is not None:
                return FakeResponse(raw_response)
            return endpoint(body if body is not None else
                            (openai_body(text) if transport == "openai" else ollama_body(text)))

        target = "urllib.request.urlopen"
        with patch(target, side_effect=fake_urlopen):
            status, reason, payload = ocr_extract.extract(
                PNG_1X1, model="minicpm-ocr:latest", base=BASE, prompt="p",
                transport=transport)
        return status, reason, payload, calls

    def test_openai_transport_request_and_response_shape(self):
        status, reason, payload, calls = self.call()
        self.assertEqual((status, reason), ("OK", ""))
        self.assertEqual(calls["url"], BASE + "/v1/chat/completions")
        content = calls["payload"]["messages"][0]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "p"})
        self.assertEqual(content[1]["image_url"]["url"],
                         "data:image/png;base64," + base64.b64encode(PNG_1X1).decode())
        self.assertEqual(payload["lines"], ["Line one", "Line two"])
        self.assertEqual(payload["eval_count"], 9)  # openai transport: completion_tokens
        self.assertEqual(calls["payload"]["model"], "minicpm-ocr:latest")
        self.assertFalse(calls["payload"]["stream"])

    def test_ollama_transport_request_and_response_shape(self):
        status, reason, payload, calls = self.call(transport="ollama")
        self.assertEqual((status, reason), ("OK", ""))
        self.assertEqual(calls["url"], BASE + "/api/chat")
        message = calls["payload"]["messages"][0]
        self.assertEqual(message["content"], "p")
        self.assertEqual(message["images"], [base64.b64encode(PNG_1X1).decode()])
        self.assertEqual(payload["eval_count"], 7)  # ollama transport: eval_count

    def test_unknown_transport_is_env_error_without_request(self):
        status, reason, _, calls = self.call(transport="bad")
        self.assertEqual((status, reason), ("NEEDS_ENV", "bad_transport"))
        self.assertIsNone(calls["url"])

    def test_blank_response_is_needs_human_not_env(self):
        status, reason, payload, _ = self.call(text="   \n \n")
        self.assertEqual((status, reason), ("NEEDS_HUMAN", "no_text"))
        self.assertNotIn("lines", payload)

    def test_non_string_content_is_env_error(self):
        status, reason, _, _ = self.call(body={"choices": [{"message": {"content": None}}]})
        self.assertEqual((status, reason), ("NEEDS_ENV", "bad_response_shape"))

    def test_missing_choices_is_env_error(self):
        status, reason, _, _ = self.call(body={"message": {"content": "x"}})
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
        status, _, payload, _ = self.call(text=text)
        self.assertEqual(status, "OK")
        self.assertTrue(payload["response_truncated"])
        self.assertEqual(len(payload["raw_response"]), ocr_extract.RESPONSE_EXCERPT_LIMIT)
        self.assertEqual(len(payload["lines"]), 1)


class RecordTest(unittest.TestCase):
    def run_record(self, record, transport="openai"):
        with patch("urllib.request.urlopen", return_value=endpoint(openai_body("line"))):
            return ocr_extract.run_record(record, model="m", base=BASE, prompt="p",
                                          transport=transport)

    def test_default_transport_record_ok(self):
        record = {"id": "img-01", "image": base64.b64encode(PNG_1X1).decode()}
        self.assertEqual(self.run_record(record), 0)

    def test_missing_fields_is_needs_human(self):
        self.assertEqual(self.run_record({"id": "x"}), 1)

    def test_bad_base64_is_env_error(self):
        self.assertEqual(self.run_record({"id": "x", "image": "!!!not-b64!!!"}), 2)

    def test_unreadable_file_is_env_error(self):
        self.assertEqual(self.run_record({"id": "x", "image_path": "/nonexistent/a.png"}), 2)

    def test_bad_transport_is_env_error(self):
        encoded = base64.b64encode(PNG_1X1).decode()
        self.assertEqual(self.run_record({"id": "x", "image": encoded},
                                         transport="carrier-pigeon"), 2)


if __name__ == "__main__":
    unittest.main()
