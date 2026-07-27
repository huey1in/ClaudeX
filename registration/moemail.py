import time
import requests
from requests.exceptions import SSLError, ConnectionError as ConnError
from core.config import MOEMAIL_API_KEY, MOEMAIL_BASE_URL

_MAX_RETRIES = 4


def _request(s, method, url, **kwargs):
    for attempt in range(_MAX_RETRIES):
        try:
            r = getattr(s, method)(url, timeout=15, **kwargs)
            r.raise_for_status()
            return r.json()
        except (SSLError, ConnError):
            if attempt < _MAX_RETRIES - 1:
                time.sleep(1 * (attempt + 1))
                continue
            raise


class MoeMailClient:
    def __init__(self, api_key=MOEMAIL_API_KEY, base_url=MOEMAIL_BASE_URL):
        """moemail 直连，不走任何代理（含系统代理）。"""
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.trust_env = False  # 禁止读取系统/环境变量代理，强制直连
        self.s.headers.update({"X-API-Key": api_key})

    def get_config(self):
        return _request(self.s, "get", f"{self.base}/api/config")

    def generate_email(self, name="test", expiry_time=3600000, domain="moemail.app"):
        payload = {"name": name, "expiryTime": expiry_time, "domain": domain}
        return _request(
            self.s, "post", f"{self.base}/api/emails/generate", json=payload
        )

    def list_messages(self, email_id, cursor=None):
        params = {"cursor": cursor} if cursor else {}
        return _request(
            self.s, "get", f"{self.base}/api/emails/{email_id}", params=params
        )

    def get_message(self, email_id, message_id):
        return _request(
            self.s, "get", f"{self.base}/api/emails/{email_id}/{message_id}"
        )

    def wait_for_message(self, email_id, sender_contains=None, timeout=120, interval=3):
        deadline = time.time() + timeout
        seen = set()
        while time.time() < deadline:
            data = self.list_messages(email_id)
            for msg in data.get("messages", []):
                mid = msg.get("id")
                if mid in seen:
                    continue
                seen.add(mid)
                frm = msg.get("from_address") or msg.get("from") or ""
                if sender_contains and sender_contains.lower() not in frm.lower():
                    continue
                return self.get_message(email_id, mid)
            time.sleep(interval)
        raise TimeoutError(f"{timeout}s 内未等到邮件")
