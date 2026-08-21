"""Loads the committed held-out evaluation dataset from disk.

`data/eval/n250/{payments,settlements}.json` are Phase 1's deterministic
generator output (seed 1337, disjoint from the seed-42 demo datasets —
see DECISIONS.md D005/generator docs); `data/ground_truth/eval/n250/ground_truth.json`
is the true condition per payment, kept in a physically separate tree
so the reconciliation engine can never read it. This module only
reads the committed JSON files — it never re-invokes the generator, so
evaluation is scored against the exact same fixed records every time,
not a freshly regenerated (if equivalent) dataset.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.models.enums import Currency, PaymentMethod, PaymentStatus, SettlementStatus
from app.models.payment import Payment
from app.models.settlement import Settlement

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVAL_DIR = _REPO_ROOT / "data" / "eval" / "n250"
DEFAULT_GROUND_TRUTH_DIR = _REPO_ROOT / "data" / "ground_truth" / "eval" / "n250"


@dataclass(frozen=True)
class EvalDataset:
    name: str
    payments: list
    settlements: list
    ground_truth: list  # list of dicts: payment_transaction_id, condition, settlement_ids, expected_amount_difference, notes


def _payment_from_dict(d: dict) -> Payment:
    return Payment(
        id=d["id"],
        transaction_id=d["transaction_id"],
        order_id=d["order_id"],
        customer_reference=d["customer_reference"],
        amount=Decimal(d["amount"]),
        currency=Currency(d["currency"]),
        payment_method=PaymentMethod(d["payment_method"]),
        payment_status=PaymentStatus(d["payment_status"]),
        created_at=datetime.fromisoformat(d["created_at"]),
    )


def _settlement_from_dict(d: dict) -> Settlement:
    return Settlement(
        id=d["id"],
        settlement_id=d["settlement_id"],
        transaction_reference=d["transaction_reference"],
        settled_amount=Decimal(d["settled_amount"]),
        fee=Decimal(d["fee"]),
        tax=Decimal(d["tax"]),
        settlement_status=SettlementStatus(d["settlement_status"]),
        settled_at=datetime.fromisoformat(d["settled_at"]),
    )


def load_eval_dataset(
    name: str = "n250",
    eval_dir: Path = DEFAULT_EVAL_DIR,
    ground_truth_dir: Path = DEFAULT_GROUND_TRUTH_DIR,
) -> EvalDataset:
    payments_path = eval_dir / "payments.json"
    settlements_path = eval_dir / "settlements.json"
    ground_truth_path = ground_truth_dir / "ground_truth.json"

    if not payments_path.exists():
        raise FileNotFoundError(f"held-out eval payments not found at {payments_path}")
    if not ground_truth_path.exists():
        raise FileNotFoundError(f"held-out eval ground truth not found at {ground_truth_path}")

    payments = [_payment_from_dict(d) for d in json.loads(payments_path.read_text())]
    settlements = [_settlement_from_dict(d) for d in json.loads(settlements_path.read_text())]
    ground_truth = json.loads(ground_truth_path.read_text())

    return EvalDataset(name=name, payments=payments, settlements=settlements, ground_truth=ground_truth)
