"""OCR API boundaries using the shared transport; no model required."""
import hashlib
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_static_assets import studio


class OcrTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(studio.app)
        self.addCleanup(self.client.close)
        self.auth = {"token": studio.TOKEN}
        self.png = b"\x89PNG\r\n\x1a\nsynthetic-test-double"

    def test_auth_type_signature_and_size_do_not_call_model(self):
        with patch.object(studio.OCR, "extract") as extract:
            self.assertEqual(self.client.post("/api/studio/ocr", content=self.png).status_code, 401)
            for content, headers, code in [
                (self.png, {"Content-Type": "image/jpeg"}, 415),
                (b"not png", {"Content-Type": "image/png"}, 400),
                (self.png, {"Content-Type": "image/png"}, 413),
            ]:
                with patch.object(studio, "OCR_IMAGE_LIMIT", 8 if code == 413 else 1024):
                    response = self.client.post("/api/studio/ocr", params=self.auth,
                                                content=content, headers=headers)
                self.assertEqual(response.status_code, code)
            extract.assert_not_called()

    def test_candidates_and_failures_remain_unadopted(self):
        for status, reason, payload in [
            ("OK", "", {"lines": ["x_1", "<script>alert(1)</script>"], "model": "fake"}),
            ("NEEDS_ENV", "timeout_or_network", {}),
            ("NEEDS_HUMAN", "no_text", {}),
        ]:
            with patch.object(studio.OCR, "extract", return_value=(status, reason, payload)) as extract:
                response = self.client.post("/api/studio/ocr", params=self.auth,
                    content=self.png, headers={"Content-Type": "image/png"})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["status"], status)
            self.assertEqual(result["review_status"], "pending")
            self.assertEqual(result["source_sha256"], hashlib.sha256(self.png).hexdigest())
            self.assertEqual(extract.call_args.kwargs["transport"], studio.OCR.DEFAULT_TRANSPORT)
            self.assertEqual(extract.call_args.args[0], self.png)
