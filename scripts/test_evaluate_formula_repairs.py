"""Replay-runner isolation, evidence accounting and real-host smoke tests."""

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import evaluate_formula_repairs as evaluation


class FormulaRepairEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = evaluation.read_catalog(evaluation.DEFAULT_CASES)
        self.cases = {case["id"]: case for case in self.catalog["cases"]}

    def test_catalog_covers_repairs_controls_dangerous_candidates_and_ambiguity(self):
        self.assertEqual({group: sum(case["group"] == group for case in self.cases.values())
                          for group in evaluation.GROUPS},
                         {"structural": 6, "control": 6, "adversarial": 6, "ambiguous": 2})

    def test_real_studio_host_accepts_reference_without_inference(self):
        studio = evaluation.load_studio()
        case = self.cases["R01"]
        provider = evaluation.FixtureProvider(case["fixture_candidates"])
        row = evaluation.run_case(studio, case, provider, "fixture")
        self.assertIsNone(row["error"])
        self.assertTrue(row["reference_match"])
        self.assertTrue(row["wrappers_preserved"])
        self.assertEqual(row["model_calls"], 0)
        self.assertEqual(row["fixture_calls"], provider.calls)

    def test_preempted_injection_is_not_counted_as_guard_rejection(self):
        studio = SimpleNamespace(_apply_fixes=lambda content, log, **kwargs: (content, []))
        case = self.cases["A01"]
        row = evaluation.run_case(studio, case, evaluation.FixtureProvider(case["fixture_candidates"]), "fixture")
        summary = evaluation.summarize([row], "fixture")
        self.assertEqual(row["fixture_disposition"], "not_injected_no_provider_call")
        self.assertEqual(summary["dangerous_fixture_cases_not_exercised"], 1)
        self.assertIsNone(summary["dangerous_fixture_acceptance_when_exercised"]["rate"])

    def test_model_mode_does_not_claim_fixture_rejection_measurements(self):
        summary = evaluation.summarize([], "local-model")
        self.assertIsNone(summary["dangerous_fixture_acceptance_when_exercised"])
        self.assertIsNone(summary["dangerous_fixture_cases_not_exercised"])
        self.assertIsNone(summary["model_accuracy"])
        self.assertIsNone(summary["semantic_accuracy"])

    def test_reference_and_fixture_answers_are_not_sent_to_local_model(self):
        # Exercise the actual local-only provider transport. The fake host only
        # selects an observed node; the runner must not enrich it with gold data.
        evaluation.load_studio()  # Establish the same module paths as the CLI.
        import local_runtime
        case = copy.deepcopy(self.cases["R01"])
        case["references"] = ["REFERENCE_ONLY_SENTINEL"]
        case["fixture_candidates"] = ["FIXTURE_ONLY_SENTINEL"]
        with patch.dict(local_runtime.os.environ, {"VLM_API_KEY": "CLOUD_KEY_MUST_NOT_BE_READ"}):
            provider = evaluation.BoundedLocalProvider(local_runtime.make_local_provider(
                "http://127.0.0.1:9/v1", "test-local-model", skill_mode="off"), 5)

        def apply(content, log, *, provider, emit):
            candidate = provider.repair_formula({"id": "f1", "data": {"latex": case["input_latex"]}})
            emit("PROVIDER_RESULT", provider_trace=provider.last_trace)
            return content.replace(case["input_latex"], candidate), []

        response = {"choices": [{"message": {"content": '{"latex":"x"}'}, "finish_reason": "stop"}]}
        with patch.object(local_runtime, "local_json_request", return_value=response) as request, \
                patch.dict(local_runtime.os.environ, {"VLM_API_KEY": "CLOUD_KEY_MUST_NOT_BE_READ"}):
            row = evaluation.run_case(SimpleNamespace(_apply_fixes=apply), case, provider, "local-model")
        payload = json.dumps(request.call_args.args[1])
        self.assertNotIn("REFERENCE_ONLY_SENTINEL", payload)
        self.assertNotIn("FIXTURE_ONLY_SENTINEL", payload)
        self.assertNotIn("CLOUD_KEY_MUST_NOT_BE_READ", payload)
        self.assertEqual(request.call_args.args[0], "http://127.0.0.1:9/v1/chat/completions")
        self.assertEqual(row["model_calls"], 1)
        self.assertEqual(row["fixture_calls"], 0)
        self.assertIsNone(row["expected"]["fixture_candidates"])

    def test_local_provider_has_a_two_invocation_budget(self):
        provider = SimpleNamespace(repair_formula=lambda *args, **kwargs: "x")
        bounded = evaluation.BoundedLocalProvider(provider, 5)
        self.assertEqual(bounded.repair_formula({}), "x")
        self.assertEqual(bounded.repair_formula({}), "x")
        with self.assertRaisesRegex(RuntimeError, "budget"):
            bounded.repair_formula({})

    def test_local_model_requires_explicit_loopback_configuration(self):
        for options in ([], ["--base-url", "https://example.com/v1", "--model", "local"],
                        ["--base-url", "http://127.0.0.1:9/v1"]):
            with tempfile.TemporaryDirectory() as directory, patch.object(evaluation, "load_studio") as load:
                output = Path(directory) / "fresh"
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    evaluation.main(["--mode", "local-model", "--outdir", str(output), *options])
                load.assert_not_called()
                self.assertFalse(output.exists())

    def test_existing_evidence_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(evaluation, "load_studio") as load:
            sentinel = Path(directory) / "report.json"
            sentinel.write_text("preserve")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                evaluation.main(["--outdir", directory])
            load.assert_not_called()
            self.assertEqual(sentinel.read_text(), "preserve")

    def test_fixture_cli_writes_replayable_reports_and_source_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = {**self.catalog, "cases": [self.cases["R01"]]}
            cases = root / "cases.json"
            cases.write_text(json.dumps(catalog), encoding="utf-8")
            outdir = root / "run"
            with contextlib.redirect_stdout(io.StringIO()):
                result = evaluation.main(["--cases", str(cases), "--outdir", str(outdir)])
            self.assertEqual(result, 0)
            report = json.loads((outdir / "report.json").read_text())
            self.assertEqual(report["mode"], "fixture")
            self.assertEqual(report["catalog_sha256"], evaluation.digest(cases.read_bytes()))
            self.assertIn("webui/app.py", report["source_sha256"])
            self.assertIsNone(report["summary"]["model_accuracy"])
            self.assertEqual(report["summary"]["model_calls"], 0)
            row = report["results"][0]
            self.assertTrue(row["reference_match"])
            self.assertTrue(row["events"])
            self.assertEqual(row["expected"]["references"], self.cases["R01"]["references"])
            self.assertIn("not model inference", (outdir / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
