"""Shared payable corrections; original delivery and inventory costs stay immutable."""
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CartonPriceReview(Base):
    __tablename__ = "carton_price_reviews"
    __table_args__ = (
        ForeignKeyConstraint(["receipt_line_id", "factory_id"], ["carton_receipt_lines.id", "carton_receipt_lines.factory_id"]),
        ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]),
        CheckConstraint("status IN ('PENDING','PROPOSED','CONFIRMED') AND revision >= 1", name="ck_carton_price_review_status"),
        CheckConstraint("source_kind IN ('REGULAR','SPECIAL') AND (status = 'PENDING' OR proposed_unit_price IS NOT NULL)", name="ck_carton_price_review_source"),
        CheckConstraint("original_unit_price >= 0 AND proposed_unit_price >= 0", name="ck_carton_price_review_price"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96), index=True)
    receipt_line_id: Mapped[str] = mapped_column(String(96), unique=True)
    source_kind: Mapped[str] = mapped_column(String(16))
    shipment_id: Mapped[str] = mapped_column(String(96), index=True)
    shipment_line_id: Mapped[str] = mapped_column(String(96))
    original_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    proposed_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64))
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(40))
