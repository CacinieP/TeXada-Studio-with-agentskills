"""Controlled evaluation safety, accounting and review binding regressions."""

import argparse
import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import evaluate_skills as evaluation


class Provider:
    def __init__(self, candidates, calls=1):
        self.candidates = iter(candidates)
        self.requests = []
        self.last_trace = {}
        self.calls = calls

    def repair_formula(self, node):
        self.requests.append(copy.deepcopy(node))
        self.last_trace = {"model_calls": self.calls, "model_called": bool(self.calls),
                           "reason": "response", "skill_loaded": True}
        return next(self.candidates)


class SkillsEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.catalog_path = evaluation.REPO / "samples/research/smoke_cases.json"
        self.catalog = evaluation.read_catalog(self.catalog_path)
        self.case = self.catalog["cases"][1]

    def arm(self, provider, verify=lambda _: {"status": "OK"}, initial=None):
        return evaluation.run_arm(self.case, "model_with_skill", "model", provider,
                                  initial or {"status": "RETRY"}, verify)

    def make_run(self, directory):
        outdir = Path(directory) / "run"
        with contextlib.redirect_stdout(io.StringIO()):
            evaluation.main(["run", "--cases", str(self.catalog_path), "--outdir", str(outdir)])
        return outdir

    def completed_review(self, directory, run, verdict="correct"):
        rows = evaluation.read_review(run / "blind-review.csv")
        rows[0].update(verdict=verdict, reviewer="Independent Test Reviewer", independent_review="yes", review_seconds="3.5")
        path = Path(directory) / "completed.csv"
        evaluation.write_csv(path, rows)
        return path, rows

    def review(self, directory, run, reviews):
        with contextlib.redirect_stdout(io.StringIO()):
            return evaluation.review(argparse.Namespace(run_dir=run, reviews=reviews,
                                                         outdir=Path(directory) / "review"))

    def test_dry_run_never_constructs_provider_or_calls_checker(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(evaluation, "OllamaProvider") as provider, patch.object(evaluation, "run_verify") as checker:
            out = self.make_run(directory)
            provider.assert_not_called()
            checker.assert_not_called()
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["mode"], "dry-run")
            self.assertIsNone(manifest["summary"]["semantic_accuracy"])
            self.assertTrue(all(v["model_calls"] == 0 for v in manifest["summary"]["by_group"].values()))

    def test_model_requires_explicit_endpoint_and_model_before_creating_output(self):
        for extra in ([], ["--base", "http://127.0.0.1:11434"], ["--model", "test"]):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory, patch.object(evaluation, "OllamaProvider") as provider, contextlib.redirect_stderr(io.StringIO()):
                out = Path(directory) / "run"
                with self.assertRaises(SystemExit):
                    evaluation.main(["run", "--mode", "model", "--cases", str(self.catalog_path), "--outdir", str(out), *extra])
                provider.assert_not_called()
                self.assertFalse(out.exists())

    def test_network_options_rejected_in_offline_modes(self):
        for mode in ("dry-run", "fixture"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()), patch.object(evaluation, "OllamaProvider") as provider:
                with self.assertRaises(SystemExit):
                    evaluation.main(["run", "--mode", mode, "--cases", str(self.catalog_path), "--outdir", str(Path(directory) / "run"), "--base", "http://example.invalid", "--model", "test"])
                provider.assert_not_called()

    def test_initial_ok_env_and_human_never_call_model(self):
        for status in ("OK", "NEEDS_ENV", "NEEDS_HUMAN"):
            with self.subTest(status=status):
                provider = Provider([])
                result = self.arm(provider, initial={"status": status})
                self.assertEqual(provider.requests, [])
                self.assertEqual(result["model_calls"], 0)
                self.assertEqual(result["output_latex"], self.case["original_latex"])

    def test_candidate_environment_failure_stops_retries(self):
        provider = Provider(["a_1+b", "unused"])
        result = self.arm(provider, verify=lambda _: {"status": "NEEDS_ENV", "reason": "missing_dependency"})
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["outcome"], "environment_failure")
        self.assertEqual(result["output_latex"], self.case["original_latex"])

    def test_rejected_candidates_are_preserved_and_budget_is_two(self):
        provider = Provider(["a_", "b_", "third must not run"])
        result = self.arm(provider, verify=lambda _: {"status": "RETRY", "reason": "syntax"})
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual([a["candidate_latex"] for a in result["attempts"]], ["a_", "b_"])
        self.assertTrue(all(a["decision"] == "rejected_by_syntax_checker" for a in result["attempts"]))
        self.assertEqual(result["output_latex"], self.case["original_latex"])

    def test_network_error_is_both_environment_failure_and_no_candidate(self):
        provider = Provider([None])
        original = provider.repair_formula

        def fail(node):
            result = original(node)
            provider.last_trace["reason"] = "network_error"
            return result

        provider.repair_formula = fail
        result = self.arm(provider)
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["outcome"], "environment_failure")
        self.assertTrue(result["no_candidate"])
        self.assertTrue(result["provider_environment_failure"])

    def test_reference_and_injection_labels_never_enter_model_input(self):
        provider = Provider(["a_1+b"])
        self.arm(provider)
        self.assertEqual(provider.requests, [{"id": self.case["id"], "type": "formula", "data": {"latex": self.case["original_latex"]}}])

    def test_actual_call_accounting_does_not_count_provider_invocation_as_request(self):
        result = self.arm(Provider([None], calls=0))
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["outcome"], "no_candidate")

    def test_fixture_calls_never_count_as_model_calls(self):
        provider = evaluation.FixtureModel({"model_with_skill": {self.case["id"]: ["a_1+b"]}}, "model_with_skill")
        result = evaluation.run_arm(self.case, "model_with_skill", "fixture", provider,
                                    {"status": "RETRY"}, lambda _: {"status": "OK"})
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["fixture_calls"], 1)
        self.assertTrue(result["candidate_accepted_by_syntax_checker"])

    def test_group_order_rotates_and_stays_deterministic(self):
        first = list(evaluation.sequence(self.catalog["cases"]))
        second = list(evaluation.sequence(self.catalog["cases"]))
        self.assertEqual(first, second)
        self.assertEqual([first[i][1] for i in (0, 3, 6)], list(evaluation.GROUPS))
        self.assertEqual(len({(c["id"], g) for c, g in first}), 9)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            keep = Path(directory) / "keep"
            keep.write_text("retained")
            with self.assertRaises(SystemExit):
                evaluation.main(["run", "--cases", str(self.catalog_path), "--outdir", directory])
            self.assertEqual(keep.read_text(), "retained")
            self.assertFalse((Path(directory) / "manifest.json").exists())

    def test_review_tampered_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path, rows = self.completed_review(directory, run)
            rows[0]["candidate_latex"] = "x+999"
            evaluation.write_csv(path, rows)
            with self.assertRaisesRegex(ValueError, "immutable"):
                self.review(directory, run, path)
            self.assertFalse((Path(directory) / "review").exists())

    def test_review_tampered_candidate_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path, rows = self.completed_review(directory, run)
            rows[0]["candidate_sha256"] = "0" * 64
            evaluation.write_csv(path, rows)
            with self.assertRaisesRegex(ValueError, "immutable"):
                self.review(directory, run, path)

    def test_no_completed_review_cannot_generate_accuracy(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            with self.assertRaisesRegex(ValueError, "no completed"):
                self.review(directory, run, run / "blind-review.csv")

    def test_completed_review_requires_reviewer_independence_and_verdict(self):
        for field, value in (("reviewer", ""), ("independent_review", "no"), ("verdict", ""), ("verdict", "syntax_OK")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                run = self.make_run(directory)
                path, rows = self.completed_review(directory, run)
                rows[0][field] = value
                evaluation.write_csv(path, rows)
                with self.assertRaises(ValueError):
                    self.review(directory, run, path)

    def test_partial_review_discloses_pending_and_only_determinate_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path, rows = self.completed_review(directory, run)
            self.review(directory, run, path)
            report = json.loads((Path(directory) / "review/review-report.json").read_text())
            self.assertEqual(sum(v["reviewed"] for v in report["summary"].values()), 1)
            self.assertEqual(sum(v["pending"] for v in report["summary"].values()), 8)
            self.assertEqual(report["mode"], "dry-run")
            reviewed = next(v for v in report["summary"].values() if v["reviewed"])
            self.assertEqual(reviewed["determinate_reviews"], 1)
            self.assertAlmostEqual(reviewed["reviewed_coverage"], 1 / 3)
            self.assertIsNone(reviewed["human_time_savings"])

    def test_uncertain_review_does_not_inflate_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path, _ = self.completed_review(directory, run, verdict="uncertain")
            self.review(directory, run, path)
            report = json.loads((Path(directory) / "review/review-report.json").read_text())
            self.assertTrue(all(v["correct_fraction_among_determinate_reviews"] is None for v in report["summary"].values()))

    def test_changed_run_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path, _ = self.completed_review(directory, run)
            with (run / "results.jsonl").open("a") as handle:
                handle.write("{}\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                self.review(directory, run, path)

    def test_duplicate_review_rows_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(directory)
            path, rows = self.completed_review(directory, run)
            evaluation.write_csv(path, [rows[0], rows[0]])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.review(directory, run, path)

    def test_nonfinite_or_negative_review_time_rejected(self):
        for seconds in ("nan", "inf", "-1", "0"):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory() as directory:
                run = self.make_run(directory)
                path, rows = self.completed_review(directory, run)
                rows[0]["review_seconds"] = seconds
                evaluation.write_csv(path, rows)
                with self.assertRaisesRegex(ValueError, "finite and positive"):
                    self.review(directory, run, path)

    def test_model_mode_uses_identical_parameters_and_counts_http_attempts(self):
        payloads = []

        def respond(request, timeout):
            payloads.append(json.loads(request.data))
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": '{"latex":"a_1+b"}'}}]}).encode())

        def verify(latex):
            return {"status": "RETRY" if latex == "a_+b" else "OK"}

        with tempfile.TemporaryDirectory() as directory, patch("docforensics.vlm.urllib.request.urlopen", side_effect=respond), patch.object(evaluation, "run_verify", side_effect=verify), contextlib.redirect_stdout(io.StringIO()):
            out = Path(directory) / "run"
            code = evaluation.main(["run", "--cases", str(self.catalog_path), "--outdir", str(out),
                                    "--mode", "model", "--base", "http://example.invalid", "--model", "test-model",
                                    "--seed", "17", "--max-tokens", "123"])
            self.assertEqual(code, 0)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertTrue(manifest["controlled_configuration_verified"])
            self.assertEqual(sum(v["model_calls"] for v in manifest["summary"]["by_group"].values()), 2)
            self.assertEqual(len(payloads), 2)
            for key in ("model", "seed", "temperature", "max_tokens"):
                self.assertEqual(payloads[0][key], payloads[1][key])
            self.assertEqual(payloads[0]["messages"][1], payloads[1]["messages"][1])
            self.assertNotEqual(payloads[0]["messages"][0], payloads[1]["messages"][0])
            self.assertIsNone(manifest["summary"]["semantic_accuracy"])

    def test_interrupted_run_keeps_completed_arms_but_cannot_be_reviewed(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            out = Path(directory) / "run"
            original = evaluation.run_arm
            calls = []

            def interrupt_after_first(*args, **kwargs):
                if calls:
                    raise KeyboardInterrupt()
                calls.append(1)
                return original(*args, **kwargs)

            with patch.object(evaluation, "run_arm", side_effect=interrupt_after_first), self.assertRaises(KeyboardInterrupt):
                evaluation.main(["run", "--cases", str(self.catalog_path), "--outdir", str(out)])
            self.assertEqual(json.loads((out / "manifest.json").read_text())["status"], "running")
            self.assertEqual(len((out / "results.jsonl").read_text().splitlines()), 1)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                self.review(directory, out, out / "blind-review.csv")

    def test_duplicate_case_and_missing_source_hash_rejected(self):
        for corrupt in ("duplicate", "missing_hash"):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory:
                catalog = copy.deepcopy(self.catalog)
                if corrupt == "duplicate":
                    catalog["cases"].append(catalog["cases"][0])
                else:
                    del catalog["cases"][0]["source"]["sha256"]
                path = Path(directory) / "cases.json"
                path.write_text(json.dumps(catalog))
                with self.assertRaises(ValueError):
                    evaluation.read_catalog(path)


if __name__ == "__main__":
    unittest.main()
