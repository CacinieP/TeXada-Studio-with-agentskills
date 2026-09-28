"""Checker boundary and auditable-output tests; no model or compiler required."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import pipeline, state  # noqa: E402
from docforensics.__main__ import write_report  # noqa: E402


def response(status="OK", code=0, **fields):
    return SimpleNamespace(returncode=code, stdout=json.dumps({"status": status, **fields}), stderr="")


class CheckerBoundaryTest(unittest.TestCase):
    def test_formula_protocol_accepts_known_statuses(self):
        for status, code in (("OK", 0), ("RETRY", 0), ("NEEDS_ENV", 2), ("NEEDS_HUMAN", 1)):
            with self.subTest(status=status, code=code), patch.object(pipeline.subprocess, "run",
                                                                      return_value=response(status, code, reason="detail")) as run:
                self.assertEqual(pipeline.run_verify("x"), {"status": status, "reason": "detail"})
                self.assertEqual(run.call_args.kwargs["timeout"], 30)
                self.assertEqual(run.call_args.args[0][-1], "x")
                self.assertNotIn("shell", run.call_args.kwargs)

    def test_formula_wrong_input_type_never_launches_checker(self):
        for value in (None, 42, ["x"], {"latex": "x"}):
            with self.subTest(value=value), patch.object(pipeline.subprocess, "run") as run:
                result = pipeline.run_verify(value)
                self.assertEqual(result["status"], "NEEDS_HUMAN")
                self.assertIn("bad_input", result["reason"])
                run.assert_not_called()

    def test_formula_failure_never_invokes_repair_provider(self):
        failures = [response("OK", code=1), response("RETRY", code=2),
                    response("NEEDS_HUMAN", code=0), response("NEEDS_HUMAN", code=2),
                    response("NEEDS_ENV", code=0), response("NEEDS_ENV", code=1), response("UNKNOWN"),
                    SimpleNamespace(returncode=0, stdout="not JSON", stderr=""),
                    SimpleNamespace(returncode=0, stdout="[]", stderr=""),
                    SimpleNamespace(returncode=0, stdout="", stderr=""),
                    FileNotFoundError("missing checker"), subprocess.TimeoutExpired("checker", 30)]
        node = {"id": "f-1", "data": {"latex": "x"}}
        for failure in failures:
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, \
                    patch.object(pipeline.subprocess, "run", **kwargs):
                provider = Mock()
                result = pipeline.run_verify("x")
                self.assertEqual(result["status"], "NEEDS_ENV")
                self.assertEqual(pipeline.process_formula(directory, "doc", node, provider), "NEEDS_HUMAN")
                provider.repair_formula.assert_not_called()
                terminal = state.load_events(directory)[-1]
                self.assertEqual(terminal["attempts"], 0)
                self.assertTrue(terminal["reason"].startswith("env:"))

    def test_formula_bad_input_status_never_invokes_model(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline.subprocess, "run", return_value=response("NEEDS_HUMAN", code=1, reason="bad_input")):
            provider = Mock()
            status = pipeline.process_formula(directory, "doc", {"id": "f-1", "data": {"latex": "x"}}, provider)
            self.assertEqual(status, "NEEDS_HUMAN")
            provider.repair_formula.assert_not_called()

    def test_real_malformed_jsonl_exit_is_preserved_by_wrapper(self):
        result = subprocess.run([sys.executable, pipeline.VERIFY], input="{malformed\n",
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        record = json.loads(result.stdout)
        self.assertEqual(record["status"], "NEEDS_HUMAN")
        self.assertEqual(record["reason"], "bad_input")
        with patch.object(pipeline.subprocess, "run", return_value=result):
            self.assertEqual(pipeline.run_verify("x"), record)

    def test_formula_checker_failure_after_candidate_stops_retrying(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline.subprocess, "run", side_effect=[response("RETRY"), response("OK", code=1)]):
            provider = Mock()
            provider.repair_formula.return_value = "x"
            result = pipeline.process_formula(directory, "doc", {"id": "f-1", "data": {"latex": "x+"}}, provider)
            self.assertEqual(result, "NEEDS_HUMAN")
            self.assertEqual(provider.repair_formula.call_count, 1)

    def test_audit_accepts_normal_human_exit_code(self):
        for status, code in (("OK", 0), ("RETRY", 0), ("NEEDS_HUMAN", 0), ("NEEDS_HUMAN", 1)):
            with self.subTest(status=status, code=code), patch.object(
                    pipeline.subprocess, "run", return_value=response(status, code, reason="reason")) as run:
                self.assertEqual(pipeline.run_audit({"rows": []}), {"status": status, "reason": "reason"})
                self.assertEqual(run.call_args.kwargs["timeout"], 30)
                self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"rows": []})

    def test_audit_failures_cannot_pass_or_invoke_repair(self):
        failures = [response("OK", code=1), response("RETRY", code=1), response("NEEDS_HUMAN", code=2),
                    response("UNKNOWN"), SimpleNamespace(returncode=0, stdout="null", stderr=""),
                    SimpleNamespace(returncode=0, stdout="not JSON", stderr=""),
                    SimpleNamespace(returncode=0, stdout="", stderr=""),
                    FileNotFoundError("missing checker"), subprocess.TimeoutExpired("checker", 30)]
        for failure in failures:
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, \
                    patch.object(pipeline.subprocess, "run", **kwargs):
                provider = Mock()
                node = {"id": "t-1", "data": {"rows": [["name", "value"], ["A", "1"]]}}
                result = pipeline.run_audit(node["data"])
                self.assertEqual(result["status"], "NEEDS_HUMAN")
                self.assertEqual(result["reason"], "checker_error")
                self.assertEqual(pipeline.process_table(directory, "doc", node, provider), "NEEDS_HUMAN")
                provider.repair_table.assert_not_called()


class ReportEvidenceTest(unittest.TestCase):
    def test_table_candidate_records_and_reports_actual_diff(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        candidate = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4"]]
        node = {"id": "t-1", "data": {"rows": original}}
        provider = pipeline.FixtureProvider()
        provider.repairs = {"t-1": {"rows": candidate}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_audit", side_effect=[{"status": "RETRY"}, {"status": "OK"}]):
            self.assertEqual(pipeline.process_table(directory, "doc", node, provider), "OK")
            terminal = state.load_events(directory)[-1]
            self.assertEqual(terminal["original_rows"], original)
            self.assertEqual(terminal["candidate_rows"], candidate)
            self.assertEqual(node["data"]["rows"], original)
            report = Path(write_report(directory, provider)).read_text()
            self.assertIn('--- original_rows', report)
            self.assertIn('+++ candidate_rows', report)
            self.assertIn('-    "4.5"', report)
            self.assertIn('+    "4"', report)
            self.assertIn("未写回源文件", report)
            self.assertIn("⚠️ 缺失", report)

    def test_legacy_table_events_remain_readable_without_inventing_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            state.append(directory, doc="old-doc", node_id="old-table", skill="doc-table-audit",
                         status="OK", repaired=True, attempts=1, evidence=None)
            state.append(directory, doc="old-doc", node_id="old-formula", skill="doc-formula-verify",
                         status="OK", repaired=True, original="a_", latex="a_1", attempts=1)
            report = Path(write_report(directory, pipeline.FixtureProvider())).read_text()
            self.assertIn("旧记录未保存原文与候选，无法还原差异", report)
            self.assertIn("`a_` → `a_1`", report)
            self.assertNotIn("```diff", report)

    def test_resume_skips_all_eight_original_fixture_nodes(self):
        # Checks the persisted identity contract without needing SymPy or a model.
        root = Path(pipeline.REPO)
        provider = pipeline.FixtureProvider(str(root / "samples/fixture_repairs.json"))
        with tempfile.TemporaryDirectory() as directory:
            for name in ("exam-01", "paper-01", "report-01"):
                layout = json.loads((root / "samples" / name / "layout.json").read_text())
                for node in layout["nodes"]:
                    status = "NEEDS_HUMAN" if node["id"] == "f-003" else "OK"
                    input_hash, context_hash = pipeline.node_identity(node, provider)
                    state.append(directory, doc=layout["doc"], node_id=node["id"], action="TERMINAL",
                                 status=status, input_sha256=input_hash, context_sha256=context_hash)
            with patch.object(pipeline, "run_verify") as verify, patch.object(pipeline, "run_audit") as audit:
                results = {name: pipeline.run(str(root / "samples" / name), directory, provider)[1]
                           for name in ("exam-01", "paper-01", "report-01")}
                verify.assert_not_called()
                audit.assert_not_called()
            self.assertEqual(results, {"exam-01": {"OK": 3, "NEEDS_HUMAN": 0},
                                       "paper-01": {"OK": 2, "NEEDS_HUMAN": 1},
                                       "report-01": {"OK": 2, "NEEDS_HUMAN": 0}})
            self.assertEqual(sum(event.get("action") == "SKIP" for event in state.load_events(directory)), 8)


if __name__ == "__main__":
    unittest.main()
