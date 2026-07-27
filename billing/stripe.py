import base64
import json
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from .models import BillingProfile, CheckoutContext, validate_iban


STRIPE_API_BASE = "https://api.stripe.com/v1"

# Values embedded in the Stripe Clover assets used by claude-sepa.js. Stripe
# validates these on Custom Checkout confirmation.
_STRIPE_JS_BUILD = "b6feaa70de"
_RUNTIME_TIMESTAMP = "2024-01-01 00:00:00 -0000"
_RUNTIME_VERSION = "b6feaa70dedca55b88393df454c06e0e651e62d9"
_SERVER_VERSION = "33983c21f0c74590a748c22833eecab4e40d7d2bd7147d075f4b3b32bb912bfb"


class StripeProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class StripePaymentResult:
    checkout_session_id: str
    payment_intent_id: str
    status: str
    raw_status: str


def _flatten_form(value, prefix=""):
    pairs = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if nested is None:
                continue
            name = f"{prefix}[{key}]" if prefix else str(key)
            pairs.extend(_flatten_form(nested, name))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            pairs.extend(_flatten_form(nested, f"{prefix}[{index}]"))
    else:
        if isinstance(value, bool):
            value = "true" if value else "false"
        pairs.append((prefix, str(value)))
    return pairs


def _encode_form(value):
    return urlencode(_flatten_form(value))


def _decode_client_secret(context):
    try:
        session_id, encoded = context.client_secret.split("_secret_", 1)
    except ValueError as exc:
        raise StripeProtocolError("Stripe Checkout client secret format is invalid") from exc
    if session_id != context.session_id:
        raise StripeProtocolError("Stripe Checkout session ID does not match client secret")

    metadata = {}
    try:
        padding = "=" * (-len(encoded) % 4)
        metadata = json.loads(base64.urlsafe_b64decode(encoded + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        # Stripe.js also treats undecodable client-secret metadata as empty.
        metadata = {}

    embedded_key = metadata.get("apiKey")
    if embedded_key and embedded_key != context.publishable_key:
        raise StripeProtocolError("Stripe publishable key does not match client secret")
    return {
        "session_id": session_id,
        "key": embedded_key or context.publishable_key,
        "stripe_account": metadata.get("stripeAccount"),
    }


def _rotate_printable(value, amount):
    return "".join(
        chr((ord(char) - 32 + amount) % 95 + 32)
        for char in value
    )


def _encoded_checksum(value):
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return _rotate_printable(base64.b64encode(raw).decode("ascii"), 11)


def _auth_data(credentials):
    result = {"key": credentials["key"]}
    if credentials.get("stripe_account"):
        result["_stripe_account"] = credentials["stripe_account"]
    return result


def _expected_amount(payment_page):
    if payment_page.get("mode") == "setup":
        return None
    invoice = payment_page.get("invoice") or {}
    billing_cycle_anchor = (
        bool(invoice.get("billing_cycle_anchor"))
        and not bool(invoice.get("has_prorations"))
    )
    if billing_cycle_anchor:
        return 0
    total_summary = payment_page.get("total_summary") or {}
    return total_summary.get("due", 0)


def _expected_amount_on_bca(payment_page):
    invoice = payment_page.get("invoice") or {}
    if not invoice.get("billing_cycle_anchor") or invoice.get("has_prorations"):
        return None
    return (payment_page.get("recurring_details") or {}).get("total")


def _status_from_page(payment_page):
    intent = payment_page.get("payment_intent") or {}
    raw_status = (
        intent.get("status")
        or payment_page.get("payment_object_status")
        or payment_page.get("payment_status")
        or payment_page.get("state")
        or payment_page.get("status")
        or "unknown"
    )
    if raw_status in {"succeeded", "paid"}:
        status = "succeeded"
    elif raw_status in {
        "failed", "canceled", "cancelled", "expired", "invalid",
        "requires_payment_method",
    }:
        status = "failed"
    else:
        status = "pending"
    return StripePaymentResult(
        checkout_session_id=payment_page.get("session_id", ""),
        payment_intent_id=intent.get("id", ""),
        status=status,
        raw_status=raw_status,
    )


class StripeCheckoutClient:
    def __init__(self, session=None, base_url=STRIPE_API_BASE,
                 stripe_js_id=None, locale="en-US"):
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.stripe_js_id = stripe_js_id or f"sjs_{uuid.uuid4().hex}"
        self.locale = locale

    def _request(self, method, path, data):
        encoded = _encode_form(data)
        kwargs = {
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            "timeout": 30,
        }
        if method == "GET":
            kwargs["params"] = encoded
        else:
            kwargs["data"] = encoded
        try:
            response = self.session.request(
                method, f"{self.base_url}/{path.lstrip('/')}", **kwargs
            )
        except requests.RequestException as exc:
            raise StripeProtocolError("Stripe request failed") from exc
        if response.status_code != 200:
            raise StripeProtocolError(f"Stripe HTTP {response.status_code}")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise StripeProtocolError("Stripe returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise StripeProtocolError("Stripe returned an invalid response")
        if isinstance(payload.get("error"), dict):
            code = payload["error"].get("code")
            suffix = f" ({code})" if code else ""
            raise StripeProtocolError(f"Stripe API rejected the request{suffix}")
        return payload

    def _init(self, credentials):
        auth = _auth_data(credentials)
        data = {
            **auth,
            "elements_session_client": {
                "elements_init_source": "custom_checkout",
                "stripe_js_id": self.stripe_js_id,
                "referrer_host": "claude.ai",
                "locale": self.locale,
                "is_aggregation_expected": False,
            },
            "elements_options_client": {
                "saved_payment_method": {
                    "enable_save": "auto",
                    "enable_redisplay": "auto",
                },
            },
            "browser_locale": self.locale,
        }
        page = self._request(
            "POST", f"payment_pages/{credentials['session_id']}/init", data
        )
        if not page.get("id") or not page.get("init_checksum"):
            raise StripeProtocolError("Stripe init response is missing required fields")
        return page

    def submit_sepa(self, context: CheckoutContext, profile: BillingProfile,
                    email: str, iban: str):
        normalized_iban = validate_iban(iban)
        credentials = _decode_client_secret(context)
        page = self._init(credentials)
        auth = _auth_data(credentials)

        self._request(
            "POST",
            f"payment_pages/{credentials['session_id']}/pre_confirm",
            {**auth, "payment_method_type": "sepa_debit"},
        )

        return_url = page.get("return_url")
        if not return_url and page.get("approval_method") != "manual":
            raise StripeProtocolError("Stripe Checkout response is missing return_url")
        payment_user_agent = (
            f"stripe.js/{_STRIPE_JS_BUILD}; stripe-js-v3/{_STRIPE_JS_BUILD}; checkout"
        )
        confirm_data = {
            **auth,
            "version": _STRIPE_JS_BUILD,
            "js_checksum": _encoded_checksum({"id": page["id"]}),
            "rv_timestamp": _encoded_checksum({
                "rvTs": _RUNTIME_TIMESTAMP,
                "rv": _RUNTIME_VERSION,
                "sv": _SERVER_VERSION,
            }),
            "init_checksum": page["init_checksum"],
            "expected_amount": _expected_amount(page),
            "expected_amount_on_bca": _expected_amount_on_bca(page),
            "return_url": return_url,
            "payment_method_data": {
                "type": "sepa_debit",
                "sepa_debit": {"iban": normalized_iban},
                "billing_details": {
                    "name": profile.name,
                    "email": email,
                    "address": {
                        "line1": profile.line1,
                        "line2": profile.line2,
                        "city": profile.city,
                        "state": profile.state,
                        "postal_code": profile.postal_code,
                        "country": profile.country,
                    },
                },
                "payment_user_agent": payment_user_agent,
            },
            "expected_payment_method_type": "sepa_debit",
            "elements_session_client": {
                "elements_init_source": "custom_checkout",
                "stripe_js_id": self.stripe_js_id,
                "referrer_host": "claude.ai",
                "locale": self.locale,
                "is_aggregation_expected": False,
            },
            "elements_options_client": {
                "saved_payment_method": {
                    "enable_save": "auto",
                    "enable_redisplay": "auto",
                },
            },
        }
        confirmed = self._request(
            "POST", f"payment_pages/{credentials['session_id']}/confirm", confirm_data
        )
        confirmed.setdefault("session_id", credentials["session_id"])
        return _status_from_page(confirmed)

    def poll(self, context: CheckoutContext):
        credentials = _decode_client_secret(context)
        page = self._request(
            "GET", f"payment_pages/{credentials['session_id']}/poll",
            _auth_data(credentials),
        )
        page.setdefault("session_id", credentials["session_id"])
        return _status_from_page(page)
