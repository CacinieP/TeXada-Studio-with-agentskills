"""Windows frozen entry stdio UTF-8 configuration tests (Issue #84)."""
from __future__ import annotations

import os
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import windows_entry  # noqa: E402


class WindowsEntryStdinUtf8Tests(unittest.TestCase):
    def test_prepare_stdio_reconfigures_or_replaces_stdin_utf8(self):
        saved_stdin, saved_stdout, saved_stderr = sys.stdin, sys.stdout, sys.stderr
        saved_env = dict(os.environ)
        try:
            fake_in = unittest.mock.MagicMock()
            fake_out = unittest.mock.MagicMock()
            fake_err = unittest.mock.MagicMock()
            sys.stdin, sys.stdout, sys.stderr = fake_in, fake_out, fake_err
            windows_entry._prepare_stdio_and_utf8()
            fake_in.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
            fake_out.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
            fake_err.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")

            sys.stdin = None
            sys.stdout = None
            sys.stderr = None
            windows_entry._prepare_stdio_and_utf8()
            self.assertIsNotNone(sys.stdin)
            self.assertIsNotNone(sys.stdout)
            self.assertIsNotNone(sys.stderr)
        finally:
            for stream, orig in ((sys.stdin, saved_stdin), (sys.stdout, saved_stdout), (sys.stderr, saved_stderr)):
                if stream is not None and stream is not orig and hasattr(stream, "close") and not isinstance(stream, unittest.mock.MagicMock):
                    try:
                        stream.close()
                    except Exception:
                        pass
            sys.stdin, sys.stdout, sys.stderr = saved_stdin, saved_stdout, saved_stderr
            os.environ.clear()
            os.environ.update(saved_env)


if __name__ == "__main__":
    unittest.main()
