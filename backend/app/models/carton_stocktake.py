from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CartonStocktake(Base):
    __tablename__ = "carton_stocktakes"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_stocktake_factory"),
        CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'POSTED', 'CANCELLED')", name="ck_carton_stocktake_status"),
        CheckConstraint("revision >= 1", name="ck_carton_stocktake_revision"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    submitted_by: Mapped[str] = mapped_column(String(64), default="")
    submitted_by_name: Mapped[str] = mapped_column(String(128), default="")
    submitted_at: Mapped[str] = mapped_column(String(40), default="")
    reviewed_by: Mapped[str] = mapped_column(String(64), default="")
    reviewed_by_name: Mapped[str] = mapped_column(String(128), default="")
    reviewed_at: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    basis_token: Mapped[str] = mapped_column(String(64), default="")


class CartonStocktakeLine(Base):
    __tablename__ = "carton_stocktake_lines"
    __table_args__ = (
        ForeignKeyConstraint(["stocktake_id", "factory_id"], ["carton_stocktakes.id", "carton_stocktakes.factory_id"]),
        UniqueConstraint("stocktake_id", "inventory_key", name="uq_carton_stocktake_line_key"),
        CheckConstraint("actual_quantity IS NULL OR actual_quantity >= 0", name="ck_carton_stocktake_actual"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    stocktake_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    inventory_key: Mapped[str] = mapped_column(String(1024))
    reference_movement_id: Mapped[str] = mapped_column(String(96))
    snapshot_json: Mapped[str] = mapped_column(Text)
    initial_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    count_book_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    actual_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    location_revision: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    movement_id: Mapped[str] = mapped_column(String(96), default="")
