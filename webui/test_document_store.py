"""Unit tests for DocumentStore filename hardening and Windows NTFS listing behavior."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from document_store import DocumentError, DocumentStore, document_name


class DocumentNameWindowsHardeningTests(unittest.TestCase):
    def test_rejects_windows_reserved_device_names_and_multi_dot_variants(self):
        reserved = [
            "CON.tex",
            "con.tex",
            "PRN.tex",
            "prn.tex",
            "AUX.tex",
            "NUL.tex",
            "COM1.tex",
            "com9.tex",
            "LPT1.tex",
            "lpt9.tex",
            "CON.notes.tex",
            "aux.backup.tex",
            "LPT2.draft.v1.tex",
            "CON .notes.tex",
        ]
        for bad in reserved:
            with self.subTest(name=bad), self.assertRaises(DocumentError):
                document_name(bad)

    def test_rejects_trailing_space_or_dot_before_extension(self):
        for bad in ("note .tex", "draft   .tex", " .tex"):
            with self.subTest(name=bad), self.assertRaises(DocumentError):
                document_name(bad)

    def test_allows_non_reserved_prefixes_and_cjk_names(self):
        for valid in ("CONSOLE.tex", "COM10.tex", "LPT10.tex", "notes.v1.tex", "微积分笔记.tex"):
            with self.subTest(name=valid):
                self.assertEqual(document_name(valid), valid)


class DocumentListingZeroInodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docs = self.root / "documents"
        self.samples = self.root / "samples"
        self.docs.mkdir()
        self.samples.mkdir()

    def test_listing_keeps_distinct_files_when_st_ino_is_zero(self):
        (self.docs / "alpha.tex").write_text("alpha", encoding="utf-8")
        (self.docs / "beta.tex").write_text("beta", encoding="utf-8")
        (self.samples / "gamma.tex").write_text("gamma", encoding="utf-8")
        store = DocumentStore(self.docs, self.samples)

        real_stat = Path.stat

        def zero_ino_stat(path_self, *args, **kwargs):
            st = real_stat(path_self, *args, **kwargs)
            return SimpleNamespace(
                st_mode=st.st_mode,
                st_size=st.st_size,
                st_mtime=st.st_mtime,
                st_dev=0,
                st_ino=0,
            )

        with patch.object(Path, "stat", autospec=True, side_effect=zero_ino_stat):
            listed = store.listing()

        self.assertEqual(listed["files"], ["alpha.tex", "beta.tex", "gamma.tex"])

    @unittest.skipUnless(hasattr(os, "link"), "hardlink test requires os.link")
    def test_listing_still_deduplicates_nonzero_inode_aliases(self):
        first = self.docs / "first.tex"
        first.write_text("same", encoding="utf-8")
        second = self.docs / "second.tex"
        os.link(first, second)
        if first.stat().st_ino == 0:
            self.skipTest("filesystem reports st_ino == 0")
        store = DocumentStore(self.docs, self.samples)
        listed = store.listing()
        self.assertEqual(len(listed["files"]), 1)


if __name__ == "__main__":
    unittest.main()
