"""Local HTTP checks: python -m unittest discover -s webui -p 'test_*.py'."""

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
spec = importlib.util.spec_from_file_location("studio_test_app", ROOT / "webui" / "app.py")
studio = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, {"DEMO_TOKEN": "test-only-asset-token"}):
    spec.loader.exec_module(studio)
ASSETS = ROOT / "webui" / "static" / "monaco" / "0.52.2"
LOADER = studio.MONACO_PREFIX + "/min/vs/loader.js"


class MonacoAssetsTest(unittest.TestCase):
    def setUp(self):
        self.token = patch.object(studio, "TOKEN", "test-only-asset-token")
        self.token.start()
        self.addCleanup(self.token.stop)
        self.client = TestClient(studio.app)
        self.addCleanup(self.client.close)

    def authorize(self):
        response = self.client.get("/studio", params={"token": studio.TOKEN})
        self.assertEqual(response.status_code, 200)
        return response

    def test_unauthorized_page_and_assets(self):
        self.assertEqual(self.client.get("/studio").status_code, 401)
        response = self.client.get(LOADER)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(studio.MONACO_COOKIE, self.client.cookies)

    def test_scoped_cookie_and_api_boundary(self):
        response = self.authorize()
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("Path=" + studio.MONACO_PREFIX + "/", cookie)
        self.assertNotIn("Secure", cookie)  # Current demo origin uses HTTP.
        self.assertNotIn(studio.TOKEN, cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/api/studio/files").status_code, 401)

    def test_https_cookie_is_secure(self):
        with TestClient(studio.app, base_url="https://testserver") as client:
            response = client.get("/studio", params={"token": studio.TOKEN})
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertEqual(client.get(LOADER).status_code, 200)

    def test_all_vendored_assets_match_manifest_over_http(self):
        self.authorize()
        for entry in (ASSETS / "SHA256SUMS").read_text().splitlines():
            digest, name = entry.split("  ", 1)
            with self.subTest(asset=name):
                response = self.client.get(studio.MONACO_PREFIX + "/" + name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(hashlib.sha256(response.content).hexdigest(), digest)
                self.assertEqual(response.headers["cache-control"], "private, max-age=3600")
                self.assertEqual(response.headers["vary"], "Cookie")

    def test_expired_tampered_and_malformed_cookies(self):
        expires = int(time.time()) - 1
        expired = f"{expires}.{studio._monaco_signature(expires)}"
        future = int(time.time()) + studio.MONACO_SESSION_TTL + 100
        invalid = [expired, "garbage", "1." + "a" * 64,
                   f"{future}.{studio._monaco_signature(future)}"]
        for value in invalid:
            with self.subTest(cookie=value[:12]):
                response = self.client.get(LOADER, headers={"Cookie": f"{studio.MONACO_COOKIE}={value}"})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertFalse(studio._valid_monaco_cookie("1." + "非" * 64))

    def test_path_traversal_cannot_read_application_source(self):
        self.authorize()
        for suffix in ("/%2e%2e%2f%2e%2e%2f%2e%2e%2fapp.py", "/missing.js"):
            self.assertEqual(self.client.get(studio.MONACO_PREFIX + suffix).status_code, 404)

    def test_conditional_cache_still_requires_auth(self):
        self.authorize()
        response = self.client.get(LOADER)
        etag = response.headers["etag"]
        self.assertEqual(self.client.get(LOADER, headers={"If-None-Match": etag}).status_code, 304)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(LOADER, headers={"If-None-Match": etag}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
