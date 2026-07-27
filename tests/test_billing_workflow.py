import json
import os
import tempfile
import unittest
from inspect import signature
from unittest.mock import patch

from billing.models import CheckoutContext
from billing.stripe import StripePaymentResult


class FakeClaudeClient:
    def __init__(self, account, events):
        self.account = account
        self.events = events

    def get_checkout_capabilities(self, org_uuid):
        self.events.append(("capabilities", self.account["email"], org_uuid))
        return {"checkout_flow": "cassia"}

    def create_checkout_session(self, org_uuid):
        self.events.append(("checkout", self.account["email"], org_uuid))
        suffix = self.account["uuid"]
        return CheckoutContext(
            session_id=f"cs_{suffix}",
            publishable_key="pk_test",
            client_secret=f"cs_{suffix}_secret_metadata",
        )


class FakeStripeClient:
    def __init__(self, account, events, fail_email=None):
        self.account = account
        self.events = events
        self.fail_email = fail_email

    def submit_sepa(self, context, profile, email, iban):
        self.events.append(("submit", email, iban, profile))
        if email == self.fail_email:
            raise RuntimeError("submission failed")
        return StripePaymentResult(
            checkout_session_id=context.session_id,
            payment_intent_id=f"pi_{self.account['uuid']}",
            status="pending",
            raw_status="processing",
        )

    def poll(self, context):
        self.events.append(("poll", self.account["email"], context.session_id))
        return StripePaymentResult(
            checkout_session_id=context.session_id,
            payment_intent_id=f"pi_{self.account['uuid']}",
            status="succeeded",
            raw_status="succeeded",
        )


class BillingWorkflowTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        self.accounts = [
            {"uuid": "one", "org_uuid": "org-one", "email": "one@example.com"},
            {"uuid": "two", "org_uuid": "org-two", "email": "two@example.com"},
        ]
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(self.accounts, file)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_removed_consent_callback_is_not_in_workflow_signature(self):
        from billing.workflow import run_sepa_workflow

        self.assertNotIn("input_fn", signature(run_sepa_workflow).parameters)

    @patch(
        "billing.workflow._random_iban_de",
        return_value="DE89370400440532013000",
    )
    def test_reuses_generated_profile_and_submits_each_account(self, random_iban):
        from billing.workflow import run_sepa_workflow

        events = []
        output = []

        results = run_sepa_workflow(
            self.accounts,
            accounts_file=self.path,
            output_fn=output.append,
            claude_client_factory=lambda account: FakeClaudeClient(account, events),
            stripe_client_factory=lambda account: FakeStripeClient(account, events),
        )

        submits = [event for event in events if event[0] == "submit"]
        polls = [event for event in events if event[0] == "poll"]
        self.assertEqual(random_iban.call_count, 2)
        self.assertEqual(len(submits), 2)
        self.assertIs(submits[0][3], submits[1][3])
        self.assertEqual(submits[0][3].country, "DE")
        self.assertTrue(submits[0][3].name)
        self.assertTrue(submits[0][3].line1)
        self.assertTrue(submits[0][3].city)
        self.assertTrue(submits[0][3].state)
        self.assertRegex(submits[0][3].postal_code, r"^\d{5}$")
        self.assertEqual(len(polls), 2)
        self.assertGreater(events.index(polls[0]), events.index(submits[1]))
        self.assertEqual([item.status for item in results], ["succeeded", "succeeded"])

        rendered_output = "\n".join(output)
        self.assertIn("[1/2] 自动订阅中…", rendered_output)
        self.assertIn("  [1/5] 生成并校验 IBAN…", rendered_output)
        self.assertIn("        IBAN: DE89...3000", rendered_output)
        self.assertIn("  [2/5] 查询 Checkout 能力…", rendered_output)
        self.assertIn("        checkout_flow: cassia", rendered_output)
        self.assertIn("  [3/5] 创建 Checkout 会话…", rendered_output)
        self.assertIn("  [4/5] 提交 SEPA Direct Debit…", rendered_output)
        self.assertIn("  [5/5] 查询异步付款状态…", rendered_output)
        self.assertIn("  [成功] 自动订阅完成: one@example.com", rendered_output)
        self.assertIn("[订阅] 完成: 成功 2 个，待处理 0 个，失败 0 个", rendered_output)

        with open(self.path, "r", encoding="utf-8") as file:
            saved = json.load(file)
        self.assertEqual(saved[0]["payment"]["status"], "succeeded")
        self.assertEqual(saved[1]["payment"]["status"], "succeeded")
        self.assertEqual(saved[0]["payment"]["iban_last4"], "3000")
        rendered = json.dumps(saved)
        self.assertNotIn("DE89370400440532013000", rendered)
        self.assertNotIn("client_secret", rendered)

    def test_uncertain_submit_is_polled_without_stopping_later_accounts(self):
        from billing.workflow import run_sepa_workflow

        third = {"uuid": "three", "org_uuid": "org-three", "email": "three@example.com"}
        accounts = self.accounts + [third]
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(accounts, file)
        events = []
        results = run_sepa_workflow(
            accounts,
            accounts_file=self.path,
            output_fn=lambda message: None,
            claude_client_factory=lambda account: FakeClaudeClient(account, events),
            stripe_client_factory=lambda account: FakeStripeClient(
                account, events, fail_email="two@example.com"
            ),
        )

        self.assertEqual([item.status for item in results], ["succeeded", "succeeded", "succeeded"])
        submitted_emails = [event[1] for event in events if event[0] == "submit"]
        self.assertEqual(submitted_emails, [
            "one@example.com", "two@example.com", "three@example.com",
        ])
        polled_emails = [event[1] for event in events if event[0] == "poll"]
        self.assertEqual(polled_emails, [
            "one@example.com", "two@example.com", "three@example.com",
        ])

    def test_empty_account_list_does_not_prompt(self):
        from billing.workflow import run_sepa_workflow

        self.assertEqual(run_sepa_workflow(
            [], accounts_file=self.path, output_fn=lambda message: None,
        ), [])

    def test_legacy_checkout_stops_before_session_creation_with_clear_error(self):
        from billing.workflow import run_sepa_workflow

        events = []
        output = []

        class LegacyClaudeClient(FakeClaudeClient):
            def get_checkout_capabilities(self, org_uuid):
                self.events.append(("capabilities", self.account["email"], org_uuid))
                return {
                    "checkout_flow": "legacy",
                    "reason": "organization_not_eligible",
                    "client_secret": "cs_live_secret_do_not_print",
                }

            def create_checkout_session(self, org_uuid):
                self.fail("legacy checkout must not create a custom session")

        results = run_sepa_workflow(
            [self.accounts[0]],
            accounts_file=self.path,
            output_fn=output.append,
            claude_client_factory=lambda account: LegacyClaudeClient(account, events),
            stripe_client_factory=lambda account: FakeStripeClient(account, events),
        )

        self.assertEqual(results[0].status, "failed")
        self.assertFalse(any(event[0] == "checkout" for event in events))
        self.assertTrue(any("legacy" in message for message in output))
        rendered = "\n".join(output)
        self.assertIn('"reason":"organization_not_eligible"', rendered)
        self.assertIn('"client_secret":"[REDACTED]"', rendered)
        self.assertNotIn("cs_live_secret_do_not_print", rendered)
        self.assertIn("[1/1] 自动订阅中…", rendered)
        self.assertIn("  [1/5] 生成并校验 IBAN…", rendered)
        self.assertIn("  [2/5] 查询 Checkout 能力…", rendered)
        self.assertIn("        checkout_flow: legacy", rendered)
        self.assertIn("  [失败] 自动订阅失败: one@example.com", rendered)
        self.assertIn("        原因: 该组织不支持 Custom Checkout", rendered)
        self.assertIn("[订阅] 完成: 成功 0 个，待处理 0 个，失败 1 个", rendered)

    def test_persists_pending_before_the_final_poll(self):
        from billing.workflow import run_sepa_workflow

        events = []
        account = self.accounts[0]

        class ImmediatelySucceededStripe(FakeStripeClient):
            def submit_sepa(self, context, profile, email, iban):
                return StripePaymentResult(
                    checkout_session_id=context.session_id,
                    payment_intent_id="pi_one",
                    status="succeeded",
                    raw_status="succeeded",
                )

        with patch("billing.workflow.update_account") as update:
            run_sepa_workflow(
                [account],
                accounts_file=self.path,
                output_fn=lambda message: None,
                claude_client_factory=lambda item: FakeClaudeClient(item, events),
                stripe_client_factory=lambda item: ImmediatelySucceededStripe(item, events),
            )

        statuses = [call.args[2]["payment"]["status"] for call in update.call_args_list]
        self.assertEqual(statuses, ["pending", "succeeded"])


if __name__ == "__main__":
    unittest.main()
