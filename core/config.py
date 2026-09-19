import os
import uuid


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#", 1)[0].strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


load_env()

MOEMAIL_API_KEY  = os.environ.get("MOEMAIL_API_KEY", "")
MOEMAIL_BASE_URL = os.environ.get("MOEMAIL_BASE_URL", "")
EMAIL_SERVICE = os.environ.get("EMAIL_SERVICE", "moemail").strip().lower()
MAILNEST_API_KEY = os.environ.get("MAILNEST_API_KEY", "")
MAILNEST_BASE_URL = os.environ.get("MAILNEST_BASE_URL", "https://mailnest.top")
MAILNEST_PROJECT_CODE = os.environ.get("MAILNEST_PROJECT_CODE", "Claude0001")

PROXY   = os.environ.get("PROXY", "")
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None

REGISTER_COUNT      = int(os.environ.get("REGISTER_COUNT", "1"))
REGISTER_CONCURRENT = int(os.environ.get("REGISTER_CONCURRENT", "1"))

ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "accounts.json")

BASE_URL = "https://claude.ai"

# 固定命名空间保证同一 seed 跨进程稳定，同时让不同字段互不关联。
_ANON_NS = uuid.UUID("6f4a1c2e-1b3d-4e5f-8a90-0c1d2e3f4a5b")
_DEVICE_NS = uuid.UUID("9d8c7b6a-5e4f-4321-9a8b-7c6d5e4f3a2b")
_PROFILE_NS = uuid.UUID("3c2b1a09-8f7e-4d6c-b5a4-9382716f5e4d")
_DEFAULT_SEED = "claudex-default"

# 每个资料包含互相匹配的浏览器 UA 和语言偏好；只选择真实组合，不拼接随机 UA。
_BROWSER_PROFILES = (
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "en-US,en;q=0.9",
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36",
        "en-US,en;q=0.9",
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 "
        "Edg/149.0.0.0",
        "en-GB,en;q=0.9",
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
        "Gecko/20100101 Firefox/133.0",
        "de-DE,de;q=0.9,en;q=0.8",
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.1 Safari/605.1.15",
        "en-US,en;q=0.9",
    ),
)

_CLIENT_PLATFORM = "web_claude_ai"
_CLIENT_VERSION = "1.0.0"
_CLIENT_SHA = "882d9a7d43eced6a100e636e1dfdebc55764bd78"


def _derive_anonymous_id(seed):
    """由 seed（通常是邮箱）哈希派生 anonymous-id：同账号稳定、跨账号各异。"""
    return "claudeai.v1." + str(uuid.uuid5(_ANON_NS, seed))


def _derive_device_id(seed):
    """由 seed 哈希派生 device-id（标准 UUID 形式）。"""
    return str(uuid.uuid5(_DEVICE_NS, seed))


def _derive_browser_profile(seed):
    """由 seed 稳定选择一套完整浏览器资料。"""
    index = uuid.uuid5(_PROFILE_NS, seed).int % len(_BROWSER_PROFILES)
    return _BROWSER_PROFILES[index]


def build_headers(seed=None):
    """构造发往 claude.ai 的请求头。

    anonymous-id、device-id 和浏览器资料都由 seed 哈希派生，保证同账号
    稳定、跨账号不同。不传 seed 时使用固定的默认 seed，结果仍可重复。

    client platform/version/sha 是协议构建元数据，使用代码常量而不伪造。
    """
    stable_seed = str(seed or _DEFAULT_SEED)
    user_agent, accept_language = _derive_browser_profile(stable_seed)

    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": BASE_URL,
        "referer": BASE_URL + "/",
        "user-agent": user_agent,
        "accept-language": accept_language,
        "anthropic-client-platform": _CLIENT_PLATFORM,
        "anthropic-client-version": _CLIENT_VERSION,
        "anthropic-client-sha": _CLIENT_SHA,
        "anthropic-anonymous-id": _derive_anonymous_id(stable_seed),
        "anthropic-device-id": _derive_device_id(stable_seed),
    }


# 无种子时的默认头（向后兼容旧引用）
COMMON_HEADERS = build_headers()
