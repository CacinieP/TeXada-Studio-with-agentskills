"""TeX lexical contexts and replacement boundaries; no model or TeX engine."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.tex_context import analyze_math, extract_math  # noqa: E402


class MathContextTests(unittest.TestCase):
    def assert_slices(self, text, nodes):
        last_end = 0
        for node in nodes:
            self.assertGreaterEqual(node["start"], last_end)
            self.assertLessEqual(node["end"], len(text))
            self.assertEqual(text[node["body_start"]:node["body_end"]], node["latex"])
            self.assertEqual(text[node["start"]:node["body_start"]], node["opening"])
            self.assertEqual(text[node["body_end"]:node["end"]], node["closing"])
            self.assertEqual(node["encoding"], "unicode-codepoints")
            last_end = node["end"]

    def test_all_delimiters_and_adjacent_inline_math(self):
        text = r"$a$$b$ \(c\) $$d$$ \[e\]"
        nodes = extract_math(text)
        self.assertEqual([node["latex"] for node in nodes], list("abcde"))
        self.assertEqual([node["kind"] for node in nodes], ["inline", "inline", "inline", "display", "display"])
        self.assertTrue(all(node["checkable"] for node in nodes))
        self.assert_slices(text, nodes)

    def test_comments_and_escaped_percent_and_dollars(self):
        text = "% $ignored$ \\(also ignored\\)\n" + r"\% $a+\%$ \$outside\$ $b$" + "\n% $$ignored$$"
        nodes = extract_math(text)
        self.assertEqual([node["latex"] for node in nodes], [r"a+\%", "b"])
        self.assertTrue(all(node["checkable"] for node in nodes))
        self.assertEqual(nodes[0]["line"], 2)

    def test_escaped_slashes_do_not_escape_following_dollar(self):
        text = r"\\$x$ \\\$ignored\$ $y$"
        self.assertEqual([node["latex"] for node in extract_math(text)], ["x", "y"])

    def test_multiline_crlf_and_unicode_codepoints(self):
        text = "标题🙂\r\n\\[\r\nx +\r\ny\r\n\\]\r\n尾 $z$"
        nodes = extract_math(text)
        self.assertEqual(len(nodes), 2)
        self.assertEqual((nodes[0]["line"], nodes[0]["column"]), (2, 1))
        self.assertEqual(nodes[0]["start"], len("标题🙂\r\n"))
        self.assertEqual(nodes[0]["latex"], "\r\nx +\r\ny\r\n")
        self.assertTrue(nodes[0]["checkable"])
        self.assert_slices(text, nodes)

    def test_math_environment_matching_and_wrapper_preservation(self):
        text = "前\\begin {equation*}\nx=1\n\\end {equation*}后"
        nodes = extract_math(text)
        self.assertEqual(len(nodes), 1)
        node = nodes[0]
        self.assertEqual(node["kind"], "equation*")
        self.assertTrue(node["checkable"])
        self.assertEqual(node["closing"], r"\end {equation*}")
        updated = text[:node["body_start"]] + "\nx=2\n" + text[node["body_end"]:]
        self.assertEqual(updated, "前\\begin {equation*}\nx=2\n\\end {equation*}后")
        self.assert_slices(text, nodes)

    def test_align_matrix_and_nested_structure_require_human_review(self):
        text = (r"\begin{align*}x&=1\\y&=2\end{align*} "
                r"\[\begin{pmatrix}1&2\\3&4\end{pmatrix}\] "
                r"\begin{equation}\begin{aligned}x&=1\end{aligned}\end{equation}")
        nodes = extract_math(text)
        self.assertEqual(len(nodes), 3)
        self.assertTrue(all(not node["checkable"] for node in nodes))
        self.assert_slices(text, nodes)

    def test_opaque_environments_and_inline_verbatim_are_skipped(self):
        text = (r"\verb|$fake$| \verb*+\(fake\)+ "
                r"\begin{verbatim}$fake$\end{verbatim} "
                r"\begin{Verbatim}[x]$$fake$$\end{Verbatim} "
                r"\begin{lstlisting}[mathescape=true]$fake$\end{lstlisting} "
                r"\begin{minted}{tex}\[fake\]\end{minted} "
                r"\begin{comment}$fake$\end{comment} $real$")
        self.assertEqual([node["latex"] for node in extract_math(text)], ["real"])

    def test_control_words_are_not_prefix_matched(self):
        text = r"\verbatimword{$real$} \beginning{$also$} \verbfoo{$yes$}"
        self.assertEqual([node["latex"] for node in extract_math(text)], ["real", "also", "yes"])

    def test_macro_definitions_are_not_rendered_math(self):
        text = (r"\newcommand{\foo}[1][x]{$#1$} "
                r"\renewcommand\bar[1]{\(#1\)} "
                r"\providecommand*{\baz}{$hidden$} "
                r"\DeclareMathOperator{\qux}{a $hidden$} "
                r"\newenvironment{custom}{$fake$}{\[fake\]} "
                r"\NewDocumentCommand{\xx}{m}{$#1$} "
                r"\NewDocumentEnvironment{opaque}{m}{$fake$}{$fake$} "
                r"\def\simple#1{$#1$} \gdef\another{\(hidden\)} $\foo{x}$ $x$")
        nodes = extract_math(text)
        self.assertEqual([node["latex"] for node in nodes], [r"\foo{x}", "x"])
        self.assertFalse(nodes[0]["checkable"])
        self.assertEqual(nodes[0]["reason"], "unsupported_command:foo")
        self.assertTrue(nodes[1]["checkable"])

    def test_single_letter_custom_commands_are_not_assumed_supported(self):
        node = extract_math(r"$\x{1}$")[0]
        self.assertFalse(node["checkable"])
        self.assertEqual(node["reason"], "unsupported_command:x")

    def test_braced_default_argument_does_not_expose_macro_body_math(self):
        text = r"\newcommand{\foo}[1][{a]$fake$}]{$body$} $real$"
        self.assertEqual([node["latex"] for node in extract_math(text)], ["real"])

    def test_comment_closer_inside_math_does_not_end_region(self):
        text = "\\[x % \\] $fake$\ny\\] $z$"
        nodes = extract_math(text)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]["latex"], "x % \\] $fake$\ny")
        self.assertFalse(nodes[0]["checkable"])
        self.assertEqual(nodes[0]["reason"], "comments_in_math")

    def test_macro_definition_inside_math_cannot_supply_its_closing_dollar(self):
        text = r"$\def\x{$fake$} y$ $z$"
        nodes = extract_math(text)
        self.assertEqual([node["latex"] for node in nodes], [r"\def\x{$fake$} y", "z"])
        self.assertFalse(nodes[0]["checkable"])

    def test_nested_dollar_within_display_is_not_scalar_repair_input(self):
        node = extract_math(r"\[a $b$\]")[0]
        self.assertFalse(node["checkable"])
        self.assertEqual(node["reason"], "nested_math_delimiter")

    def test_unclosed_math_yields_diagnostic_without_edit_range(self):
        for text in ("$broken", "$$broken", r"\(broken", r"\[broken", r"\begin{equation}broken"):
            with self.subTest(text=text):
                result = analyze_math(text)
                self.assertEqual(result["nodes"], [])
                self.assertEqual(result["diagnostics"][0]["code"], "unclosed_math")
                self.assertNotIn("body_end", result["diagnostics"][0])

    def test_unclosed_inline_recovers_at_explicit_display(self):
        result = analyze_math(r"\(broken \[good\] $later$")
        self.assertEqual([node["latex"] for node in result["nodes"]], ["good", "later"])
        self.assertEqual(result["diagnostics"][0]["code"], "unclosed_math")

    def test_unclosed_display_does_not_swallow_the_next_display(self):
        result = analyze_math("\\[\\section{定积分}\n\\[ \\int_0^1 x^2\\,dx = \\frac{{3} \\]")
        self.assertEqual(result["diagnostics"][0]["code"], "unclosed_math")
        self.assertNotIn("body_end", result["diagnostics"][0])
        self.assertEqual([node["latex"] for node in result["nodes"]],
                         [" \\int_0^1 x^2\\,dx = \\frac{{3} "])
        self.assertTrue(result["nodes"][0]["checkable"])

    def test_mismatched_environment_recovers_without_editing_broken_region(self):
        result = analyze_math(r"\begin{equation}x\end{align} $later$")
        self.assertEqual([node["latex"] for node in result["nodes"]], ["later"])
        self.assertEqual(result["diagnostics"][0]["code"], "mismatched_environment")

    def test_unclosed_raw_regions_and_definition_do_not_leak_fake_math(self):
        for text, code in ((r"\begin{verbatim}$fake$", "unclosed_opaque_environment"),
                           (r"\newcommand{\x}{$fake$", "unclosed_definition"),
                           ("\\verb|$fake$\n$real$", "unclosed_verb")):
            with self.subTest(text=text):
                result = analyze_math(text)
                self.assertEqual(result["diagnostics"][0]["code"], code)
                self.assertNotIn("fake", [node["latex"] for node in result["nodes"]])

    def test_replacements_are_unambiguous_when_formulas_repeat(self):
        text = "🙂 $x+$ and \\(x+\\) then $$x+$$"
        nodes = extract_math(text)
        updated = text
        for index, node in reversed(list(enumerate(nodes))):
            self.assertEqual(updated[node["body_start"]:node["body_end"]], "x+")
            updated = updated[:node["body_start"]] + f"x+{index}" + updated[node["body_end"]:]
        self.assertEqual(updated, "🙂 $x+0$ and \\(x+1\\) then $$x+2$$")

    def test_category_code_changes_disable_scalar_repair(self):
        result = analyze_math(r"$before$ \catcode`\$=12 $after$")
        self.assertEqual([node["checkable"] for node in result["nodes"]], [True, False])
        self.assertEqual(result["diagnostics"][0]["code"], "category_codes_unsupported")

    def test_empty_math_and_input_types(self):
        self.assertFalse(extract_math(r"\(\)")[0]["checkable"])
        self.assertEqual(analyze_math("") , {"nodes": [], "diagnostics": []})
        with self.assertRaises(TypeError):
            extract_math(None)


if __name__ == "__main__":
    unittest.main()
