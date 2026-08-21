"""Ground-truth condition labels used ONLY by the synthetic generator
and evaluation tooling. Deliberately kept separate from
app.models.enums.ExceptionType so the future reconciliation engine's
inferred output can never accidentally read/import the answer key.
"""
from enum import Enum


class GroundTruthCondition(str, Enum):
    NORMAL_MATCH = "normal_match"
    MISSING_SETTLEMENT = "missing_settlement"
    DUPLICATE_SETTLEMENT = "duplicate_settlement"
    AMOUNT_MISMATCH = "amount_mismatch"
    PARTIAL_SETTLEMENT = "partial_settlement"
    FEE_MISMATCH = "fee_mismatch"
    DELAYED_SETTLEMENT = "delayed_settlement"
    INVALID_REFERENCE = "invalid_reference"
