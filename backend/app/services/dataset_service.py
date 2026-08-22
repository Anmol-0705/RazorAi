"""Generate/persist demo datasets.

Reuses Phase 1's deterministic generator as-is (`app.data_generation`);
this module's only job is converting its dataclass output into rows and
persisting them idempotently.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data_generation.config import GeneratorConfig
from app.data_generation.generator import generate_dataset
from app.db.models import PaymentORM, SettlementORM
from app.services.errors import ConflictError


def dataset_id_for(seed: int, num_records: int) -> str:
    # Deterministic: the same (seed, num_records) always names the same
    # dataset, so re-requesting it is naturally idempotent.
    return f"demo-seed{seed}-n{num_records}"


def _existing_dataset(db: Session, dataset_id: str, seed: int, num_records: int) -> dict | None:
    existing_payment_id = db.scalar(
        select(PaymentORM.id).where(PaymentORM.dataset_id == dataset_id).limit(1)
    )
    if existing_payment_id is None:
        return None
    payment_rows = db.execute(
        select(PaymentORM).where(PaymentORM.dataset_id == dataset_id)
    ).scalars().all()
    settlement_rows = db.execute(
        select(SettlementORM).where(SettlementORM.dataset_id == dataset_id)
    ).scalars().all()
    return {
        "dataset_id": dataset_id,
        "seed": seed,
        "num_records": num_records,
        "payment_count": len(payment_rows),
        "settlement_count": len(settlement_rows),
        "created": False,
    }


def generate_and_persist_demo_dataset(db: Session, seed: int, num_records: int) -> dict:
    dataset_id = dataset_id_for(seed, num_records)

    existing = _existing_dataset(db, dataset_id, seed, num_records)
    if existing is not None:
        return existing

    bundle = generate_dataset(GeneratorConfig(seed=seed, num_records=num_records))

    for payment in bundle.payments:
        db.add(
            PaymentORM(
                id=payment.id,
                dataset_id=dataset_id,
                transaction_id=payment.transaction_id,
                order_id=payment.order_id,
                customer_reference=payment.customer_reference,
                amount=payment.amount,
                currency=payment.currency.value,
                payment_method=payment.payment_method.value,
                payment_status=payment.payment_status.value,
                created_at=payment.created_at,
            )
        )
    for settlement in bundle.settlements:
        db.add(
            SettlementORM(
                id=settlement.id,
                dataset_id=dataset_id,
                settlement_id=settlement.settlement_id,
                transaction_reference=settlement.transaction_reference,
                settled_amount=settlement.settled_amount,
                fee=settlement.fee,
                tax=settlement.tax,
                settlement_status=settlement.settlement_status.value,
                settled_at=settlement.settled_at,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        # The pre-check above only rules out this exact dataset_id
        # already existing; it cannot see a same-seed sibling dataset
        # of a different num_records (the generator derives
        # transaction_id from (seed, index) only -- see
        # app.data_generation.generator._build_payment -- so any two
        # datasets sharing a seed always collide on their overlapping
        # index range's transaction_id, which is globally unique across
        # ALL datasets, not scoped per dataset_id). Postgres has
        # already aborted the whole transaction; roll back so this
        # session can run new queries, then tell the two possible
        # causes apart:
        db.rollback()
        existing = _existing_dataset(db, dataset_id, seed, num_records)
        if existing is not None:
            # A concurrent identical request won the race and
            # committed first between our pre-check and our own
            # insert. Nothing was duplicated (our failed insert never
            # committed) -- reuse what the other request persisted.
            return existing
        # Not a race with ourselves: this dataset_id still doesn't
        # exist, so the conflict is a genuinely different, already-
        # persisted dataset sharing this seed. Never silently swallow
        # this or fabricate a "created" response for a dataset that
        # was NOT actually written.
        raise ConflictError(
            f"cannot generate dataset '{dataset_id}': seed {seed}'s deterministic "
            "transaction IDs collide with an already-persisted dataset that used the "
            "same seed with a different num_records. Use a different seed, or only ever "
            "generate one num_records size per seed."
        )

    return {
        "dataset_id": dataset_id,
        "seed": seed,
        "num_records": num_records,
        "payment_count": len(bundle.payments),
        "settlement_count": len(bundle.settlements),
        "created": True,
    }
