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

    def test_non_total_labels_containing_total_substrings_are_treated_as_data_rows(self):
        non_total_tables = [
            [["Test", "Value"], ["LDL", "100"], ["Total Cholesterol", "185"]],
            [["Item", "Amount"], ["A", "60"], ["Subtotal", "100"]],
            [["项目", "金额"], ["甲", "5"], ["非合计项", "10"]],
        ]
        for rows in non_total_tables:
            with self.subTest(last_label=rows[-1][0]):
                self.assertEqual(audit_module.audit({"rows": rows}), ("OK", "", ""))
        # Reference col total sums all data rows including "Total Cholesterol"
        cholesterol_rows = [["Test", "Value"], ["LDL", "100"], ["Total Cholesterol", "185"]]
        self.assertEqual(
            audit_module.audit({"rows": cholesterol_rows, "expected": {"totals": {"col:1": "285"}}}),
            ("OK", "", ""),
        )
        # Exact normalized total labels (trimmed, case-insensitive) still audit as total rows
        for label in ("合计", " 总计 ", "Total", " TOTAL "):
            with self.subTest(total_label=label):
                bad_rows = [["Item", "Amount"], ["A", "1.5"], ["B", "2.5"], [label, "4.5"]]
                self.assertEqual(audit_module.audit({"rows": bad_rows})[:2], ("RETRY", "sum_mismatch"))
                good_rows = [["Item", "Amount"], ["A", "1.5"], ["B", "2.5"], [label, "4.0"]]
                self.assertEqual(audit_module.audit({"rows": good_rows}), ("OK", "", ""))

    def test_scientific_repr_finite_float_scalars_and_non_finite_values(self):
        small_rows = [["item", "amount"], ["A", 0.00001], ["B", 0.00002], ["total", 0.00003]]
        self.assertEqual(
            audit_module.audit({"rows": small_rows, "expected": {"totals": {"col:1": 0.00003}}}),
            ("OK", "", ""),
        )
        neg_rows = [["item", "amount"], ["A", -0.00001], ["B", 0.00003], ["total", "0.00002"]]
        self.assertEqual(audit_module.audit({"rows": neg_rows}), ("OK", "", ""))
        # Non-finite floats/Decimals and scientific-notation strings remain rejected
        for bad_ref in (float("nan"), float("inf"), float("-inf"),
                        audit_module.Decimal("NaN"), audit_module.Decimal("Infinity"), "1e-05"):
            with self.subTest(bad_ref=bad_ref):
                status, reason, _ = audit_module.audit({"rows": self.rows, "expected": {"totals": {"col:1": bad_ref}}})
                self.assertEqual((status, reason), ("NEEDS_HUMAN", "bad_expectation"))
        sci_str_rows = [["item", "amount"], ["A", "1e-05"], ["B", "0.00002"], ["total", "0.00003"]]
        self.assertEqual(audit_module.audit({"rows": sci_str_rows})[:2], ("RETRY", "bad_number"))


if __name__ == "__main__":
    unittest.main()
