import json
import re

from .models import CheckoutContext


class BillingProtocolError(RuntimeError):
    pass


_SENSITIVE_RESPONSE_KEYS = {
    "authorization", "client_secret", "cookie", "cookies",
    "access_token", "refresh_token", "token",
}


def _redact_response_value(value):
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if str(key).lower() in _SENSITIVE_RESPONSE_KEYS
                or str(key).lower().endswith("_token")
                else _redact_response_value(nested)
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_response_value(item) for item in value]
    return value


def safe_response_text(value):
    return json.dumps(
        _redact_response_value(value), ensure_ascii=False,
        separators=(",", ":"),
    )


def _upstream_response_text(response):
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            payload = response.json()
        except (TypeError, ValueError):
            pass
        else:
            return safe_response_text(payload)

    text = response.text or "<empty>"
    return re.sub(
        r"cs_[A-Za-z0-9_]+_secret_[A-Za-z0-9_-]+",
        "[REDACTED_CLIENT_SECRET]",
        text,
    )


class ClaudeBillingClient:
    def __init__(self, session, base_url="https://claude.ai", publishable_key=""):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.publishable_key = publishable_key

    def _json(self, response):
        content_type = response.headers.get("content-type", "")
        if not 200 <= response.status_code < 300:
            raise BillingProtocolError(
                f"Claude 付款接口返回 HTTP {response.status_code}; "
                f"上游响应: {_upstream_response_text(response)}"
            )
        if "json" not in content_type.lower():
            raise BillingProtocolError("Claude 付款接口未返回 JSON")
        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            raise BillingProtocolError("Claude 付款接口 JSON 无效") from exc
        if not isinstance(data, dict):
            raise BillingProtocolError("Claude 付款接口 JSON 结构无效")
        return data

    def get_checkout_capabilities(self, org_uuid):
        response = self.session.get(
            f"{self.base_url}/api/organizations/{org_uuid}/subscription/checkout_capabilities",
            timeout=20,
        )
        return self._json(response)

    def create_checkout_session(self, org_uuid):
        response = self.session.post(
            f"{self.base_url}/api/organizations/{org_uuid}/subscription/checkout_session",
            json={
                "billing_interval": "monthly",
                "payment_method_type": "sepa_debit",
                "checkout_flow": "custom",
            },
            timeout=20,
        )
        data = self._json(response)
        client_secret = (
            data.get("client_secret") or data.get("checkout_session_client_secret")
        )
        session_id = data.get("session_id") or data.get("checkout_session_id")
        if not session_id and isinstance(client_secret, str) and "_secret_" in client_secret:
            session_id = client_secret.split("_secret_", 1)[0]
        publishable_key = (
            data.get("publishable_key")
            or data.get("stripe_publishable_key")
            or self.publishable_key
        )

        missing = [
            name for name, value in (
                ("client_secret", client_secret),
                ("session_id", session_id),
            ) if not value
        ]
        if missing:
            raise BillingProtocolError(
                "Claude Checkout 响应缺少字段: " + ", ".join(missing)
            )
        return CheckoutContext(
            session_id=session_id,
            publishable_key=publishable_key,
            client_secret=client_secret,
        )
