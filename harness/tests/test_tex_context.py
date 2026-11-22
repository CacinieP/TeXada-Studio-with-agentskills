"""TeX lexical contexts and replacement boundaries; no model or TeX engine."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.tex_context import _command, analyze_math, check_math_grids, extract_math, mask_opaque  # noqa: E402


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
        text = r"$a$ $b$ \(c\) $$d$$ \[e\]"
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

    def test_text_box_inner_math_stays_one_node_while_unclosed_math_brace_still_closes(self):
        text = r"$\text{$x$ {a + b $y$}}$ and $\frac{1}{2$ and \(\mbox{see \(z\) and $w$}\)"
        nodes = extract_math(text)
        self.assertEqual([node["latex"] for node in nodes],
                         [r"\text{$x$ {a + b $y$}}", r"\frac{1}{2", r"\mbox{see \(z\) and $w$}"])
        self.assertEqual([node["checkable"] for node in nodes], [False, True, False])
        self.assert_slices(text, nodes)

    def test_outer_end_environment_terminates_unclosed_inline_or_display_math(self):
        text = "\\begin{itemize}\n\\item $unclosed\n\\end{itemize}\nNext $x+1$."
        result = analyze_math(text)
        self.assertEqual([d["code"] for d in result["diagnostics"]], ["unclosed_math"])
        self.assertEqual([node["latex"] for node in result["nodes"]], ["x+1"])

    def test_unclosed_single_dollar_does_not_consume_display_double_dollar(self):
        result = analyze_math("$unclosed $$d+1$$ $ok$")
        self.assertEqual([d["code"] for d in result["diagnostics"]], ["unclosed_math"])
        self.assertEqual([(n["kind"], n["latex"]) for n in result["nodes"]],
                         [("display", "d+1"), ("inline", "ok")])
        adjacent_bad = analyze_math("$a$$b$")
        self.assertTrue(any(d["code"] == "unclosed_math" for d in adjacent_bad["diagnostics"]))

    def test_non_signature_definition_tokens_do_not_blind_scanner_or_mask_opaque(self):
        for prefix in (r"\let\myenv\newenvironment" + "\n\\section{Intro}\n",
                       r"\expandafter\newcommand\csname foo\endcsname{bar}" + "\n"):
            doc = prefix + "$x+1$\n\\begin{tabular}{ll}\nA & 1\\\\\n\\end{tabular}\n"
            with self.subTest(prefix=prefix):
                result = analyze_math(doc)
                self.assertEqual(result["diagnostics"][0]["code"], "unclosed_definition")
                self.assertEqual([n["latex"] for n in result["nodes"]], ["x+1"])
                self.assertIn(r"\begin{tabular}", mask_opaque(doc))

    def test_ascii_only_command_scanning_splits_cjk_suffix(self):
        self.assertEqual(_command(r"\quad中文", 0), ("quad", 5))
        nodes = extract_math(r"$a\quad中文$")
        self.assertEqual(len(nodes), 1)
        self.assertTrue(nodes[0]["checkable"])
        self.assertEqual(nodes[0]["reason"], "")


class MathGridTests(unittest.TestCase):
    def test_row_spacing_is_distinguished_from_bracketed_matrix_cells(self):
        self.assertEqual(
            check_math_grids(r"\begin{pmatrix} 1 & 2 \\[4pt] 3 & 4 \end{pmatrix}"),
            {"status": "OK", "reason": "", "scope": "grid_shape"},
        )
        self.assertEqual(
            check_math_grids(r"\begin{pmatrix} 1 & 2 \\[\jot] 3 & 4 \end{pmatrix}"),
            {"status": "OK", "reason": "", "scope": "grid_shape"},
        )
        for ragged in (
            r"\begin{vmatrix} 1 & 2 \\ 3 & 4 \\ [5] \end{vmatrix}",
            "\\begin{vmatrix} 1 & 2 \\\\ 3 & 4 \\\\\n[5] \\end{vmatrix}",
        ):
            with self.subTest(ragged=ragged):
                verdict = check_math_grids(ragged)
                self.assertIsNotNone(verdict)
                self.assertEqual(verdict["status"], "NEEDS_HUMAN")
                self.assertIn("[2, 2, 1]", verdict["reason"])

    def test_cases_allows_one_or_two_uniform_columns_and_vmatrix_variants_require_square(self):
        for valid in (
            r"f(x)=\begin{vmatrix}2x&1&-1\\-x&x&x\\1&2&x\end{vmatrix}",
            r"\begin{Vmatrix}a&b\\c&d\end{Vmatrix}",
            r"\delta_{ij}=\begin{cases}1,&i=j\\0,&i\neq j\end{cases}",
            r"\begin{cases} x+y=1 \\ x-y=0 \end{cases}",
            r"f(x)=\begin{cases}x,&\text{if }x>0\\0,&\text{otherwise}\end{cases}",
            r"f(x)=\begin{cases}1,&x\ge 0\\-1,&\text{其他}\end{cases}",
            r"f(x)=\begin{cases}x^2,&0\le x\le 1\\0,&x<0\end{cases}",
        ):
            with self.subTest(valid=valid):
                self.assertEqual(check_math_grids(valid), {"status": "OK", "reason": "", "scope": "grid_shape"})

        ragged_cases = check_math_grids(r"\begin{cases}1,&i=j\\0\end{cases}")
        self.assertEqual(ragged_cases["status"], "NEEDS_HUMAN")
        self.assertIn("[2, 1]", ragged_cases["reason"])

        wide_cases = check_math_grids(r"\begin{cases}1&2&3\\4&5&6\end{cases}")
        self.assertEqual(wide_cases["status"], "NEEDS_HUMAN")
        self.assertIn("预期每行 1 或 2 列", wide_cases["reason"])

        nonsquare_norm = check_math_grids(r"\begin{Vmatrix}1&2&3\\4&5&6\end{Vmatrix}")
        self.assertEqual(nonsquare_norm["status"], "NEEDS_HUMAN")
        self.assertIn("[3, 3]", nonsquare_norm["reason"])

    def test_broken_cells_and_broken_outer_formulas_are_never_certified_ok(self):
        broken = (
            r"\frac{1}{ + \begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix} }}}} \foobar",
            r"\frac{1}{ + \begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix} }",
            r"\frac{1}{\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} \frac{1}{ & 2 \\ 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} x+ & 2 \\ 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} (1 & 2 \\ 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} & 2 \\ 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} \foobar & 2 \\ 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} 1 & 2 \\[x+1] 3 & 4 \end{pmatrix}",
            r"\begin{pmatrix} 1 & 2 \\[5] 3 & 4 \end{pmatrix}",
            r"\begin{cases} 1, & \text{} \\ 0, & x<0 \end{cases}",
            r"\begin{cases} 1, & \text{bad $x$} \\ 0, & x<0 \end{cases}",
            r"\begin{cases} 1, & \text{\verb|x|} \\ 0, & x<0 \end{cases}",
        )
        for expr in broken:
            with self.subTest(expr=expr):
                verdict = check_math_grids(expr)
                self.assertNotEqual(verdict and verdict.get("status"), "OK")


if __name__ == "__main__":
    unittest.main()
