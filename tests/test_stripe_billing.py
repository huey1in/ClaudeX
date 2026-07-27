import base64
import json
import unittest
from urllib.parse import parse_qs

from billing.models import BillingProfile, CheckoutContext


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.headers = {"content-type": "application/json"}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def checkout_context():
    metadata = base64.urlsafe_b64encode(json.dumps({
        "apiKey": "pk_live_example",
        "stripeAccount": "acct_example",
        "uiMode": "custom",
    }, separators=(",", ":")).encode()).decode().rstrip("=")
    secret = "cs_live_session_secret_" + metadata
    return CheckoutContext(
        session_id="cs_live_session",
        publishable_key="pk_live_example",
        client_secret=secret,
    )


def profile():
    return BillingProfile(
        name="Ada Lovelace",
        country="DE",
        line1="Invalidenstrasse 1",
        line2="2. OG",
        city="Berlin",
        state="BE",
        postal_code="10115",
    )


class StripeCheckoutClientTests(unittest.TestCase):
    def test_submits_custom_checkout_sepa_protocol_as_form_data(self):
        from billing.stripe import StripeCheckoutClient

        session = FakeSession([
            FakeResponse(payload={
                "id": "ppage_123",
                "session_id": "cs_live_session",
                "init_checksum": "init_abc",
                "mode": "subscription",
                "return_url": "https://claude.ai/settings/billing",
                "invoice": {
                    "billing_cycle_anchor": 123456789,
                    "has_prorations": False,
                    "amount_due": 2000,
                },
                "recurring_details": {"total": 2000},
                "total_summary": {"due": 2000},
            }),
            FakeResponse(payload={"payment_method_type": "sepa_debit"}),
            FakeResponse(payload={
                "id": "ppage_123",
                "state": "processing_async_payment",
                "payment_intent": {"id": "pi_123", "status": "processing"},
            }),
        ])
        client = StripeCheckoutClient(session=session, stripe_js_id="sjs_test")

        result = client.submit_sepa(
            checkout_context(), profile(), "ada@example.com",
            "DE89 3704 0044 0532 0130 00",
        )

        self.assertEqual(result.checkout_session_id, "cs_live_session")
        self.assertEqual(result.payment_intent_id, "pi_123")
        self.assertEqual(result.status, "pending")
        self.assertEqual([call[0] for call in session.calls], ["POST", "POST", "POST"])
        self.assertTrue(session.calls[0][1].endswith("/v1/payment_pages/cs_live_session/init"))
        self.assertTrue(session.calls[1][1].endswith("/v1/payment_pages/cs_live_session/pre_confirm"))
        self.assertTrue(session.calls[2][1].endswith("/v1/payment_pages/cs_live_session/confirm"))

        init = parse_qs(session.calls[0][2]["data"])
        self.assertEqual(init["key"], ["pk_live_example"])
        self.assertEqual(init["_stripe_account"], ["acct_example"])
        self.assertEqual(init["elements_session_client[elements_init_source]"], ["custom_checkout"])
        self.assertEqual(init["elements_session_client[stripe_js_id]"], ["sjs_test"])

        pre_confirm = parse_qs(session.calls[1][2]["data"])
        self.assertEqual(pre_confirm["payment_method_type"], ["sepa_debit"])

        confirm = parse_qs(session.calls[2][2]["data"])
        self.assertEqual(confirm["payment_method_data[type]"], ["sepa_debit"])
        self.assertEqual(confirm["payment_method_data[sepa_debit][iban]"], ["DE89370400440532013000"])
        self.assertEqual(confirm["payment_method_data[billing_details][name]"], ["Ada Lovelace"])
        self.assertEqual(confirm["payment_method_data[billing_details][email]"], ["ada@example.com"])
        self.assertEqual(confirm["payment_method_data[billing_details][address][country]"], ["DE"])
        self.assertEqual(confirm["expected_payment_method_type"], ["sepa_debit"])
        self.assertEqual(confirm["init_checksum"], ["init_abc"])
        self.assertEqual(confirm["expected_amount"], ["0"])
        self.assertEqual(confirm.get("expected_amount_on_bca"), ["2000"])
        self.assertEqual(confirm["return_url"], ["https://claude.ai/settings/billing"])
        self.assertIn("version", confirm)
        self.assertIn("js_checksum", confirm)
        self.assertIn("rv_timestamp", confirm)

    def test_polls_checkout_status(self):
        from billing.stripe import StripeCheckoutClient

        session = FakeSession([FakeResponse(payload={
            "state": "succeeded",
            "payment_object_status": "succeeded",
            "payment_intent": {"id": "pi_123", "status": "succeeded"},
        })])
        result = StripeCheckoutClient(session=session).poll(checkout_context())

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.payment_intent_id, "pi_123")
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.endswith("/v1/payment_pages/cs_live_session/poll"))
        self.assertEqual(parse_qs(kwargs["params"])["key"], ["pk_live_example"])

    def test_rejects_mismatched_publishable_key(self):
        from billing.stripe import StripeCheckoutClient, StripeProtocolError

        context = checkout_context()
        context = CheckoutContext(context.session_id, "pk_live_other", context.client_secret)
        with self.assertRaises(StripeProtocolError):
            StripeCheckoutClient(session=FakeSession([])).poll(context)

    def test_error_does_not_echo_secrets_or_response_body(self):
        from billing.stripe import StripeCheckoutClient, StripeProtocolError

        iban = "DE89370400440532013000"
        context = checkout_context()
        session = FakeSession([FakeResponse(
            status_code=400,
            payload={"error": {"message": "bad request", "iban": iban,
                                "client_secret": context.client_secret}},
        )])
        with self.assertRaises(StripeProtocolError) as caught:
            StripeCheckoutClient(session=session).submit_sepa(
                context, profile(), "ada@example.com", iban,
            )
        message = str(caught.exception)
        self.assertNotIn(iban, message)
        self.assertNotIn(context.client_secret, message)
        self.assertIn("HTTP 400", message)


if __name__ == "__main__":
    unittest.main()
