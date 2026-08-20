import time

import requests
from requests.exceptions import SSLError, ConnectionError as ConnError

from core.config import (
    MAILNEST_API_KEY,
    MAILNEST_BASE_URL,
    MAILNEST_PROJECT_CODE,
)

_MAX_RETRIES = 4


class MailNestAPIError(RuntimeError):
    def __init__(self, code, message, payload=None):
        super().__init__(f"MailNest API error {code}: {message}")
        self.code = code
        self.message = message
        self.payload = payload or {}


def _request(s, method, url, **kwargs):
    for attempt in range(_MAX_RETRIES):
        try:
            r = getattr(s, method)(url, timeout=30, **kwargs)
            r.raise_for_status()
            data = r.json()
            code = data.get("code")
            if code and code != "00000":
                raise MailNestAPIError(code, data.get("msg", ""), data)
            return data
        except (SSLError, ConnError):
            if attempt < _MAX_RETRIES - 1:
                time.sleep(1 * (attempt + 1))
                continue
            raise


class MailNestClient:
    def __init__(
        self,
        api_key=MAILNEST_API_KEY,
        base_url=MAILNEST_BASE_URL,
        project_code=MAILNEST_PROJECT_CODE,
    ):
        """MailNest direct client. It does not inherit system proxy settings."""
        self.base = base_url.rstrip("/")
        self.project_code = project_code
        self._email_by_order_id = {}
        self.s = requests.Session()
        self.s.trust_env = False
        self.s.headers.update({"Authorization": f"Bearer {api_key}"})

    def get_config(self):
        data = _request(self.s, "get", f"{self.base}/api/product/info")["data"]
        return {
            "domains": ["mailnest.top"],
            "projects": data.get("temporary", []),
            "exclusive": data.get("exclusive", {}),
        }

    def generate_email(self, name="test", expiry_time=3600000, domain=None):
        payload = {"project_code": self.project_code, "count": 1}
        data = _request(
            self.s,
            "post",
            f"{self.base}/api/v1/email/temporary/buy",
            json=payload,
        )["data"]
        if not data:
            raise RuntimeError("MailNest did not return a purchased email")
        item = data[0]
        email = item["email"]
        order_id = item.get("id") or email
        self._email_by_order_id[order_id] = email
        return {"id": order_id, "email": email}

    def receive_email(self, email):
        return _request(
            self.s,
            "post",
            f"{self.base}/api/v1/email/receive",
            json={"email": email},
        )["data"]

    def release_email(self, email):
        return _request(
            self.s,
            "post",
            f"{self.base}/api/v1/email/release",
            json={"email": email},
        )

    def wait_for_message(self, email_id, sender_contains=None, timeout=120, interval=3):
        email = self._email_by_order_id.get(email_id, email_id)
        deadline = time.time() + timeout
        seen = set()
        while time.time() < deadline:
            messages = self.receive_email(email) or []
            for msg in messages:
                mid = msg.get("id")
                if mid in seen:
                    continue
                seen.add(mid)
                if sender_contains and sender_contains.lower() not in _sender_text(msg):
                    continue
                return msg
            time.sleep(interval)
        raise TimeoutError(f"{timeout}s no matching MailNest message received")


def _sender_text(msg):
    parts = [
        msg.get("from_email", ""),
        msg.get("from_domain", ""),
        msg.get("from_name", ""),
        msg.get("subject", ""),
    ]
    return " ".join(str(part).lower() for part in parts if part)
