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

    def test_does_not_close_a_group_that_still_leaves_a_required_argument_missing(self):
        for value in (r"\frac{{3}", r"\dfrac{{3}", r"\binom{{n}",
                      r"\int_0^1 x^2\,dx = \frac{{3}", r"\frac{{3}}"):
            with self.subTest(value=value):
                self.assertEqual(repair_blocker(value), "missing_command_argument")
                self.assertIsNone(deterministic_candidate(value))
                self.assertFalse(assess_candidate(value, value + "}")["allowed"])
        self.assertFalse(assess_candidate(r"\frac{{3}", r"\frac{1}{3}")["allowed"])
        self.assertFalse(assess_candidate(r"\frac{{3}", r"\frac{3}{}")["allowed"])

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

    def test_checker_rejects_invalid_or_mismatched_left_right_and_duplicate_scripts(self):
        path = Path(__file__).resolve().parents[2] / "skills/doc-formula-verify/scripts/verify.py"
        spec = importlib.util.spec_from_file_location("formula_checker", path)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        for valid_precheck in (
            r"\left(0,1\right]",
            r"\left.\frac{d}{dx}x^2\right|_{x=1}=2",
            r"\left\{ x \right\}",
            r"\left\| x \right\Vert",
            r"\left\lvert x \right\rvert",
            r"\left\lVert x \right\rVert",
            r"\left\langle x \right\rangle",
            r"\left\lfloor x \right\rfloor",
            r"\left\lceil x \right\rceil",
            r"\left\backslash x \right/",
            r"\left\uparrow x \right\downarrow",
            r"\left\Uparrow x \right\Downarrow",
            r"\left\updownarrow x \right\Updownarrow",
            "x_1^2", "x^2_1", "x^12", "x^12^3", "{x^2}^3",
        ):
            with self.subTest(valid_precheck=valid_precheck):
                self.assertIsNone(checker._lexical_error(valid_precheck))
        for valid_parse in ("x_1^2", "x^2_1", "x^12", "x^12^3", "{x^2}^3", r"\left(a+b\right)"):
            with self.subTest(valid_parse=valid_parse):
                self.assertEqual(checker.check(valid_parse)[0], "OK")
        for invalid in (
            r"\left\lvert x \right",
            r"x \left + y",
            r"\frac{\left(x+1)}{2}",
            r"\left(x+1)+2",
            r"(x+1\right)",
            r"\frac{\left(x+1}{2}\right)",
            "x^2^3",
            "x_i_j",
            "x^2_1^3",
            r"x^\alpha^\beta",
            "x^{a}^{b}",
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(checker.check(invalid)[0], "RETRY")

    def test_interleaved_and_control_word_duplicate_scripts_are_repair_blockers(self):
        for value in ("x^2_1^3", "x_1^2_3", r"x^\alpha^\beta", r"x^\alpha_1^\beta", r"x_\alpha^\beta_\gamma"):
            with self.subTest(value=value):
                self.assertEqual(repair_blocker(value), "duplicate_script")
                self.assertIsNone(deterministic_candidate(value))

    def test_unbraced_single_char_arguments_and_empty_brace_arguments(self):
        self.assertIsNone(repair_blocker(r"\frac12"))
        self.assertIsNone(repair_blocker(r"\frac\alpha\beta"))
        self.assertEqual(deterministic_candidate(r"\frac12 + \frac{a}{b"), r"\frac12 + \frac{a}{b}")
        self.assertEqual(deterministic_candidate(r"\frac1{b"), r"\frac1{b}")
        for invalid in (r"\frac1", r"\frac\alpha", r"\frac{}{3", r"\frac{3}{}", r"\frac{}{3}", r"\binom{}{k}"):
            with self.subTest(invalid=invalid):
                self.assertEqual(repair_blocker(invalid), "missing_command_argument")
                self.assertIsNone(deterministic_candidate(invalid))

    def test_trailing_control_space_is_not_misclassified_as_incomplete_command(self):
        self.assertIsNone(repair_blocker(r"x\ "))
        self.assertIsNone(repair_blocker(r"\frac{a}{b\ "))
        self.assertEqual(deterministic_candidate(r"\frac{a}{b\ "), r"\frac{a}{b\ }")
        self.assertEqual(repair_blocker("x\\"), "incomplete_command")
        self.assertFalse(assess_candidate(r"x + y\ ", "x + y\\")["allowed"])

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


class MissingScriptTests(unittest.TestCase):
    def test_uncertain_scripts_are_preserved(self):
        for original, candidate in (("a_+b", "a_1+b"), ("x^+1", "x^2+1"),
                                    ("a_ + b", "a_{1} + b"), ("a_", "a_1")):
            with self.subTest(original=original):
                self.assertIsNone(deterministic_candidate(original))
                evidence = assess_candidate(original, candidate)
                self.assertFalse(evidence["allowed"])
                self.assertEqual(evidence["reason"], "missing_script_operand")

    def test_rejects_fills_outside_empty_script_slots(self):
        # 抓的破坏点：扩权被滥用于任意位置插字（操作数/已占用槽/命令/超长/结构改动）
        cases = [
            ("x+1", "x2+1"),                # 操作数后插字——不是 script 槽
            ("x+1", "x+21"),                # 同上，数字尾插字
            ("a_1+b", "a_21+b"),            # 槽已被 1 占用，不是空槽
            ("a_+b", "a_\\alpha+b"),        # 命令不是单 token 填充
            ("a_+b", "a_123456789+b"),      # 超出 8 字符上限
            ("a_+b", "a_ 1+b"),             # 位置在空格后而非 script 标记后（间距改动）
            ("z^3+", "z^3+1"),              # 尾操作数缺失不允许臆造（SKILL 教义保持）
            ("a_", "a_1"),                  # 行尾空槽：repair_blocker=missing_script_operand 保持拦截
            (r"\frac{{3}", r"\frac{1}{3}"),  # 缺 frac 参数不允许臆造（既有裁决保持）
        ]
        for original, candidate in cases:
            with self.subTest(original=original, candidate=candidate):
                self.assertFalse(assess_candidate(original, candidate)["allowed"])

    def test_gap_fill_cannot_bypass_repair_blocker(self):
        # 抓的破坏点：repair_blocker 拦下的源（注释等）借填充绕过
        evidence = assess_candidate("x^+1%c", "x^2+1%c")
        self.assertFalse(evidence["allowed"])

    def test_postfix_superscripts_allow_deterministic_brace_closure(self):
        for original in (
            r"\lim_{x \to 0^+} \frac{1}{x",
            r"f(0^-) + \frac{1}{2",
            r"A^* + \frac{1}{2",
            r"A^+ = \frac{1}{2",
        ):
            with self.subTest(original=original):
                self.assertIsNone(repair_blocker(original))
                self.assertEqual(deterministic_candidate(original), original + "}")
        for ambiguous in (
            "x^+1", "x^+y", "a_+b", "a_ + b", "a_",
            r"[a_] + \frac{1}{2", r"(a_, b) + \frac{1}{2",
            r"[x^] + \frac{1}{2", r"\left[a_\right] + \frac{1}{2",
            r"\{a_; b\} + \frac{1}{2",
        ):
            with self.subTest(ambiguous=ambiguous):
                self.assertEqual(repair_blocker(ambiguous), "missing_script_operand")
                self.assertIsNone(deterministic_candidate(ambiguous))
        self.assertEqual(repair_blocker(r"0 \le x \le 1"), "parser_coverage_unsupported")
        self.assertIsNone(repair_blocker(r"0 \le x \le 1", allow_parser_gaps=True))
        self.assertEqual(repair_blocker(r"0 \le x_ \le 1", allow_parser_gaps=True), "missing_script_operand")


class StructuralDelimiterInsertionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / "skills/doc-formula-verify/scripts/verify.py"
        spec = importlib.util.spec_from_file_location("formula_checker_structural", path)
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def test_authorizes_pure_interior_and_opening_brace_insertions(self):
        cases = [
            (r"x^{n+1 + y = 0", r"x^{n+1} + y = 0"),
            (r"\frac{a}{b + c = d", r"\frac{a}{b + c} = d"),
            (r"\sqrt{x+1 + y = 2", r"\sqrt{x+1} + y = 2"),
            (r"\frac1}{2}", r"\frac{1}{2}"),
            (r"x^n+1}", r"x^{n+1}"),
            (r"x_{i+1} + y_j+1}", r"x_{i+1} + y_{j+1}"),
        ]
        for original, candidate in cases:
            with self.subTest(original=original, candidate=candidate):
                verdict = assess_candidate(original, candidate)
                self.assertTrue(verdict["allowed"], verdict)
                self.assertEqual(verdict["method"], "structural_delimiter_insertion")
                self.assertEqual(verdict["reason"], "structural_syntax_repair")
                self.assertEqual(self.checker.check(candidate)[0], "OK")

    def test_authorizes_pure_left_right_structural_insertions(self):
        cases = [
            (r"\left(\frac{a}{b} = c", r"\left(\frac{a}{b}\right) = c"),
            (r"\left(a + \left[b\right]) = c", r"\left(a + \left[b\right]\right) = c"),
            (r"(x+1\right)", r"\left(x+1\right)"),
            (r"x+1\right)", r"\left(x+1\right)"),
            (r"\left\lvert x \right", r"\left\lvert x \right\rvert"),
        ]
        for original, candidate in cases:
            with self.subTest(original=original, candidate=candidate):
                verdict = assess_candidate(original, candidate)
                self.assertTrue(verdict["allowed"], verdict)
                self.assertEqual(verdict["method"], "structural_delimiter_insertion")
                self.assertEqual(self.checker.check(candidate)[0], "OK")

    def test_rejects_surplus_braces_spacing_changes_and_ambiguous_juxtaposition(self):
        rejected = [
            (r"x^{n+1 + y = 0", r"{x^{n+1}} + y = 0"),
            (r"x^{n+1 + y = 0", r"x^{n + 1} + y = 0"),
            (r"x} + {y", r"{x} + {y}"),
            (r"x + }", r"x + {}"),
            (r"\frac{\left(x+1}{2}", r"\frac{\left(x+1}{2}\right)"),
            (r"\displaystyle \int_{0}^{1 x^2\,dx", r"\displaystyle \int_{0}^{1} x^2\,dx"),
            (r"\lim_{y \to b k(y)=N", r"\lim_{y \to b} k(y)=N"),
            ("x}+", "{x}+"),
            ("a_+b}", "a_{1}+b}"),
        ]
        for original, candidate in rejected:
            with self.subTest(original=original, candidate=candidate):
                self.assertFalse(assess_candidate(original, candidate)["allowed"])

    def test_rejects_delimiters_split_inside_number_literals(self):
        for original, candidate in (
            ("12 + 3}", "1{2 + 3}"),
            (r"\left(12 + 3 = 0", r"\left(1\right)2 + 3 = 0"),
            (r"12\right)", r"1\left(2\right)"),
            ("3.14}", "3.{14}"),
            ("3.14}", "3{.14}"),
        ):
            with self.subTest(original=original, candidate=candidate):
                self.assertFalse(assess_candidate(original, candidate)["allowed"])

    def test_opening_brace_requires_brace_accepting_slot_and_preserves_valid_slots(self):
        for original, candidate in (
            (r"2 \cdot 3 + 4}", r"2 \cdot {3 + 4}"),
            (r"a b + c}", r"a {b + c}"),
            (r"x + y} \cdot z", r"{x + y} \cdot z"),
        ):
            with self.subTest(rejected=original, candidate=candidate):
                self.assertFalse(assess_candidate(original, candidate)["allowed"])

        for original, candidate in (
            (r"\frac1}{2}", r"\frac{1}{2}"),
            (r"\frac{1}2}", r"\frac{1}{2}"),
            (r"x^n+1}", r"x^{n+1}"),
            (r"x_{i+1}+y_j+1}", r"x_{i+1}+y_{j+1}"),
            (r"\sqrt[3]x+1}", r"\sqrt[3]{x+1}"),
            (r"\sqrt x+1}", r"\sqrt{x+1}"),
        ):
            with self.subTest(allowed=original, candidate=candidate):
                verdict = assess_candidate(original, candidate)
                self.assertTrue(verdict["allowed"], verdict)
                self.assertEqual(self.checker.check(candidate)[0], "OK")

    def test_left_right_interior_boundaries_and_symmetric_pairs(self):
        for original, candidate in (
            (r"\left(a b c = 1", r"\left(a\right) b c = 1"),
            (r"a \cdot b + c\right)", r"a \cdot \left(b + c\right)"),
            (r"\left(x + 1 = 0", r"\left(x + 1\right] = 0"),
            (r"\left[x + 1 = 0", r"\left[x + 1\right) = 0"),
        ):
            with self.subTest(rejected=original, candidate=candidate):
                self.assertFalse(assess_candidate(original, candidate)["allowed"])

        for original, candidate in (
            (r"\left(x + 1 = 0", r"\left(x + 1\right) = 0"),
            (r"(x + 1\right)", r"\left(x + 1\right)"),
            (r"y = x + 1\right)", r"y = \left(x + 1\right)"),
            (r"\left(\frac{a}{b}^2", r"\left(\frac{a}{b}\right)^2"),
            (r"\left[0, 1\right) + x^{n+1 = 0", r"\left[0, 1\right) + x^{n+1} = 0"),
        ):
            with self.subTest(allowed=original, candidate=candidate):
                verdict = assess_candidate(original, candidate)
                self.assertTrue(verdict["allowed"], verdict)


if __name__ == "__main__":
    unittest.main()
