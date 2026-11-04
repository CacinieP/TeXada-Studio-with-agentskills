"""Verify source packages with tiny independent Git repositories."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().with_name("package.sh")


class SourcePackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="texada package test ")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "checkout with spaces"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic Package Test")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("config", "core.autocrlf", "false")
        for name in ("LICENSE", "README.md", "README.en.md", "THIRD_PARTY_NOTICES.md",
                     "scripts/run-local-studio.py", "webui/app.py", "webui/requirements.txt",
                     "harness/requirements.txt", ".github/workflows/test.yml", "state/.gitkeep"):
            self.write(name, "synthetic source: " + name + "\n")
        shutil.copyfile(SCRIPT, self.repo / "scripts/package.sh")
        self.write(".gitattributes", ".github/ export-ignore\nstate/ export-ignore\n")
        self.write(".gitignore", "dist/\n.venv/\nmodels/\n.env\n")
        self.write(".env.example", "# No credential values; configuration example only.\n")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              text=True, capture_output=True).stdout.strip()

    def write(self, path, content):
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Synthetic source snapshot")

    def package(self):
        return subprocess.run(["bash", str(self.repo / "scripts/package.sh")],
                              cwd=self.temporary.name,
                              env={**os.environ, "TEXADA_PACKAGE_PYTHON": sys.executable},
                              capture_output=True, text=True)

    def output_files(self):
        return sorted((self.repo / "dist").glob("*"))

    def test_clean_head_package_has_verified_manifest_and_no_untracked_runtime_data(self):
        for name in ("untracked.tex", ".env", "session.json", "models/private.gguf",
                     ".venv/local-tool", "state/upload.tex", "work/evaluation.json"):
            self.write(name, "UNTRACKED_PRIVATE_SYNTHETIC_SENTINEL")
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        revision = self.git("rev-parse", "--short=12", "HEAD")
        stem = "TeXada-Studio-with-agentskills-" + revision
        archive = self.repo / "dist" / (stem + ".zip")
        manifest_path = archive.with_suffix(".manifest.json")
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(manifest["tree"], self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(manifest["archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            self.assertTrue(all(name.startswith(stem + "/") for name in names))
            self.assertEqual(package.comment.decode(), manifest["commit"])
            self.assertIsNone(package.testzip())
            self.assertIn(stem + "/.env.example", names)
            self.assertNotIn(stem + "/state/", names)
            self.assertNotIn(stem + "/.github/", names)
            self.assertNotIn(stem + "/untracked.tex", names)
            self.assertEqual(manifest["file_count"], sum(not entry.is_dir() for entry in package.infolist()))
            for item in manifest["files"]:
                payload = package.read(stem + "/" + item["path"])
                self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(item["bytes"], len(payload))
                self.assertNotIn(b"UNTRACKED_PRIVATE_SYNTHETIC_SENTINEL", payload)
        for entry in archive.with_suffix(".SHA256SUMS").read_text().splitlines():
            checksum, filename = entry.split("  ", 1)
            self.assertEqual(checksum, hashlib.sha256((archive.parent / filename).read_bytes()).hexdigest())
        self.assertEqual(len(self.output_files()), 3)

    def test_tracked_worktree_and_index_changes_are_rejected_without_output(self):
        self.write("README.md", "dirty source")
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("提交", result.stderr)
        self.assertEqual(self.output_files(), [])
        self.git("add", "README.md")
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output_files(), [])

    def test_accidentally_committed_runtime_or_private_paths_fail_validation(self):
        for name in ("models/private.gguf", ".env", "session.json", "credentials.json",
                     "nested/__pycache__/module.pyc"):
            with self.subTest(path=name):
                self.write(name, "SYNTHETIC_COMMITTED_PRIVATE_SENTINEL")
                self.git("add", "-f", name)
                self.git("commit", "-q", "-m", "Synthetic packaging rejection case")
                result = self.package()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("验证失败", result.stderr)
                self.assertEqual(self.output_files(), [])
                self.git("rm", "--", name)
                self.git("commit", "-q", "-m", "Remove synthetic rejected path")

    def test_native_tool_binary_without_an_extension_is_not_a_source_package_member(self):
        pe_header = bytearray(128)
        pe_header[:2] = b"MZ"
        pe_header[60:64] = (64).to_bytes(4, "little")
        pe_header[64:68] = b"PE\0\0"
        for header in (b"\xcf\xfa\xed\xfeSYNTHETIC_MACHO", b"\x7fELFSYNTHETIC_ELF", bytes(pe_header)):
            with self.subTest(header=header[:4]):
                self.write("tools/tectonic", "placeholder")
                (self.repo / "tools/tectonic").write_bytes(header)
                self.commit()
                result = self.package()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("native runtime binary", result.stderr)
                self.assertEqual(self.output_files(), [])

    def test_mz_at_start_of_source_text_is_not_treated_as_a_native_program(self):
        self.write("examples/format-notes.txt", "MZ is the name of an executable header signature, not this text.\n")
        self.commit()
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_required_source_file_cannot_produce_a_successful_package(self):
        self.git("rm", "--", "LICENSE")
        self.git("commit", "-q", "-m", "Synthetic incomplete source")
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LICENSE", result.stderr)
        self.assertEqual(self.output_files(), [])

    def test_package_never_follows_committed_symbolic_links(self):
        (self.repo / "linked.tex").symlink_to("../../outside.tex")
        self.commit()
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symbolic links", result.stderr)
        self.assertEqual(self.output_files(), [])

    def test_same_commit_rebuild_has_identical_bytes_and_checksums(self):
        first = self.package()
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {path.name: path.read_bytes() for path in self.output_files()}
        second = self.package()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output_files()})


if __name__ == "__main__":
    unittest.main()
