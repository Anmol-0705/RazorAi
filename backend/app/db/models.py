"""SQLAlchemy ORM models — the persistence mirror of the Phase 1-3
domain dataclasses (`app.models.*`).

These are deliberately kept as a separate persistence layer rather than
converting the frozen domain dataclasses into ORM classes directly:
the reconciliation/auto-resolution/review engines stay pure-Python,
DB-agnostic, and fully unit-testable (per ARCHITECTURE.md), and this
module's job is only to store/load their inputs and outputs. Service
functions in `app.services` translate between the two.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PaymentORM(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    transaction_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    customer_reference: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SettlementORM(Base):
    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    settlement_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    transaction_reference: Mapped[str] = mapped_column(String, index=True, nullable=False)
    settled_amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    fee: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    settlement_status: Mapped[str] = mapped_column(String(20), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReconciliationRunORM(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list["ReconciliationResultORM"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    exceptions: Mapped[list["ExceptionCaseORM"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ReconciliationResultORM(Base):
    __tablename__ = "reconciliation_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("reconciliation_runs.id"), index=True, nullable=False
    )
    payment_reference: Mapped[str] = mapped_column(String, index=True, nullable=False)
    settlement_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    match_status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    match_strategy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    amount_difference: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[ReconciliationRunORM] = relationship(back_populates="results")


class ExceptionCaseORM(Base):
    __tablename__ = "exception_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("reconciliation_runs.id"), index=True, nullable=False
    )
    reconciliation_result_id: Mapped[str] = mapped_column(
        String, ForeignKey("reconciliation_results.id"), index=True, nullable=False
    )
    payment_reference: Mapped[str] = mapped_column(String, index=True, nullable=False)
    exception_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    financial_impact: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(20), nullable=False)
    auto_resolvable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    run: Mapped[ReconciliationRunORM] = relationship(back_populates="exceptions")
    auto_resolution_records: Mapped[list["AutoResolutionRecordORM"]] = relationship(
        back_populates="exception", cascade="all, delete-orphan"
    )
    review_audits: Mapped[list["ReviewAuditORM"]] = relationship(
        back_populates="exception", cascade="all, delete-orphan"
    )


class AutoResolutionRecordORM(Base):
    __tablename__ = "auto_resolution_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    exception_case_id: Mapped[str] = mapped_column(
        String, ForeignKey("exception_cases.id"), index=True, nullable=False
    )
    resolution_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    financial_impact: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    exception: Mapped[ExceptionCaseORM] = relationship(back_populates="auto_resolution_records")


class ReviewAuditORM(Base):
    __tablename__ = "review_audits"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    exception_case_id: Mapped[str] = mapped_column(
        String, ForeignKey("exception_cases.id"), index=True, nullable=False
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    exception: Mapped[ExceptionCaseORM] = relationship(back_populates="review_audits")
