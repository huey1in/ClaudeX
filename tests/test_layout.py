import unittest
from pathlib import Path


class ProjectLayoutTests(unittest.TestCase):
    def test_application_modules_are_grouped_by_feature(self):
        root = Path(__file__).resolve().parents[1]
        expected = [
            "account/__init__.py",
            "account/check.py",
            "account/storage.py",
            "billing/__init__.py",
            "billing/claude.py",
            "billing/models.py",
            "billing/stripe.py",
            "billing/workflow.py",
            "core/__init__.py",
            "core/config.py",
            "core/console.py",
            "core/session.py",
            "core/version.py",
            "registration/__init__.py",
            "registration/moemail.py",
            "registration/register.py",
            "version.json",
        ]
        obsolete_root_modules = [
            "accounts.py",
            "check.py",
            "config.py",
            "console.py",
            "moemail.py",
            "register.py",
            "session.py",
            "version.py",
        ]

        self.assertFalse((root / "claudex").exists())
        for relative_path in expected:
            with self.subTest(path=relative_path):
                self.assertTrue((root / relative_path).exists())
        for relative_path in obsolete_root_modules:
            with self.subTest(obsolete=relative_path):
                self.assertFalse((root / relative_path).exists())


if __name__ == "__main__":
    unittest.main()
