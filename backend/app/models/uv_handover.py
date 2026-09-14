"""UV handover comparison snapshots. These records do not move warehouse stock."""
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.uv_printing import Record


class UvHandover(Record, Base):
    __tablename__ = "uv_handovers"
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("uv_products.id"), index=True)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("uv_reports.id"), nullable=True)
    product_no: Mapped[str] = mapped_column(String(128))
    product_name: Mapped[str] = mapped_column(String(255))
    reported_qty: Mapped[int] = mapped_column(Integer)
    received_qty: Mapped[int] = mapped_column(Integer)
    difference_qty: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16))
    receiver: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("factory_id", "report_id", name="uq_uv_handover_report"),
        CheckConstraint("factory_id = 'huakang-a'", name="ck_uv_handover_factory"),
        CheckConstraint("reported_qty >= 0 AND received_qty >= 0", name="ck_uv_handover_quantities"),
        CheckConstraint("difference_qty = received_qty - reported_qty", name="ck_uv_handover_difference"),
        CheckConstraint("state IN ('pending', 'reconciled', 'difference')", name="ck_uv_handover_state"),
    )
