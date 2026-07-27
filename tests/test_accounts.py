import json
import tempfile
import unittest
from pathlib import Path

from account.storage import load_accounts, update_account


class UpdateAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "accounts.json"
        self.path.write_text(json.dumps([
            {"uuid": "acct-1", "email": "one@example.com"},
            {"uuid": "acct-2", "email": "two@example.com"},
        ]), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_updates_only_matching_account(self):
        updated = update_account(
            str(self.path),
            "acct-1",
            {"payment": {"status": "pending", "iban_last4": "3000"}},
        )

        records = load_accounts(str(self.path))
        self.assertEqual(updated["payment"]["status"], "pending")
        self.assertEqual(records[0]["payment"]["iban_last4"], "3000")
        self.assertNotIn("payment", records[1])

    def test_rejects_payment_secrets(self):
        for secret in (
            {"payment": {"iban": "DE89370400440532013000"}},
            {"payment": {"client_secret": "pi_secret_value"}},
        ):
            with self.subTest(secret=secret):
                with self.assertRaisesRegex(ValueError, "敏感"):
                    update_account(str(self.path), "acct-1", secret)

    def test_raises_when_account_is_missing(self):
        with self.assertRaises(KeyError):
            update_account(str(self.path), "missing", {"payment": {}})


if __name__ == "__main__":
    unittest.main()
