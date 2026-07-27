import unittest

from billing.models import (
    BillingProfile,
    PaymentRecord,
    mask_iban,
    normalize_iban,
    validate_iban,
)


class IbanTests(unittest.TestCase):
    def test_normalizes_and_validates_iban(self):
        raw = "de89 3704 0044 0532 0130 00"

        self.assertEqual(normalize_iban(raw), "DE89370400440532013000")
        self.assertEqual(validate_iban(raw), "DE89370400440532013000")

    def test_accepts_iban_from_other_sepa_countries(self):
        try:
            result = validate_iban("PL61 1090 1014 0000 0712 1981 2874")
        except ValueError:
            result = None
        self.assertEqual(
            result,
            "PL61109010140000071219812874",
        )

    def test_rejects_invalid_checksum(self):
        with self.assertRaisesRegex(ValueError, "IBAN"):
            validate_iban("DE89370400440532013001")

    def test_masks_iban(self):
        self.assertEqual(mask_iban("DE89370400440532013000"), "DE89...3000")


class BillingModelTests(unittest.TestCase):
    def test_profile_normalizes_country(self):
        profile = BillingProfile(
            name="Ada Lovelace",
            country="de",
            line1="1 Example Street",
            city="Berlin",
            postal_code="10115",
        )

        self.assertEqual(profile.country, "DE")

    def test_payment_record_contains_no_payment_secrets(self):
        record = PaymentRecord(
            checkout_session_id="cs_123",
            payment_intent_id="pi_123",
            status="pending",
            iban_last4="3000",
            updated_at="2026-07-27T00:00:00Z",
        )

        serialized = record.to_dict()
        rendered = repr(serialized)
        self.assertNotIn("client_secret", serialized)
        self.assertNotIn("iban", rendered.lower().replace("iban_last4", ""))
        self.assertEqual(serialized["iban_last4"], "3000")


if __name__ == "__main__":
    unittest.main()
