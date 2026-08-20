import base64
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.exceptions import SSLError, ConnectionError as ReqConnError
from requests.utils import dict_from_cookiejar

from account.storage import save_account
from core.config import ACCOUNTS_FILE, BASE_URL, EMAIL_SERVICE, PROXIES, build_headers
from core.console import print_log

from .moemail import MoeMailClient
from .mailnest import MailNestClient

# 常见美国人名/姓氏，用于生成邮箱前缀
_FIRST_NAMES = [
    "james", "john", "robert", "michael", "william", "david", "richard",
    "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
    "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua",
    "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara",
    "susan", "jessica", "sarah", "karen", "nancy", "lisa", "betty",
    "margaret", "sandra", "ashley", "kimberly", "emily", "donna", "michelle",
]
_LAST_NAMES = [
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller",
    "davis", "rodriguez", "martinez", "hernandez", "lopez", "gonzalez",
    "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
    "lee", "perez", "thompson", "white", "harris", "sanchez", "clark",
    "ramirez", "lewis", "robinson", "walker", "young", "allen", "king",
]


def _random_name() -> str:
    """生成类似美国人的邮箱前缀，如 john.smith82、msarah_lee。"""
    first = random.choice(_FIRST_NAMES)
    last = random.choice(_LAST_NAMES)
    sep = random.choice([".", "_", ""])
    num = random.choice(["", str(random.randint(1, 99)),
                         str(random.randint(1970, 2005))])
    return f"{first}{sep}{last}{num}"


def _mail_client():
    if EMAIL_SERVICE == "moemail":
        return MoeMailClient()
    if EMAIL_SERVICE == "mailnest":
        return MailNestClient()
    raise RuntimeError(f"Unsupported EMAIL_SERVICE: {EMAIL_SERVICE}")


def _bare_session(seed=None):
    """注册专用 session：带完整浏览器头，禁用 keep-alive 避免代理断连。

    传入 seed（账号邮箱）时，anonymous-id / device-id 按其哈希派生，
    使每个账号拥有稳定且互不相同的指纹。
    """
    s = requests.Session()
    s.headers.update(build_headers(seed))
    s.headers.update({"Connection": "close"})
    if PROXIES:
        s.proxies.update(PROXIES)
    return s


def _get_exit_ip() -> str:
    """通过代理查询出口 IP 及类型，失败返回 '?'。"""
    try:
        s = _bare_session()
        # ip-api.com 免费接口（HTTP），返回 IP + 类型字段
        r = s.get(
            "http://ip-api.com/json",
            params={"fields": "query,isp,mobile,proxy,hosting"},
            timeout=8,
        )
        d = r.json()
        ip = d.get("query", "?")

        if d.get("proxy"):
            ip_type = "代理/VPN"
        elif d.get("hosting"):
            ip_type = "数据中心"
        elif d.get("mobile"):
            ip_type = "移动网络"
        else:
            ip_type = "家宽"

        isp = d.get("isp", "")
        return f"{ip}  [{ip_type}]  {isp}"
    except Exception:
        return "?"

_MAX_RETRIES = 5


def _req(s, method, url, max_retries=_MAX_RETRIES, **kwargs):
    """在已有 session 上执行请求，保留 Cookie。SSL 错误时原地重试（urllib3 自动重建 TCP）。"""
    last_err = None
    for attempt in range(max_retries):
        try:
            r = getattr(s, method)(url, timeout=20, **kwargs)

            if r.status_code == 403:
                raise RuntimeError(f"HTTP 403: {r.text[:100]}")

            if r.status_code == 429:
                wait = 3 * (attempt + 1)
                print_log(f"    [重试 {attempt+1}/{max_retries}] HTTP 429，等待 {wait}s…")
                time.sleep(wait)
                last_err = Exception("HTTP 429")
                continue

            if r.status_code not in (200, 201, 204):
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

            r.raise_for_status()

            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                m = re.search(r"<title>(.*?)</title>", r.text[:500])
                title = m.group(1) if m else ct
                raise RuntimeError(f"非 JSON 响应 ({r.status_code}): {title}")

            # 空 body（如 send_magic_link 成功）返回空 dict
            if not r.text.strip():
                return {}
            return r.json()

        except (SSLError, ReqConnError) as e:
            last_err = e
            wait = 2 ** attempt
            print_log(
                f"    [重试 {attempt+1}/{max_retries}] "
                f"{type(e).__name__}，等待 {wait}s…"
            )
            time.sleep(wait)
        except Exception:
            raise

    raise last_err


def _get_login_methods(s, email):
    return _req(s, "get", f"{BASE_URL}/api/auth/login_methods",
                params={"email": email, "source": "claude"})


def _send_magic_link(s, email, utc_offset=-480):
    body = {"utc_offset": utc_offset, "email_address": email,
            "login_intent": None, "locale": "en-US",
            "return_to": None, "source": "claude"}
    _req(s, "post", f"{BASE_URL}/api/auth/send_magic_link", data=json.dumps(body))


def _verify_magic_link(s, email, nonce, encoded_email=None):
    if not encoded_email:
        encoded_email = base64.b64encode(email.encode()).decode()
    body = {
        "credentials": {"method": "nonce", "nonce": nonce,
                        "encoded_email_address": encoded_email},
        "locale": "en-US",
        "source": "claude",
    }
    return _req(s, "post", f"{BASE_URL}/api/auth/verify_magic_link", data=json.dumps(body))


def _serialize_cookies(cookie_jar):
    """遍历 Cookie 条目，避免同名但不同域的 Cookie 触发冲突。"""
    return dict_from_cookiejar(cookie_jar)


def _extract_nonce(text):
    m = re.search(r'/magic-link#([0-9a-fA-F]+):([A-Za-z0-9+/=]+)', text)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'[?&]nonce=([0-9a-fA-F]+)', text)
    return (m.group(1) if m else None), None


def register_account(accounts_file=ACCOUNTS_FILE):
    """注册单个账号，成功后追加到 accounts_file 并返回记录 dict。"""
    # ── 步骤 1/7：检查出口 IP ────────────────────────────────────────────
    print_log("  [1/7] 检查出口 IP…")
    ip = _get_exit_ip()
    print_log(f"        出口 IP: {ip}")

    # ── 步骤 2/7：查询临时邮箱服务配置 ──────────────────────────────────
    print_log(f"  [2/7] 查询临时邮箱服务配置 ({EMAIL_SERVICE})…")
    mail = _mail_client()
    cfg = mail.get_config()
    raw = cfg.get("emailDomains") or cfg.get("domains") or "moemail.app"
    domains = [x.strip() for x in raw.split(",")] if isinstance(raw, str) else raw
    domain = random.choice(domains) if domains else None
    print_log(f"        可用域名: {domains}")
    if cfg.get("projects"):
        print_log(f"        可用项目: {[p.get('code') for p in cfg['projects']]}")
    print_log(f"        选用域名: {domain or 'service-managed'}")

    # ── 步骤 3/7：生成临时邮箱 ───────────────────────────────────────────
    print_log("  [3/7] 生成临时邮箱…")
    name = _random_name()
    box = mail.generate_email(name=name, expiry_time=3600000, domain=domain)
    email = box["email"]
    email_id = box["id"]
    print_log(f"        邮箱: {email}")
    print_log(f"        邮箱 ID: {email_id}")

    s = _bare_session(seed=email)

    # ── 步骤 4/7：查询登录方式 ───────────────────────────────────────────
    print_log("  [4/7] 查询 claude.ai 登录方式…")
    methods = _get_login_methods(s, email)
    print_log(f"        可用方式: {methods.get('methods', methods)}")

    # ── 步骤 5/7：发送 magic link ────────────────────────────────────────
    print_log("  [5/7] 发送 magic link 邮件…")
    time.sleep(1)
    _send_magic_link(s, email)
    print_log("        已发送，等待邮件到达…")

    # ── 步骤 6/7：等待邮件并提取 nonce ───────────────────────────────────
    print_log("  [6/7] 轮询邮箱，等待 Anthropic 验证邮件…")
    msg = mail.wait_for_message(email_id, sender_contains="anthropic",
                                timeout=120, interval=3)
    print_log("        收到验证邮件，提取 nonce…")
    nonce, enc_email = _extract_nonce(json.dumps(msg, ensure_ascii=False))
    if not nonce:
        raise RuntimeError("未能从邮件中提取 nonce")
    print_log(f"        nonce: {nonce}")
    print_log(f"        encoded_email: {enc_email}")

    # ── 步骤 7/7：换取会话并保存 ─────────────────────────────────────────
    print_log("  [7/7] 用 nonce 换取登录会话…")
    data = _verify_magic_link(s, email, nonce, encoded_email=enc_email)
    acct = data.get("account", {})
    mems = acct.get("memberships", [])
    org = mems[0]["organization"] if mems else {}

    record = {
        "email": email,
        "uuid": acct.get("uuid"),
        "email_address": acct.get("email_address") or acct.get("email"),
        "org_uuid": org.get("uuid"),
        "org_name": org.get("name"),
        "cookies": _serialize_cookies(s.cookies),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print_log(f"        账号 UUID: {record['uuid']}")
    print_log(f"        组织: {record['org_name']}")
    print_log(f"        会话 Cookie: {list(record['cookies'].keys())}")

    save_account(record, accounts_file)
    print_log(f"        已保存到 {accounts_file}")
    print_log(f"  [成功] 注册完成: {email}")
    return record


def register_batch(count, concurrent=1, accounts_file=ACCOUNTS_FILE,
                   on_success=None):
    """批量注册账号。"""
    results = []
    failed = 0

    if concurrent <= 1:
        for i in range(count):
            print_log(f"\n[{i+1}/{count}] 注册中…")
            try:
                account = register_account(accounts_file)
            except Exception as e:
                failed += 1
                print_log(f"  [失败] {e}")
            else:
                results.append(account)
                if on_success:
                    on_success(account)
            time.sleep(1)
    else:
        def _task(idx):
            print_log(f"\n[{idx}/{count}] 注册中…")
            return register_account(accounts_file)

        with ThreadPoolExecutor(max_workers=concurrent) as pool:
            futures = {pool.submit(_task, i + 1): i + 1 for i in range(count)}
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    account = fut.result()
                except Exception as e:
                    failed += 1
                    print_log(f"[{idx}/{count}] 失败: {e}")
                else:
                    results.append(account)
                    if on_success:
                        on_success(account)

    print_log(f"\n[注册] 完成: 成功 {len(results)} 个，失败 {failed} 个")
    return results
