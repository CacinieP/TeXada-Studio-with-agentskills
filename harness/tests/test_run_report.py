import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from unittest.mock import patch

from docforensics import __main__ as cli, pipeline
from docforensics.__main__ import write_run_report


class RunReportTest(unittest.TestCase):
    def render(self, events, run_id):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run_report(directory, SimpleNamespace(name="test"), events, run_id)
            return Path(path).read_text()

    def terminal(self, run="one", **fields):
        return dict(action="TERMINAL", run_id=run, doc="paper", node_id="f1", status="OK",
                    input_sha256="a", context_sha256="b", **fields)

    def test_duplicate_explicit_document_ids_rejected_before_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = []
            for name in ("first", "second"):
                sample = root / name
                sample.mkdir()
                (sample / "layout.json").write_text(json.dumps({"doc": "same-document", "nodes": []}))
                samples.append(str(sample))
            error = io.StringIO()
            with patch.object(pipeline, "run") as run, contextlib.redirect_stderr(error):
                result = cli.main(["run", *samples, "--state", str(root / "state")])
            self.assertEqual(result, 2)
            run.assert_not_called()
            self.assertIn("duplicate document identity", error.getvalue())
            self.assertFalse((root / "state/state.jsonl").exists())

    def test_fallback_document_id_collides_with_explicit_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "same-name", root / "other"
            first.mkdir()
            second.mkdir()
            (first / "layout.json").write_text(json.dumps({"doc": "", "nodes": []}))
            (second / "layout.json").write_text(json.dumps({"doc": "same-name", "nodes": []}))
            with patch.object(pipeline, "run") as run, contextlib.redirect_stderr(io.StringIO()):
                result = cli.main(["run", str(first) + "/", str(second), "--state", str(root / "state")])
            self.assertEqual(result, 2)
            run.assert_not_called()
            self.assertFalse((root / "state/state.jsonl").exists())

    def test_distinct_documents_preserve_both_run_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = []
            for name in ("first", "second"):
                sample = root / name
                sample.mkdir()
                (sample / "layout.json").write_text(json.dumps({"doc": name, "nodes": [
                    {"id": "f1", "type": "formula", "data": {"latex": "x"}}]}))
                samples.append(str(sample))
            with patch.object(pipeline, "run_verify", return_value={"status": "OK"}), contextlib.redirect_stdout(io.StringIO()):
                result = cli.main(["run", *samples, "--state", str(root / "state")])
            self.assertEqual(result, 0)
            report = (root / "state/report.md").read_text()
            self.assertIn("## first", report)
            self.assertIn("## second", report)
            self.assertEqual(report.count("OK 1"), 2)

    def test_current_run_and_flat_request_fields(self):
        report = self.render([
            self.terminal("old", repaired=True, original="old+", latex="old"),
            {"action": "PROVIDER_RESULT", "run_id": "old", "model_calls": 90, "model_calls_known": True},
            {"action": "PROVIDER_RESULT", "run_id": "one", "doc": "paper", "node_id": "f1",
             "model_calls": 2, "model_calls_known": True}, self.terminal()], "one")
        self.assertIn("请求尝试：2", report)
        self.assertIn("OK 1", report)
        self.assertNotIn("old+", report)

    def test_reuse_displays_prior_candidate_without_counting_old_requests(self):
        report = self.render([self.terminal(repaired=True, original="x+", latex="x+1"),
            {"action": "SKIP", "run_id": "two", "doc": "paper", "node_id": "f1", "status": "OK",
             "input_sha256": "a", "context_sha256": "b", "reused_run_id": "one"}], "two")
        self.assertIn("请求尝试：0", report)
        self.assertIn("复用 1", report)
        self.assertIn("x+1", report)

    def test_unmatched_start_is_unknown_and_unfinished_history_remains_visible(self):
        report = self.render([
            {"action": "RUN_START", "run_id": "one"},
            {"action": "CHECK", "run_id": "one", "doc": "paper", "node_id": "f1",
             "original": "broken+", "checker_status": "RETRY"},
            {"action": "PROVIDER_START", "run_id": "one", "doc": "paper", "node_id": "f1",
             "attempt": 1, "input_sha256": "a", "context_sha256": "b"}], "one")
        self.assertIn("请求尝试：至少 0", report)
        self.assertIn("已知下界", report)
        self.assertIn("1 条请求开始事件尚无对应结果", report)
        self.assertIn("本次运行没有结束记录", report)
        self.assertIn("OK 0 · 待人工 0 · 复用 0 · 未完成 1", report)
        self.assertIn("### 节点 f1", report)
        self.assertIn("broken+", report)
        self.assertIn("PROVIDER_START", report)
        self.assertNotIn("检查终态：NEEDS_HUMAN", report)

    def test_completed_request_is_known_even_if_node_has_no_terminal(self):
        common = dict(run_id="one", doc="paper", node_id="f1", attempt=1,
                      input_sha256="a", context_sha256="b")
        report = self.render([
            dict(common, action="PROVIDER_START"),
            dict(common, action="PROVIDER_RESULT", model_calls=1, model_calls_known=True,
                 candidate="x")], "one")
        self.assertIn("请求尝试：1", report)
        self.assertNotIn("已知下界", report)
        self.assertIn("未完成 1", report)
        self.assertIn('"candidate": "x"', report)
        self.assertNotIn("检查终态：OK", report)

    def test_attempt_and_input_binding_prevent_wrong_start_pairing(self):
        common = dict(run_id="one", doc="paper", node_id="f1", attempt=1,
                      input_sha256="a", context_sha256="b")
        for changed in ({"attempt": 2}, {"input_sha256": "new"}, {"context_sha256": "new"}):
            with self.subTest(changed=changed):
                result = dict(common, action="PROVIDER_RESULT", model_calls=1, model_calls_known=True)
                result.update(changed)
                report = self.render([dict(common, action="PROVIDER_START"), result], "one")
                self.assertIn("请求尝试：至少 1", report)
                self.assertIn("1 条请求开始事件尚无对应结果", report)

    def test_unknown_call_count_and_transient_cause(self):
        terminal = self.terminal(provider_reason="timeout", resumable=False)
        terminal["status"] = "NEEDS_HUMAN"
        report = self.render([terminal, {"action": "PROVIDER_RESULT", "run_id": "one",
            "model_calls": 0, "model_calls_known": False}], "one")
        self.assertIn("已知下界", report)
        self.assertIn("timeout", report)
        self.assertIn("同一状态目录重跑", report)


if __name__ == "__main__":
    unittest.main()
