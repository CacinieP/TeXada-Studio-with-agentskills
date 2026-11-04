"""Formula syntax repairs preserve source tokens in both Studio host routes."""

import copy
import tempfile
import unittest
from unittest.mock import patch

from test_static_assets import studio
from docforensics.planner import ConstrainedPlanner, PlannerBudget


ORIGINAL = r"\frac{a}{b"
FIXED = r"\frac{a}{b}"


class RepairProvider:
    name = "offline-test"

    def __init__(self, candidates=(), reasons=()):
        self.candidates = iter(candidates)
        self.reasons = iter(reasons)
        self.calls = []
        self.last_trace = {}

    def fingerprint(self):
        return {"provider": self.name, "skill_mode": "off"}

    def repair_formula(self, node, **kwargs):
        self.calls.append(copy.deepcopy(node))
        candidate = next(self.candidates)
        self.last_trace = {"model_calls": 1, "reason": next(self.reasons, "candidate")}
        return candidate


def verifier(latex):
    return {"status": "RETRY", "reason": "missing_closing_brace"} if latex.strip() == ORIGINAL else {"status": "OK"}


class StudioFormulaRepairQualityTest(unittest.TestCase):
    def run_route(self, route, content, provider, events, **kwargs):
        emit = lambda action, **fields: events.append({"action": action, **fields})
        if route == "ordinary":
            return (*studio._apply_fixes(content, [], provider=provider, emit=emit), None)
        return studio._apply_planned_fixes(content, [], provider=provider, emit=emit,
                                          use_model_planner=False, **kwargs)

    def test_deterministic_patch_uses_same_checker_without_provider_and_retains_source(self):
        for route in ("ordinary", "planned"):
            with self.subTest(route=route), patch.object(studio, "_verify_formula", side_effect=verifier):
                events, provider = [], RepairProvider()
                source = "prefix \\[\n " + ORIGINAL + " \n\\] suffix\r\n"
                candidate, edits, report = self.run_route(route, source, provider, events)
                body = "\n " + ORIGINAL + " \n"
                self.assertEqual(candidate, source.replace(body, body + "}"))
                self.assertEqual(edits[0]["after"], edits[0]["before"] + "}")
                self.assertEqual(len(edits), 1)
                self.assertEqual(provider.calls, [])
                self.assertEqual([e["action"] for e in events if e["action"].startswith("PROVIDER_")], [])
                self.assertTrue(any(e["action"] == "DETERMINISTIC_REPAIR" and e["model_calls"] == 0 for e in events))
                self.assertTrue(any(e["action"] == "CANDIDATE_SCOPE" and e["scope"]["allowed"] for e in events))
                if report:
                    self.assertEqual(report["reserved_model_calls"], 0)

    def test_safe_rule_patch_is_a_real_checker_acceptance_not_a_mocked_parse(self):
        provider, events = RepairProvider(), []
        source = "$" + ORIGINAL + "$"
        candidate, edits, _ = self.run_route("ordinary", source, provider, events)
        checks = [e["check"]["status"] for e in events if e["action"] in {"CHECK", "CANDIDATE_CHECK"}]
        if "NEEDS_ENV" in checks:
            self.skipTest("local SymPy/ANTLR checker unavailable")
        self.assertEqual(checks, ["RETRY", "OK"])
        self.assertEqual(candidate, "$" + FIXED + "$")
        self.assertEqual(len(edits), 1)
        self.assertFalse(provider.calls)

    def test_model_candidate_requires_checker_and_preservation_and_gets_rejection_feedback(self):
        for route in ("ordinary", "planned"):
            events, provider = [], RepairProvider(["0", FIXED])
            with self.subTest(route=route), patch.object(studio, "deterministic_candidate", return_value=None), \
                    patch.object(studio, "_verify_formula", side_effect=verifier):
                candidate, edits, _ = self.run_route(route, "$" + ORIGINAL + "$", provider, events)
            self.assertEqual(candidate, "$" + FIXED + "$")
            self.assertEqual(len(edits), 1)
            self.assertEqual(len(provider.calls), 2)
            first, second = [call["data"]["repair_context"] for call in provider.calls]
            self.assertEqual(first["attempt"], 1)
            self.assertEqual(first["checker"]["status"], "RETRY")
            self.assertEqual(second["attempt"], 2)
            self.assertEqual(second["previous_candidate"], "0")
            self.assertTrue(second["rejection_reason"])
            self.assertNotEqual(first, second)
            rejected = [e for e in events if e["action"] == "CANDIDATE_REJECTED"]
            self.assertEqual(rejected[0]["candidate"], "0")
            self.assertEqual(rejected[0]["check"]["status"], "OK")
            self.assertTrue(any(e["action"] == "CANDIDATE_SCOPE" and not e["scope"]["allowed"] for e in events))

    def test_empty_response_carries_provider_failure_to_second_attempt(self):
        for route in ("ordinary", "planned"):
            events, provider = [], RepairProvider([None, FIXED], ["invalid_response_json", "candidate"])
            with self.subTest(route=route), patch.object(studio, "deterministic_candidate", return_value=None), \
                    patch.object(studio, "_verify_formula", side_effect=verifier):
                candidate, _, _ = self.run_route(route, "$" + ORIGINAL + "$", provider, events)
            self.assertEqual(candidate, "$" + FIXED + "$")
            context = provider.calls[1]["data"]["repair_context"]
            self.assertEqual(context["rejection_reason"], "invalid_response_json")
            self.assertIsNone(context["previous_candidate"])
            self.assertEqual(context["attempt"], 2)

    def test_repeated_rejected_candidate_stops_without_another_checker_or_edit(self):
        for route in ("ordinary", "planned"):
            events, provider = [], RepairProvider(["0", "0"])
            with self.subTest(route=route), patch.object(studio, "deterministic_candidate", return_value=None), \
                    patch.object(studio, "_verify_formula", side_effect=verifier) as check:
                candidate, edits, _ = self.run_route(route, "$" + ORIGINAL + "$", provider, events)
            self.assertEqual(candidate, "$" + ORIGINAL + "$")
            self.assertFalse(edits)
            self.assertEqual([call.args[0] for call in check.call_args_list], [ORIGINAL, "0"])
            self.assertTrue(any(e.get("reason") == "repeated_candidate" for e in events))

    def test_ambiguous_missing_operands_and_parser_boundaries_never_reach_model(self):
        for route in ("ordinary", "planned"):
            for original in ("x+", "a_", "x^2^3", "x=1=2", r"\left.x^2\right|_{x=1}"):
                events, provider = [], RepairProvider()
                with self.subTest(route=route, original=original), \
                        patch.object(studio, "_verify_formula", return_value={"status": "RETRY", "reason": "parse_error"}):
                    candidate, edits, _ = self.run_route(route, "$" + original + "$", provider, events)
                self.assertEqual(candidate, "$" + original + "$")
                self.assertFalse(edits)
                self.assertFalse(provider.calls)
                self.assertTrue(any(e["action"] == "REPAIR_SKIPPED" for e in events))

    def test_analysis_marks_ambiguous_retry_as_manual_without_changing_checker_evidence(self):
        events = []
        with patch.object(studio, "_verify_formula", return_value={"status": "RETRY", "reason": "parse_error"}):
            problems = studio._formula_problems("$x+$", lambda action, **fields: events.append({"action": action, **fields}))
        self.assertEqual(problems[0]["status"], "NEEDS_HUMAN")
        self.assertEqual(problems[0]["repair_blocker"], "missing_operator_operand")
        self.assertIn("missing_operator_operand", problems[0]["reason"])
        self.assertEqual(events[0]["check"], {"status": "RETRY", "reason": "parse_error"})

    def test_deterministic_checker_environment_failure_stops_later_formula_repairs(self):
        for route in ("ordinary", "planned"):
            events, provider = [], RepairProvider()
            def failing_check(latex):
                return {"status": "NEEDS_ENV", "reason": "missing_antlr"} if latex == FIXED else {"status": "RETRY"}
            with self.subTest(route=route), patch.object(studio, "_verify_formula", side_effect=failing_check):
                source = "$" + ORIGINAL + "$ and $" + ORIGINAL + "$"
                candidate, edits, _ = self.run_route(route, source, provider, events)
            self.assertEqual(candidate, source)
            self.assertFalse(edits)
            self.assertFalse(provider.calls)
            self.assertEqual(len([e for e in events if e["action"] == "DETERMINISTIC_REPAIR"]), 1)

    def test_model_checker_environment_failure_stops_later_formula_repairs(self):
        for route in ("ordinary", "planned"):
            events, provider = [], RepairProvider([FIXED])
            def failing_check(latex):
                return {"status": "NEEDS_ENV", "reason": "missing_antlr"} if latex == FIXED else {"status": "RETRY"}
            with self.subTest(route=route), patch.object(studio, "deterministic_candidate", return_value=None), \
                    patch.object(studio, "_verify_formula", side_effect=failing_check):
                source = "$" + ORIGINAL + "$ and $" + ORIGINAL + "$"
                candidate, edits, _ = self.run_route(route, source, provider, events)
            self.assertEqual(candidate, source)
            self.assertFalse(edits)
            self.assertEqual(len(provider.calls), 1)

    def test_planner_discards_late_deterministic_checker_result_without_model_reservation(self):
        clock, events, provider = [0.0], [], RepairProvider()
        def factory(*args, **kwargs):
            return ConstrainedPlanner(*args, **kwargs, budget=PlannerBudget(seconds=1), clock=lambda: clock[0])
        def late_check(latex):
            if latex == FIXED:
                clock[0] = 2.0
                return {"status": "OK"}
            return {"status": "RETRY"}
        with patch.object(studio, "ConstrainedPlanner", side_effect=factory), \
                patch.object(studio, "_verify_formula", side_effect=late_check):
            candidate, edits, report = self.run_route("planned", "$" + ORIGINAL + "$", provider, events)
        self.assertEqual(candidate, "$" + ORIGINAL + "$")
        self.assertFalse(edits)
        self.assertFalse(provider.calls)
        self.assertEqual(report["reserved_model_calls"], 0)
        self.assertFalse(any(e["action"] == "CANDIDATE_ACCEPTED" for e in events))
        self.assertTrue(any(e.get("reason") == "planner_deadline_exhausted" for e in events))

    def test_worker_reports_deterministic_formula_repair_without_model_calls(self):
        job_id, provider = "7" * 32, RepairProvider()
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None}}, clear=True), \
                patch.object(studio, "_new_provider", return_value=provider), \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.object(studio, "_verify_formula", side_effect=verifier):
            studio._studio_job("notes.tex", "$" + ORIGINAL + "$", job_id)
            result = studio._jobs[job_id]["result"]
        self.assertEqual(result["fixed_content"], "$" + FIXED + "$")
        self.assertEqual(result["model_calls"], 0)
        self.assertIsNone(result["model"])
        self.assertEqual(result["provider"], "deterministic-checks")


if __name__ == "__main__":
    unittest.main()
