import time
from requests.exceptions import SSLError, HTTPError

import requests

from .accounts import load_accounts
from .config import ACCOUNTS_FILE, BASE_URL, build_headers


def _make_direct_session(cookies=None, seed=None):
    """Check 命令直连 claude.ai，不走代理，避免 SSL 断连。"""
    s = requests.Session()
    s.headers.update(build_headers(seed))
    if cookies:
        for k, v in cookies.items():
            s.cookies.set(k, v, domain="claude.ai")
    return s


def _fetch_with_retry(s, url, params=None, max_retries=3):
    """发起请求，SSL 错误时重试。"""
    for attempt in range(max_retries):
        try:
            r = s.get(url, params=params, timeout=15)
            r.raise_for_status()
            # 返回 HTML 说明 session 失效（302 重定向到登录页后返回 200 HTML）
            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                e = HTTPError(response=r)
                e.response.status_code = 401  # 标记为未认证
                raise e
            return r.json()
        except SSLError:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
                continue
            raise
        except HTTPError:
            raise


def _fetch_account(s):
    return _fetch_with_retry(s, f"{BASE_URL}/api/account",
                             params={"statsig_hashing_algorithm": "djb2"})


def _fetch_user_access(s, org_uuid):
    return _fetch_with_retry(s, f"{BASE_URL}/api/bootstrap/{org_uuid}/current_user_access")


def _parse_plan(org):
    tier = org.get("rate_limit_tier", "")
    if tier == "default_claude_ai":
        return "Free"
    if "pro" in tier.lower():
        return "Pro"
    if "team" in tier.lower():
        return "Team"
    return tier or "Unknown"


def _parse_model_limits(acct_data):
    mems = acct_data.get("memberships", [])
    if not mems:
        return []
    cfg = mems[0]["organization"].get("claude_ai_bootstrap_models_config", [])
    return [{"model": m.get("model"), "hard_limit": m.get("hard_limit")} for m in cfg]


def _parse_features(access_data):
    return {f["feature"]: f["status"] for f in access_data.get("features", [])}


def check_usage(accounts_file=ACCOUNTS_FILE):
    """查询并打印账号文件中所有账号的用量状态。"""
    accounts = load_accounts(accounts_file)
    if not accounts:
        print("未找到账号，请先运行: python main.py register")
        return

    print(f"共找到 {len(accounts)} 个账号\n")

    stats = {"ok": 0, "expired": 0, "error": 0}

    for i, record in enumerate(accounts, 1):
        email    = record["email"]
        org_uuid = record.get("org_uuid", "")
        cookies  = record.get("cookies", {})

        print(f"[{i}/{len(accounts)}] {email}")
        try:
            s    = _make_direct_session(cookies, seed=email)
            acct = _fetch_account(s)
            mems = acct.get("memberships", [])

            plan   = _parse_plan(mems[0]["organization"]) if mems else "Unknown"
            limits = _parse_model_limits(acct)

            features   = {}
            if org_uuid:
                access   = _fetch_user_access(s, org_uuid)
                features = _parse_features(access)

            chat_status = features.get("chat", "unknown")
            status      = "active" if chat_status == "available" else chat_status
            icon        = "[OK]" if status == "active" else "[ERR]"

            print(f"  {icon} 状态: {status}  套餐: {plan}")
            for m in limits[:3]:  # 仅显示前 3 个模型
                limit_str = f"{m['hard_limit']:,}" if m["hard_limit"] else "unlimited"
                print(f"    {m['model']:<34} {limit_str}")
            if len(limits) > 3:
                print(f"    ... (共 {len(limits)} 个模型)")
            stats["ok"] += 1

        except HTTPError as e:
            code = getattr(e.response, 'status_code', 0)
            if code in (401, 403):
                print(f"  [EXPIRED] 会话已失效 ({code})")
                stats["expired"] += 1
            else:
                print(f"  [ERR] HTTP {code}")
                stats["error"] += 1
        except Exception as e:
            err_msg = str(e)
            if "SSLEOFError" in err_msg or "SSL" in err_msg:
                print("  [ERR] SSL 连接失败（代理问题）")
            else:
                print(f"  [ERR] {err_msg[:80]}")
            stats["error"] += 1

        print()

    print(f"汇总: {stats['ok']} 正常, {stats['expired']} 失效, {stats['error']} 错误")
    if stats["expired"] > 0:
        print("\n提示: 失效账号需重新登录，运行: python main.py register")
