"""The fixed host loads real instructions and fails closed at its file boundary."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.skills_runtime import load_skill, MAX_SKILL_BYTES


class SkillRuntimeTest(unittest.TestCase):
    def make_skill(self, root, text=None):
        directory = Path(root) / "doc-formula-verify"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "SKILL.md"
        path.write_text(text or '---\nname: doc-formula-verify\ndescription: Syntax review\n---\nKeep human review.\n', encoding="utf-8")
        return path

    def test_reads_exact_body_and_hash_and_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_skill(directory)
            checker = path.parent / "scripts" / "verify.py"
            checker.parent.mkdir()
            checker.write_text("# checker\n")
            skill = load_skill(skill_root=directory)
            self.assertEqual(skill.instructions, path.read_text())
            self.assertEqual(skill.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(skill.checker_sha256, hashlib.sha256(checker.read_bytes()).hexdigest())
            path.write_text(path.read_text() + "New rule.\n")
            self.assertNotEqual(load_skill(skill_root=directory).sha256, skill.sha256)

    def test_disallows_arbitrary_names_and_traversal(self):
        for name in ("../other", "doc-table-audit", "/tmp/SKILL.md"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "skill_not_allowed"):
                load_skill(name)

    def test_rejects_skill_symlink_outside_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            outside = self.make_skill(Path(directory) / "outside")
            (root / "doc-formula-verify").symlink_to(outside.parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "skill_path_escape"):
                load_skill(skill_root=root)

    def test_rejects_checker_symlink_outside_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            path = self.make_skill(root)
            outside = Path(directory) / "outside.py"
            outside.write_text("# outside\n")
            scripts = path.parent / "scripts"
            scripts.mkdir()
            (scripts / "verify.py").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "skill_path_escape"):
                load_skill(skill_root=root)

    def test_rejects_invalid_metadata_encoding_and_oversized_content(self):
        cases = [
            (b"no frontmatter", "skill_missing_frontmatter"),
            (b"---\nname: other\ndescription: hi\n---\nbody", "skill_name_mismatch"),
            (b"---\nname: doc-formula-verify\nname: other\n---\nbody", "skill_invalid_frontmatter"),
            (b"---\nname: doc-formula-verify\ndescription: hi\n---\n", "skill_empty_instructions"),
            (b"\xff", "skill_invalid_encoding"),
            (b"x" * (MAX_SKILL_BYTES + 1), "skill_too_large"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_skill(directory)
            for raw, reason in cases:
                with self.subTest(reason=reason):
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(ValueError, reason):
                        load_skill(skill_root=directory)

    def test_unavailable_skill_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "skill_unavailable"):
            load_skill(skill_root=directory)


if __name__ == "__main__":
    unittest.main()
