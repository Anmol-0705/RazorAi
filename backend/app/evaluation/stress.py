"""Deterministic noise injection for the Stress / Dirty Data
evaluation benchmark (Part B).

Perturbs a *copy* of the committed held-out dataset in memory — the
files on disk under `data/eval/n250/` are never touched or
regenerated (`app.evaluation.loader` still reads them unmodified).

Noise is only ever applied to the **settlement side** (reference
string, settled amount, settled timestamp) — `Payment.transaction_id`
and every other payment field are left byte-identical to the clean
baseline. This is a deliberate scoring-integrity boundary, not an
oversight: `app.evaluation.scoring.score()` aligns ground truth to the
run's output via `payment.transaction_id` /
`ExceptionCaseORM.payment_reference`, both payment-side identifiers.
Perturbing them would silently break that alignment and make the
resulting metrics meaningless rather than "stressed." Real-world data
quality issues of the kind being simulated here (truncated bank
references, delayed settlement feeds, rounding drift) also
overwhelmingly originate on the settlement/bank-statement side of a
reconciliation pipeline, not on the merchant's own transaction record
— so this boundary matches the real failure mode it's modeling, not
just a scoring convenience.

Every noise type is applied independently per settlement via a single
`random.Random(seed)` stream consumed in a fixed, sorted iteration
order (`sorted(settlements, key=lambda s: s.settlement_id)`), so the
exact same seed always reproduces byte-identical noisy output —
required for the "reproducible" half of "reproducible noisy/stress
evaluation benchmark."
"""
from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal

from app.evaluation.loader import EvalDataset


@dataclass(frozen=True)
class NoiseConfig:
    seed: int = 9001

    # Small, usually-harmless clock skew (bank feed timestamp jitter).
    timestamp_offset_rate: float = 0.15
    timestamp_offset_minutes: int = 45

    # A larger shift that deliberately pushes settled_at past
    # ReconciliationConfig.delayed_settlement_threshold (72h by
    # default), simulating a genuinely late settlement feed.
    delayed_timestamp_rate: float = 0.08
    delayed_timestamp_extra_hours: int = 30

    # Small settled_amount drift (paise-level rounding noise from a
    # bank statement re-export).
    rounding_diff_rate: float = 0.10
    rounding_diff_max: Decimal = Decimal("0.05")

    # Reference-string corruption: trailing truncation, a stripped
    # leading prefix (e.g. "TXN-"), case changes, and stray whitespace
    # — all realistic symptoms of a bank feed that doesn't preserve a
    # merchant reference verbatim.
    reference_truncation_rate: float = 0.06
    missing_prefix_rate: float = 0.06
    case_whitespace_rate: float = 0.10

    # Reassigns a settlement's reference to a *different* payment's
    # transaction_id, simulating a misaligned/duplicated bank record.
    duplicate_misalignment_rate: float = 0.04


def _truncate(ref: str, rng: random.Random) -> str:
    if len(ref) <= 4:
        return ref
    return ref[:-3]


def _strip_prefix(ref: str) -> str:
    if "-" in ref:
        return ref.split("-", 1)[1]
    return ref


def _case_whitespace(ref: str, rng: random.Random) -> str:
    if rng.random() < 0.5:
        return f"  {ref.lower()}  "
    return ref.upper()


def apply_noise(dataset: EvalDataset, config: NoiseConfig | None = None) -> tuple[EvalDataset, list[dict]]:
    """Returns (noisy_dataset, noise_log). `noise_log` is one entry per
    settlement listing which noise types were applied — used to report
    an honest, inspectable noise summary alongside the metrics, never
    just an unverifiable claim of "noise was added."
    """
    config = config or NoiseConfig()
    rng = random.Random(config.seed)

    settlements = sorted(dataset.settlements, key=lambda s: s.settlement_id)
    txn_ids = sorted({p.transaction_id for p in dataset.payments})

    noisy_settlements = []
    noise_log = []

    for settlement in settlements:
        s = settlement
        applied: list[str] = []

        if rng.random() < config.timestamp_offset_rate:
            delta_minutes = rng.randint(-config.timestamp_offset_minutes, config.timestamp_offset_minutes)
            s = replace(s, settled_at=s.settled_at + timedelta(minutes=delta_minutes))
            applied.append("timestamp_offset")

        if rng.random() < config.delayed_timestamp_rate:
            s = replace(s, settled_at=s.settled_at + timedelta(hours=config.delayed_timestamp_extra_hours))
            applied.append("delayed_settlement_timestamp")

        if rng.random() < config.rounding_diff_rate:
            magnitude = float(config.rounding_diff_max)
            noise = Decimal(str(round(rng.uniform(-magnitude, magnitude), 2)))
            new_amount = s.settled_amount + noise
            if new_amount > 0:
                s = replace(s, settled_amount=new_amount)
                applied.append("rounding_diff")

        ref = s.transaction_reference
        if rng.random() < config.reference_truncation_rate:
            new_ref = _truncate(ref, rng)
            if new_ref != ref:
                ref = new_ref
                applied.append("reference_truncation")
        if rng.random() < config.missing_prefix_rate:
            new_ref = _strip_prefix(ref)
            if new_ref != ref:
                ref = new_ref
                applied.append("missing_reference_prefix")
        if rng.random() < config.case_whitespace_rate:
            ref = _case_whitespace(ref, rng)
            applied.append("case_whitespace")
        if ref != s.transaction_reference:
            s = replace(s, transaction_reference=ref)

        if rng.random() < config.duplicate_misalignment_rate and txn_ids:
            wrong_ref = rng.choice(txn_ids)
            s = replace(s, transaction_reference=wrong_ref)
            applied.append("duplicate_misaligned_reference")

        noisy_settlements.append(s)
        noise_log.append({"settlement_id": settlement.settlement_id, "noise_applied": applied})

    noisy_dataset = EvalDataset(
        name=f"{dataset.name}-stress",
        payments=dataset.payments,
        settlements=noisy_settlements,
        ground_truth=dataset.ground_truth,
    )
    return noisy_dataset, noise_log


def summarize_noise(noise_log: list[dict]) -> dict:
    counts: dict[str, int] = {}
    affected = 0
    for entry in noise_log:
        if entry["noise_applied"]:
            affected += 1
        for noise_type in entry["noise_applied"]:
            counts[noise_type] = counts.get(noise_type, 0) + 1
    return {
        "total_settlements": len(noise_log),
        "affected_settlements": affected,
        "noise_type_counts": counts,
    }
