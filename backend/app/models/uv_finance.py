"""UV append-only stock/cost facts and immutable settlement snapshots."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def now():
    return datetime.now(UTC).isoformat()


class Record:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    factory_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
    created_by: Mapped[str] = mapped_column(String(64))


class UvInkSku(Record, Base):
    __tablename__ = 'uv_ink_skus'
    supplier: Mapped[str] = mapped_column(String(128))
    material: Mapped[str] = mapped_column(String(16))
    color: Mapped[str] = mapped_column(String(64))
    color_aliases: Mapped[list] = mapped_column(JSON, default=list)
    package_ml: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    location: Mapped[str] = mapped_column(String(128), default='UV仓')
    threshold_ml: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    available_ml: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    stock_value: Mapped[Decimal | None] = mapped_column(Numeric(26, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('factory_id', 'supplier', 'material', 'color', 'location'),
                      CheckConstraint('available_ml >= 0 AND package_ml > 0 AND threshold_ml >= 0'))


class UvInkMovement(Record, Base):
    __tablename__ = 'uv_ink_movements'
    sku_id: Mapped[str] = mapped_column(ForeignKey('uv_ink_skus.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    occurred_on: Mapped[str] = mapped_column(String(10), index=True)
    posted_on: Mapped[str] = mapped_column(String(10), index=True)
    quantity_ml: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    signed_ml: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    bottle_input: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(26, 8), nullable=True)
    cost_value: Mapped[Decimal | None] = mapped_column(Numeric(26, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    machine_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(Text, default='')
    source_doc: Mapped[str] = mapped_column(String(255), default='')
    evidence: Mapped[str] = mapped_column(Text, default='')
    source_movement_id: Mapped[str | None] = mapped_column(ForeignKey('uv_ink_movements.id'), nullable=True)
    reverses_movement_id: Mapped[str | None] = mapped_column(ForeignKey('uv_ink_movements.id'), nullable=True, unique=True)
    reversed_by_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balance_after_ml: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    __table_args__ = (CheckConstraint('quantity_ml > 0 AND balance_after_ml >= 0'),)


class UvExpense(Record, Base):
    __tablename__ = 'uv_expenses'
    category: Mapped[str] = mapped_column(String(32))
    occurred_on: Mapped[str] = mapped_column(String(10), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(22, 6))
    currency: Mapped[str] = mapped_column(String(3))
    machine_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default='manual')
    note: Mapped[str] = mapped_column(Text, default='')
    reverses_expense_id: Mapped[str | None] = mapped_column(ForeignKey('uv_expenses.id'), nullable=True, unique=True)


class UvMonthlyPolicy(Record, Base):
    __tablename__ = 'uv_monthly_policies'
    month: Mapped[str] = mapped_column(String(7), index=True)
    working_days: Mapped[list] = mapped_column(JSON)
    allocation_method: Mapped[str] = mapped_column(String(20))
    rent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    utilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    management_wage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (UniqueConstraint('factory_id', 'month', 'version'),)


class UvPolicyAllocation(Record, Base):
    __tablename__ = 'uv_policy_allocations'
    policy_id: Mapped[str] = mapped_column(ForeignKey('uv_monthly_policies.id'), index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    category: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(22, 6))
    __table_args__ = (UniqueConstraint('policy_id', 'business_date', 'category'),)


class UvPricingQuote(Record, Base):
    __tablename__ = 'uv_pricing_quotes'
    label: Mapped[str] = mapped_column(String(128))
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    adopted_rate_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str] = mapped_column(Text, default='')


class UvPeriod(Record, Base):
    __tablename__ = 'uv_periods'
    period: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), default='closed')
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('factory_id', 'period'),)


class UvPayrollBatch(Record, Base):
    __tablename__ = 'uv_payroll_batches'
    date_from: Mapped[str] = mapped_column(String(10), index=True)
    date_to: Mapped[str] = mapped_column(String(10), index=True)
    shift: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default='draft')
    snapshot: Mapped[dict] = mapped_column(JSON)
    source_versions: Mapped[list] = mapped_column(JSON)
    adjustment_of: Mapped[str | None] = mapped_column(ForeignKey('uv_payroll_batches.id'), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default='')


class UvPayrollBatchLine(Record, Base):
    __tablename__ = 'uv_payroll_batch_lines'
    batch_id: Mapped[str] = mapped_column(ForeignKey('uv_payroll_batches.id'), index=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    worker_name: Mapped[str] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(22, 6))
    __table_args__ = (UniqueConstraint('batch_id', 'worker_id'),)


class UvImportBatch(Record, Base):
    __tablename__ = 'uv_import_batches'
    kind: Mapped[str] = mapped_column(String(32))
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='previewed')
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    rows: Mapped[list] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON)
    applied_ids: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint('factory_id', 'kind', 'sha256'),)
