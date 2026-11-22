"""Verify git bundle backup and pruning under paths containing spaces."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("backup.sh")


class BackupScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="texada backup test ")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name) / "dir with spaces"
        self.repo = self.parent / "my repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.repo / "scripts" / "backup.sh")
        (self.repo / "scripts" / "backup.sh").chmod(0o755)
        (self.repo / "README.md").write_text("synthetic backup test\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic Backup Test")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Initial commit")
        self.backup_dir = self.parent / "_backups" / "my repo"

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def run_backup(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.repo / "scripts" / "backup.sh")],
            cwd=str(self.parent),
            text=True,
            capture_output=True,
        )

    def test_backup_in_path_with_spaces_prunes_12_bundles_to_10_newest(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        manual_snapshot = self.backup_dir / "0000-manual-snapshot.bundle"
        manual_snapshot.write_bytes(b"manual-pinned-bundle")
        older_names = [f"20250101-0000{index:02d}.bundle" for index in range(1, 12)]
        base_ts = 1_700_000_000
        for offset, name in enumerate(older_names):
            bundle_path = self.backup_dir / name
            bundle_path.write_bytes(b"synthetic-old-bundle")
            os.utime(bundle_path, (base_ts + offset, base_ts + offset))

        result = self.run_backup()
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout}\nstderr={result.stderr}")

        self.assertTrue(manual_snapshot.exists(), "手动命名的非时间戳 .bundle 不应被自动清理误删")
        remaining = sorted(
            item.name for item in self.backup_dir.glob("*.bundle") if item.name != manual_snapshot.name
        )
        self.assertEqual(len(remaining), 10, f"Expected 10 newest timestamped bundles, got {remaining}")
        self.assertNotIn("20250101-000001.bundle", remaining)
        self.assertNotIn("20250101-000002.bundle", remaining)
        for kept in older_names[2:]:
            self.assertIn(kept, remaining)

        newest_bundle = self.backup_dir / remaining[-1]
        self.assertNotIn(newest_bundle.name, older_names)
        verify = subprocess.run(
            ["git", "-C", str(self.repo), "bundle", "verify", str(newest_bundle)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_first_backup_in_path_with_spaces_succeeds_when_under_retention_limit(self):
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout}\nstderr={result.stderr}")
        bundles = list(self.backup_dir.glob("*.bundle"))
        self.assertEqual(len(bundles), 1)
        verify = subprocess.run(
            ["git", "-C", str(self.repo), "bundle", "verify", str(bundles[0])],
            text=True,
            capture_output=True,
        )
        self.assertEqual(verify.returncode, 0, verify.stderr)


if __name__ == "__main__":
    unittest.main()
