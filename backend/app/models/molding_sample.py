from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MoldingSampleOrder(Base):
    __tablename__ = "molding_sample_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_number: Mapped[str] = mapped_column(String(128), default="")
    doc_number: Mapped[str] = mapped_column(String(128), default="")
    product_name: Mapped[str] = mapped_column(String(255))
    client_name: Mapped[str] = mapped_column(String(255), default="")
    date: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(20), default="")
    order_type: Mapped[str] = mapped_column(String(20), default="啤办")
    workshop: Mapped[str] = mapped_column(String(64), default="A车间")
    send_to: Mapped[str] = mapped_column(String(64), default="")
    supervisor: Mapped[str] = mapped_column(String(128), default="")
    eng_name: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="待审核", index=True)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    completed_date: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")

    items: Mapped[list["MoldingSampleItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="MoldingSampleItem.sort_order",
    )
    audit_logs: Mapped[list["MoldingSampleAuditLog"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="desc(MoldingSampleAuditLog.id)",
    )
    requisitions: Mapped[list["MoldingSampleRequisition"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="MoldingSampleRequisition.req_number",
    )


class MoldingSampleItem(Base):
    __tablename__ = "molding_sample_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("molding_sample_orders.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    mold_id: Mapped[str] = mapped_column(String(128), default="")
    mold_name: Mapped[str] = mapped_column(String(255), default="")
    machine_type: Mapped[str] = mapped_column(String(64), default="")
    material: Mapped[str] = mapped_column(String(255), default="")
    color: Mapped[str] = mapped_column(String(255), default="")
    pigment_no: Mapped[str] = mapped_column(String(128), default="")
    quantity: Mapped[str] = mapped_column(String(64), default="")
    shoot_qty: Mapped[int] = mapped_column(Integer, default=0)
    gross_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_material_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    mold_return_time: Mapped[str] = mapped_column(String(32), default="")
    completion_time: Mapped[str] = mapped_column(String(32), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    receipt_no: Mapped[str] = mapped_column(String(128), default="")
    collected_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_amount_hkd: Mapped[float | None] = mapped_column(Float, nullable=True)
    injection_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    injection_cost_hkd: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_rate_at_save: Mapped[float | None] = mapped_column(Float, nullable=True)

    order: Mapped[MoldingSampleOrder] = relationship(back_populates="items")


class MoldingSampleAuditLog(Base):
    __tablename__ = "molding_sample_audit_logs"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("molding_sample_orders.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(128))
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    actor_role: Mapped[str] = mapped_column(String(64), default="")
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")

    order: Mapped[MoldingSampleOrder] = relationship(back_populates="audit_logs")


class MoldingSampleMaterialPrice(Base):
    __tablename__ = "molding_sample_material_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    unit_price: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")


class MoldingSampleSetting(Base):
    __tablename__ = "molding_sample_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")


class MoldingSampleAuthPin(Base):
    __tablename__ = "molding_sample_auth_pins"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(64), index=True)
    pin_salt: Mapped[str] = mapped_column(String(64))
    pin_hash: Mapped[str] = mapped_column(String(128))
    must_change: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class MoldingSampleRequisition(Base):
    __tablename__ = "molding_sample_requisitions"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    req_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    date: Mapped[str] = mapped_column(String(20), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("molding_sample_orders.id", ondelete="CASCADE"), index=True)
    order_number: Mapped[str] = mapped_column(String(128), default="")
    material: Mapped[str] = mapped_column(String(255), default="")
    requested_weight_kg: Mapped[float] = mapped_column(Float)
    applicant: Mapped[str] = mapped_column(String(128), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    inventory_batch_id: Mapped[str] = mapped_column(String(96), default="")
    inventory_batch_no: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="待出库", index=True)
    issued_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")

    order: Mapped[MoldingSampleOrder] = relationship(back_populates="requisitions")


class MoldingSampleInventoryBatch(Base):
    __tablename__ = "molding_sample_inventory_batches"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    material: Mapped[str] = mapped_column(String(255), index=True)
    batch_no: Mapped[str] = mapped_column(String(128), index=True)
    location: Mapped[str] = mapped_column(String(128), default="")
    initial_weight_kg: Mapped[float] = mapped_column(Float)
    available_weight_kg: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")
