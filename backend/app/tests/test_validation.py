import unittest
from datetime import datetime
from decimal import Decimal

from app.data_generation.config import GeneratorConfig
from app.data_generation.generator import generate_dataset
from app.models.enums import Currency, PaymentMethod, PaymentStatus, SettlementStatus
from app.models.payment import Payment
from app.models.settlement import Settlement
from app.validation import ValidationError


def _valid_payment_kwargs():
    return dict(
        id="pay-1",
        transaction_id="TXN-1",
        order_id="ORD-1",
        customer_reference="CUST-1",
        amount=Decimal("100.00"),
        currency=Currency.INR,
        payment_method=PaymentMethod.UPI,
        payment_status=PaymentStatus.CAPTURED,
        created_at=datetime(2026, 1, 1),
    )


class PaymentValidationTests(unittest.TestCase):
    def test_valid_payment_constructs(self):
        Payment(**_valid_payment_kwargs())

    def test_negative_amount_rejected(self):
        kwargs = _valid_payment_kwargs()
        kwargs["amount"] = Decimal("-5.00")
        with self.assertRaises(ValidationError):
            Payment(**kwargs)

    def test_zero_amount_rejected(self):
        kwargs = _valid_payment_kwargs()
        kwargs["amount"] = Decimal("0.00")
        with self.assertRaises(ValidationError):
            Payment(**kwargs)

    def test_empty_transaction_id_rejected(self):
        kwargs = _valid_payment_kwargs()
        kwargs["transaction_id"] = "   "
        with self.assertRaises(ValidationError):
            Payment(**kwargs)

    def test_invalid_timestamp_rejected(self):
        kwargs = _valid_payment_kwargs()
        kwargs["created_at"] = "not-a-date"
        with self.assertRaises(ValidationError):
            Payment(**kwargs)

    def test_unsupported_currency_rejected(self):
        # Payment.currency must be a Currency enum member; passing a raw
        # unsupported string should fail the enum-membership check first.
        kwargs = _valid_payment_kwargs()
        kwargs["currency"] = "GBP"
        with self.assertRaises(ValidationError):
            Payment(**kwargs)


class SettlementValidationTests(unittest.TestCase):
    def test_negative_settled_amount_rejected(self):
        with self.assertRaises(ValidationError):
            Settlement(
                id="stl-1", settlement_id="STL-1", transaction_reference="TXN-1",
                settled_amount=Decimal("-1.00"), fee=Decimal("1.00"), tax=Decimal("0.18"),
                settlement_status=SettlementStatus.SETTLED, settled_at=datetime(2026, 1, 2),
            )

    def test_negative_fee_rejected(self):
        with self.assertRaises(ValidationError):
            Settlement(
                id="stl-1", settlement_id="STL-1", transaction_reference="TXN-1",
                settled_amount=Decimal("10.00"), fee=Decimal("-1.00"), tax=Decimal("0.18"),
                settlement_status=SettlementStatus.SETTLED, settled_at=datetime(2026, 1, 2),
            )

    def test_empty_reference_rejected(self):
        with self.assertRaises(ValidationError):
            Settlement(
                id="stl-1", settlement_id="STL-1", transaction_reference="",
                settled_amount=Decimal("10.00"), fee=Decimal("1.00"), tax=Decimal("0.18"),
                settlement_status=SettlementStatus.SETTLED, settled_at=datetime(2026, 1, 2),
            )


class DatasetUniquenessTests(unittest.TestCase):
    def test_unique_payment_transaction_ids(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        ids = [p.transaction_id for p in bundle.payments]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unique_settlement_ids_even_with_duplicates_anomaly(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        ids = [s.settlement_id for s in bundle.settlements]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
