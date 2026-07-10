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

PROXY   = os.environ.get("PROXY", "")
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None

REGISTER_COUNT      = int(os.environ.get("REGISTER_COUNT", "1"))
REGISTER_CONCURRENT = int(os.environ.get("REGISTER_CONCURRENT", "1"))

ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "accounts.json")

BASE_URL = os.environ.get("CLAUDE_BASE_URL", "https://claude.ai").rstrip("/")

# 请求头逐项可配置，默认值与原硬编码保持一致
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)

# uuid5 命名空间：固定值保证同一 seed 每次派生出相同 UUID（跨进程稳定）
_ANON_NS = uuid.UUID("6f4a1c2e-1b3d-4e5f-8a90-0c1d2e3f4a5b")
_DEVICE_NS = uuid.UUID("9d8c7b6a-5e4f-4321-9a8b-7c6d5e4f3a2b")
_UA_NS = uuid.UUID("3c2b1a09-8f7e-4d6c-b5a4-9382716f5e4d")

# 真实浏览器 UA 池：轮换只从中挑选，绝不拼接随机串（伪造 UA 会生成不存在的
# 浏览器指纹，更易被识别）。按需补充为当前主流版本即可。
_UA_POOL = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
    "Gecko/20100101 Firefox/133.0",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]

# 是否对 anonymous-id / device-id / user-agent 按账号哈希派生（关掉则用固定值）
RANDOMIZE_FINGERPRINT = os.environ.get(
    "CLAUDE_RANDOMIZE_FINGERPRINT", "1").strip() not in ("", "0", "false", "False")

_FALLBACK_ANON_ID = os.environ.get(
    "CLAUDE_ANONYMOUS_ID", "claudeai.v1.551770c2-6f7e-499b-a039-9cbb0998b0a9")
_FALLBACK_DEVICE_ID = os.environ.get(
    "CLAUDE_DEVICE_ID", "8370843e-1ef9-4a50-badf-7894e7957a29")

# 显式设置 CLAUDE_USER_AGENT 时固定用它（禁用轮换）；否则轮换 / 回退默认
_PINNED_UA = os.environ.get("CLAUDE_USER_AGENT")


def _derive_anonymous_id(seed):
    """由 seed（通常是邮箱）哈希派生 anonymous-id：同账号稳定、跨账号各异。"""
    return "claudeai.v1." + str(uuid.uuid5(_ANON_NS, seed))


def _derive_device_id(seed):
    """由 seed 哈希派生 device-id（标准 UUID 形式）。"""
    return str(uuid.uuid5(_DEVICE_NS, seed))


def _derive_user_agent(seed):
    """由 seed 哈希从 _UA_POOL 中稳定挑选一个真实 UA：同账号固定、跨账号分散。"""
    idx = uuid.uuid5(_UA_NS, seed).int % len(_UA_POOL)
    return _UA_POOL[idx]


def _pick_user_agent(seed):
    if _PINNED_UA:                       # .env 显式指定 → 固定
        return _PINNED_UA
    if seed and RANDOMIZE_FINGERPRINT:   # 有账号种子 → 从池中哈希挑选
        return _derive_user_agent(seed)
    return _DEFAULT_UA                    # 无种子 → 默认


def build_headers(seed=None):
    """构造发往 claude.ai 的请求头。

    传入 seed（如账号邮箱）且开启 RANDOMIZE_FINGERPRINT 时，
    anonymous-id / device-id / user-agent 由该 seed 哈希派生，
    保证同账号稳定、跨账号不同。不传 seed 则回退到固定默认值。

    注意：anthropic-client-sha 是客户端真实构建版本号，不做随机化；
    user-agent 也只从真实浏览器 UA 池中哈希挑选，绝不拼接随机串。
    """
    if seed and RANDOMIZE_FINGERPRINT:
        anon_id = _derive_anonymous_id(seed)
        device_id = _derive_device_id(seed)
    else:
        anon_id = _FALLBACK_ANON_ID
        device_id = _FALLBACK_DEVICE_ID

    return {
        "accept": os.environ.get("CLAUDE_ACCEPT", "*/*"),
        "content-type": "application/json",
        "origin": BASE_URL,
        "referer": BASE_URL + "/",
        "user-agent": _pick_user_agent(seed),
        "accept-language": os.environ.get("CLAUDE_ACCEPT_LANGUAGE", "en-US,en;q=0.9"),
        "anthropic-client-platform": os.environ.get("CLAUDE_CLIENT_PLATFORM", "web_claude_ai"),
        "anthropic-client-version": os.environ.get("CLAUDE_CLIENT_VERSION", "1.0.0"),
        "anthropic-client-sha": os.environ.get(
            "CLAUDE_CLIENT_SHA", "882d9a7d43eced6a100e636e1dfdebc55764bd78"),
        "anthropic-anonymous-id": anon_id,
        "anthropic-device-id": device_id,
    }


# 无种子时的默认头（向后兼容旧引用）
COMMON_HEADERS = build_headers()
