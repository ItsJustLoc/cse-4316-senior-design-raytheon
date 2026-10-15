"""Exercise the commit-message hook through its command-line interface."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_commit_message.py"


class CommitMessageTests(unittest.TestCase):
    def check_message(self, message):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "COMMIT_EDITMSG"
            path.write_text(message, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path)], capture_output=True
            )

    def test_allowed_prefixes_and_optional_body(self):
        for prefix in ("docs", "bug", "feat", "patch"):
            with self.subTest(prefix=prefix):
                result = self.check_message(f"{prefix}: describe the change\n\nDetails.\n")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_subjects_are_rejected(self):
        for message in (
            "", "docs:", "docs: ", "docs:   ", "docs:  extra space",
            "docs:no space", "docs:\twrong separator", "Docs: wrong case",
            "fix: unsupported prefix", "<docs>: literal brackets",
            "update README", "\nfeat: empty subject", "Merge branch 'main'",
        ):
            with self.subTest(message=message):
                result = self.check_message(message)
                self.assertEqual(result.returncode, 1)
                self.assertIn(b"docs: update README", result.stderr)

    def test_unicode_and_windows_line_endings(self):
        result = self.check_message("docs: clarify café example\r\n\r\nDetails.\r\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_range_checks_each_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(
                    ["git", *args], cwd=directory, text=True, stderr=subprocess.DEVNULL
                ).strip()

            git("init", "-q")
            git("config", "user.name", "Hook Test")
            git("config", "user.email", "test@example.invalid")
            git("config", "commit.gpgsign", "false")
            git("commit", "--allow-empty", "-m", "old unconstrained commit")
            base = git("rev-parse", "HEAD")
            git("commit", "--allow-empty", "-m", "feat: valid new commit")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--range", f"{base}..HEAD"],
                cwd=directory, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            git("commit", "--allow-empty", "-m", "invalid new commit")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--range", f"{base}..HEAD"],
                cwd=directory, capture_output=True,
            )
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
