from sqlalchemy import Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CustomerPriceSettings(Base):
    __tablename__ = "customer_price_settings"

    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)


class CustomerPriceSettingsSnapshot(Base):
    __tablename__ = "customer_price_settings_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)


@event.listens_for(CustomerPriceSettingsSnapshot, "before_update")
@event.listens_for(CustomerPriceSettingsSnapshot, "before_delete")
def _immutable_snapshot(*_args):
    raise ValueError("Customer pricing settings snapshots are immutable")
