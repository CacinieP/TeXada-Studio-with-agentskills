"""Unit tests for scripts/run_table_repair_pilot.py --cases path handling."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_table_repair_pilot as pilot  # noqa: E402


class _FakeProvider:
    name = "openai-compatible"

    def __init__(self, **_kwargs):
        self.last_trace = {"model_called": True, "model_calls": 1, "reason": "ok"}

    def fingerprint(self):
        return {"schema_version": 1, "provider": self.name}

    def repair_table(self, node, **_kwargs):
        self.last_trace = {"model_called": True, "model_calls": 1, "reason": "ok"}
        cid = node["id"]
        if cid == "TR01":
            return [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.0"]]
        if cid == "TR02":
            return [["item", "amount"], ["A", "1.5"], ["B", "2.5"], ["total", "4.0"]]
        if cid == "TR03":
            return [["月份", "收入", "支出"], ["1月", "100", "80"], ["2月", "120", "90"], ["合计", "220", "170"]]
        return [["项目", "金额"], ["A", "1.5"], ["B", "3.0"], ["合计", "4.5"]]


class TableRepairPilotTests(unittest.TestCase):
    def test_relative_cases_path_succeeds_and_records_repo_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "out-rel"
            old_cwd = Path.cwd()
            try:
                os.chdir(pilot.REPO)
                with patch.object(pilot.vlm, "OpenAICompatibleProvider", _FakeProvider), \
                        patch.object(pilot, "_ollama_show", return_value={"show_exit": 0}), \
                        contextlib.redirect_stdout(io.StringIO()):
                    rc = pilot.main([
                        "--cases", "samples/research/table_repair_cases.json",
                        "--model", "test-model",
                        "--outdir", str(outdir),
                    ])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(rc, 0)
            manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
            report = (outdir / "report.md").read_text(encoding="utf-8")
            self.assertEqual(manifest["cases_path"], "samples/research/table_repair_cases.json")
            self.assertIsNotNone(manifest["cases_sha256"])
            self.assertIn("- cases: `samples/research/table_repair_cases.json`", report)

    def test_external_cases_path_succeeds_without_leaking_host_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            external_cases = tmp_path / "custom_cases.json"
            external_cases.write_text(
                (pilot.REPO / "samples/research/table_repair_cases.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            outdir = tmp_path / "out-ext"
            with patch.object(pilot.vlm, "OpenAICompatibleProvider", _FakeProvider), \
                    patch.object(pilot, "_ollama_show", return_value={"show_exit": 0}), \
                    contextlib.redirect_stdout(io.StringIO()):
                rc = pilot.main([
                    "--cases", str(external_cases),
                    "--model", "test-model",
                    "--outdir", str(outdir),
                ])
            self.assertEqual(rc, 0)
            manifest_text = (outdir / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            report = (outdir / "report.md").read_text(encoding="utf-8")
            self.assertEqual(manifest["cases_path"], "custom_cases.json")
            self.assertIsNotNone(manifest["cases_sha256"])
            self.assertIn("- cases: `custom_cases.json`", report)
            self.assertNotIn(str(external_cases.parent), manifest_text)
            self.assertNotIn(str(external_cases.resolve().parent), manifest_text)
            self.assertNotIn(str(external_cases.parent), report)
            self.assertNotIn(str(external_cases.resolve().parent), report)


if __name__ == "__main__":
    unittest.main()
