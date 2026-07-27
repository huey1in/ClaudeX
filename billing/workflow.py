import random
import time

from account.storage import update_account
from core.config import BASE_URL
from core.console import print_log
from core.session import make_session

from .claude import BillingProtocolError, ClaudeBillingClient, safe_response_text
from .models import BillingProfile, PaymentRecord, mask_iban, validate_iban
from .stripe import StripeCheckoutClient, StripeProtocolError


# (country, state_or_region, city, postal_prefix, street_names)
_DE_DATA = [
    ("DE", "Berlin",          "Berlin",       ("101", "102", "103", "104", "105", "106", "107", "108", "109", "110"),
     ["Friedrichstraße", "Unter den Linden", "Kurfürstendamm", "Alexanderplatz", "Prenzlauer Allee", "Schönhauser Allee"]),
    ("DE", "Bayern",          "München",      ("801", "802", "803", "804", "805", "806", "807", "808", "809", "810"),
     ["Leopoldstraße", "Maximilianstraße", "Sendlinger Straße", "Kaufingerstraße", "Ludwigstraße"]),
    ("DE", "Hamburg",         "Hamburg",      ("200", "201", "202", "203", "204", "205", "206", "207", "208", "209"),
     ["Mönckebergstraße", "Jungfernstieg", "Reeperbahn", "Osterstraße", "Grindelallee"]),
    ("DE", "Nordrhein-Westfalen", "Köln",     ("507", "508", "509", "510", "511", "512", "513", "514", "515", "516"),
     ["Schildergasse", "Ehrenstraße", "Breite Straße", "Hohe Straße", "Aachener Straße"]),
    ("DE", "Baden-Württemberg", "Stuttgart",  ("701", "702", "703", "704", "705", "706", "707", "708", "709", "710"),
     ["Königstraße", "Calwer Straße", "Rotebühlplatz", "Tübinger Straße", "Marienstraße"]),
    ("DE", "Hessen",          "Frankfurt am Main", ("601", "602", "603", "604", "605", "606", "607", "608", "609", "610"),
     ["Zeil", "Goethestraße", "Berger Straße", "Schweizer Straße", "Sachsenhäuser Ufer"]),
]

# 真实德国银行 BLZ（银行代码），用于生成格式合法的 DE IBAN
_DE_BLZS = [
    "10020030", "10050000", "10070024", "20010020", "20030000",
    "20070024", "21050170", "30070010", "37040044", "37070060",
    "50040000", "50070010", "60050101", "70020270", "70070010",
]


def _random_iban_de() -> str:
    """生成一个校验和合法的随机德国 IBAN（DE, 22位）。"""
    blz = random.choice(_DE_BLZS)
    # 10位账号：首位非零，其余随机
    account = str(random.randint(1, 9)) + "".join(
        str(random.randint(0, 9)) for _ in range(9)
    )
    bban = blz + account  # 18位数字
    # MOD-97 计算校验位：移到末尾后字母转数字
    rearranged = bban + "DE00"
    numeric = "".join(
        str(ord(c) - ord("A") + 10) if c.isalpha() else c
        for c in rearranged
    )
    check = 98 - (int(numeric) % 97)
    return f"DE{check:02d}{bban}"


_FIRST_NAMES = [
    "Anna", "Emma", "Lena", "Sophie", "Laura", "Julia", "Lea", "Marie", "Hannah", "Sarah",
    "Thomas", "Michael", "Andreas", "Stefan", "Christian", "Klaus", "Markus", "Peter", "Lukas", "Felix",
]
_LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
    "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann",
]


def _random_billing_profile() -> BillingProfile:
    """每次调用生成一个随机的德国账单地址。"""
    country, state, city, postal_prefixes, streets = random.choice(_DE_DATA)
    first = random.choice(_FIRST_NAMES)
    last = random.choice(_LAST_NAMES)
    street = random.choice(streets)
    house_number = random.randint(1, 120)
    postal_code = random.choice(postal_prefixes) + str(random.randint(10, 99))
    return BillingProfile(
        name=f"{first} {last}",
        country=country,
        line1=f"{street} {house_number}",
        city=city,
        state=state,
        postal_code=postal_code,
    )


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_claude_client(account):
    session = make_session(
        cookies=account.get("cookies"),
        seed=account.get("email") or account.get("uuid"),
    )
    return ClaudeBillingClient(session=session, base_url=BASE_URL)


def _default_stripe_client(account):
    return StripeCheckoutClient()


def _record(result, iban_last4, status=None):
    return PaymentRecord(
        checkout_session_id=result.checkout_session_id,
        payment_intent_id=result.payment_intent_id,
        status=status or result.status,
        iban_last4=iban_last4,
        updated_at=_utc_now(),
    )


def _write_payment(accounts_file, account, record):
    update_account(accounts_file, account["uuid"], {"payment": record.to_dict()})


def _safe_error_detail(exc):
    if isinstance(exc, (BillingProtocolError, StripeProtocolError)):
        return str(exc)
    return type(exc).__name__


def run_sepa_workflow(accounts, accounts_file="accounts.json", output_fn=print_log,
                      claude_client_factory=None, stripe_client_factory=None):
    """Submit SEPA details serially, then refresh all submitted sessions once."""
    if not accounts:
        return []

    claude_client_factory = claude_client_factory or _default_claude_client
    stripe_client_factory = stripe_client_factory or _default_stripe_client
    profile = _random_billing_profile()
    records = {}
    pending = []

    for index, account in enumerate(accounts, 1):
        email = account.get("email") or account.get("email_address") or account["uuid"]
        output_fn(f"\n[{index}/{len(accounts)}] 自动订阅中…")
        output_fn("  [1/5] 生成并校验 IBAN…")
        iban = validate_iban(_random_iban_de())
        output_fn(f"        IBAN: {mask_iban(iban)}")

        context = None
        stripe = None
        try:
            claude = claude_client_factory(account)
            output_fn("  [2/5] 查询 Checkout 能力…")
            capabilities = claude.get_checkout_capabilities(account["org_uuid"])
            checkout_flow = capabilities.get("checkout_flow")
            output_fn(f"        checkout_flow: {checkout_flow or 'missing'}")
            if checkout_flow not in {"cassia", "custom"}:
                raise BillingProtocolError(
                    "该组织不支持 Custom Checkout "
                    f"(checkout_flow={checkout_flow or 'missing'}); "
                    f"原始响应: {safe_response_text(capabilities)}"
                )
            output_fn("  [3/5] 创建 Checkout 会话…")
            context = claude.create_checkout_session(account["org_uuid"])
            output_fn(f"        Checkout Session: {context.session_id}")
            stripe = stripe_client_factory(account)
            output_fn("  [4/5] 提交 SEPA Direct Debit…")
            submitted = stripe.submit_sepa(context, profile, email, iban)
            payment = _record(submitted, iban[-4:], status="pending")
            _write_payment(accounts_file, account, payment)
            records[account["uuid"]] = payment
            pending.append((account, context, stripe, iban[-4:]))
            output_fn("        当前状态: pending")
        except Exception as exc:
            uncertain = context is not None and stripe is not None
            failed = PaymentRecord(
                checkout_session_id=context.session_id if context else "",
                payment_intent_id="",
                status="pending" if uncertain else "failed",
                iban_last4=iban[-4:],
                updated_at=_utc_now(),
            )
            _write_payment(accounts_file, account, failed)
            records[account["uuid"]] = failed
            if uncertain:
                pending.append((account, context, stripe, iban[-4:]))
                output_fn(f"  [待处理] 自动订阅结果待确认: {email}")
                output_fn(
                    f"        原因: {type(exc).__name__}，保留 pending 并稍后查询。"
                )
            else:
                output_fn(f"  [失败] 自动订阅失败: {email}")
                output_fn(f"        原因: {_safe_error_detail(exc)}")

    if pending:
        output_fn("\n[订阅] 所有账户提交完毕，开始统一查询异步状态…")
    for account, context, stripe, iban_last4 in pending:
        email = account.get("email") or account.get("email_address") or account["uuid"]
        output_fn("  [5/5] 查询异步付款状态…")
        output_fn(f"        账户: {email}")
        try:
            refreshed = stripe.poll(context)
            payment = _record(refreshed, iban_last4)
            _write_payment(accounts_file, account, payment)
            records[account["uuid"]] = payment
            output_fn(f"        最终状态: {payment.status}")
            if payment.status == "succeeded":
                output_fn(f"  [成功] 自动订阅完成: {email}")
            elif payment.status == "pending":
                output_fn(f"  [待处理] 自动订阅尚未完成: {email}")
            else:
                output_fn(f"  [失败] 自动订阅失败: {email}")
        except Exception as exc:
            output_fn(f"  [待处理] 自动订阅状态待确认: {email}")
            output_fn(f"        原因: {_safe_error_detail(exc)}，保留 pending。")

    results = [records[account["uuid"]] for account in accounts]
    succeeded = sum(record.status == "succeeded" for record in results)
    pending_count = sum(record.status == "pending" for record in results)
    failed = len(results) - succeeded - pending_count
    output_fn(
        f"\n[订阅] 完成: 成功 {succeeded} 个，"
        f"待处理 {pending_count} 个，失败 {failed} 个"
    )
    return results
