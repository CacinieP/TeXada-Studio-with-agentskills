"""Regression tests for report integrity and bounded local checker execution."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import evaluate_cases as evaluator


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        catalog = evaluator.read_catalog(evaluator.REPO / "samples/evaluation/cases.json")
        self.cases = {case["id"]: case for case in catalog["cases"]}

    def test_real_table_checker_matches_decimal_case(self):
        result = evaluator.run_case(self.cases["T01"], 5)
        self.assertTrue(result["expectation_match"])
        self.assertEqual(result["observed"]["outcome"], "checker-result")

    def test_crash_is_not_counted_as_invalid_input_rejection(self):
        proc = subprocess.CompletedProcess([], 1, "", "IndexError: missing cell")
        with patch.object(evaluator.subprocess, "run", return_value=proc):
            result = evaluator.run_case(self.cases["T11"], 1)
        self.assertFalse(result["expectation_match"])
        self.assertEqual(result["observed"]["outcome"], "process-error")
        self.assertIsNone(result["observed"]["status"])

    def test_matching_status_with_wrong_exit_code_is_not_green(self):
        proc = subprocess.CompletedProcess([], 9, json.dumps({"id": "T01", "status": "OK"}) + "\n", "")
        with patch.object(evaluator.subprocess, "run", return_value=proc):
            result = evaluator.run_case(self.cases["T01"], 1)
        self.assertFalse(result["expectation_match"])
        self.assertEqual(result["observed"]["outcome"], "invalid-exit-code")

    def test_nonscalar_checker_status_is_invalid_output(self):
        for status in ([], {}):
            proc = subprocess.CompletedProcess([], 0, json.dumps({"status": status}) + "\n", "")
            with self.subTest(status=status), patch.object(evaluator.subprocess, "run", return_value=proc):
                result = evaluator.run_case(self.cases["T01"], 1)
                self.assertFalse(result["expectation_match"])
                self.assertEqual(result["observed"]["outcome"], "invalid-output")

    def test_timeout_is_reported_with_partial_output(self):
        error = subprocess.TimeoutExpired(["checker"], 1, output=b"partial", stderr=b"diagnostic")
        with patch.object(evaluator.subprocess, "run", side_effect=error):
            result = evaluator.run_case(self.cases["F01"], 1)
        self.assertFalse(result["expectation_match"])
        self.assertEqual(result["observed"]["outcome"], "timeout")
        self.assertEqual(result["observed"]["stdout"], "partial")

    def test_declared_reason_must_match(self):
        proc = subprocess.CompletedProcess([], 0, json.dumps({"id": "T02", "status": "RETRY", "reason": "bad_number"}) + "\n", "")
        with patch.object(evaluator.subprocess, "run", return_value=proc):
            result = evaluator.run_case(self.cases["T02"], 1)
        self.assertFalse(result["expectation_match"])

    def test_known_gaps_stay_out_of_contract_counts(self):
        rows = [
            {"checker": "formula", "evaluation_group": "contract", "expectation_match": True,
             "observed": {"outcome": "checker-result"}},
            {"checker": "formula", "evaluation_group": "known-gap", "expectation_match": False,
             "observed": {"outcome": "process-error"}},
        ]
        summary = evaluator.summarize(rows)
        self.assertEqual(summary["all"]["unmatched"], 1)
        self.assertEqual(summary["by_group"]["contract"]["total"], 1)
        self.assertEqual(summary["by_group"]["known-gap"]["unmatched"], 1)

    def test_existing_output_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "report.json"
            sentinel.write_text("keep existing evidence", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                evaluator.main(["--outdir", directory])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(sentinel.read_text(), "keep existing evidence")
            self.assertFalse((Path(directory) / "report.md").exists())

    def test_nul_argv_is_rejected_before_output_or_process_start(self):
        case = json.loads(json.dumps(self.cases["F01"]))
        case["input"]["latex"] = "x\x00+y"
        data = {"schema_version": 1, "synthetic": True, "cases": [case]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            outdir = Path(directory) / "report"
            with contextlib.redirect_stderr(io.StringIO()), \
                    patch.object(evaluator.subprocess, "run") as run, \
                    self.assertRaises(SystemExit) as error:
                evaluator.main(["--cases", str(path), "--outdir", str(outdir)])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()
            self.assertFalse(outdir.exists())

    def test_nonscalar_catalog_discriminators_are_rejected(self):
        for key in ("checker", "evaluation_group", "status"):
            for value in ([], {}):
                with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as directory:
                    case = json.loads(json.dumps(self.cases["F01"]))
                    target = case["expected"] if key == "status" else case
                    target[key] = value
                    data = {"schema_version": 1, "synthetic": True, "cases": [case]}
                    path = Path(directory) / "cases.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        evaluator.read_catalog(path)

    def test_duplicate_case_id_is_rejected(self):
        data = {"schema_version": 1, "synthetic": True, "cases": [self.cases["T01"], self.cases["T01"]]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate case id"):
                evaluator.read_catalog(path)


if __name__ == "__main__":
    unittest.main()
