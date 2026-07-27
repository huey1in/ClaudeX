import re
from dataclasses import asdict, dataclass, field


_IBAN_LENGTHS = {
    "AD": 24, "AL": 28, "AT": 20, "BE": 16, "BG": 22,
    "CH": 21, "CY": 28, "CZ": 24, "DE": 22, "DK": 18,
    "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22,
    "GI": 23, "GR": 27, "HR": 21, "HU": 28, "IE": 22,
    "IS": 26, "IT": 27, "LI": 21, "LT": 20, "LU": 20,
    "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19,
    "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25,
    "RO": 24, "RS": 22, "SE": 24, "SI": 19, "SK": 24,
    "SM": 27, "VA": 22, "XK": 20,
}


def normalize_iban(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


def validate_iban(value):
    iban = normalize_iban(value)
    country = iban[:2]
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]+", iban):
        raise ValueError("IBAN 格式无效")
    if country not in _IBAN_LENGTHS or len(iban) != _IBAN_LENGTHS[country]:
        raise ValueError("IBAN 长度无效")

    rearranged = iban[4:] + iban[:4]
    numeric = "".join(
        str(ord(char) - ord("A") + 10) if char.isalpha() else char
        for char in rearranged
    )
    if int(numeric) % 97 != 1:
        raise ValueError("IBAN 校验和无效")
    return iban


def mask_iban(value):
    iban = validate_iban(value)
    return f"{iban[:4]}...{iban[-4:]}"


@dataclass(frozen=True)
class BillingProfile:
    name: str
    country: str
    line1: str
    city: str
    postal_code: str
    line2: str = ""
    state: str = ""

    def __post_init__(self):
        object.__setattr__(self, "country", self.country.strip().upper())


@dataclass(frozen=True)
class CheckoutContext:
    session_id: str
    publishable_key: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True)
class PaymentRecord:
    checkout_session_id: str
    payment_intent_id: str
    status: str
    iban_last4: str
    updated_at: str

    def to_dict(self):
        return asdict(self)
