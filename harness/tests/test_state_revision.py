"""Per-node revision binding (#28-A): evidence names the formula version it describes.

No model or compiler required; legacy journals without the field stay readable.
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import pipeline, state  # noqa: E402
from docforensics.vlm import FixtureProvider  # noqa: E402


def response(status="OK", code=0, **fields):
    from types import SimpleNamespace
    return SimpleNamespace(returncode=code, stdout=json.dumps({"status": status, **fields}), stderr="")


def layout(path, doc, latex):
    (Path(path) / "layout.json").write_text(
        json.dumps({"doc": doc, "nodes": [{"id": "f-1", "type": "formula", "data": {"latex": latex}}]}),
        encoding="utf-8")


class NodeRevisionTest(unittest.TestCase):
    def test_first_version_is_zero_and_each_new_hash_takes_the_next_number(self):
        events = [{"doc": "d", "node_id": "n", "input_sha256": "aaa"}]
        self.assertEqual(state.node_revision(events, "d", "n", "aaa"), 0)
        events.append({"doc": "d", "node_id": "n", "input_sha256": "bbb"})
        self.assertEqual(state.node_revision(events, "d", "n", "bbb"), 1)
        self.assertEqual(state.node_revision(events, "d", "n", "ccc"), 2)

    def test_reverting_text_reidentifies_the_earlier_revision(self):
        events = [{"doc": "d", "node_id": "n", "input_sha256": "aaa"},
                  {"doc": "d", "node_id": "n", "input_sha256": "bbb"}]
        self.assertEqual(state.node_revision(events, "d", "n", "aaa"), 0)

    def test_other_nodes_and_legacy_events_do_not_contribute(self):
        events = [{"doc": "other", "node_id": "n", "input_sha256": "zzz"},
                  {"doc": "d", "node_id": "other", "input_sha256": "zzz"},
                  {"doc": "d", "node_id": "n"},
                  {"doc": "d", "node_id": "n", "input_sha256": None},
                  "corrupted line"]
        self.assertEqual(state.node_revision(events, "d", "n", "aaa"), 0)

    def test_unhashed_input_has_no_revision(self):
        self.assertIsNone(state.node_revision([], "d", "n", None))
        self.assertIsNone(state.node_revision([], "d", "n", ""))


class PipelineRevisionBindingTest(unittest.TestCase):
    def test_node_events_carry_the_revision(self):
        with tempfile.TemporaryDirectory() as run_dir, patch.object(
                pipeline.subprocess, "run", return_value=response("OK", code=0)) as run:
            status = pipeline.process_formula(run_dir, "doc",
                                              {"id": "f-1", "data": {"latex": "x+1"}}, Mock())
            self.assertEqual(status, "OK")
            run.assert_called_once()
            events = state.load_events(run_dir)
            self.assertGreaterEqual(len(events), 2)
            self.assertEqual({event.get("action") for event in events} >= {"CHECK", "TERMINAL"}, True)
            self.assertTrue(all(event["revision"] == 0 for event in events if event.get("action") != "PARSE"))

    def test_text_change_increments_revision_in_the_same_run_dir(self):
        with tempfile.TemporaryDirectory() as run_dir, patch.object(
                pipeline.subprocess, "run", return_value=response("OK", code=0)):
            for latex, expected in (("x+1", 0), ("x+2", 1)):
                with tempfile.TemporaryDirectory() as sample:
                    layout(sample, "doc", latex)
                    doc, _ = pipeline.run(sample, run_dir, Mock())
                    self.assertEqual(doc, "doc")
                events = [event for event in state.load_events(run_dir) if event.get("node_id") == "f-1"]
                self.assertTrue(events, f"no events for latex={latex}")
                self.assertEqual(events[-1]["revision"], expected)
            # Reverting the text re-identifies revision 0.
            with tempfile.TemporaryDirectory() as sample:
                layout(sample, "doc", "x+1")
                pipeline.run(sample, run_dir, Mock())
            events = [event for event in state.load_events(run_dir) if event.get("node_id") == "f-1"]
            self.assertEqual(events[-1]["revision"], 0)

    def test_skip_and_resume_stay_compatible_across_schema_versions(self):
        with tempfile.TemporaryDirectory() as run_dir, patch.object(
                pipeline.subprocess, "run", return_value=response("OK", code=0)):
            with tempfile.TemporaryDirectory() as sample:
                layout(sample, "doc", "x+1")
                pipeline.run(sample, run_dir, FixtureProvider())
            with tempfile.TemporaryDirectory() as sample:
                layout(sample, "doc", "x+1")
                pipeline.run(sample, run_dir, FixtureProvider())
            events = state.load_events(run_dir)
            skip = [event for event in events if event.get("action") == "SKIP"]
            self.assertEqual(len(skip), 1)
            self.assertEqual(skip[0]["revision"], 0)
            # A legacy terminal without a revision field still resumes by hash.
            legacy = {"action": "TERMINAL", "status": "OK", "resumable": True}
            self.assertEqual(state.terminal_event([legacy], "doc", "f-1", "a", "b"), None)
            legacy.update(doc="doc", node_id="f-1", input_sha256="a", context_sha256="b")
            self.assertEqual(state.terminal_event([legacy], "doc", "f-1", "a", "b")["status"], "OK")

    def test_pass_through_nodes_bind_a_revision(self):
        with tempfile.TemporaryDirectory() as run_dir:
            with tempfile.TemporaryDirectory() as sample:
                (Path(sample) / "layout.json").write_text(
                    json.dumps({"doc": "doc", "nodes": [{"id": "u-1", "type": "text", "data": {}}]}),
                    encoding="utf-8")
                pipeline.run(sample, run_dir, Mock())
            terminal = [event for event in state.load_events(run_dir) if event.get("action") == "TERMINAL"][0]
            self.assertEqual(terminal["revision"], 0)


if __name__ == "__main__":
    unittest.main()
