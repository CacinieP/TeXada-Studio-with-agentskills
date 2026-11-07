"""TeX context scanning regressions: comments, verbatim bodies and display math."""

import unittest
from unittest.mock import Mock, patch

from test_static_assets import studio


class FormulaContextTest(unittest.TestCase):
    """No model, no compiler: the checker is a recording test double."""

    def checked(self, content, emit=None):
        captured = []

        def fake_verify(latex):
            captured.append(latex)
            return {"status": "RETRY", "reason": "test double"}

        with patch.object(studio, "_verify_formula", side_effect=fake_verify):
            problems = studio._formula_problems(content, emit)
        return captured, problems

    def test_dollar_pairs_in_comments_are_not_candidates(self):
        content = (
            "% Memo: $1+1=3$ never reaches the checker.\n"
            "$a^2$ real code % mirror $a^2$ stays a comment\n"
        )
        captured, problems = self.checked(content)
        self.assertEqual(captured, ["a^2"])
        self.assertEqual([p["id"] for p in problems], ["f-002-1"])
        self.assertEqual(problems[0]["line"], 2)

    def test_escaped_percent_keeps_later_formulas_scannable(self):
        content = "Growth $s=x/(x+y)$ reaches 30\\% of the total $x+y$.\n"
        captured, _ = self.checked(content)
        self.assertEqual(captured, ["s=x/(x+y)", "x+y"])

    def test_double_backslash_then_percent_still_starts_a_comment(self):
        content = "alpha \\\\ % $z$ hides after a TeX line break\n"
        captured, _ = self.checked(content)
        self.assertEqual(captured, [])

    def test_verbatim_bodies_are_skipped_and_scanning_resumes(self):
        content = (
            "\\begin{verbatim}\n"
            "raw $1+1=3$ and \\left( stay literal\n"
            "\\end{verbatim} then $a_1$ resumes\n"
        )
        captured, problems = self.checked(content)
        self.assertEqual(captured, ["a_1"])
        self.assertEqual(problems[0]["line"], 3)

    def test_lstlisting_and_unclosed_verbatim_stay_literal(self):
        content = (
            "\\begin{lstlisting}[language=Python]\n"
            "rate = \"$1+1=3$\"  # dollar pairs stay code\n"
            "\\end{lstlisting}\n"
            "After a block. \\begin{verbatim}\n"
            "$tail$ swallowed until the end\n"
        )
        captured, _ = self.checked(content)
        self.assertEqual(captured, [])

    def test_display_math_is_not_an_inline_candidate(self):
        content = "$inline$ stays while $$x^2+1$$ is display\n"
        captured, _ = self.checked(content)
        self.assertEqual(captured, ["inline"])

    def test_unclosed_display_excludes_the_rest_of_the_line(self):
        captured, _ = self.checked("$$x $y$ unreachable tail\n")
        self.assertEqual(captured, [])

    def test_dollar_run_after_an_inline_pair_opens_display(self):
        captured, _ = self.checked("$a$$b$ asks for human reading\n")
        self.assertEqual(captured, [])

    def test_full_context_document_yields_only_scannable_inline_formulas(self):
        content = (
            "% $1+1=3$ comment\n"
            "$a^2$ inline\n"
            "\\begin{verbatim}\n"
            "$hidden$\n"
            "\\end{verbatim} $after$\n"
            "$$x^2$$ display\n"
        )
        captured, problems = self.checked(content)
        self.assertEqual(captured, ["a^2", "after"])
        self.assertEqual([p["id"] for p in problems], ["f-002-1", "f-005-2"])
        self.assertEqual([p["line"] for p in problems], [2, 5])


class TableContextTest(unittest.TestCase):
    """Verbatim protection without changing the documented cell contract."""

    @staticmethod
    def table(beta="60"):
        return "\n".join((
            "\\begin{tabular}{|l|r|}",
            "项目 & 数量 \\\\",
            "Alpha & 45 \\\\",
            f"Beta & {beta} \\\\",
            "合计 & 115 \\\\",
            "\\end{tabular}",
        ))

    def test_tabular_text_inside_verbatim_is_not_audited(self):
        content = (
            "\\begin{verbatim}\n"
            "\\begin{tabular}{|l|r|}\n"
            "X & $ broken \\\\\n"
            "\\end{tabular}\n"
            "\\end{verbatim}\n"
            + self.table() + "\n"
        )
        problems = studio._table_problems(content)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["status"], "RETRY")
        self.assertEqual(problems[0]["right"], "105")

    def test_percent_cells_keep_needing_human_review(self):
        for beta in ("60%", "60\\%"):
            with self.subTest(beta=beta):
                problems = studio._table_problems(self.table(beta))
                self.assertEqual(len(problems), 1)
                self.assertEqual(problems[0]["status"], "NEEDS_HUMAN")
                self.assertNotIn("right", problems[0])


class CandidateSpanTest(unittest.TestCase):
    """Accepted candidates only rewrite the scannable span they came from."""

    def test_edits_stay_within_the_scannable_span(self):
        content = "$$n+1$$ display first, then $n+1$ needs repair\n"

        def fake_verify(latex):
            if latex == "n+1":
                return {"status": "RETRY", "reason": "test double"}
            return {"status": "OK", "reason": ""}

        provider = Mock()
        provider.repair_formula.return_value = "n+2"
        provider.last_trace = {"provider": "test-double", "model_calls": 0, "model_called": False}
        with patch.object(studio, "_verify_formula", side_effect=fake_verify):
            fixed, edits = studio._apply_fixes(content, [], provider=provider)
        self.assertEqual(provider.repair_formula.call_count, 1)
        self.assertIn("$n+2$ needs repair", fixed)
        self.assertIn("$$n+1$$ display first", fixed)  # display text is untouched
        self.assertEqual(edits, [{"line": 1, "before": "n+1", "after": "n+2",
                                  "skill": "doc-formula-verify"}])


if __name__ == "__main__":
    unittest.main()
