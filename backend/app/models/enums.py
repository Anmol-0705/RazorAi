"""Shared domain enums for the finance data model.

Values are stable strings so they serialize cleanly to JSON now and to
a Postgres ENUM / SQLAlchemy Enum column later without translation.
"""
from enum import Enum


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"


class PaymentMethod(str, Enum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    EMI = "emi"


class PaymentStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class SettlementStatus(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    REVERSED = "reversed"


class MatchStatus(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    PARTIAL = "partial"
    DUPLICATE = "duplicate"
    PENDING_REVIEW = "pending_review"


class MatchStrategy(str, Enum):
    EXACT_REFERENCE = "exact_reference"
    REFERENCE_AMOUNT = "reference_amount"
    TIMESTAMP_TOLERANCE = "timestamp_tolerance"
    AMOUNT_DATE_HEURISTIC = "amount_date_heuristic"
    MANUAL = "manual"
    AI_ASSISTED = "ai_assisted"


class ExceptionType(str, Enum):
    MISSING_SETTLEMENT = "missing_settlement"
    DUPLICATE_SETTLEMENT = "duplicate_settlement"
    AMOUNT_MISMATCH = "amount_mismatch"
    PARTIAL_SETTLEMENT = "partial_settlement"
    FEE_MISMATCH = "fee_mismatch"
    DELAYED_SETTLEMENT = "delayed_settlement"
    INVALID_REFERENCE = "invalid_reference"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_RESOLVED = "auto_resolved"


class RecommendedAction(str, Enum):
    AUTO_RESOLVE = "auto_resolve"
    ESCALATE = "escalate"
    IGNORE = "ignore"
    REQUEST_INFO = "request_info"


class ResolutionType(str, Enum):
    FEE_ADJUSTMENT_ACCEPTED = "fee_adjustment_accepted"
    DELAY_ACCEPTED = "delay_accepted"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
