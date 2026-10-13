"""Factory-scoped records, immutable command evidence and retained source artifacts."""
from sqlalchemy import CheckConstraint, Integer, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class IndonesiaMaterialRecord(Base):
    __tablename__ = 'indonesia_material_records'
    __table_args__ = (
        UniqueConstraint('factory_id', 'kind', 'business_key'),
        CheckConstraint("kind IN ('material','product','order','supply','allocation','shipment','import')"),
        CheckConstraint('version > 0'),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    business_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(String(40))


class IndonesiaMaterialCommand(Base):
    __tablename__ = 'indonesia_material_commands'
    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    changes: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class IndonesiaMaterialAsset(Base):
    __tablename__ = 'indonesia_material_assets'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(240))
    media_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(String(40))
