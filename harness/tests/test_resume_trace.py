"""Resume and candidate journal contracts, using deterministic provider doubles."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import pipeline, state  # noqa: E402


class ProviderDouble:
    name = "deterministic-test-provider"

    def __init__(self, candidates=(), model_calls=0):
        self.candidates = list(candidates)
        self.model_calls = model_calls
        self.configuration = {"model": "test", "skill_sha256": "a" * 64}
        self.calls = 0
        self.last_trace = {}

    def fingerprint(self):
        return copy.deepcopy(self.configuration)

    def repair_formula(self, node):
        self.calls += 1
        self.last_trace = {"model_calls": self.model_calls, "model_called": bool(self.model_calls),
                           "reason": "candidate_generated", "skill_sha256": "a" * 64,
                           "prompt_sha256": "b" * 64}
        candidate = self.candidates.pop(0) if self.candidates else None
        if isinstance(candidate, Exception):
            raise candidate
        return candidate

    repair_table = repair_formula


def formula(latex="x+"):
    return {"id": "f-1", "type": "formula", "data": {"latex": latex}}


def save_layout(path, nodes, doc="document"):
    path.mkdir(exist_ok=True)
    (path / "layout.json").write_text(json.dumps({"doc": doc, "nodes": nodes}), encoding="utf-8")


class JournalTest(unittest.TestCase):
    def test_load_ignores_non_objects_and_broken_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(state.state_path(directory))
            path.write_text('{}\nnull\n[]\n"a"\n42\n{broken\n{"ok": true}\n', encoding="utf-8")
            self.assertEqual(state.load_events(directory), [{}, {"ok": True}])
            path.write_bytes(path.read_bytes() + b'{"partial":')
            state.append(directory, action="NEW", value="line\nbreak")
            self.assertEqual(state.load_events(directory)[-1]["action"], "NEW")
            self.assertEqual(state.load_events(directory)[-1]["value"], "line\nbreak")
            self.assertEqual(path.read_bytes().splitlines()[-1].count(b"schema_version"), 1)

    def test_legacy_and_intermediate_status_cannot_authorize_resume(self):
        events = [None, {"doc": "d", "node_id": "n", "status": "OK"},
                  {"doc": "d", "node_id": "n", "status": "OK", "action": "CHECK",
                   "input_sha256": "i", "context_sha256": "c"}]
        self.assertIsNone(state.terminal_state(events, "d", "n"))
        self.assertIsNone(state.terminal_state(events, "d", "n", "i", "c"))
        events.append({"doc": "d", "node_id": "n", "status": "OK", "action": "TERMINAL",
                       "input_sha256": "i", "context_sha256": "c"})
        self.assertEqual(state.terminal_state(events, "d", "n", "i", "c"), "OK")
        events.append({**events[-1], "status": "NEEDS_HUMAN", "resumable": False})
        self.assertIsNone(state.terminal_state(events, "d", "n", "i", "c"))
        self.assertIsNone(state.terminal_state(events, "d", "n", "new-input", "c"))

    def test_malformed_terminal_status_does_not_crash_or_authorize_reuse(self):
        base = {"doc": "d", "node_id": "n", "action": "TERMINAL",
                "input_sha256": "i", "context_sha256": "c"}
        for status in ([], {}, 1, None):
            with self.subTest(status=status):
                self.assertIsNone(state.terminal_event([{**base, "status": status}], "d", "n", "i", "c"))

    def test_canonical_hash_is_stable_under_key_order(self):
        self.assertEqual(state.canonical_sha256({"a": 1, "b": [2, 3]}),
                         state.canonical_sha256({"b": [2, 3], "a": 1}))
        self.assertNotEqual(state.canonical_sha256([1, 2]), state.canonical_sha256([2, 1]))


class ResumeTest(unittest.TestCase):
    def test_matching_run_skips_but_same_node_id_changed_input_rechecks(self):
        provider = ProviderDouble()
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", return_value={"status": "OK"}) as verify:
            sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
            save_layout(sample, [formula("x")])
            pipeline.run(str(sample), journal, provider, run_id="one")
            pipeline.run(str(sample), journal, provider, run_id="two")
            self.assertEqual(verify.call_count, 1)
            skipped = [e for e in state.load_events(journal) if e.get("action") == "SKIP"]
            self.assertEqual([(e["run_id"], e["reused_run_id"], e["status"]) for e in skipped],
                             [("two", "one", "OK")])
            save_layout(sample, [formula("y")])
            pipeline.run(str(sample), journal, provider, run_id="three")
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(verify.call_args.args, ("y",))
            third = [e for e in state.load_events(journal) if e["run_id"] == "three"]
            self.assertFalse(any(e.get("action") == "SKIP" for e in third))

    def test_model_and_skill_fingerprint_changes_invalidate_resume(self):
        for field in ("model", "skill_sha256"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory, patch.object(
                    pipeline, "run_verify", return_value={"status": "OK"}) as verify:
                provider = ProviderDouble()
                sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
                save_layout(sample, [formula("x")])
                pipeline.run(str(sample), journal, provider)
                provider.configuration[field] = "changed"
                pipeline.run(str(sample), journal, provider)
                self.assertEqual(verify.call_count, 2)

    def test_checker_and_environment_changes_invalidate_context(self):
        node, provider = formula("x"), ProviderDouble()
        before = pipeline.node_identity(node, provider)
        with patch.object(pipeline, "_file_sha256", return_value="changed-checker"):
            after = pipeline.node_identity(node, provider)
        self.assertEqual(before[0], after[0])
        self.assertNotEqual(before[1], after[1])
        with patch.object(pipeline.importlib.metadata, "version", return_value="changed-dependency"):
            changed_environment = pipeline.node_identity(node, provider)
        self.assertNotEqual(before[1], changed_environment[1])

    def test_crop_bytes_change_input_hash_without_exposing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            crop = Path(directory) / "private-crop.bin"
            crop.write_bytes(b"old")
            node = formula("x")
            node["data"]["crop"] = str(crop)
            before = pipeline.node_identity(node, ProviderDouble())
            crop.write_bytes(b"new")
            after = pipeline.node_identity(node, ProviderDouble())
            self.assertNotEqual(before[0], after[0])
            self.assertEqual(before[1], after[1])

    def test_legacy_logs_and_unfingerprinted_provider_are_not_skipped(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", return_value={"status": "OK"}) as verify:
            sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
            save_layout(sample, [formula("x")])
            state.append(journal, doc="document", node_id="f-1", status="OK")
            provider = ProviderDouble()
            pipeline.run(str(sample), journal, provider)
            self.assertEqual(verify.call_count, 1)
            provider.fingerprint = None
            pipeline.run(str(sample), journal, provider)
            pipeline.run(str(sample), journal, provider)
            self.assertEqual(verify.call_count, 3)

    def test_checker_recovery_retries_same_directory_then_becomes_resumable(self):
        for kind, failure in (("formula", {"status": "NEEDS_ENV", "reason": "temporary_checker_failure"}),
                              ("table", {"status": "NEEDS_HUMAN", "reason": "checker_error"})):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                node = formula("x") if kind == "formula" else {
                    "id": "t-1", "type": "table", "data": {"rows": [["N", "V"], ["A", "1"]]}}
                sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
                save_layout(sample, [node])
                provider = ProviderDouble()
                checker = "run_verify" if kind == "formula" else "run_audit"
                with patch.object(pipeline, checker, side_effect=[failure, {"status": "OK"}]) as check:
                    pipeline.run(str(sample), journal, provider, run_id="failed")
                    pipeline.run(str(sample), journal, provider, run_id="recovered")
                    pipeline.run(str(sample), journal, provider, run_id="reused")
                self.assertEqual(check.call_count, 2)
                events = state.load_events(journal)
                terminals = [e for e in events if e.get("action") == "TERMINAL"]
                self.assertEqual([(e["run_id"], e["resumable"]) for e in terminals],
                                 [("failed", False), ("recovered", True)])
                skipped = [e for e in events if e.get("action") == "SKIP"]
                self.assertEqual([(e["run_id"], e["reused_run_id"]) for e in skipped], [("reused", "recovered")])

    def test_provider_recovery_retries_without_input_or_context_change(self):
        for failure_reason in sorted(pipeline.TRANSIENT_PROVIDER_FAILURES):
            with self.subTest(reason=failure_reason), tempfile.TemporaryDirectory() as directory:
                sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
                save_layout(sample, [formula("x+")])
                provider = ProviderDouble([None, "x"], model_calls=1)
                original_repair = provider.repair_formula
                def repair(node):
                    candidate = original_repair(node)
                    provider.last_trace["reason"] = failure_reason if candidate is None else "ok"
                    return candidate
                provider.repair_formula = repair
                with patch.object(pipeline, "run_verify", side_effect=[
                        {"status": "RETRY", "reason": "parse_error"},
                        {"status": "RETRY", "reason": "parse_error"}, {"status": "OK"}]):
                    pipeline.run(str(sample), journal, provider, run_id="failed")
                    pipeline.run(str(sample), journal, provider, run_id="recovered")
                    pipeline.run(str(sample), journal, provider, run_id="reused")
                self.assertEqual(provider.calls, 2)
                events = state.load_events(journal)
                terminals = [e for e in events if e.get("action") == "TERMINAL"]
                self.assertFalse(terminals[0]["resumable"])
                self.assertTrue(terminals[1]["resumable"])
                self.assertEqual(terminals[0]["input_sha256"], terminals[1]["input_sha256"])
                self.assertEqual(terminals[0]["context_sha256"], terminals[1]["context_sha256"])
                self.assertEqual(sum(e["model_calls"] for e in terminals), 2)
                rejected = [e for e in events if e.get("action") == "CANDIDATE_REJECTED"]
                self.assertEqual(rejected[0]["reason"], failure_reason)
                self.assertEqual([e["reused_run_id"] for e in events if e.get("action") == "SKIP"], ["recovered"])

    def test_exhausted_syntax_retries_and_human_boundaries_remain_resumable(self):
        for checks, candidates in (([{"status": "RETRY", "reason": "syntax"}] * 3, ["a+", "b+"]),
                                    ([{"status": "NEEDS_HUMAN", "reason": "bad_input"}], [])):
            with self.subTest(checks=checks), tempfile.TemporaryDirectory() as directory:
                sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
                save_layout(sample, [formula("x+")])
                provider = ProviderDouble(candidates)
                with patch.object(pipeline, "run_verify", side_effect=checks) as check:
                    pipeline.run(str(sample), journal, provider, run_id="human")
                    pipeline.run(str(sample), journal, provider, run_id="reused")
                self.assertEqual(check.call_count, len(checks))
                events = state.load_events(journal)
                terminal = next(e for e in events if e.get("action") == "TERMINAL")
                self.assertTrue(terminal["resumable"])
                self.assertEqual([e["reused_run_id"] for e in events if e.get("action") == "SKIP"], ["human"])

    def test_invalid_layouts_fail_before_creating_events(self):
        bad_layouts = [[], {"nodes": {}}, {"nodes": [1]}, {"nodes": [{"id": 1, "type": "formula"}]},
                       {"nodes": [formula(), formula()]}, {"doc": [], "nodes": []}]
        # Empty doc falls back to sample name; a non-empty non-string is invalid.
        bad_layouts[-1] = {"doc": ["invalid"], "nodes": []}
        for layout in bad_layouts:
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as directory:
                sample, journal = Path(directory) / "sample", str(Path(directory) / "journal")
                sample.mkdir()
                (sample / "layout.json").write_text(json.dumps(layout))
                with self.assertRaises(ValueError):
                    pipeline.run(str(sample), journal, ProviderDouble())
                self.assertFalse(Path(state.state_path(journal)).exists())


class CandidateTraceTest(unittest.TestCase):
    def test_two_candidates_preserve_rejection_acceptance_and_model_counts(self):
        provider = ProviderDouble(["x+", "x"], model_calls=1)
        node = formula("broken+")
        original_node = copy.deepcopy(node)
        checks = [{"status": "RETRY", "reason": "original_error"},
                  {"status": "RETRY", "reason": "still_broken"}, {"status": "OK", "reason": "parsed"}]
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline, "run_verify", side_effect=checks):
            self.assertEqual(pipeline.process_formula(directory, "d", node, provider, run_id="r"), "OK")
            events = state.load_events(directory)
        self.assertEqual([e["action"] for e in events], ["CHECK", "PROVIDER_START", "PROVIDER_RESULT", "CHECK",
            "CANDIDATE_REJECTED", "PROVIDER_START", "PROVIDER_RESULT", "CHECK", "CANDIDATE_ACCEPTED", "TERMINAL"])
        self.assertEqual([(e["stage"], e["checker_reason"]) for e in events if e["action"] == "CHECK"],
                         [("original", "original_error"), ("candidate", "still_broken"), ("candidate", "parsed")])
        self.assertEqual([e["candidate"] for e in events if e["action"] == "PROVIDER_RESULT"], ["x+", "x"])
        terminal = events[-1]
        self.assertEqual((terminal["attempts"], terminal["model_calls"], terminal["latex"]), (2, 2, "x"))
        self.assertEqual(terminal["original"], "broken+")
        self.assertTrue(terminal["review_required"])
        self.assertNotIn("adopted", terminal)
        self.assertTrue(all(e["run_id"] == "r" for e in events))
        self.assertTrue(all(len(e["input_sha256"]) == 64 and len(e["context_sha256"]) == 64 for e in events))
        self.assertEqual(node, original_node)

    def test_fixture_candidates_have_zero_model_calls(self):
        provider = ProviderDouble(["x"], model_calls=0)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", side_effect=[{"status": "RETRY"}, {"status": "OK"}]):
            pipeline.process_formula(directory, "d", formula(), provider)
            terminal = state.load_events(directory)[-1]
        self.assertEqual(terminal["model_calls"], 0)
        self.assertEqual(terminal["attempts"], 1)
        self.assertTrue(terminal["model_calls_known"])

    def test_provider_failure_has_safe_reason_and_no_endpoint_in_journal(self):
        secret = "https://private-user:private-secret@private-host/path?token=private-token"
        provider = ProviderDouble([RuntimeError(secret)], model_calls=1)
        provider.configuration["base"] = secret
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", return_value={"status": "RETRY", "reason": "bad syntax"}):
            self.assertEqual(pipeline.process_formula(directory, "d", formula(), provider), "NEEDS_HUMAN")
            text = Path(state.state_path(directory)).read_text()
            events = state.load_events(directory)
        self.assertNotIn("private-", text)
        result = next(e for e in events if e["action"] == "PROVIDER_RESULT")
        self.assertEqual(result["reason"], "provider_exception")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertEqual(events[-1]["model_calls"], 1)
        self.assertEqual(events[-1]["provider_reason"], "provider_exception")

    def test_environment_failure_rejects_candidate_without_second_provider_call(self):
        provider = ProviderDouble(["x", "y"], model_calls=1)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", side_effect=[{"status": "RETRY"},
                                                     {"status": "NEEDS_ENV", "reason": "missing_parser"}]):
            self.assertEqual(pipeline.process_formula(directory, "d", formula(), provider), "NEEDS_HUMAN")
            events = state.load_events(directory)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(events[-2]["action"], "CANDIDATE_REJECTED")
        self.assertEqual(events[-2]["checker_status"], "NEEDS_ENV")
        self.assertFalse(events[-1]["repaired"])
        self.assertEqual(events[-1]["latex"], "x+")
        self.assertEqual(events[-1]["reason"], "env: missing_parser")

    def test_exhausted_candidates_remain_visible_and_original_is_preserved(self):
        provider = ProviderDouble(["a+", "b+"], model_calls=0)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", return_value={"status": "RETRY", "reason": "parse_error"}):
            self.assertEqual(pipeline.process_formula(directory, "d", formula("original+"), provider), "NEEDS_HUMAN")
            events = state.load_events(directory)
        self.assertEqual([e["candidate"] for e in events if e["action"] == "CANDIDATE_REJECTED"], ["a+", "b+"])
        self.assertEqual(events[-1]["latex"], "original+")
        self.assertEqual(events[-1]["attempts"], 2)

    def test_invalid_candidate_response_is_preserved_with_bounded_trace(self):
        provider = pipeline.OllamaProvider(skill_mode="off")
        content = "not-json:" + "x" * 9000
        def invalid_response(_prompt):
            provider.last_trace.update(model_calls=1, model_called=True)
            return {"choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32}}
        with tempfile.TemporaryDirectory() as directory, patch.object(
                pipeline, "run_verify", return_value={"status": "RETRY", "reason": "parse_error"}), patch.object(
                provider, "_chat", side_effect=invalid_response):
            pipeline.process_formula(directory, "d", formula(), provider)
            events = state.load_events(directory)
        result = next(e for e in events if e["action"] == "PROVIDER_RESULT")
        self.assertEqual(result["reason"], "bad_candidate_json")
        self.assertEqual(result["raw_candidate_response"], content[:8192])
        self.assertTrue(result["response_truncated"])
        self.assertEqual(result["usage"]["total_tokens"], 32)
        self.assertEqual(events[-1]["provider_reason"], "bad_candidate_json")
        self.assertEqual(events[-1]["model_calls"], 1)

    def test_missing_formula_data_is_not_sent_to_provider(self):
        for data in (None, [], {}, {"other": "not latex"}):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                provider = ProviderDouble(["x"], model_calls=1)
                node = {"id": "f-1", "type": "formula", "data": data}
                status = pipeline.process_formula(directory, "d", node, provider)
                self.assertEqual(status, "NEEDS_HUMAN")
                self.assertEqual(provider.calls, 0)
                self.assertIn("bad_input", state.load_events(directory)[-1]["reason"])

    def test_table_trace_keeps_original_and_each_candidate(self):
        original = [["Name", "Total"], ["A", "3"], ["Total", "4"]]
        failed = [["Name", "Total"], ["A", "3"], ["Total", "5"]]
        passed = [["Name", "Total"], ["A", "3"], ["Total", "3"]]
        node = {"id": "t-1", "type": "table", "data": {"rows": original}}
        provider = ProviderDouble([failed, passed])
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline, "run_audit", side_effect=[
                {"status": "RETRY", "reason": "sum_mismatch"},
                {"status": "RETRY", "reason": "sum_mismatch"}, {"status": "OK"}]):
            pipeline.process_table(directory, "d", node, provider)
            events = state.load_events(directory)
        self.assertEqual(events[0]["original"], original)
        self.assertEqual([e["candidate"] for e in events if e["action"] == "PROVIDER_RESULT"], [failed, passed])
        self.assertEqual(events[-1]["original_rows"], original)
        self.assertEqual(events[-1]["candidate_rows"], passed)
        self.assertEqual(node["data"]["rows"], original)


if __name__ == "__main__":
    unittest.main()
