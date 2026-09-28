"""Check distributable Studio scenarios with real parsers and no model/compiler."""

import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
