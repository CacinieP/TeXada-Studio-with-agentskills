"""Anchor drift guard (#28-B): operators, Greek letters and script structure.

Positive cases cover unchanged sources and the deterministic syntax patch;
negative cases cover the drift the issue calls out (operator downgrade, loss,
upgrade, Greek loss, script loss). No model, compiler or subprocess required;
the standalone script is exercised through its module interface.
"""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import anchor_guard, pipeline, state  # noqa: E402
from docforensics.formula_repair import deterministic_candidate  # noqa: E402

GUARD = str(Path(__file__).resolve().parents[2] / "scripts" / "doc-anchor-guard.py")


class AnchorGuardPositiveTest(unittest.TestCase):
    def test_unchanged_source_has_no_drift(self):
        for latex in ("\\iint_D f\\,dx", "\\sum_{k=1}^{n} \\alpha_k", "", "x"):
            with self.subTest(latex=latex):
                verdict = anchor_guard.anchor_drift(latex, latex)
                self.assertFalse(verdict["drift"])
                self.assertEqual(verdict["reason"], "")

    def test_deterministic_syntax_patch_never_drifts(self):
        for original in ("\\frac{1}{2", "\\left( x + 1", "\\left[ a_1 + \\sum_{i}^{n} b_i"):
            candidate = deterministic_candidate(original)
            self.assertIsNotNone(candidate, original)
            with self.subTest(original=original, candidate=candidate):
                self.assertFalse(anchor_guard.anchor_drift(original, candidate)["drift"])

    def test_spacing_differences_are_not_drift(self):
        verdict = anchor_guard.anchor_drift("\\int_0^1 f(x)\\,dx", "\\int_0 ^ 1 f ( x ) dx")
        self.assertFalse(verdict["drift"])

    def test_non_string_inputs_do_not_drift(self):
        for original, candidate in ((None, "x"), ("x", None), (42, "x"), ("x", ["y"])):
            with self.subTest(original=original, candidate=candidate):
                verdict = anchor_guard.anchor_drift(original, candidate)
                self.assertFalse(verdict["drift"])
                self.assertEqual(verdict["reason"], "invalid_input")


class AnchorGuardNegativeTest(unittest.TestCase):
    def test_operator_downgrade_iint_to_int(self):
        verdict = anchor_guard.anchor_drift("\\iint_D f\\,dA", "\\int_D f\\,dA")
        self.assertTrue(verdict["drift"])
        self.assertEqual(verdict["reason"], "anchor_drift:operator_downgraded:\\iint")
        self.assertEqual(verdict["findings"][0]["kind"], "operator_downgraded")

    def test_operator_loss_sum_dropped(self):
        verdict = anchor_guard.anchor_drift("\\sum_{k} a_k + b", "a_k + b")
        self.assertTrue(verdict["drift"])
        self.assertEqual(verdict["reason"], "anchor_drift:operator_lost:\\sum")

    def test_operator_upgrade_int_to_iint(self):
        verdict = anchor_guard.anchor_drift("\\int_D f", "\\iint_D f")
        self.assertTrue(verdict["drift"])
        self.assertEqual(verdict["reason"], "anchor_drift:operator_upgraded:\\int")

    def test_greek_letter_loss_is_reported(self):
        verdict = anchor_guard.anchor_drift("\\alpha + \\beta", "\\beta")
        self.assertTrue(verdict["drift"])
        self.assertEqual(verdict["reason"], "anchor_drift:greek_lost:\\alpha")

    def test_script_structure_loss_is_reported(self):
        verdict = anchor_guard.anchor_drift("x^{2} + y_{i}", "x + y")
        self.assertTrue(verdict["drift"])
        kinds = {finding["kind"] for finding in verdict["findings"]}
        self.assertEqual(kinds, {"script_lost"})

    def test_unknown_change_reports_added_anchor(self):
        tester = anchor_guard.anchor_drift("x", "\\oint_C f\\,ds")
        self.assertTrue(tester["drift"])
        self.assertEqual(tester["findings"][0]["kind"], "operator_added")


class GuardPipelineConsistencyTest(unittest.TestCase):
    def test_drifting_candidate_is_rejected_with_anchor_reason(self):
        node = {"id": "f-1", "data": {"latex": "\\iint_D f\\,dA"}}
        provider = Mock()
        provider.repair_formula.side_effect = ["\\int_D f\\,dA", "\\int_D f\\,dX"]
        provider.last_trace = {}
        with tempfile.TemporaryDirectory() as run_dir, patch.object(
                pipeline.subprocess, "run", return_value=_checker("RETRY")):
            status = pipeline.process_formula(run_dir, "doc", node, provider)
            self.assertEqual(status, "NEEDS_HUMAN")
            events = state.load_events(run_dir)
            scope = [event for event in events if event.get("action") == "CANDIDATE_SCOPE"][-1]
            self.assertEqual(scope["anchor"]["reason"], "anchor_drift:operator_downgraded:\\iint")
            rejected = [event for event in events
                        if event.get("action") == "CANDIDATE_REJECTED" and "anchor" in event][0]
            self.assertTrue(rejected["anchor"]["drift"])
            terminal = events[-1]
            self.assertEqual(terminal["reason"], "anchor_drift:operator_downgraded:\\iint")
            retry_context = provider.repair_formula.call_args_list[-1].args[0]["data"]["repair_context"]
            self.assertEqual(retry_context["rejection_reason"],
                             "anchor_drift:operator_downgraded:\\iint")

    def test_preserving_candidate_passes_guard_and_scope(self):
        original = "\\left( x \\right"
        node = {"id": "f-1", "data": {"latex": original}}
        provider = Mock()
        with tempfile.TemporaryDirectory() as run_dir, patch.object(
                pipeline.subprocess, "run",
                side_effect=[_checker("RETRY"), _checker("OK")]):
            status = pipeline.process_formula(run_dir, "doc", node, provider)
            self.assertEqual(status, "OK")
            events = state.load_events(run_dir)
            repair = [event for event in events if event.get("action") == "DETERMINISTIC_REPAIR"][-1]
            self.assertFalse(repair["anchor"]["drift"])
            accepted = [event for event in events if event.get("action") == "CANDIDATE_ACCEPTED"][-1]
            self.assertEqual(accepted["attempt"], 0)
            provider.repair_formula.assert_not_called()


class AnchorGuardScriptTest(unittest.TestCase):
    def load_script_module(self):
        spec = importlib.util.spec_from_file_location("doc_anchor_guard_script", GUARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_verdict_argument_mode_semantics(self):
        script = self.load_script_module()
        record = script.verdict("\\iint_D f\\,dA", "\\int_D f\\,dA")
        self.assertEqual(record["status"], "RETRY")
        self.assertEqual(record["reason"], "anchor_drift:operator_downgraded:\\iint")
        record = script.verdict("\\sum_k a_k", "\\sum_k a_k")
        self.assertEqual(record["status"], "OK")
        record = script.verdict(None, "x")
        self.assertEqual(record["status"], "NEEDS_HUMAN")

    def test_jsonl_mode_reports_per_line(self):
        script = self.load_script_module()
        payload = "\n".join([
            json.dumps({"id": "a", "original": "\\sum_k a_k", "candidate": "\\sum_k a_k"}),
            json.dumps({"id": "b", "original": "\\sum_k a_k", "candidate": "a_k"}),
            "not json",
            json.dumps({"id": "d"}),
        ]) + "\n"
        with patch.object(sys, "stdin", io.StringIO(payload)), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            exit_code = script.main(["-"])
        records = [json.loads(line) for line in out.getvalue().strip().splitlines()]
        self.assertEqual(exit_code, 0)
        self.assertEqual(records[0]["status"], "OK")
        self.assertEqual(records[0]["id"], "a")
        self.assertEqual(records[1]["status"], "RETRY")
        self.assertEqual(records[1]["id"], "b")
        self.assertEqual(records[2]["status"], "NEEDS_HUMAN")
        self.assertEqual(records[3]["status"], "NEEDS_HUMAN")

    def test_wrong_arguments_print_usage(self):
        script = self.load_script_module()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            exit_code = script.main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("doc-anchor-guard", err.getvalue())


def _checker(status, **fields):
    from types import SimpleNamespace
    return SimpleNamespace(returncode=0, stdout=json.dumps({"status": status, **fields}), stderr="")


if __name__ == "__main__":
    unittest.main()
