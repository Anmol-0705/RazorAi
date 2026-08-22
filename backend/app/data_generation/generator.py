"""Deterministic synthetic payment/settlement generator.

Reproducibility contract: given the same GeneratorConfig (seed,
num_records, weights), generate_dataset() always produces identical
payments, settlements, and ground truth. All randomness is drawn from
a single seeded random.Random instance, consumed in a fixed order.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.data_generation.config import GeneratorConfig
from app.data_generation.enums import GroundTruthCondition
from app.data_generation.ground_truth import GroundTruthRecord
from app.models.enums import PaymentStatus, SettlementStatus
from app.models.payment import Payment
from app.models.settlement import Settlement

FEE_RATE = Decimal("0.02")
TAX_RATE = Decimal("0.18")
NORMAL_SETTLEMENT_DELAY_HOURS = (1, 48)
DELAYED_SETTLEMENT_DELAY_DAYS = (10, 30)
PAYMENT_AMOUNT_RANGE_PAISE = (10_000, 500_000)  # 100.00 - 5000.00


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _deterministic_id(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128)))


def _standard_fee(amount: Decimal) -> Decimal:
    return _q2(amount * FEE_RATE)


def _standard_tax(fee: Decimal) -> Decimal:
    return _q2(fee * TAX_RATE)


@dataclass
class DatasetBundle:
    payments: list
    settlements: list
    ground_truth: list

    def to_dict(self) -> dict:
        return {
            "payments": [p.to_dict() for p in self.payments],
            "settlements": [s.to_dict() for s in self.settlements],
        }

    def ground_truth_to_dict(self) -> dict:
        return {"ground_truth": [g.to_dict() for g in self.ground_truth]}


def _condition_sequence(rng: random.Random, num_records: int, weights: dict) -> list:
    """Turn weights into an exact, shuffled count-based sequence so
    every anomaly type is guaranteed to appear (not left to chance),
    while still deterministic under a fixed seed."""
    counts = {cond: round(weight * num_records) for cond, weight in weights.items()}
    drift = num_records - sum(counts.values())
    counts[GroundTruthCondition.NORMAL_MATCH] += drift
    sequence: list = []
    for cond, count in counts.items():
        sequence.extend([cond] * count)
    rng.shuffle(sequence)
    return sequence


def _build_payment(rng: random.Random, index: int, config: GeneratorConfig) -> Payment:
    # Namespaced by num_records (not just seed): Payment.transaction_id
    # carries a table-wide UNIQUE DB constraint, but is otherwise a pure
    # function of (seed, index) alone, so two datasets sharing a seed
    # would always collide on their overlapping index range regardless
    # of num_records (see DECISIONS.md). order_id has no DB uniqueness
    # constraint, but is namespaced the same way for consistency -- two
    # different real payments (from differently-sized same-seed
    # datasets) should never display the same Order ID.
    txn_id = f"TXN-{config.seed}-N{config.num_records}-{index:06d}"
    order_id = f"ORD-{config.seed}-N{config.num_records}-{index:06d}"
    customer_ref = f"CUST-{rng.randint(100000, 999999)}"
    amount = _q2(Decimal(rng.randrange(*PAYMENT_AMOUNT_RANGE_PAISE)) / 100)
    currency = rng.choice(config.currencies)
    method = rng.choice(config.payment_methods)
    created_at = config.base_date + timedelta(minutes=rng.randint(0, 60 * 24 * 90))
    return Payment(
        id=_deterministic_id(rng),
        transaction_id=txn_id,
        order_id=order_id,
        customer_reference=customer_ref,
        amount=amount,
        currency=currency,
        payment_method=method,
        payment_status=PaymentStatus.CAPTURED,
        created_at=created_at,
    )


def _make_settlement(
    rng: random.Random,
    transaction_reference: str,
    settled_amount: Decimal,
    fee: Decimal,
    tax: Decimal,
    settled_at,
    num_records: int,
    status: SettlementStatus = SettlementStatus.SETTLED,
) -> Settlement:
    # Namespaced by num_records: Settlement.settlement_id carries a
    # table-wide UNIQUE DB constraint. Unlike transaction_id it isn't a
    # clean function of (seed, index) -- it's an rng.randint() draw --
    # but the draw sequence still depends on num_records (via the
    # earlier condition-shuffle consuming a different number of rng
    # calls per size), so two datasets sharing a seed were empirically
    # confirmed to collide on ~10-20% of settlement_ids without this
    # prefix (see DECISIONS.md).
    return Settlement(
        id=_deterministic_id(rng),
        settlement_id=f"STL-N{num_records}-{rng.randint(10**9, 10**10 - 1)}",
        transaction_reference=transaction_reference,
        settled_amount=settled_amount,
        fee=fee,
        tax=tax,
        settlement_status=status,
        settled_at=settled_at,
    )


def _build_for_condition(rng: random.Random, payment: Payment, condition: GroundTruthCondition, config: GeneratorConfig):
    fee = _standard_fee(payment.amount)
    tax = _standard_tax(fee)
    normal_settled = _q2(payment.amount - fee - tax)
    normal_settled_at = payment.created_at + timedelta(hours=rng.randint(*NORMAL_SETTLEMENT_DELAY_HOURS))

    if condition == GroundTruthCondition.NORMAL_MATCH:
        s = _make_settlement(rng, payment.transaction_id, normal_settled, fee, tax, normal_settled_at, config.num_records)
        return [s], GroundTruthRecord(payment.transaction_id, condition, (s.settlement_id,), Decimal("0.00"), "normal matched settlement")

    if condition == GroundTruthCondition.MISSING_SETTLEMENT:
        return [], GroundTruthRecord(payment.transaction_id, condition, tuple(), payment.amount, "settlement never generated")

    if condition == GroundTruthCondition.DUPLICATE_SETTLEMENT:
        s1 = _make_settlement(rng, payment.transaction_id, normal_settled, fee, tax, normal_settled_at, config.num_records)
        s2 = _make_settlement(rng, payment.transaction_id, normal_settled, fee, tax, normal_settled_at + timedelta(hours=rng.randint(1, 6)), config.num_records)
        return [s1, s2], GroundTruthRecord(payment.transaction_id, condition, (s1.settlement_id, s2.settlement_id), normal_settled, "settlement processed twice for the same transaction")

    if condition == GroundTruthCondition.AMOUNT_MISMATCH:
        delta = _q2(Decimal(rng.randint(500, 5000)) / 100) * rng.choice([1, -1])
        mismatched = _q2(normal_settled + delta)
        if mismatched <= 0:
            mismatched = _q2(normal_settled + abs(delta))
        s = _make_settlement(rng, payment.transaction_id, mismatched, fee, tax, normal_settled_at, config.num_records)
        diff = abs(_q2(mismatched - normal_settled))
        return [s], GroundTruthRecord(payment.transaction_id, condition, (s.settlement_id,), diff, "settled amount does not match expected payout")

    if condition == GroundTruthCondition.PARTIAL_SETTLEMENT:
        fraction = Decimal(rng.randint(40, 80)) / Decimal(100)
        partial = _q2(normal_settled * fraction)
        s = _make_settlement(rng, payment.transaction_id, partial, fee, tax, normal_settled_at, config.num_records)
        diff = _q2(normal_settled - partial)
        return [s], GroundTruthRecord(payment.transaction_id, condition, (s.settlement_id,), diff, "only part of the expected amount was settled")

    if condition == GroundTruthCondition.FEE_MISMATCH:
        multiplier = Decimal(str(rng.choice([0.5, 1.5, 2.0])))
        wrong_fee = _q2(fee * multiplier)
        wrong_tax = _standard_tax(wrong_fee)
        settled = _q2(payment.amount - wrong_fee - wrong_tax)
        s = _make_settlement(rng, payment.transaction_id, settled, wrong_fee, wrong_tax, normal_settled_at, config.num_records)
        diff = abs(_q2(settled - normal_settled))
        return [s], GroundTruthRecord(payment.transaction_id, condition, (s.settlement_id,), diff, "fee applied does not match the standard fee schedule")

    if condition == GroundTruthCondition.DELAYED_SETTLEMENT:
        delayed_at = payment.created_at + timedelta(days=rng.randint(*DELAYED_SETTLEMENT_DELAY_DAYS))
        s = _make_settlement(rng, payment.transaction_id, normal_settled, fee, tax, delayed_at, config.num_records)
        return [s], GroundTruthRecord(payment.transaction_id, condition, (s.settlement_id,), Decimal("0.00"), "settlement arrived well outside the normal window")

    if condition == GroundTruthCondition.INVALID_REFERENCE:
        corrupted_ref = f"TXN-{config.seed}-{rng.randint(900000, 999999)}"
        s = _make_settlement(rng, corrupted_ref, normal_settled, fee, tax, normal_settled_at, config.num_records)
        return [s], GroundTruthRecord(payment.transaction_id, condition, (s.settlement_id,), Decimal("0.00"), "settlement reference does not correspond to any known payment")

    raise ValueError(f"unhandled condition: {condition}")


def _assert_uniqueness(payments: list, settlements: list) -> None:
    txn_ids = [p.transaction_id for p in payments]
    if len(txn_ids) != len(set(txn_ids)):
        raise ValueError("duplicate payment transaction_id generated")
    settlement_ids = [s.settlement_id for s in settlements]
    if len(settlement_ids) != len(set(settlement_ids)):
        raise ValueError("duplicate settlement_id generated")
    payment_ids = [p.id for p in payments]
    if len(payment_ids) != len(set(payment_ids)):
        raise ValueError("duplicate payment id generated")


def generate_dataset(config: GeneratorConfig) -> DatasetBundle:
    # Seeded by (seed, num_records), not seed alone: Payment.id and
    # Settlement.id are drawn from this rng stream via
    # _deterministic_id() (uuid from raw getrandbits), and empirically
    # (not just in theory) two runs sharing a seed but different
    # num_records produce a meaningful number of colliding ids -- e.g.
    # 27-63 collisions per pair across n100/n250/n500 -- because
    # _condition_sequence's rng.shuffle() consumes a different amount
    # of Mersenne Twister state per num_records, occasionally
    # realigning the underlying word stream. A different effective seed
    # per num_records gives every (seed, num_records) pair its own,
    # independent trajectory -- the same collision-avoidance guarantee
    # already relied on for two genuinely different seeds never
    # colliding -- while a *repeated* call with the identical
    # (seed, num_records) still reseeds identically and stays fully
    # reproducible (see DECISIONS.md).
    rng = random.Random(f"{config.seed}:{config.num_records}")
    conditions = _condition_sequence(rng, config.num_records, config.anomaly_weights)

    payments = []
    settlements = []
    ground_truth = []

    for index, condition in enumerate(conditions):
        payment = _build_payment(rng, index, config)
        payments.append(payment)
        new_settlements, gt = _build_for_condition(rng, payment, condition, config)
        settlements.extend(new_settlements)
        ground_truth.append(gt)

    _assert_uniqueness(payments, settlements)
    return DatasetBundle(payments=payments, settlements=settlements, ground_truth=ground_truth)
