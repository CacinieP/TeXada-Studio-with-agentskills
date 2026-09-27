import contextlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import format_whitespace as cleanup


class TexTests(unittest.TestCase):
    def test_symbols_citations_comments_and_paragraphs_survive(self):
        source = (
            "\\citet{a} and \\citep{b}.   \n"
            "$R=10$, $x\\in\\mathbb{R}$, $\\epsilon\\ne\\varepsilon$.  \n"
            "% TODO: unresolved; keep exact comment.   \n\n"
            "Text% no inserted word separator   \nnext line\n"
        )
        expected = source.replace("and \\citep{b}.   \n", "and \\citep{b}.\n").replace("\\varepsilon$.  \n", "\\varepsilon$.\n")
        self.assertEqual(cleanup.format_tex(source)[0], expected)

    def test_literal_environments_and_inline_verb_are_exact(self):
        for name in cleanup.LITERAL_ENVS:
            with self.subTest(name=name):
                source = f"before  \n\\begin{{{name}}}\nvalue   \n  \n\\end{{{name}}}\nafter  \n"
                expected = source.replace("before  \n", "before\n").replace("after  \n", "after\n")
                self.assertEqual(cleanup.format_tex(source)[0], expected)
        self.assertEqual(cleanup.format_tex("\\verb|a  |   \n")[0], "\\verb|a  |   \n")

    def test_escaped_percent_and_control_space(self):
        source = "Rate is 50\\%.  \nline\\   \nrow\\\\   \n"
        self.assertEqual(cleanup.format_tex(source)[0], "Rate is 50\\%.\nline\\   \nrow\\\\   \n")

    def test_custom_literal_environment_and_unclosed_block(self):
        source = "\\begin{CustomCode}\n  trailing   \n"
        result, notes = cleanup.format_tex(source, ["CustomCode"])
        self.assertEqual(result, source)
        self.assertTrue(notes)

    def test_custom_catcode_file_is_unchanged(self):
        source = "\\catcode`\\ =12\nkeep   \n"
        self.assertEqual(cleanup.format_tex(source)[0], source)

    def test_bom_crlf_and_no_final_newline(self):
        source = b"\xef\xbb\xbfHello  \r\nWorld  "
        result, _ = cleanup.transform(source, ".tex")
        self.assertEqual(result, b"\xef\xbb\xbfHello\r\nWorld")
        self.assertEqual(cleanup.transform(result, ".tex")[0], result)

    def test_unicode_separator_is_not_a_source_newline(self):
        source = "left \u2028right   \n"
        self.assertEqual(cleanup.format_tex(source)[0], "left \u2028right\n")


@unittest.skipUnless(importlib.util.find_spec("markdown_it"), "markdown-it-py is optional")
class MarkdownTests(unittest.TestCase):
    def check_case(self, protected):
        from markdown_it import MarkdownIt
        source = "Ordinary paragraph. \n\n" + protected + "\n\nAnother paragraph. \n"
        expected = "Ordinary paragraph.\n\n" + protected + "\n\nAnother paragraph.\n"
        result, _ = cleanup.format_markdown(source)
        self.assertEqual(result, expected)
        self.assertEqual(MarkdownIt().render(source), MarkdownIt().render(result))
        self.assertEqual(cleanup.format_markdown(result)[0], result)

    def test_hard_breaks_and_tabs(self):
        self.check_case("Two spaces.  \nThree spaces.   \nBackslash.\\\nTabs.\t")

    def test_fences_of_different_lengths_and_types(self):
        for protected in ["````python\nvalue = 'x '   \n```\nkept   \n````", "~~~text\nraw   \n~~~", "    indented   \n    code   "]:
            with self.subTest(protected=protected):
                self.check_case(protected)

    def test_multiline_inline_code(self):
        self.check_case("Use `code \ncontinued ` literally. ")

    def test_nested_list_and_quote_fence(self):
        self.check_case("- Item   \n\n  ```text\n  keep   \n  ```\n\n> ~~~\n> keep   \n> ~~~")

    def test_html_comments_and_preformatted_html(self):
        self.check_case("<pre>\nexact   \n\nmore   \n</pre>\n\n<!-- TODO keep   -->")

    def test_multiline_math_across_blank_lines(self):
        for protected in ["$$\nR \\ne \\mathbb{R}   \n\ne = 1   \n$$", "\\[\na   \n\nb   \n\\]", "Inline $\\epsilon \\ne \\varepsilon$. "]:
            with self.subTest(protected=protected):
                self.check_case(protected)

    def test_math_environments_do_not_skip_surrounding_prose(self):
        for opening, closing in [("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)")]:
            protected = (
                opening + "\n\\begin{array}{cc}\na & b \\\\   \n\n"
                "\\begin{aligned}\nx &= y   \n\\end{aligned}\n\\end{array}\n" + closing
            )
            with self.subTest(opening=opening):
                self.check_case(protected)
                self.assertEqual(cleanup.format_markdown(protected)[1], [])

    def test_inline_array_does_not_skip_surrounding_prose(self):
        self.check_case("Write $\\begin{array}{r} x = y \\end{array}$ with $x \\in R$. ")

    def test_tex_examples_in_code_do_not_skip_surrounding_prose(self):
        for protected in [
            "````tex\n$$\n\\begin{array}{cc}\na & b   \n````",
            "    \\begin{verbatim}\n    exact   ",
            "Use `\\begin{array}` here. ",
            "Use ``\\begin{array}\nmore ` code   `` here. ",
            "<!-- \\begin{example} $$ -->",
        ]:
            with self.subTest(protected=protected):
                self.check_case(protected)

    def test_code_delimiters_do_not_end_a_math_block(self):
        source = "Before. \n\n$$\n\\begin{array}{c}\n\n```\n$$\n```\n\nkeep exact \n"
        result, notes = cleanup.format_markdown(source)
        self.assertEqual(result, source.replace("Before. \n", "Before.\n"))
        self.assertTrue(any("Unclosed math delimiter" in note for note in notes))

    def test_raw_tex_outside_math_is_still_preserved(self):
        for protected in [
            "\\begin{verbatim}\n\nkeep exact \n\n\\end{verbatim}",
            "$$x$$ \\begin{verbatim}\n\nkeep exact \n\n\\end{verbatim}",
            "$x$ \\begin{verbatim}\n\nkeep exact \n\n\\end{verbatim}",
            "Price $5 and $10. \\begin{verbatim}\n\nkeep exact \n\n\\end{verbatim}",
            "Use `code` then \\begin{verbatim}\n\nkeep exact \n\n\\end{verbatim}",
            "Use `$$` literally.\n\n\\begin{verbatim}\n$$\n\nkeep exact \n\n\\end{verbatim}",
            r"\$$" + "\n\\begin{verbatim}\n$$\n\nkeep exact \n\n\\end{verbatim}",
        ]:
            source = "Before. \n\n" + protected + "\n\nAfter. \n"
            with self.subTest(protected=protected):
                result, notes = cleanup.format_markdown(source)
                self.assertEqual(result, source)
                self.assertTrue(any("raw TeX" in note for note in notes))

    def test_unclosed_math_environment_preserves_remainder(self):
        source = "Before. \n\n$$\n\\begin{array}{c}\n\nkeep exact \n"
        result, notes = cleanup.format_markdown(source)
        self.assertEqual(result, source.replace("Before. \n", "Before.\n"))
        self.assertTrue(any("Unclosed math delimiter" in note for note in notes))
        self.assertEqual(cleanup.format_markdown(result)[0], result)

    def test_math_environment_preserves_bom_crlf_and_eof(self):
        source = b"\xef\xbb\xbfBefore. \r\n\r\n$$\r\n\\begin{array}{c}\r\nx   \r\n\\end{array}\r\n$$\r\n\r\nAfter. "
        expected = source.replace(b"Before. \r\n", b"Before.\r\n").removesuffix(b" ")
        result, notes = cleanup.transform(source, ".md")
        self.assertEqual(result, expected)
        self.assertEqual(notes, [])
        self.assertEqual(cleanup.transform(result, ".md")[0], result)

    def test_front_matter_block_scalar(self):
        source = "---\ntitle: Notes\nraw: |\n  keep   \n  literal   \n---\n\nParagraph. \n"
        result, _ = cleanup.format_markdown(source)
        self.assertEqual(result, source[:-2] + "\n")

    def test_unclosed_front_matter_is_preserved(self):
        source = "---\nraw: |\n  keep   \n"
        self.assertEqual(cleanup.format_markdown(source)[0], source)

    def test_links_footnotes_table_and_currency(self):
        self.check_case("[label](image.png) \n\n[id]: ./target.md \n\n[^note]: A note. \n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nCosts $5. ")

    def test_unknown_container_is_preserved(self):
        source = ":::custom\ncontent \n:::\n"
        self.assertEqual(cleanup.format_markdown(source)[0], source)

    def test_bom_and_crlf_are_preserved(self):
        source = b"\xef\xbb\xbfParagraph. \r\n\r\nMore. \r\n"
        self.assertEqual(cleanup.transform(source, ".md")[0], b"\xef\xbb\xbfParagraph.\r\n\r\nMore.\r\n")


class WriteTests(unittest.TestCase):
    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cleanup.main(list(args))
        return code, json.loads(output.getvalue())

    def test_check_does_not_write_and_apply_backs_up_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "source.tex"
            source = b"\xef\xbb\xbfText.   \r\n% TODO preserve   \r\n"
            path.write_bytes(source)
            path.chmod(0o640)
            code, report = self.invoke(str(path))
            self.assertEqual(code, 0)
            self.assertEqual(path.read_bytes(), source)
            code, report = self.invoke(str(path), "--write", "--backup-dir", str(base / "backup"))
            self.assertEqual(code, 0)
            entry = report["files"][0]
            self.assertEqual(Path(entry["backup"]).read_bytes(), source)
            self.assertTrue(entry["written"])
            self.assertEqual(path.read_bytes(), b"\xef\xbb\xbfText.\r\n% TODO preserve   \r\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            _, second = self.invoke(str(path))
            self.assertEqual(second["files"][0]["changed_lines"], [])

    def test_existing_backup_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "source.tex"
            path.write_bytes(b"Text   \n")
            (base / "backup").mkdir()
            (base / "backup" / "keep").write_bytes(b"original backup")
            code, _ = self.invoke(str(path), "--write", "--backup-dir", str(base / "backup"))
            self.assertEqual(code, 2)
            self.assertEqual(path.read_bytes(), b"Text   \n")
            self.assertEqual((base / "backup" / "keep").read_bytes(), b"original backup")

    def test_invalid_second_file_prevents_all_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            good, bad = base / "good.tex", base / "bad.md"
            good.write_bytes(b"Text   \n")
            bad.write_bytes(b"\xff\xfe")
            code, _ = self.invoke(str(good), str(bad), "--write", "--backup-dir", str(base / "backup"))
            self.assertEqual(code, 2)
            self.assertEqual(good.read_bytes(), b"Text   \n")
            self.assertFalse((base / "backup").exists())

    def test_concurrent_edit_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.tex"
            path.write_bytes(b"User's newer edit")
            with self.assertRaises(RuntimeError):
                cleanup.atomic_replace(path, b"old content", b"replacement")
            self.assertEqual(path.read_bytes(), b"User's newer edit")

    def test_missing_markdown_dependency_prevents_all_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            tex, md = base / "main.tex", base / "notes.md"
            tex.write_bytes(b"Text   \n")
            md.write_bytes(b"Paragraph. \n")
            result = subprocess.run([sys.executable, "-S", str(Path(cleanup.__file__)), str(tex), str(md),
                                     "--write", "--backup-dir", str(base / "backup")],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("markdown-it-py is unavailable", json.loads(result.stdout)["error"])
            self.assertEqual(tex.read_bytes(), b"Text   \n")
            self.assertEqual(md.read_bytes(), b"Paragraph. \n")
            self.assertFalse((base / "backup").exists())

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "target.tex").write_bytes(b"Text   \n")
            (base / "link.tex").symlink_to(base / "target.tex")
            code, _ = self.invoke(str(base / "link.tex"))
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
