"""Invalid reference totals are input errors, never model repair requests."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import pipeline, state

spec = importlib.util.spec_from_file_location("table_audit", pipeline.AUDIT)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class TableExpectationTests(unittest.TestCase):
    rows = [["item", "amount"], ["A", "1.5"], ["B", "2.5"], ["total", "4"]]

    def test_invalid_reference_total_is_input_error_even_when_table_needs_repair(self):
        for value in (None, True, False, "unknown", "NaN", "Infinity", [], {}):
            for total in ("4", "5"):
                rows = [*self.rows[:-1], ["total", total]]
                with self.subTest(value=value, total=total):
                    status, reason, _ = audit_module.audit({"rows": rows, "expected": {"totals": {"col:1": value}}})
                    self.assertEqual((status, reason), ("NEEDS_HUMAN", "bad_expectation"))

    def test_invalid_reference_total_never_invokes_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            node = {"id": "t-1", "data": {"rows": self.rows, "expected": {"totals": {"col:1": "unknown"}}}}
            provider = Mock()
            self.assertEqual(pipeline.process_table(directory, "doc", node, provider), "NEEDS_HUMAN")
            provider.repair_table.assert_not_called()
            self.assertEqual(state.load_events(directory)[-1]["checker_reason"], "bad_expectation")

    def test_invalid_reference_keys_precede_table_total_mismatch(self):
        rows = [*self.rows[:-1], ["total", "5"]]
        for key in ("invalid:1", "col:-1", "row:-1", "col:99", "row:99", "col:one", "col:1:2", 1):
            with self.subTest(key=key):
                result = audit_module.audit({"rows": rows, "expected": {"totals": {key: 4}}})
                self.assertEqual(result[:2], ("NEEDS_HUMAN", "bad_expectation"))

    def test_reference_range_is_checked_after_repairable_target_shape(self):
        cases = [([["item", "amount"], ["A", "4"]], {"n_cols": 3, "totals": {"col:2": 4}}),
                 ([["item", "amount"], ["A", "4"]], {"n_rows": 3, "totals": {"row:2": 4}})]
        for rows, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(audit_module.audit({"rows": rows, "expected": expected})[:2],
                                 ("RETRY", "shape_mismatch"))

    def test_valid_reference_totals_keep_exact_comparison(self):
        for value in (4, 4.0, "4.00"):
            with self.subTest(value=value):
                self.assertEqual(audit_module.audit({"rows": self.rows, "expected": {"totals": {"col:1": value}}})[0], "OK")
        self.assertEqual(audit_module.audit({"rows": self.rows, "expected": {"totals": {"col:1": "5"}}})[:2],
                         ("RETRY", "sum_mismatch"))


if __name__ == "__main__":
    unittest.main()
