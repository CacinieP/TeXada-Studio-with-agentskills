import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_ocr_corpus as corpus


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def book(self, identity, data, suffix=".tex", overlays=None):
        path = self.base / (identity + suffix)
        path.write_bytes(data)
        result = {"id": identity, "source": path.name, "source_sha256": corpus.sha(data)}
        if overlays is not None:
            result["overlays"] = overlays
        return result

    def overlay(self, identity, before, after):
        before_path, after_path = self.base / (identity + ".before"), self.base / (identity + ".after")
        before_path.write_bytes(before)
        after_path.write_bytes(after)
        return {"id": identity, "before": before_path.name, "before_sha256": corpus.sha(before),
                "after": after_path.name, "after_sha256": corpus.sha(after)}

    def run_books(self, books):
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "books": books}))
        report = corpus.run(manifest, self.base / "private", self.base / "export")
        return report, self.base / "private", self.base / "export"

    @unittest.skipUnless(importlib.util.find_spec("markdown_it"), "markdown-it-py is optional")
    def test_all_book_states_and_original_bytes_are_preserved(self):
        inputs = [("clean", b"Done.\n"), ("change", b"Plain. \n\nHard break.  \n"),
                  ("nul", b"Text\x00. \n"), ("rawtex", b"\\begin{custom}\nText. \n")]
        report, private, export = self.run_books([self.book(identity, data, ".md") for identity, data in inputs])
        self.assertEqual([b["status"] for b in report["books"]],
                         ["unchanged", "changed", "refused_preserved", "skipped_preserved"])
        self.assertFalse(report["summary"]["fully_formatted"])
        self.assertTrue(report["summary"]["originals_unchanged"])
        self.assertEqual((private / "change.md").read_bytes(), b"Plain.\n\nHard break.  \n")
        for identity, data in inputs:
            self.assertEqual((self.base / (identity + ".md")).read_bytes(), data)
            if identity != "change":
                self.assertEqual((private / (identity + ".md")).read_bytes(), data)
        self.assertEqual(sorted(p.name for p in (export / "diffs").iterdir()), ["change.diff"])
        self.assertNotIn(str(self.base), (export / "summary.json").read_text())

    def test_overlay_in_nul_book_is_saved_without_claiming_formatter_success(self):
        original = b"Untouched\x00.\nWrong R.\nTail.\n"
        overlay = self.overlay("page", b"Wrong R.\n", b"Correct M.\n")
        report, private, export = self.run_books([self.book("nul", original, ".md", [overlay])])
        self.assertEqual((private / "nul.md").read_bytes(), b"Untouched\x00.\nCorrect M.\nTail.\n")
        book = report["books"][0]
        self.assertEqual(book["status"], "refused_preserved")
        self.assertEqual(book["idempotence"], "not_run")
        self.assertTrue(book["output_changed"])
        self.assertEqual(len(book["overlays"]), 1)
        self.assertNotIn(b"\x00", (export / "diffs/nul.diff").read_bytes())

    def test_nul_edit_exports_replayable_escaped_json(self):
        original, expected = b"Left\x00 right\nKeep\x1cseparator\n", b"Left R right\nKeep\x1cseparator\n"
        overlay = self.overlay("page", b"Left\x00 right\n", b"Left R right\n")
        report, private, export = self.run_books([self.book("control", original, ".tex", [overlay])])
        book = report["books"][0]
        self.assertEqual(book["diff_export_status"], "json_byte_patch_exported")
        raw = (export / book["text_patch"]).read_bytes()
        self.assertNotIn(b"\x00", raw)
        self.assertNotIn(b"\x1c", raw)
        self.assertEqual(corpus.apply_text_patch(original, json.loads(raw)), expected)
        self.assertEqual((private / "control.tex").read_bytes(), expected)

    def test_overlay_matches_original_offsets_independent_of_replacement_lengths(self):
        original = b"A old.\nMiddle.\nB old.\n"
        one = self.overlay("first", b"A old.\n", b"A much longer corrected.\n")
        two = self.overlay("second", b"B old.\n", b"B.\n")
        report, private, _ = self.run_books([self.book("book", original, overlays=[two, one])])
        self.assertEqual((private / "book.tex").read_bytes(), b"A much longer corrected.\nMiddle.\nB.\n")
        self.assertEqual([item["id"] for item in report["books"][0]["overlays"]], ["first", "second"])

    def test_duplicate_overlay_match_preserves_book(self):
        original = b"same\nsame\n"
        report, private, _ = self.run_books([self.book("book", original, overlays=[self.overlay("p", b"same", b"new")])])
        self.assertEqual(report["books"][0]["status"], "input_error_preserved")
        self.assertEqual((private / "book.tex").read_bytes(), original)

    def test_case_insensitive_book_ids_are_rejected_before_output(self):
        first = self.book("first", b"First\n")
        second = self.book("second", b"Second\n")
        first["id"], second["id"] = "Book", "book"
        with self.assertRaisesRegex(ValueError, "unique safe"):
            self.run_books([first, second])
        self.assertFalse((self.base / "private").exists())

    def test_concurrent_output_file_is_not_overwritten(self):
        book = self.book("book", b"Source\n")
        def competing_writer(data, suffix):
            (self.base / "private/book.tex").write_bytes(b"Other writer\n")
            return data, {"status": "unchanged", "idempotence": "passed"}
        with patch.object(corpus, "format_copy", side_effect=competing_writer):
            with self.assertRaises(FileExistsError):
                self.run_books([book])
        self.assertEqual((self.base / "private/book.tex").read_bytes(), b"Other writer\n")

    def test_overlapping_overlay_ranges_preserve_book(self):
        original = b"abcdef\n"
        overlays = [self.overlay("p1", b"abcd", b"new"), self.overlay("p2", b"cdef", b"newer")]
        report, private, _ = self.run_books([self.book("book", original, overlays=overlays)])
        self.assertIn("overlap", report["books"][0]["error"])
        self.assertEqual((private / "book.tex").read_bytes(), original)

    def test_overlay_hash_mismatch_preserves_book(self):
        original = b"before\n"
        overlay = self.overlay("p", original, b"after\n")
        (self.base / overlay["after"]).write_bytes(b"changed after review\n")
        report, private, _ = self.run_books([self.book("book", original, overlays=[overlay])])
        self.assertEqual(report["books"][0]["status"], "input_error_preserved")
        self.assertEqual((private / "book.tex").read_bytes(), original)

    def test_source_hash_mismatch_is_visible_without_aborting_other_books(self):
        bad = self.book("stale", b"Current  \n")
        bad["source_sha256"] = "0" * 64
        report, private, _ = self.run_books([bad, self.book("good", b"Clean.   \n")])
        self.assertEqual([book["status"] for book in report["books"]], ["input_error_preserved", "changed"])
        self.assertEqual((private / "stale.tex").read_bytes(), b"Current  \n")
        self.assertEqual((private / "good.tex").read_bytes(), b"Clean.\n")

    def test_missing_file_remains_visible_and_does_not_leak_path(self):
        book = self.book("missing", b"Text\n")
        (self.base / book["source"]).unlink()
        report, _, export = self.run_books([book])
        self.assertEqual(report["books"][0]["status"], "input_unavailable")
        self.assertIsNone(report["books"][0]["output"])
        self.assertNotIn(str(self.base), (export / "summary.json").read_text())

    def test_nonidempotent_candidate_is_discarded(self):
        calls = [(b"First\n", []), (b"Second\n", [])]
        with patch.object(corpus.format_whitespace, "transform", side_effect=calls):
            report, private, _ = self.run_books([self.book("bad", b"Original\n")])
        self.assertEqual((private / "bad.tex").read_bytes(), b"Original\n")
        self.assertEqual(report["books"][0]["status"], "validation_failed_preserved")
        self.assertEqual(report["books"][0]["idempotence"], "failed")

    def test_existing_output_is_never_overwritten(self):
        books = [self.book("book", b"Text.  \n")]
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "books": books}))
        private = self.base / "private"
        private.mkdir()
        keep = private / "keep"
        keep.write_bytes(b"Existing")
        with self.assertRaisesRegex(ValueError, "both be new"):
            corpus.run(manifest, private, self.base / "export")
        self.assertEqual(keep.read_bytes(), b"Existing")

    def test_nested_private_and_export_directories_are_rejected(self):
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "books": [self.book("book", b"Text.\n")]}))
        with self.assertRaisesRegex(ValueError, "non-nested"):
            corpus.run(manifest, self.base / "private", self.base / "private/export")

    def test_unsafe_or_duplicate_ids_are_rejected_before_creating_output(self):
        for bad_id in ["../escape", "space id", ""]:
            with self.subTest(identity=bad_id):
                book = self.book("safe", b"Text.\n")
                book["id"] = bad_id
                with self.assertRaises(ValueError):
                    self.run_books([book])
                self.assertFalse((self.base / "private").exists())
        book = self.book("safe", b"Text.\n")
        with self.assertRaises(ValueError):
            self.run_books([book, book])

    @unittest.skipUnless(shutil.which("git"), "git required to validate patch replay")
    def test_git_patch_replays_controls_crlf_bom_and_missing_final_newline(self):
        original = b"\xef\xbb\xbfText\x0bwith\x1ccontrols\r\nNext\x1dline\r\nChanged. \r\nLast. "
        expected = b"\xef\xbb\xbfText\x0bwith\x1ccontrols\r\nNext\x1dline\r\nChanged.\r\nLast."
        (self.base / "book.md").write_bytes(original)
        diff = corpus.make_diff(original, expected, "book.md")
        (self.base / "change.diff").write_bytes(diff)
        completed = subprocess.run(["git", "apply", "--unidiff-zero", "change.diff"], cwd=self.base,
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual((self.base / "book.md").read_bytes(), expected)
        self.assertIn(b"@@ -3,2 +3,2 @@", diff)
        self.assertNotIn(b"\x0b", diff)

    def test_text_patch_refuses_stale_source_and_tampered_range(self):
        original, after = b"A\x00\nB\n", b"A R\nB\n"
        result = corpus.make_text_patch(original, after)
        self.assertEqual(corpus.apply_text_patch(original, result), after)
        with self.assertRaisesRegex(ValueError, "source hash"):
            corpus.apply_text_patch(b"different", result)
        result["edits"][0]["old"] = "wrong"
        with self.assertRaisesRegex(ValueError, "old bytes"):
            corpus.apply_text_patch(original, result)

    def test_text_patch_supports_insert_delete_and_invalid_utf8(self):
        for original, after in [(b"A\nB\n", b"Prefix\nA\nB\n"), (b"A\nB\n", b"B\n"),
                                (b"A\xff\n", b"A\xfe\n"), (b"", b"Text")]:
            with self.subTest(original=original):
                patch_value = corpus.make_text_patch(original, after)
                serialized = json.dumps(patch_value, ensure_ascii=True).encode("ascii")
                self.assertEqual(corpus.apply_text_patch(original, json.loads(serialized)), after)

    def test_batch_end_rechecks_already_processed_originals(self):
        books = [self.book("early", b"Early.\n"), self.book("later", b"Later.\n")]
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "books": books}))
        def change_early(done, total, entry):
            if done == total:
                (self.base / "early.tex").write_bytes(b"User edit after early processing\n")
        report = corpus.run(manifest, self.base / "private", self.base / "export", change_early)
        self.assertEqual(report["books"][0]["status"], "source_changed_after_processing")
        self.assertFalse(report["summary"]["originals_unchanged"])
        self.assertFalse(report["summary"]["fully_formatted"])
        self.assertEqual((self.base / "private/early.tex").read_bytes(), b"Early.\n")
        self.assertEqual((self.base / "early.tex").read_bytes(), b"User edit after early processing\n")

    def test_source_change_during_processing_is_reported(self):
        book = self.book("race", b"Original\n")
        def mutate(data, suffix):
            (self.base / "race.tex").write_bytes(b"Concurrent edit\n")
            return data, []
        with patch.object(corpus.format_whitespace, "transform", side_effect=mutate):
            report, private, _ = self.run_books([book])
        self.assertEqual(report["books"][0]["status"], "input_error_preserved")
        self.assertFalse(report["summary"]["originals_unchanged"])
        self.assertEqual((self.base / "race.tex").read_bytes(), b"Concurrent edit\n")
        self.assertEqual((private / "race.tex").read_bytes(), b"Original\n")


if __name__ == "__main__":
    unittest.main()
