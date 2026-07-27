import base64
import json
import unittest

from billing.claude import ClaudeBillingClient, BillingProtocolError


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content_type="application/json",
                 text=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.text = text if text is not None else (
            "<html>login</html>" if "json" not in content_type
            else json.dumps(payload or {})
        )

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


class ClaudeBillingClientTests(unittest.TestCase):
    def test_reads_checkout_capabilities_without_modifying_response(self):
        session = FakeSession([FakeResponse({"checkout_flow": "cassia"})])
        client = ClaudeBillingClient(session, "https://claude.ai")

        result = client.get_checkout_capabilities("org-1")

        self.assertEqual(result, {"checkout_flow": "cassia"})
        self.assertEqual(
            session.calls[0][1],
            "https://claude.ai/api/organizations/org-1/subscription/checkout_capabilities",
        )

    def test_creates_custom_sepa_checkout_session(self):
        session = FakeSession([FakeResponse({
            "client_secret": "cs_test_secret_value",
            "session_id": "cs_test_123",
            "publishable_key": "pk_test_1234567890123456",
        })])
        client = ClaudeBillingClient(session, "https://claude.ai")

        checkout = client.create_checkout_session("org-1")

        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(
            url,
            "https://claude.ai/api/organizations/org-1/subscription/checkout_session",
        )
        self.assertEqual(kwargs["json"], {
            "billing_interval": "monthly",
            "payment_method_type": "sepa_debit",
            "checkout_flow": "custom",
        })
        self.assertEqual(checkout.session_id, "cs_test_123")
        self.assertEqual(checkout.publishable_key, "pk_test_1234567890123456")

    def test_accepts_publishable_key_embedded_in_client_secret(self):
        metadata = base64.urlsafe_b64encode(json.dumps({
            "apiKey": "pk_test_embedded",
        }).encode("utf-8")).decode("ascii").rstrip("=")
        client_secret = f"cs_test_123_secret_{metadata}"
        session = FakeSession([FakeResponse({"client_secret": client_secret})])

        checkout = ClaudeBillingClient(session).create_checkout_session("org-1")

        self.assertEqual(checkout.session_id, "cs_test_123")
        self.assertEqual(checkout.client_secret, client_secret)
        self.assertEqual(checkout.publishable_key, "")

    def test_rejects_incomplete_checkout_response(self):
        session = FakeSession([FakeResponse({"session_id": "cs_test_123"})])

        with self.assertRaisesRegex(BillingProtocolError, "缺少"):
            ClaudeBillingClient(session).create_checkout_session("org-1")

    def test_rejects_non_json_response(self):
        session = FakeSession([FakeResponse(None, content_type="text/html")])

        with self.assertRaisesRegex(BillingProtocolError, "JSON"):
            ClaudeBillingClient(session).get_checkout_capabilities("org-1")

    def test_http_error_includes_redacted_upstream_response(self):
        session = FakeSession([FakeResponse({
            "error": {
                "message": "payment method type is not supported",
                "client_secret": "cs_live_secret_do_not_print",
            },
            "request_id": "req_123",
        }, status_code=400)])

        with self.assertRaises(BillingProtocolError) as raised:
            ClaudeBillingClient(session).create_checkout_session("org-1")

        message = str(raised.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("payment method type is not supported", message)
        self.assertIn("req_123", message)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn("cs_live_secret_do_not_print", message)


if __name__ == "__main__":
    unittest.main()
