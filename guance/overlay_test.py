#!/usr/bin/env python3
"""Check that incremental archive overlays apply and revert fork changes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from overlay import overlay


class OverlayTest(unittest.TestCase):
    def test_changes_and_reverts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, source = root / "repo", root / "src"
            repo.mkdir()
            source.mkdir()

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("init", "-q")
            git("config", "user.email", "local-test@example.invalid")
            git("config", "user.name", "Local test")
            for name in ("modified", "deleted"):
                (repo / name).write_text("base")
                (source / name).write_text("base")
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            (repo / "modified").write_text("fork")
            (repo / "deleted").unlink()
            (repo / "new").write_text("executable")
            (repo / "new").chmod(0o755)
            (repo / "link").symlink_to("modified")
            git("add", ".")
            git("commit", "-qm", "fork")
            state = root / "paths.json"
            overlay(repo, source, base, state)
            self.assertEqual((source / "modified").read_text(), "fork")
            self.assertFalse((source / "deleted").exists())
            self.assertTrue((source / "new").stat().st_mode & 0o111)
            self.assertTrue((source / "link").is_symlink())
            git("checkout", "--detach", "-q", base)
            overlay(repo, source, base, state)
            self.assertEqual((source / "modified").read_text(), "base")
            self.assertEqual((source / "deleted").read_text(), "base")
            self.assertFalse((source / "new").exists())
            self.assertFalse((source / "link").is_symlink())


if __name__ == "__main__":
    unittest.main()
