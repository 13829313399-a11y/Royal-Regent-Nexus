"""Location subledger. Quantity/cost ownership stays on the original inventory ledger."""
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CartonLocation(Base):
    __tablename__ = "carton_locations"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_location_factory"),
        UniqueConstraint("factory_id", "warehouse", "bin_code", name="uq_carton_location_name"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    warehouse: Mapped[str] = mapped_column(String(64))
    bin_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class CartonPositionEntry(Base):
    __tablename__ = "carton_position_entries"
    __table_args__ = (
        ForeignKeyConstraint(["location_id", "factory_id"], ["carton_locations.id", "carton_locations.factory_id"]),
        ForeignKeyConstraint(["movement_id", "factory_id"], ["carton_inventory_movements.id", "carton_inventory_movements.factory_id"]),
        UniqueConstraint("movement_id", "location_id", name="uq_carton_movement_position"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    inventory_key: Mapped[str] = mapped_column(String(1024))
    location_id: Mapped[str] = mapped_column(String(96))
    movement_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    transfer_id: Mapped[str] = mapped_column(String(96), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    occurred_at: Mapped[str] = mapped_column(String(40))
