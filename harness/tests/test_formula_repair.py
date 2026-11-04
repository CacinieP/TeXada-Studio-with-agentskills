"""Source-preserving syntax repairs and drift rejections, without a model."""

from pathlib import Path
import importlib.util
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.formula_repair import assess_candidate, deterministic_candidate, repair_blocker


class DeterministicRepairTests(unittest.TestCase):
    def test_closes_only_missing_group_braces(self):
        cases = [(r"\frac{a}{b", r"\frac{a}{b}"), (r"\sqrt[3]{x", r"\sqrt[3]{x}"),
                 ("x_{i+1", "x_{i+1}"), (r"\frac{\frac{a}{b}}{\frac{c}{d", r"\frac{\frac{a}{b}}{\frac{c}{d}}"),
                 ("  x^{a+b  ", "  x^{a+b  }")]
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(deterministic_candidate(original), expected)
                evidence = assess_candidate(original, expected)
                self.assertTrue(evidence["allowed"])
                self.assertEqual(evidence["method"], "close_trailing_braces")

    def test_escaped_braces_do_not_change_group_balance(self):
        self.assertEqual(deterministic_candidate(r"\frac{\{a\}}{b"), r"\frac{\{a\}}{b}")
        self.assertIsNone(deterministic_candidate(r"\{a\}"))
        self.assertEqual(repair_blocker(r"\frac{a}{b}\}"), None)
        self.assertEqual(repair_blocker(r"x} + {y"), "extra_closing_brace")

    def test_noop_is_not_a_repair(self):
        for value in ("x+1", r"\frac{a}{b}", r"\left(x+1\right)", "x^12^3", "x^2_3"):
            with self.subTest(value=value):
                self.assertIsNone(deterministic_candidate(value))
                self.assertTrue(assess_candidate(value, "  " + value + "  ")["allowed"])

    def test_does_not_guess_missing_operands_or_duplicate_scripts(self):
        for value in ("x+", "a_", "x^", "x^2^3", "x_i_j", "x^{a+b}^{c}", "x_{i+1}_{j}", r"\frac{a}{", r"\left("):
            with self.subTest(value=value):
                self.assertIsNotNone(repair_blocker(value))
                self.assertIsNone(deterministic_candidate(value))

    def test_comments_macros_control_characters_and_extra_closers_are_not_repaired(self):
        for value in ("x% comment", r"\verb|x{|", r"\def\x{a", r"\newcommand{\x}{a", "x}\n", "x\x0b+1", "x\x00", "x} + {y", "$x", "x\\"):
            with self.subTest(value=value):
                self.assertIsNotNone(repair_blocker(value))
                self.assertIsNone(deterministic_candidate(value))
        self.assertEqual(deterministic_candidate(r"\frac{a\%}{b"), r"\frac{a\%}{b}")

    def test_invalid_and_oversized_inputs_are_bounded(self):
        for value in (None, [], 4, "", " ", "x" * 32769):
            with self.subTest(value_type=type(value).__name__):
                self.assertIsNone(deterministic_candidate(value))
                self.assertFalse(assess_candidate(value, "x")["allowed"])
        for candidate in (None, [], 4, "", " ", "x" * 32769, "x\x01", "x\x7f"):
            with self.subTest(candidate_type=type(candidate).__name__):
                self.assertFalse(assess_candidate("x", candidate)["allowed"])
        self.assertIsNone(deterministic_candidate("{" * 20000 + "x"))

    def test_closes_one_unambiguous_left_delimiter(self):
        cases = [(r"\left(x+1", r"\left(x+1\right)"),
                 (r"\left[x+1", r"\left[x+1\right]"),
                 (r"\left\{x+1", r"\left\{x+1\right\}"),
                 (r"\left\langle x+1", r"\left\langle x+1\right\rangle"),
                 (r"\left((x+1)", r"\left((x+1)\right)"),
                 (r"\frac{\left(x+1)}{2}", r"\frac{\left(x+1\right)}{2}"),
                 (r"\left(x+1)+2", r"\left(x+1\right)+2")]
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(deterministic_candidate(original), expected)
                self.assertEqual(assess_candidate(original, expected)["method"], "pair_left_right")

    def test_missing_delimiter_after_final_right_is_appended_and_rechecked(self):
        path = Path(__file__).resolve().parents[2] / "skills/doc-formula-verify/scripts/verify.py"
        spec = importlib.util.spec_from_file_location("formula_checker", path)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        for original, suffix in ((r"\left( a+b \right", ")"), (r"\left[x+1 \right", "]"),
                                 (r"\left( (a+b) \right  ", ")")):
            with self.subTest(original=original):
                candidate = deterministic_candidate(original)
                self.assertEqual(candidate, original + suffix)
                self.assertTrue(assess_candidate(original, candidate)["allowed"])
                self.assertEqual(checker.check(original)[0], "RETRY")
                self.assertEqual(checker.check(candidate)[0], "OK")

    def test_combines_only_compatible_group_and_left_closures(self):
        self.assertEqual(deterministic_candidate(r"\left(\frac{a}{b"), r"\left(\frac{a}{b}\right)")
        self.assertEqual(assess_candidate(r"\left(\frac{a}{b", r"\left(\frac{a}{b}\right)")["method"],
                         "close_trailing_braces_and_left_right")
        self.assertEqual(deterministic_candidate(r"\frac{\left(x\right)}{2"), r"\frac{\left(x\right)}{2}")

    def test_ambiguous_delimiters_and_cross_group_pairs_are_not_guessed(self):
        for value in (r"\left|x", r"\left.x", r"\left\lvert x", r"\left(x]", r"\left((x",
                      r"\left(x+\left[y", r"\frac{\left(x}{2}", r"\frac{\left(x", r"\left(x+[y",
                      r"\left((x \right", r"\left(x)\right", r"\left(x \right+1"):
            with self.subTest(value=value):
                self.assertIsNone(deterministic_candidate(value))

    def test_known_parser_gaps_preserve_math_for_human_review(self):
        values = [r"AV_{[0.5,0.75]}=-16-16(0.25)=-20", "a=b=c", "a<b<c", "a<=b<=c",
                  r"\left. x^2 \right|_{x=1}", r"\left. f(x) \right\vert_{x=1}"]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(repair_blocker(value), "parser_coverage_unsupported")
                self.assertIsNone(deterministic_candidate(value))

    def test_nested_relations_are_not_mistaken_for_top_level_chains(self):
        for value in (r"\sum_{i=1}^{n} x_i=n", r"f(x=1)=2", r"A_{[i=1]}=B_{j=2}",
                      r"\frac{a=b}{c=d}=1", r"\left(x=1\right)=2", "a<=b", "a>=b"):
            with self.subTest(value=value):
                self.assertIsNone(repair_blocker(value))

    def test_trailing_space_inside_an_unclosed_group_is_preserved(self):
        original = r"\frac{a}{b "
        self.assertEqual(deterministic_candidate(original), r"\frac{a}{b }")
        self.assertFalse(assess_candidate(original, r"\frac{a}{b}")["allowed"])

    def test_multiline_math_whitespace_is_preserved_inside_its_original_group(self):
        original = "\r\n\t" + r"\frac{a}{b " + "\n"
        expected = original + "}"
        self.assertIsNone(repair_blocker(original))
        self.assertEqual(deterministic_candidate(original), expected)
        self.assertTrue(assess_candidate(original, expected)["allowed"])
        self.assertFalse(assess_candidate(original, "\r\n\t" + r"\frac{a}{b}" + " \n")["allowed"])


class CandidatePreservationTests(unittest.TestCase):
    def test_rejects_math_drift_even_when_the_candidate_would_parse(self):
        cases = [(r"\frac{a}{b", r"\frac{a}{c}"), (r"\sqrt[3]{x", r"\sqrt[2]{x}"),
                 (r"\int_0^1 x dx+", r"\int_0^2 x dx"), ("x_{i+1", "x_{j+1}"),
                 ("x^{2", "x^{3}"), ("a+b", "b+a"), ("x+1", "x-1"),
                 (r"\binom{n}{k}", r"\frac{n}{k}"), ("12", "1.2")]
        for original, candidate in cases:
            with self.subTest(original=original, candidate=candidate):
                evidence = assess_candidate(original, candidate)
                self.assertFalse(evidence["allowed"])
                self.assertIn("token_index", evidence)
                self.assertNotEqual(evidence["original_token"], evidence["candidate_token"])

    def test_token_diagnostic_names_the_ordered_math_change(self):
        result = assess_candidate(r"\frac{a}{b", r"\frac{a}{c}")
        self.assertEqual(result["reason"], "unauthorized_source_change")
        self.assertEqual((result["original_token"], result["candidate_token"]), ("b", "c"))
        result = assess_candidate("12", "123")
        self.assertEqual((result["token_index"], result["original_token"], result["candidate_token"]), (0, "12", "123"))

    def test_group_changes_cannot_hide_behind_identical_payload_tokens(self):
        for original, candidate in (("x+1", "{x}+1"), ("x^{2}", "{x^2}"), ("a+b", "a + b")):
            with self.subTest(original=original):
                self.assertFalse(assess_candidate(original, candidate)["allowed"])
        self.assertEqual(assess_candidate("a+b", "a + b")["reason"], "source_spacing_changed")

    def test_only_the_known_patch_result_is_authorized(self):
        for candidate in (r"\frac{a}{b}}", r"\frac{a}{b}+1", r"\dfrac{a}{b}", r"\frac{{a}}{b}"):
            with self.subTest(candidate=candidate):
                self.assertFalse(assess_candidate(r"\frac{a}{b", candidate)["allowed"])
        self.assertTrue(assess_candidate(r"\frac{a}{b", "  " + r"\frac{a}{b}" + " ")["allowed"])


if __name__ == "__main__":
    unittest.main()
