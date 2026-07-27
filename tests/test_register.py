import unittest
from inspect import signature
from unittest.mock import patch

from requests.cookies import CookieConflictError, RequestsCookieJar

from registration import register


class RegisterBatchTests(unittest.TestCase):
    def test_serializes_duplicate_cookie_names_without_conflict(self):
        jar = RequestsCookieJar()
        jar.set("__cf_bm", "host-cookie", domain="claude.ai", path="/")
        jar.set("__cf_bm", "domain-cookie", domain=".claude.ai", path="/")
        jar.set("sessionKey", "session-value", domain="claude.ai", path="/")

        with self.assertRaises(CookieConflictError):
            dict(jar)

        cookies = register._serialize_cookies(jar)

        self.assertIn(cookies["__cf_bm"], {"host-cookie", "domain-cookie"})
        self.assertEqual(cookies["sessionKey"], "session-value")

    @patch("registration.register.time.sleep")
    @patch("registration.register.register_account")
    def test_notifies_after_each_successful_registration(self, register_account, sleep):
        self.assertIn("on_success", signature(register.register_batch).parameters)

        accounts = [{"uuid": "one"}, {"uuid": "two"}]
        events = []

        def register_side_effect(accounts_file):
            account = accounts[len(events) // 2]
            events.append(("registered", account["uuid"]))
            return account

        def on_success(account):
            events.append(("subscribed", account["uuid"]))

        register_account.side_effect = register_side_effect

        results = register.register_batch(
            count=2,
            concurrent=1,
            accounts_file="custom.json",
            on_success=on_success,
        )

        self.assertEqual(results, accounts)
        self.assertEqual(events, [
            ("registered", "one"),
            ("subscribed", "one"),
            ("registered", "two"),
            ("subscribed", "two"),
        ])
        self.assertEqual(register_account.call_count, 2)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
