"""Table candidate scope guard, provider contract, and three-path pipeline verification."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import pipeline, state, vlm  # noqa: E402
from docforensics.__main__ import write_report  # noqa: E402
from docforensics.skill_selection import load_catalog, load_selected_skill  # noqa: E402
from docforensics.skills_runtime import load_table_skill  # noqa: E402
from docforensics.table_repair import assess_table_candidate, is_total_row  # noqa: E402


class TableScopeGuardTest(unittest.TestCase):
    def test_allows_total_row_numeric_recomputation_preserving_headers_and_data(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        candidate = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4"]]
        verdict = assess_table_candidate(original, candidate, {"n_rows": 4, "n_cols": 2})
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["method"], "recompute_total_row")

    def test_allows_filling_missing_cells_in_existing_short_total_row(self):
        original = [["item", "amount"], ["A", "1.5"], ["B", "2.5"], ["total"]]
        candidate = [["item", "amount"], ["A", "1.5"], ["B", "2.5"], ["total", "4.0"]]
        verdict = assess_table_candidate(original, candidate, {"n_rows": 4, "n_cols": 2})
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["method"], "complete_total_row")

    def test_allows_appending_missing_total_row_when_declared_in_expected_shape(self):
        original = [["月份", "收入", "支出"], ["1月", "100", "80"], ["2月", "120", "90"]]
        candidate = [["月份", "收入", "支出"], ["1月", "100", "80"], ["2月", "120", "90"], ["合计", "220", "170"]]
        verdict = assess_table_candidate(original, candidate, {"n_rows": 4, "n_cols": 3})
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["method"], "append_total_row")

    def test_rejects_data_row_mutation_even_when_new_sum_is_internally_consistent(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        # Mutates B from 2.5 to 3.0 to match the wrong total 4.5
        candidate = [["项目", "金额"], ["A", "1.5"], ["B", "3.0"], ["合计", "4.5"]]
        verdict = assess_table_candidate(original, candidate)
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["reason"], "table_data_modified")
        self.assertEqual(verdict["row_index"], 2)
        self.assertEqual(verdict["col_index"], 1)

    def test_rejects_header_and_total_label_modifications(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        header_changed = [["Item", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4"]]
        self.assertEqual(assess_table_candidate(original, header_changed)["reason"], "table_header_modified")
        label_changed = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["总计", "4"]]
        self.assertEqual(assess_table_candidate(original, label_changed)["reason"], "table_total_label_modified")

    def test_rejects_unchanged_and_out_of_scope_candidates(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        self.assertEqual(assess_table_candidate(original, copy.deepcopy(original))["reason"], "unchanged_candidate")
        extra_row = [*original, ["备注", "0"]]
        self.assertEqual(assess_table_candidate(original, extra_row)["reason"], "table_scope_violation")
        non_total_append = [["月份", "收入"], ["1月", "100"], ["2月", "120"]]
        bad_append = [*non_total_append, ["3月", "220"]]
        self.assertEqual(assess_table_candidate(non_total_append, bad_append, {"n_rows": 4, "n_cols": 2})["reason"],
                         "table_scope_violation")

    def test_exact_total_row_labels_reject_substring_false_positives(self):
        for label in ("合计", " 总计 ", "total", "Total", " TOTAL "):
            self.assertTrue(is_total_row([label, "10"]), msg=label)
        for non_total, old_val, new_val in (
            ("Total Cholesterol", "185", "165"),
            ("Subtotal", "100", "165"),
            ("非合计项", "10", "165"),
        ):
            with self.subTest(label=non_total):
                self.assertFalse(is_total_row([non_total, old_val]))
                original = [["Metric", "Value"], ["HDL", "55"], ["LDL", "110"], [non_total, old_val]]
                candidate = [["Metric", "Value"], ["HDL", "55"], ["LDL", "110"], [non_total, new_val]]
                verdict = assess_table_candidate(original, candidate, {"n_rows": 4, "n_cols": 2})
                self.assertFalse(verdict["allowed"])
                self.assertEqual(verdict["reason"], "table_data_modified")
                self.assertEqual(verdict["row_index"], 3)
                self.assertEqual(verdict["col_index"], 1)
        # Appending a non-exact total label such as "Subtotal" is also out of scope
        base = [["Item", "Amount"], ["A", "60"], ["B", "40"]]
        subtotal_append = [*base, ["Subtotal", "100"]]
        self.assertEqual(
            assess_table_candidate(base, subtotal_append, {"n_rows": 4, "n_cols": 2})["reason"],
            "table_scope_violation",
        )

    def test_rejects_truncating_extra_cells_in_existing_total_row(self):
        original = [["item", "amount"], ["A", "1.5"], ["B", "2.5"], ["total", "4.0", "extra"]]
        candidate = [["item", "amount"], ["A", "1.5"], ["B", "2.5"], ["total", "4.0"]]
        verdict = assess_table_candidate(original, candidate, {"n_rows": 4, "n_cols": 2})
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["reason"], "table_scope_violation")
        self.assertEqual(verdict["row_index"], 3)

    def test_preserves_scalar_int_and_float_cells_serialized_as_strings(self):
        original = [["item", 2024], [1, 2.5], [2, 0.00001], ["total", 9.9]]
        candidate = [["item", "2024"], ["1", "2.5"], ["2", "0.00001"], ["total", "2.50001"]]
        verdict = assess_table_candidate(original, candidate, {"n_rows": 4, "n_cols": 2})
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["method"], "recompute_total_row")

        # Unchanged scalar table serialized to strings without any actual edit is unchanged_candidate
        same_as_strings = [["item", "2024"], ["1", "2.5"], ["2", "0.00001"], ["total", "9.9"]]
        self.assertEqual(assess_table_candidate(original, same_as_strings)["reason"], "unchanged_candidate")

        # Actual value or formatting changes remain rejected as table_data_modified
        rejected_pairs = [
            (1, "2"),
            (1, 1.0),
            (1.0, 1),
            (1, "1.0"),
            (1.0, "1"),
            (1, " 1 "),
            ("1", "1.0"),
            (" 1 ", "1"),
            (2.5, "2.50"),
            (0.00001, "0.00002"),
            (0.00001, "1e-05"),
        ]
        for orig_cell, cand_cell in rejected_pairs:
            with self.subTest(orig_cell=orig_cell, cand_cell=cand_cell):
                orig_grid = [["item", "amount"], ["A", orig_cell], ["total", "9"]]
                cand_grid = [["item", "amount"], ["A", cand_cell], ["total", "1"]]
                verdict = assess_table_candidate(orig_grid, cand_grid)
                self.assertFalse(verdict["allowed"])
                self.assertEqual(verdict["reason"], "table_data_modified")
                self.assertEqual(verdict["row_index"], 1)
                self.assertEqual(verdict["col_index"], 1)

    def test_rejects_non_finite_floats_in_original_or_candidate_grids(self):
        valid = [["item", "amount"], ["A", "1"], ["total", "1"]]
        for bad_float in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad_float=bad_float):
                bad_orig = [["item", "amount"], ["A", bad_float], ["total", "1"]]
                self.assertEqual(assess_table_candidate(bad_orig, valid)["reason"], "bad_original")
                bad_cand = [["item", "amount"], ["A", "1"], ["total", bad_float]]
                self.assertEqual(assess_table_candidate(valid, bad_cand)["reason"], "bad_candidate_type")


class TablePipelineThreePathsTest(unittest.TestCase):
    def test_path1_normal_repair_accepts_valid_total_fix_and_records_diff(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        repaired = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.0"]]
        node = {"id": "t-201", "type": "table", "data": {"rows": original, "expected": {"n_rows": 4, "n_cols": 2}}}
        provider = vlm.OpenAICompatibleProvider(skill_mode="on")
        with tempfile.TemporaryDirectory() as directory, patch.object(
                provider, "_chat", return_value={"choices": [{"message": {"content": json.dumps({"rows": repaired})}}],
                                                 "usage": {"prompt_tokens": 20, "completion_tokens": 12, "total_tokens": 32}}):
            provider.last_trace = {"model_calls": 1, "model_called": True}
            # Let repair_table call mocked _chat and real run_audit verify
            status = pipeline.process_table(directory, "exam-01", node, provider, run_id="r-ok")
            events = state.load_events(directory)
            report = Path(write_report(directory, provider, run_id="r-ok")).read_text()
        self.assertEqual(status, "OK")
        self.assertTrue(any(e["action"] == "CANDIDATE_SCOPE" and e["scope"]["allowed"] for e in events))
        self.assertTrue(any(e["action"] == "CANDIDATE_ACCEPTED" for e in events))
        terminal = events[-1]
        self.assertTrue(terminal["repaired"])
        self.assertEqual(terminal["original_rows"], original)
        self.assertEqual(terminal["candidate_rows"], repaired)
        self.assertIn("--- original_rows", report)
        self.assertIn("+++ candidate_rows", report)

    def test_path2_unauthorized_data_mutation_is_rejected_even_when_checker_passes(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        # Both attempts mutate data row B so the sum equals 4.5 (passes audit_table.py!)
        drifted_1 = [["项目", "金额"], ["A", "1.5"], ["B", "3.0"], ["合计", "4.5"]]
        drifted_2 = [["项目", "金额"], ["A", "2.0"], ["B", "2.5"], ["合计", "4.5"]]
        node = {"id": "t-drift", "type": "table", "data": {"rows": copy.deepcopy(original), "expected": {"n_rows": 4, "n_cols": 2}}}
        provider = vlm.OpenAICompatibleProvider(skill_mode="off")
        replies = [
            {"choices": [{"message": {"content": json.dumps({"rows": drifted_1})}}]},
            {"choices": [{"message": {"content": json.dumps({"rows": drifted_2})}}]},
        ]
        prompts = []
        def fake_chat(prompt, **_kwargs):
            prompts.append(json.loads(prompt))
            provider.last_trace.update(model_called=True, model_calls=1)
            return replies.pop(0)

        with tempfile.TemporaryDirectory() as directory, patch.object(provider, "_chat", side_effect=fake_chat):
            status = pipeline.process_table(directory, "doc", node, provider, run_id="r-drift")
            events = state.load_events(directory)
            report = Path(write_report(directory, provider, run_id="r-drift")).read_text()
        self.assertEqual(status, "NEEDS_HUMAN")
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[1]["repair_context"]["rejection_reason"], "table_data_modified")
        self.assertFalse(any(e["action"] == "CANDIDATE_ACCEPTED" for e in events))
        rejected = [e for e in events if e["action"] == "CANDIDATE_REJECTED"]
        self.assertEqual(len(rejected), 2)
        self.assertFalse( rejected[0]["scope"]["allowed"])
        self.assertEqual(rejected[0]["scope"]["reason"], "table_data_modified")
        terminal = events[-1]
        self.assertFalse(terminal["repaired"])
        self.assertEqual(terminal["reason"], "table_data_modified")
        self.assertNotIn("candidate_rows", terminal)
        self.assertEqual(node["data"]["rows"], original)
        self.assertIn("table_data_modified", report)

    def test_path3_provider_failure_and_bad_json_preserve_original_without_edits(self):
        original = [["项目", "金额"], ["A", "1.5"], ["B", "2.5"], ["合计", "4.5"]]
        node = {"id": "t-fail", "type": "table", "data": {"rows": copy.deepcopy(original)}}
        provider = vlm.OpenAICompatibleProvider(skill_mode="off")
        replies = [
            {"choices": [{"message": {"content": "not valid json"}}]},
            {"choices": [{"message": {"content": json.dumps({"rows": [["only_one_cell"]]})}}]},
        ]
        def fake_chat(_prompt, **_kwargs):
            provider.last_trace.update(model_called=True, model_calls=1)
            return replies.pop(0)

        with tempfile.TemporaryDirectory() as directory, patch.object(provider, "_chat", side_effect=fake_chat):
            status = pipeline.process_table(directory, "doc", node, provider, run_id="r-fail")
            events = state.load_events(directory)
        self.assertEqual(status, "NEEDS_HUMAN")
        rejected = [e for e in events if e["action"] == "CANDIDATE_REJECTED"]
        self.assertEqual([e["reason"] for e in rejected], ["bad_candidate_json", "bad_candidate_type"])
        terminal = events[-1]
        self.assertFalse(terminal["repaired"])
        self.assertFalse(terminal["resumable"])
        self.assertEqual(terminal["model_calls"], 2)
        self.assertEqual(node["data"]["rows"], original)

    def test_scalar_numeric_grid_repairs_end_to_end_with_string_candidate_cells(self):
        original = [["item", "amount"], ["A", 1], ["B", 0.00001], ["total", 2]]
        repaired = [["item", "amount"], ["A", "1"], ["B", "0.00001"], ["total", "1.00001"]]
        node = {"id": "t-scalar", "type": "table", "data": {"rows": original, "expected": {"n_rows": 4, "n_cols": 2}}}
        provider = vlm.OpenAICompatibleProvider(skill_mode="on")
        with tempfile.TemporaryDirectory() as directory, patch.object(
                provider, "_chat", return_value={"choices": [{"message": {"content": json.dumps({"rows": repaired})}}]}):
            provider.last_trace = {"model_calls": 1, "model_called": True}
            status = pipeline.process_table(directory, "doc", node, provider, run_id="r-scalar")
            events = state.load_events(directory)
        self.assertEqual(status, "OK")
        self.assertTrue(events[-1]["repaired"])
        self.assertEqual(events[-1]["candidate_rows"], repaired)


class TableSkillContractAlignmentTest(unittest.TestCase):
    def test_table_skill_loads_in_runtime_and_selection_without_obsolete_claims(self):
        runtime_skill = load_table_skill()
        catalog = load_catalog()
        self.assertEqual(catalog["doc-table-audit"].version, "1.0.0")
        selected_skill = load_selected_skill(catalog["doc-table-audit"])
        self.assertEqual(runtime_skill.sha256, selected_skill.sha256)
        self.assertNotIn("not_supported", runtime_skill.instructions)
        self.assertNotIn(
            "Table body loading does not turn deterministic arithmetic into a model-generated repair",
            runtime_skill.instructions,
        )
        self.assertNotIn("first cell contains", runtime_skill.instructions.lower())


if __name__ == "__main__":
    unittest.main()
