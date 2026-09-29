"""Check distributable Studio scenarios with real parsers and no model/compiler."""

from collections import Counter
import json
from pathlib import PurePosixPath
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_static_assets import ROOT, studio


class SampleContractTest(unittest.TestCase):
    def check_sample(self, name, expected_statuses, expected_edits):
        source = (ROOT / "samples" / "docs" / name).read_text(encoding="utf-8")
        with patch.object(studio.PROVIDER, "repair_formula", side_effect=AssertionError("unexpected model call")) as model:
            problems = studio._analyze(source)
            candidate, edits = studio._apply_fixes(source, [])
        model.assert_not_called()
        self.assertEqual([p["status"] for p in problems], expected_statuses)
        self.assertEqual(len(edits), expected_edits)
        if expected_edits == 0:
            self.assertEqual(candidate, source)
        else:
            self.assertIn("105", candidate)
            self.assertEqual(edits[0]["before"], "115")
            self.assertEqual(edits[0]["after"], "105")
            self.assertEqual(studio._analyze(candidate), [])

    def test_clean_control_is_unchanged(self):
        self.check_sample("clean-control.tex", [], 0)

    def test_semantic_error_is_not_a_syntax_failure(self):
        self.check_sample("semantic-boundary.tex", [], 0)

    def test_unsupported_tables_are_preserved(self):
        self.check_sample("manual-review.tex", ["NEEDS_HUMAN"] * 3, 0)

    def test_report_total_is_a_deterministic_candidate(self):
        self.check_sample("report-01.tex", ["RETRY"], 1)


class LatexSampleCatalogTest(unittest.TestCase):
    """Published teaching examples: extraction and candidate handling, not truth."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "samples" / "studio-cases.json").read_text(encoding="utf-8"))
        cls.cases = cls.catalog["cases"]

    def source(self, case):
        return (ROOT / "samples" / case["file"]).read_text(encoding="utf-8")

    def setUp(self):
        compiler = patch.object(studio, "_studio_compile", side_effect=AssertionError("sample contracts must not compile"))
        compiler.start()
        self.addCleanup(compiler.stop)

    def test_catalog_has_unique_safe_inputs_and_explicit_evidence_limits(self):
        self.assertEqual(self.catalog["schema_version"], 1)
        self.assertIs(self.catalog["synthetic"], True)
        self.assertEqual(self.catalog["license"], "AGPL-3.0-only")
        self.assertTrue(self.catalog["scope"])
        self.assertTrue(self.cases)
        self.assertEqual(len({case["case_id"] for case in self.cases}), len(self.cases))
        self.assertEqual(len({case["file"] for case in self.cases}), len(self.cases))
        self.assertEqual(
            {case["file"] for case in self.cases},
            {f"docs/{path.name}" for path in (ROOT / "samples" / "docs").glob("math-*.tex")},
        )
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                self.assertRegex(case["case_id"], r"^S[0-9]{2,}$")
                path = PurePosixPath(case["file"])
                self.assertEqual(path.parts[0], "docs")
                self.assertEqual(len(path.parts), 2)
                self.assertNotIn("..", path.parts)
                self.assertEqual(path.suffix, ".tex")
                self.assertEqual((ROOT / "samples" / path).resolve().parent, (ROOT / "samples" / "docs").resolve())
                self.assertTrue(case["source"])
                self.assertTrue(case["intent"])
                self.assertTrue(case["semantic_boundary"])
                self.assertIsInstance(case["extraction_boundary"], list)
                if not case["expected_analysis"]["formula_checks"]:
                    self.assertTrue(case["extraction_boundary"], "zero extracted formulas needs an explicit scope explanation")
                self.assertIs(case["repair_expectation"]["model_success_not_guaranteed"], True)
                self.assertEqual(case["repair_expectation"]["deterministic_edits"], 0)
                for reference in case["reference_edits"]:
                    self.assertEqual(reference["origin"], "author_supplied_not_model_output")
                    self.assertEqual(reference["expected_status"], "OK")
                    self.assertEqual(self.source(case).count(f"${reference['original']}$"), 1)

    def test_catalog_samples_are_discoverable_and_served_unchanged(self):
        with tempfile.TemporaryDirectory() as uploads, patch.object(studio, "STUDIO_DOCS", uploads):
            files = studio.studio_files(token=studio.TOKEN)["files"]
            for case in self.cases:
                with self.subTest(case=case["case_id"]):
                    name = PurePosixPath(case["file"]).name
                    self.assertIn(name, files)
                    self.assertEqual(studio.studio_file(name=name, token=studio.TOKEN)["content"], self.source(case))

    def test_real_checker_matches_declared_extraction_and_analysis(self):
        verify = studio._verify_formula
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                checks = []

                def capture_check(latex):
                    result = verify(latex)
                    checks.append({"latex": latex, "status": result["status"]})
                    return result

                with patch.object(studio, "_verify_formula", side_effect=capture_check), patch.object(
                    studio.PROVIDER, "repair_formula", side_effect=AssertionError("analysis must not request a model")
                ) as model:
                    problems = studio._analyze(self.source(case))
                model.assert_not_called()
                expected = case["expected_analysis"]
                self.assertEqual(checks, expected["formula_checks"])
                self.assertEqual(len(problems), expected["problem_count"])
                self.assertEqual(dict(Counter(p["status"] for p in problems)), expected["status_counts"])
                self.assertEqual(dict(Counter(p["type"] for p in problems)), expected["problem_types"])
                self.assertNotIn("NEEDS_ENV", {check["status"] for check in checks})

    def test_absent_candidates_preserve_text_and_respect_request_budget(self):
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                provider = Mock()
                provider.repair_formula.return_value = None
                provider.last_trace = {"provider": "sample-test-double", "model_calls": 0, "model_called": False}
                events = []
                source = self.source(case)
                with patch.object(studio.PROVIDER, "repair_formula", side_effect=AssertionError("real model prohibited")):
                    candidate, edits = studio._apply_fixes(
                        source, [], provider=provider, emit=lambda action, **fields: events.append({"action": action, **fields})
                    )
                expected = case["repair_expectation"]
                self.assertEqual(provider.repair_formula.call_count, expected["model_provider_calls_without_candidates"])
                self.assertEqual(len(edits), expected["edits_without_candidates"])
                self.assertTrue(expected["preserve_original_without_candidates"])
                self.assertEqual(candidate, source)
                retry_inputs = [check["latex"] for check in case["expected_analysis"]["formula_checks"] if check["status"] == "RETRY"]
                self.assertEqual(
                    Counter(call.args[0]["data"]["latex"] for call in provider.repair_formula.call_args_list),
                    Counter({latex: 2 * retry_inputs.count(latex) for latex in retry_inputs}),
                )
                self.assertFalse(any(event["action"] == "CANDIDATE_ACCEPTED" for event in events))
                self.assertEqual(sum(event["provider_trace"]["model_calls"] for event in events if event["action"] == "PROVIDER_RESULT"), 0)

    def test_author_candidates_only_change_declared_formula_spans(self):
        for case in self.cases:
            references = case["reference_edits"]
            if not references:
                continue
            with self.subTest(case=case["case_id"]):
                source = self.source(case)
                by_original = {item["original"]: item["candidate"] for item in references}
                self.assertEqual(len(by_original), len(references))
                provider = Mock()
                provider.repair_formula.side_effect = lambda node: by_original[node["data"]["latex"]]
                provider.last_trace = {"provider": "author-reference-test-double", "model_calls": 0, "model_called": False}
                with patch.object(studio.PROVIDER, "repair_formula", side_effect=AssertionError("real model prohibited")):
                    candidate, edits = studio._apply_fixes(source, [], provider=provider)
                # An independent whole-document oracle preserves every character
                # outside the author's explicitly declared formula spans.
                spans = sorted((source.index(f"${old}$"), f"${old}$", f"${new}$") for old, new in by_original.items())
                pieces, cursor = [], 0
                for start, old, new in spans:
                    pieces.extend((source[cursor:start], new))
                    cursor = start + len(old)
                pieces.append(source[cursor:])
                self.assertEqual(candidate, "".join(pieces))
                self.assertEqual(
                    [(edit["before"], edit["after"]) for edit in edits],
                    [(old[1:-1], new[1:-1]) for _, old, new in spans],
                )
                self.assertTrue(all(edit["skill"] == "doc-formula-verify" for edit in edits))
                self.assertEqual(provider.repair_formula.call_count, len(references))


if __name__ == "__main__":
    unittest.main()
