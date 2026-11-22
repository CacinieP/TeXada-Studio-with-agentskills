import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compile_tex as compiler


class CompileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "-source with spaces.tex"
        self.root.write_text("\\documentclass{article}\n", encoding="utf-8")
        self.outdir = self.base / "build"

    def tearDown(self):
        self.temporary.cleanup()

    def fake_compiler(self, body):
        if os.name == "nt":
            py_script = self.base / "fake-tectonic.py"
            py_script.write_text("import sys\nfrom pathlib import Path\n" + body, encoding="utf-8")
            cmd_path = self.base / "fake-tectonic.cmd"
            cmd_path.write_text(f'@"{sys.executable}" "{py_script}" %*\r\n', encoding="utf-8")
            return patch.object(compiler.shutil, "which", return_value=str(cmd_path))
        executable = self.base / "fake-tectonic"
        executable.write_text("#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n" + body, encoding="utf-8")
        executable.chmod(0o755)
        return patch.object(compiler.shutil, "which", return_value=str(executable))

    def test_real_subprocess_exit_code_is_retained(self):
        with self.fake_compiler("print('LaTeX error: missing figure')\nsys.exit(7)\n"):
            result = compiler.compile_document(self.root, "tectonic", self.outdir)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["compiler_exit_code"], 7)
        self.assertIn("missing figure", (self.outdir / "console.log").read_text())

    def test_zero_exit_without_pdf_fails(self):
        with self.fake_compiler("print('no PDF generated')\n"):
            result = compiler.compile_document(self.root, "tectonic", self.outdir)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["compiler_exit_code"], 0)
        self.assertIsNone(result["pdf"])

    def test_missing_tool_is_not_run(self):
        with patch.object(compiler.shutil, "which", return_value=None):
            result = compiler.compile_document(self.root, "tectonic", self.outdir)
        self.assertEqual(result["status"], "not_run")
        self.assertIsNone(result["compiler_exit_code"])
        self.assertFalse(self.outdir.exists())

    def test_existing_pdf_cannot_count_as_success(self):
        self.outdir.mkdir()
        (self.outdir / "-source with spaces.pdf").write_bytes(b"%PDF-old")
        result = compiler.compile_document(self.root, "tectonic", self.outdir)
        self.assertEqual(result["status"], "not_run")
        self.assertEqual((self.outdir / "-source with spaces.pdf").read_bytes(), b"%PDF-old")

    def test_real_subprocess_timeout_is_retained(self):
        # The interpreter need not finish starting before the deadline. Check the
        # real timeout path without assuming that the child has produced output.
        with self.fake_compiler("import time\nwhile True: time.sleep(60)\n"):
            result = compiler.compile_document(self.root, "tectonic", self.outdir, timeout=1)
        self.assertEqual(result["status"], "timeout")
        self.assertIsNotNone(result["compiler_exit_code"])
        self.assertNotEqual(result["compiler_exit_code"], 0)
        self.assertIsNone(result["pdf"])
        self.assertTrue((self.outdir / "console.log").is_file())
        self.assertEqual(json.loads((self.outdir / "build-result.json").read_text()), result)

    def test_timeout_preserves_available_console_output(self):
        # Verify the output handoff independently of OS child-startup scheduling.
        # Include non-UTF-8 bytes: the saved console must remain byte-for-byte intact.
        console = b"starting\nOverfull \\hbox (1.2pt too wide)\npartial output: \xff"
        with patch.object(compiler.shutil, "which", return_value="/test/tectonic"), \
                patch.object(compiler, "run_process", return_value=(-9, console, True, 1.0)):
            result = compiler.compile_document(self.root, "tectonic", self.outdir, timeout=1)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["compiler_exit_code"], -9)
        self.assertEqual((self.outdir / "console.log").read_bytes(), console)
        self.assertEqual(Path(result["diagnostics_source"]), (self.outdir / "console.log").resolve())
        self.assertEqual(len(result["diagnostics"]["overfull"]), 1)
        self.assertEqual(json.loads((self.outdir / "build-result.json").read_text()), result)

    def test_success_keeps_final_log_warnings_and_safe_filename(self):
        body = (
            "out = Path(sys.argv[sys.argv.index('--outdir') + 1])\n"
            "assert sys.argv[-1].startswith('./-source with spaces')\n"
            "stem = Path(sys.argv[-1]).stem\n"
            "(out / (stem + '.pdf')).write_bytes(b'%PDF-test')\n"
            "(out / (stem + '.log')).write_text('Overfull \\\\hbox (1.2pt too wide)\\nLaTeX Warning: Reference `missing` on page 1 undefined.\\n')\n"
            "print('intermediate pass warning: something else')\n"
        )
        with self.fake_compiler(body):
            result = compiler.compile_document(self.root, "tectonic", self.outdir)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["diagnostics"]["overfull"]), 1)
        self.assertEqual(len(result["diagnostics"]["undefined_references_or_citations"]), 1)
        self.assertEqual(json.loads((self.outdir / "build-result.json").read_text()), result)

    def test_non_tectonic_offline_does_not_pretend_supported(self):
        result = compiler.compile_document(self.root, "xelatex", self.outdir, offline=True)
        self.assertEqual(result["status"], "not_run")

    def test_windows_timeout_kills_process_tree_before_communicate(self):
        fake_proc = MagicMock()
        fake_proc.pid = 8765
        fake_proc.returncode = 1
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["fake.cmd"], timeout=1),
            (b"partial", b""),
        ]
        with patch.object(compiler.os, "name", "nt"), \
                patch.object(compiler.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.object(compiler.subprocess, "Popen", return_value=fake_proc), \
                patch.object(compiler.subprocess, "run") as run_mock:
            code, output, timed_out, _ = compiler.run_process(["fake.cmd"], self.base, timeout=1)

        self.assertTrue(timed_out)
        self.assertEqual(code, 1)
        self.assertEqual(output, b"partial")
        run_mock.assert_called_once_with(
            ["taskkill", "/F", "/T", "/PID", "8765"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        fake_proc.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
