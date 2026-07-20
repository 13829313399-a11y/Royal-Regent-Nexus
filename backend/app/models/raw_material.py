from sqlalchemy import CheckConstraint, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RawMaterial(Base):
    __tablename__ = "raw_materials"
    __table_args__ = (
        CheckConstraint("factory_id = '*'", name="ck_raw_materials_global_factory"),
        UniqueConstraint("material_code", name="uq_raw_materials_material_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    material_code: Mapped[str] = mapped_column(String(128), index=True)
    material_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(128), default="")
    spec: Mapped[str] = mapped_column(String(255), default="")
    unit: Mapped[str] = mapped_column(String(64), default="KG")
    supplier: Mapped[str] = mapped_column(String(255), default="")
    safety_stock_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="启用", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")
