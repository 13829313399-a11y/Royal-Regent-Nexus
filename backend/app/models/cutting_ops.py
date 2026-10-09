"""Versioned cutting master data. No stock, orders or financial postings."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CuttingMaster(Base):
    __tablename__ = "cutting_ops_masters"
    __table_args__ = (
        UniqueConstraint("factory_id", "kind", "code"),
        CheckConstraint("factory_id = 'huakang-c'"),
        CheckConstraint("kind IN ('material', 'resource', 'bom')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)


class CuttingRevision(Base):
    __tablename__ = "cutting_ops_revisions"
    __table_args__ = (ForeignKeyConstraint(["master_id"], ["cutting_ops_masters.id"]),)
    master_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))


class CuttingCommand(Base):
    """Atomic operation receipt and append-only audit evidence."""
    __tablename__ = "cutting_ops_commands"
    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(120))
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class CuttingOrder(Base):
    __tablename__ = 'cutting_ops_orders'
    __table_args__ = (
        ForeignKeyConstraint(['line_id'], ['order_ledger_lines.id']),
        ForeignKeyConstraint(['dispatch_id'], ['order_ledger_dispatches.id']),
        CheckConstraint("factory_id = 'huakang-c'"),
    )
    line_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32))
    dispatch_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)


class CuttingOrderRevision(Base):
    __tablename__ = 'cutting_ops_order_revisions'
    __table_args__ = (ForeignKeyConstraint(['line_id'], ['cutting_ops_orders.line_id']),)
    line_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
