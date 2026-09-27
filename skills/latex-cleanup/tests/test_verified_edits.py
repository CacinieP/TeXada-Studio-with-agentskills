import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_verified_edits as verified


class VerifiedEditsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source.tex"
        self.plan_path = self.base / "edits.json"
        self.backup = self.base / "backup"

    def edit(self, old="errored", new="correct", edit_id="fix-1"):
        return {"id": edit_id, "old": old, "new": new, "evidence": {
            "kind": "source_page", "reference": "book.pdf", "locator": "PDF page 42, equation 3",
            "note": "The supplied page shows the corrected spelling.",
        }}

    def setup_plan(self, data=b"This is errored.\n", edits=None):
        self.source.write_bytes(data)
        plan = {"schema_version": 1, "source": self.source.name,
                "source_sha256": verified.digest(data), "edits": [self.edit()] if edits is None else edits}
        self.save_plan(plan)
        return plan

    def save_plan(self, plan):
        self.plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def invoke(self, write=False, diff=False):
        args = [str(self.plan_path)]
        if write:
            args += ["--write", "--backup-dir", str(self.backup)]
        if diff:
            args += ["--diff"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = verified.main(args)
        return code, json.loads(out.getvalue()), err.getvalue()

    def test_default_dry_run_and_relative_paths(self):
        self.setup_plan()
        before = self.source.read_bytes()
        code, report, diff = self.invoke(diff=True)
        self.assertEqual(code, 0)
        self.assertFalse(report["written"])
        self.assertTrue(report["changed"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.backup.exists())
        self.assertIn("-This is errored.", diff)
        self.assertIn("+This is correct.", diff)
        self.assertEqual(report["edits"][0]["resolved_reference"], str(self.base / "book.pdf"))
        self.assertIn("not independently validated", report["evidence_verification"])

    def test_write_has_exact_backups_traceability_and_permissions(self):
        original = b"\xef\xbb\xbfThis is errored.\r\nLast line"
        plan = self.setup_plan(original)
        self.source.chmod(0o640)
        plan_bytes = self.plan_path.read_bytes()
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["written"])
        self.assertEqual(self.source.read_bytes(), b"\xef\xbb\xbfThis is correct.\r\nLast line")
        self.assertEqual(stat.S_IMODE(self.source.stat().st_mode), 0o640)
        self.assertEqual((self.backup / "original.bin").read_bytes(), original)
        self.assertEqual(stat.S_IMODE((self.backup / "original.bin").stat().st_mode), 0o640)
        self.assertEqual((self.backup / "plan.json").read_bytes(), plan_bytes)
        record = json.loads((self.backup / "record.json").read_text())
        self.assertEqual(record["status"], "prepared")
        self.assertFalse(record["written"])
        self.assertEqual(record["before_sha256"], verified.digest(original))
        self.assertEqual(record["after_sha256"], verified.digest(self.source.read_bytes()))
        self.assertEqual(record["plan_sha256"], verified.digest(plan_bytes))
        self.assertEqual(record["edits"][0]["evidence"], plan["edits"][0]["evidence"])
        self.assertEqual(record["edits"][0]["start_char"], 8)

    def test_stale_hash_prevents_backup_and_write(self):
        self.setup_plan()
        current = b"User's newer edit."
        self.source.write_bytes(current)
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertIn("Stale plan", report["error"])
        self.assertEqual(self.source.read_bytes(), current)
        self.assertFalse(self.backup.exists())

    def test_ambiguous_including_overlapping_matches(self):
        for data, old in [(b"errored errored", "errored"), (b"aaa", "aa")]:
            with self.subTest(data=data):
                self.setup_plan(data, [self.edit(old)])
                code, report, _ = self.invoke(write=True)
                self.assertEqual(code, 2)
                self.assertIn("ambiguous", report["error"])
                self.assertEqual(self.source.read_bytes(), data)
                self.assertFalse(self.backup.exists())

    def test_all_edits_validate_before_mutation(self):
        self.setup_plan(edits=[self.edit(), self.edit("absent", "replacement", "fix-2")])
        before = self.source.read_bytes()
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertIn("not found", report["error"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.backup.exists())

    def test_overlapping_edits_rejected(self):
        self.setup_plan(b"abcdef", [self.edit("abc", "ABC"), self.edit("cde", "CDE", "fix-2")])
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertIn("Overlapping", report["error"])
        self.assertEqual(self.source.read_bytes(), b"abcdef")

    def test_original_coordinates_not_cascading_replacements(self):
        self.setup_plan(b"abc def", [self.edit("abc", "def"), self.edit("def", "ghi", "fix-2")])
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.source.read_bytes(), b"def ghi")

    def test_deletion_empty_list_and_noop(self):
        self.setup_plan(b"delete this", [self.edit("delete this", "")])
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.source.read_bytes(), b"")
        self.backup = self.base / "unused-backup"
        for edits in ([], [self.edit("text", "text")]):
            self.setup_plan(b"text", edits)
            code, report, _ = self.invoke(write=True)
            self.assertEqual(code, 0, report)
            self.assertFalse(report["changed"])
            self.assertFalse(report["written"])
            self.assertFalse(self.backup.exists())

    def test_empty_old_and_missing_evidence_rejected(self):
        invalid = [self.edit("", "insert")]
        for field in ("kind", "reference", "locator", "note"):
            edit = self.edit()
            edit["evidence"][field] = " "
            invalid.append(edit)
        edit = self.edit()
        del edit["evidence"]["note"]
        invalid.append(edit)
        for edit in invalid:
            with self.subTest(edit=edit):
                self.setup_plan(edits=[edit])
                code, _, _ = self.invoke(write=True)
                self.assertEqual(code, 2)
                self.assertFalse(self.backup.exists())

    def test_duplicate_ids_and_json_keys_rejected(self):
        self.setup_plan(b"abc def", [self.edit("abc"), self.edit("def")])
        code, report, _ = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("Duplicate edit id", report["error"])
        self.plan_path.write_text('{"schema_version": 1, "schema_version": 1}')
        code, report, _ = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("Duplicate JSON key", report["error"])

    def test_utf8_required_and_unicode_not_normalized(self):
        for data in (b"\xfferrored", b"errored\x00"):
            self.setup_plan(data)
            code, _, _ = self.invoke(write=True)
            self.assertEqual(code, 2)
            self.assertEqual(self.source.read_bytes(), data)
            self.assertFalse(self.backup.exists())
        original = "e\u0301\u2028errored\rrest".encode("utf-8")
        self.setup_plan(original)
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.source.read_bytes(), original.replace(b"errored", b"correct"))

    def test_existing_backup_never_overwritten(self):
        self.setup_plan()
        before = self.source.read_bytes()
        self.backup.mkdir()
        (self.backup / "original.bin").write_bytes(b"older backup")
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertIn("must be new", report["error"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual((self.backup / "original.bin").read_bytes(), b"older backup")

    def test_symlink_and_hardlink_sources_not_written(self):
        plan = self.setup_plan()
        link = self.base / "link.tex"
        link.symlink_to(self.source)
        plan["source"] = link.name
        self.save_plan(plan)
        code, _, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        link.unlink()
        os.link(self.source, link)
        code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertIn("hard-linked", report["error"])
        self.assertEqual(self.source.read_bytes(), b"This is errored.\n")
        self.assertFalse(self.backup.exists())

    def test_failed_backup_prevents_source_replacement(self):
        self.setup_plan()
        before = self.source.read_bytes()
        real_write = verified.write_exclusive
        def fail_record(path, data, mode=0o600):
            if path.name == "record.json":
                raise OSError("simulated backup failure")
            real_write(path, data, mode)
        with mock.patch.object(verified, "write_exclusive", side_effect=fail_record):
            code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertFalse(report["written"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual((self.backup / "original.bin").read_bytes(), before)
        self.assertEqual(list(self.base.glob(".verified-edits-*")), [])

    def test_atomic_replace_only_after_complete_backup(self):
        self.setup_plan()
        before = self.source.read_bytes()
        real_replace = verified.os.replace
        def checked_replace(temporary, target):
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual((self.backup / "original.bin").read_bytes(), before)
            self.assertEqual((self.backup / "plan.json").read_bytes(), self.plan_path.read_bytes())
            self.assertEqual(json.loads((self.backup / "record.json").read_text())["status"], "prepared")
            real_replace(temporary, target)
        with mock.patch.object(verified.os, "replace", side_effect=checked_replace):
            code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(list(self.base.glob(".verified-edits-*")), [])

    def test_concurrent_change_preserved_after_backup(self):
        self.setup_plan()
        newer = b"User edited while backup was being saved"
        real_write = verified.write_exclusive
        def change_source(path, data, mode=0o600):
            real_write(path, data, mode)
            if path.name == "record.json":
                self.source.write_bytes(newer)
        with mock.patch.object(verified, "write_exclusive", side_effect=change_source):
            code, report, _ = self.invoke(write=True)
        self.assertEqual(code, 2)
        self.assertIn("changed since validation", report["error"])
        self.assertEqual(self.source.read_bytes(), newer)
        self.assertEqual((self.backup / "original.bin").read_bytes(), b"This is errored.\n")
        self.assertEqual(list(self.base.glob(".verified-edits-*")), [])

    def test_url_reference_and_no_final_newline_diff(self):
        edit = self.edit()
        edit["evidence"]["reference"] = "https://example.com/page"
        self.setup_plan(b"errored", [edit])
        code, report, diff = self.invoke(diff=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["edits"][0]["resolved_reference"], "https://example.com/page")
        self.assertEqual(diff.count("\\ No newline at end of file"), 2)

    def test_stdlib_cli_works_without_site_packages(self):
        self.setup_plan()
        result = subprocess.run([sys.executable, "-S", str(Path(verified.__file__)), str(self.plan_path)],
                                capture_output=True, text=True, timeout=10, cwd=self.base.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["source"], str(self.source))
        self.assertEqual(self.source.read_bytes(), b"This is errored.\n")


if __name__ == "__main__":
    unittest.main()
