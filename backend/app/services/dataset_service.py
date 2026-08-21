"""Generate/persist demo datasets.

Reuses Phase 1's deterministic generator as-is (`app.data_generation`);
this module's only job is converting its dataclass output into rows and
persisting them idempotently.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.config import GeneratorConfig
from app.data_generation.generator import generate_dataset
from app.db.models import PaymentORM, SettlementORM


def dataset_id_for(seed: int, num_records: int) -> str:
    # Deterministic: the same (seed, num_records) always names the same
    # dataset, so re-requesting it is naturally idempotent.
    return f"demo-seed{seed}-n{num_records}"


def generate_and_persist_demo_dataset(db: Session, seed: int, num_records: int) -> dict:
    dataset_id = dataset_id_for(seed, num_records)

    existing_payment_id = db.scalar(
        select(PaymentORM.id).where(PaymentORM.dataset_id == dataset_id).limit(1)
    )
    if existing_payment_id is not None:
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
    db.commit()

    return {
        "dataset_id": dataset_id,
        "seed": seed,
        "num_records": num_records,
        "payment_count": len(bundle.payments),
        "settlement_count": len(bundle.settlements),
        "created": True,
    }
