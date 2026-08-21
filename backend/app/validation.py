"""Small, dependency-free validation helpers.

Phase 1 uses these directly from dataclass __post_init__ methods. The
same rules are meant to become Pydantic validators once the backend
gains its FastAPI/Pydantic dependencies (see DECISIONS.md D006).
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum

ALLOWED_CURRENCIES = {"INR", "USD"}


class ValidationError(ValueError):
    """Raised when a generated or provided record fails domain validation."""


def require_non_empty_str(value, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")


def require_positive_amount(value, field_name: str) -> None:
    if not isinstance(value, Decimal) or value <= 0:
        raise ValidationError(f"{field_name} must be a positive decimal amount")


def require_non_negative_amount(value, field_name: str) -> None:
    if not isinstance(value, Decimal) or value < 0:
        raise ValidationError(f"{field_name} must be a non-negative decimal amount")


def require_valid_currency(value, field_name: str = "currency") -> None:
    code = value.value if isinstance(value, Enum) else value
    if code not in ALLOWED_CURRENCIES:
        raise ValidationError(f"{field_name} '{code}' is not a supported currency")


def require_valid_timestamp(value, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise ValidationError(f"{field_name} must be a datetime instance")


def require_valid_enum_member(value, enum_cls, field_name: str) -> None:
    if not isinstance(value, enum_cls):
        raise ValidationError(f"{field_name} must be a {enum_cls.__name__} member")
