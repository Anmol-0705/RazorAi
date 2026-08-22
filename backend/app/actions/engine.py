"""Bounded Finance Controller Action Engine.

Closes the finance-ops loop: reconciliation detects an exception,
auto-resolution (or a human) decides it is safe, and this module
executes exactly one small, allowlisted, synthetic downstream
finance-operation action for it — a bounded instruction recorded in
this application, never a call to a real banking/settlement system,
never real money movement.

Deterministic and pure, like `app.reconciliation.engine` and
`app.auto_resolution.engine`: no I/O, no FastAPI, and — critically —
no AI provider import anywhere in this module. The LLM is never in a
position to select or execute an action; only this fixed rule table
is. See ARCHITECTURE.md's "Bounded Finance Controller Action" section
and DECISIONS.md for the full safety-boundary writeup.

Eligibility reuses `app.auto_resolution.engine.policy_decision` — the
exact same exception-type/financial-impact bounds already proven out
by Phase 3's auto-resolution engine — rather than a second, possibly
drifting, set of thresholds. On top of that shared safety rule, this
engine adds one extra guard: an exception a human has explicitly
`REJECTED` is never eligible, regardless of type/impact, since acting
on it would override an explicit human decision.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.actions.config import ACTOR
from app.auto_resolution.config import AutoResolutionConfig
from app.auto_resolution.engine import policy_decision
from app.models.action_execution import ActionExecution
from app.models.enums import ActionStatus, ActionType, ResolutionType, ReviewStatus
from app.models.exception_case import ExceptionCase

_ID_NAMESPACE = uuid.UUID("ac710000-0000-4000-8000-000000000000")

# Every safe, bounded resolution the auto-resolution policy recognizes
# maps to exactly one allowlisted downstream action type. This is the
# entire set the Action Engine will ever produce — nothing else is
# reachable, and nothing here is selectable by request input or by the
# AI (see docs/deployment-independent safety notes in ARCHITECTURE.md).
_ACTION_TYPE_BY_RESOLUTION: dict[ResolutionType, ActionType] = {
    ResolutionType.FEE_ADJUSTMENT_ACCEPTED: ActionType.SETTLEMENT_ADJUSTMENT_INSTRUCTION,
    ResolutionType.DELAY_ACCEPTED: ActionType.SETTLEMENT_FOLLOWUP_INSTRUCTION,
    ResolutionType.DUPLICATE_SUPPRESSED: ActionType.DUPLICATE_SETTLEMENT_REVIEW_INSTRUCTION,
}

_REFERENCE_PREFIX = {
    ActionType.SETTLEMENT_ADJUSTMENT_INSTRUCTION: "SAI",
    ActionType.SETTLEMENT_FOLLOWUP_INSTRUCTION: "SFI",
    ActionType.DUPLICATE_SETTLEMENT_REVIEW_INSTRUCTION: "DRI",
}

# A human decision that must never be silently overridden by an
# automated action, even if the exception's type/impact would
# otherwise be within the bounded policy.
_BLOCKING_REVIEW_STATUSES = {ReviewStatus.REJECTED}


def _idempotency_key(exception_id: str, action_type: ActionType) -> str:
    """Deterministic per (exception, action_type) key — the same
    exception always produces the same key for the same action type,
    so retried/duplicate execute-action calls never create a second
    row (see `app.services.action_service`, which uses this as the
    row's primary key)."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{exception_id}:{action_type.value}"))


@dataclass
class ActionEligibility:
    eligible: bool
    action_type: Optional[ActionType]
    reason: str
    rule_id: str


def check_eligibility(
    exception: ExceptionCase, config: Optional[AutoResolutionConfig] = None
) -> ActionEligibility:
    """Pure eligibility check. No side effects, no persistence."""
    config = config or AutoResolutionConfig()

    if exception.review_status in _BLOCKING_REVIEW_STATUSES:
        return ActionEligibility(
            eligible=False,
            action_type=None,
            reason="a reviewer already rejected this exception; a controller action cannot override that decision",
            rule_id="action_policy:human_rejected",
        )

    decision = policy_decision(exception, config)
    if decision is None:
        return ActionEligibility(
            eligible=False,
            action_type=None,
            reason=(
                "this exception type or financial impact is outside the bounded "
                "auto-execution policy; it requires human review before any action is taken"
            ),
            rule_id="action_policy:not_eligible",
        )

    resolution_type, reason = decision
    action_type = _ACTION_TYPE_BY_RESOLUTION[resolution_type]
    return ActionEligibility(
        eligible=True,
        action_type=action_type,
        reason=reason,
        rule_id=f"action_policy:{resolution_type.value}",
    )


def execute_action(
    exception: ExceptionCase,
    config: Optional[AutoResolutionConfig] = None,
    now: Optional[datetime] = None,
) -> tuple[ActionEligibility, Optional[ActionExecution]]:
    """Decide + (if eligible) build the ActionExecution record for one
    exception. Never mutates `exception`. Returns
    `(eligibility, None)` for an ineligible exception — no record is
    fabricated for a rejected attempt. Persistence, idempotent
    replay-detection, exception-status update, and the audit entry are
    all the caller's job (`app.services.action_service`) — this
    function has no database access.
    """
    now = now or datetime.now(timezone.utc)
    eligibility = check_eligibility(exception, config)
    if not eligibility.eligible:
        return eligibility, None

    idempotency_key = _idempotency_key(exception.id, eligibility.action_type)
    prefix = _REFERENCE_PREFIX[eligibility.action_type]
    resulting_reference = f"SYN-{prefix}-{idempotency_key[:8].upper()}"

    record = ActionExecution(
        id=idempotency_key,
        exception_case_id=exception.id,
        action_type=eligibility.action_type,
        actor=ACTOR,
        reason=eligibility.reason,
        rule_id=eligibility.rule_id,
        status=ActionStatus.COMPLETED,
        idempotency_key=idempotency_key,
        created_at=now,
        completed_at=now,
        resulting_reference=resulting_reference,
    )
    return eligibility, record
