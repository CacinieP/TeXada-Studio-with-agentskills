import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from managed_models import ManagedModels, ModelFile, ModelProfile, PROFILES, _download


class SourceResponse:
    def __init__(self, payload, status, content_range=None):
        self.payload = payload
        self.status = status
        self.headers = {"Content-Range": content_range}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

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
