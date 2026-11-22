"""Conservative TeX cleanup inspection, deterministic stripping, and scope checks."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.tex_cleanup import (  # noqa: E402
    assess_cleanup_candidate,
    cleanup_edits,
    deterministic_cleanup_candidate,
    inspect_tex_cleanup,
)


class TexCleanupInspectionTests(unittest.TestCase):
    def test_clean_documents_and_samples_report_zero_problems(self):
        samples_dir = Path(__file__).resolve().parents[2] / "samples" / "docs"
        for sample in sorted(samples_dir.glob("*.tex")):
            with self.subTest(sample=sample.name):
                report = inspect_tex_cleanup(sample.read_text(encoding="utf-8"))
                self.assertEqual(report["problems"], [])
                self.assertIsNone(deterministic_cleanup_candidate(sample.read_text(encoding="utf-8")))

    def test_detects_and_strips_zero_width_noise_outside_protected_regions(self):
        source = (
            "\ufeff\\section{标题}\n"
            "正文\u200b内容 $x^2 + 1$ 结束\u200d。\n"
            "% 注释保留 \u200b 原样\n"
            "\\begin{verbatim}\nkeep \u200b literal\n\\end{verbatim}\n"
        )
        report = inspect_tex_cleanup(source)
        self.assertEqual(len(report["problems"]), 1)
        self.assertEqual(report["problems"][0]["kind"], "zero_width_noise")
        cleaned = deterministic_cleanup_candidate(source)
        expected = (
            "\\section{标题}\n"
            "正文内容 $x^2 + 1$ 结束。\n"
            "% 注释保留 \u200b 原样\n"
            "\\begin{verbatim}\nkeep \u200b literal\n\\end{verbatim}\n"
        )
        self.assertEqual(cleaned, expected)
        verdict = assess_cleanup_candidate(source, cleaned)
        self.assertTrue(verdict["allowed"], verdict)
        self.assertEqual(verdict["method"], "strip_zero_width")
        edits = cleanup_edits(source, cleaned)
        self.assertTrue(edits)
        rebuilt = source
        for edit in sorted(edits, key=lambda item: (item["start"], item["end"]), reverse=True):
            self.assertEqual(rebuilt[edit["start"]:edit["end"]], edit["before"])
            rebuilt = rebuilt[:edit["start"]] + edit["after"] + rebuilt[edit["end"]:]
        self.assertEqual(rebuilt, cleaned)

    def test_detects_unclosed_single_line_commands_and_prose_environments(self):
        unclosed_cmd = "\\documentclass{article}\n\\begin{document}\n\\section{引言\n这里是正文 $\\frac{1}{2}$。\n\\end{document}\n"
        report = inspect_tex_cleanup(unclosed_cmd)
        self.assertEqual([p["kind"] for p in report["problems"]], ["unclosed_command_brace"])
        self.assertIsNone(deterministic_cleanup_candidate(unclosed_cmd))

        repaired_cmd = "\\documentclass{article}\n\\begin{document}\n\\section{引言}\n这里是正文 $\\frac{1}{2}$。\n\\end{document}\n"
        verdict = assess_cleanup_candidate(unclosed_cmd, repaired_cmd)
        self.assertTrue(verdict["allowed"], verdict)
        self.assertEqual(verdict["method"], "structural_cleanup_insertion")

        unclosed_env = "\\begin{document}\n\\begin{itemize}\n\\item 第一项\n\\item 第二项\n\n总结段落。\n\\end{document}\n"
        env_report = inspect_tex_cleanup(unclosed_env)
        self.assertEqual([p["kind"] for p in env_report["problems"]], ["unclosed_environment"])
        repaired_env = "\\begin{document}\n\\begin{itemize}\n\\item 第一项\n\\item 第二项\n\\end{itemize}\n\n总结段落。\n\\end{document}\n"
        env_verdict = assess_cleanup_candidate(unclosed_env, repaired_env)
        self.assertTrue(env_verdict["allowed"], env_verdict)

    def test_multiline_closed_command_is_not_misflagged(self):
        closed_multiline = "\\textbf{第一行\n第二行} 与未闭合数学 $\\frac{a}{b$。\n"
        self.assertEqual(inspect_tex_cleanup(closed_multiline)["problems"], [])

    def test_rejects_prose_math_or_comment_tampering_in_cleanup_candidate(self):
        source = "\\section{引言\n这里是原始正文 $x+1$。 % 原始注释\n"
        bad_candidates = [
            "\\section{引言}\n这里是改写正文 $x+1$。 % 原始注释\n",
            "\\section{引言}\n这里是原始正文 $x+2$。 % 原始注释\n",
            "\\section{引言}\n这里是原始正文 $x+1$。 % 修改注释\n",
            "\\section{引言}}\n这里是原始正文 $x+1$。 % 原始注释\n",
            "\\section{引言}\n\\input{secret}\n这里是原始正文 $x+1$。 % 原始注释\n",
            source,
        ]
        for candidate in bad_candidates:
            with self.subTest(candidate=candidate):
                self.assertFalse(assess_cleanup_candidate(source, candidate)["allowed"])

    def test_unclosed_single_line_command_cannot_swallow_following_lines_or_comments(self):
        multiline = "\\section{引言\n正文第一段。\n正文第二段。\n"
        self.assertFalse(
            assess_cleanup_candidate(multiline, "\\section{引言\n正文第一段。\n正文第二段。}\n")["allowed"]
        )
        self.assertTrue(
            assess_cleanup_candidate(multiline, "\\section{引言}\n正文第一段。\n正文第二段。\n")["allowed"]
        )

        commented = "\\section{引言 % 标题注释\n正文。\n"
        self.assertFalse(
            assess_cleanup_candidate(commented, "\\section{引言 % 标题注释}\n正文。\n")["allowed"]
        )
        self.assertTrue(
            assess_cleanup_candidate(commented, "\\section{引言} % 标题注释\n正文。\n")["allowed"]
        )

    def test_tabular_ranges_ignore_commented_end_tabular_and_forbid_interior_insertions(self):
        from docforensics.tex_cleanup import _tabular_ranges

        source = (
            "\\section{标题\n"
            "\\begin{tabular}{lr}\n"
            "项目 & 金额 \\\\\n"
            "A & 1 \\\\ % fake \\end{tabular}\n"
            "合计 & 99 \\\\\n"
            "\\end{tabular}\n"
        )
        ranges = _tabular_ranges(source)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(source[ranges[0][0]:ranges[0][1]], source[source.index("\\begin{tabular}"):source.rindex("\\end{tabular}") + len("\\end{tabular}")])

        # Closing \section{ inside the tabular body must be rejected.
        bad_inside_tab = source.replace("合计 & 99 \\\\", "合计 & 99} \\\\")
        self.assertFalse(assess_cleanup_candidate(source, bad_inside_tab)["allowed"])

        good = source.replace("\\section{标题\n", "\\section{标题}\n")
        self.assertTrue(assess_cleanup_candidate(source, good)["allowed"])
        edits = cleanup_edits(source, good)
        self.assertEqual(len(edits), 1)
        self.assertLessEqual(edits[0]["end"], ranges[0][0])


if __name__ == "__main__":
    unittest.main()
