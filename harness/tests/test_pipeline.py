"""Checker boundary and auditable-output tests; no model or compiler required."""

import json
import os
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

    def test_formula_checker_failure_after_deterministic_candidate_stops_retrying(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline.subprocess, "run", side_effect=[response("RETRY"), response("OK", code=1)]):
            provider = Mock()
            provider.repair_formula.return_value = "x"
            result = pipeline.process_formula(directory, "doc", {"id": "f-1", "data": {"latex": r"\frac{a}{b"}}, provider)
            self.assertEqual(result, "NEEDS_HUMAN")
            provider.repair_formula.assert_not_called()

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

    def test_model_abstention_stops_retry_immediately_on_unchanged_formula(self):
        original = r"\sin(x"
        provider = Mock()
        provider.repair_formula.side_effect = [original, r"\sin(x)"]
        provider.last_trace = {"model_calls": 1, "model_called": True, "reason": "ok"}
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", return_value={"status": "RETRY", "reason": "parse_error"}):
            status = pipeline.process_formula(directory, "doc", {"id": "f-1", "data": {"latex": original}}, provider)
            events = state.load_events(directory)
        self.assertEqual(status, "NEEDS_HUMAN")
        self.assertEqual(provider.repair_formula.call_count, 1)
        terminal = events[-1]
        self.assertEqual(terminal["attempts"], 1)
        self.assertEqual(terminal["reason"], "model_abstained")
        self.assertTrue(terminal["resumable"])

    def test_cleared_provider_reason_allows_resumable_success_on_second_attempt(self):
        original = r"\sin(x"
        candidate = r"\sin(x)"
        provider = Mock()
        traces = [{"model_calls": 1, "model_called": True, "reason": "bad_candidate_json"},
                  {"model_calls": 1, "model_called": True, "reason": "ok"}]
        replies = [None, candidate]

        def repair(_node):
            provider.last_trace = traces.pop(0)
            return replies.pop(0)

        provider.repair_formula.side_effect = repair
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", side_effect=[{"status": "RETRY", "reason": "err"}, {"status": "OK"}]), \
                patch.object(pipeline, "assess_candidate",
                             return_value={"allowed": True, "reason": "test_scope", "method": "test"}):
            status = pipeline.process_formula(directory, "doc", {"id": "f-1", "data": {"latex": original}}, provider)
            terminal = state.load_events(directory)[-1]
        self.assertEqual(status, "OK")
        self.assertEqual(terminal["attempts"], 2)
        self.assertTrue(terminal["resumable"])
        self.assertNotIn("provider_reason", terminal)

    def test_evidence_resolves_against_sample_path_and_rejects_symlinks_traversal_and_oversized_crops(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            sample = base / "sample"
            crops = sample / "crops"
            crops.mkdir(parents=True)
            valid_crop = crops / "f1.png"
            valid_crop.write_bytes(b"png-bytes")
            outside = base / "outside.png"
            outside.write_bytes(b"secret")
            symlink_crop = crops / "link.png"
            symlink_crop.symlink_to(valid_crop)
            oversized = crops / "huge.png"
            with open(oversized, "wb") as stream:
                stream.seek(24 * 1024 * 1024)
                stream.write(b"x")
            nodes = [
                {"id": "f-valid", "type": "formula", "data": {"latex": r"\frac{a}{b", "crop": "crops/f1.png"}},
                {"id": "f-trav", "type": "formula", "data": {"latex": r"\frac{a}{b", "crop": "../outside.png"}},
                {"id": "f-abs", "type": "formula", "data": {"latex": r"\frac{a}{b", "crop": str(outside)}},
                {"id": "f-link", "type": "formula", "data": {"latex": r"\frac{a}{b", "crop": "crops/link.png"}},
                {"id": "f-huge", "type": "formula", "data": {"latex": r"\frac{a}{b", "crop": "crops/huge.png"}},
            ]
            (sample / "layout.json").write_text(json.dumps({"doc": "crop-doc", "nodes": nodes}))
            run_dir = base / "run"
            other_cwd = base / "elsewhere"
            other_cwd.mkdir()
            prev_cwd = os.getcwd()
            try:
                os.chdir(other_cwd)
                with patch.object(pipeline, "run_verify",
                                  side_effect=[{"status": "RETRY"}, {"status": "OK"}] * len(nodes)):
                    pipeline.run(str(sample), str(run_dir), pipeline.FixtureProvider())
            finally:
                os.chdir(prev_cwd)
            terminals = {e["node_id"]: e for e in state.load_events(str(run_dir)) if e.get("action") == "TERMINAL"}
            self.assertIsNotNone(terminals["f-valid"]["evidence"])
            self.assertTrue((run_dir / terminals["f-valid"]["evidence"]).is_file())
            for bad_id in ("f-trav", "f-abs", "f-link", "f-huge"):
                with self.subTest(bad_id=bad_id):
                    self.assertIsNone(terminals[bad_id]["evidence"])

    def test_extra_closing_brace_and_interior_brace_allow_verified_model_repair(self):
        for original, candidate in ((r"\frac1}{2}", r"\frac{1}{2}"), (r"x^{n+1 + y = 0", r"x^{n+1} + y = 0")):
            provider = Mock()
            provider.repair_formula.return_value = candidate
            provider.last_trace = {"model_calls": 1, "model_called": True, "reason": "ok"}
            with self.subTest(original=original), tempfile.TemporaryDirectory() as directory:
                status = pipeline.process_formula(directory, "doc", {"id": "f-struct", "data": {"latex": original}}, provider)
                events = state.load_events(directory)
            self.assertEqual(status, "OK")
            self.assertEqual(provider.repair_formula.call_count, 1)
            self.assertFalse(any(e.get("action") == "REPAIR_SKIPPED" for e in events))
            self.assertEqual(events[-1]["latex"], candidate)
            self.assertTrue(events[-1]["repaired"])

        provider = Mock()
        with tempfile.TemporaryDirectory() as directory:
            status = pipeline.process_formula(directory, "doc", {"id": "f-unrepairable", "data": {"latex": r"x} + {y"}}, provider)
            events = state.load_events(directory)
        self.assertEqual(status, "NEEDS_HUMAN")
        provider.repair_formula.assert_not_called()
        self.assertTrue(any(e.get("action") == "REPAIR_SKIPPED" for e in events))

    def test_run_verify_and_run_audit_use_utf8_and_windows_create_no_window(self):
        seen = []

        def fake_run(cmd, **kwargs):
            seen.append((Path(cmd[1]).name, kwargs))
            return Mock(returncode=0, stdout='{"id":"x","status":"OK","reason":""}\n', stderr="")

        with patch.object(pipeline.sys, "platform", "win32"), \
                patch.object(pipeline.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.object(pipeline.subprocess, "run", side_effect=fake_run):
            self.assertEqual(pipeline.run_verify("x^2")["status"], "OK")
            self.assertEqual(pipeline.run_audit({"id": "t", "rows": [["项目", "金额"]]})["status"], "OK")
        self.assertEqual([name for name, _ in seen], ["verify.py", "audit_table.py"])
        for name, kwargs in seen:
            with self.subTest(script=name):
                self.assertEqual(kwargs.get("encoding"), "utf-8")
                self.assertEqual(kwargs.get("errors"), "replace")
                self.assertEqual(kwargs.get("creationflags"), 0x08000000)


if __name__ == "__main__":
    unittest.main()
