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
        order_by="desc(MoldingSampleAuditLog.created_at)",
    )
    notifications: Mapped[list["MoldingSampleNotification"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="desc(MoldingSampleNotification.created_at)",
    )
    requisitions: Mapped[list["MoldingSampleRequisition"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="MoldingSampleRequisition.req_number",
    )
    problems: Mapped[list["MoldingSampleProblem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="desc(MoldingSampleProblem.created_at)",
    )


class MoldingSampleItem(Base):
    __tablename__ = "molding_sample_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("molding_sample_orders.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    mold_id: Mapped[str] = mapped_column(String(128), default="")
    mold_name: Mapped[str] = mapped_column(String(255), default="")
    mold_dimensions: Mapped[str] = mapped_column(String(128), default="")
    mold_presence_status: Mapped[str] = mapped_column(String(20), default="unknown")
    machine_type: Mapped[str] = mapped_column(String(64), default="")
    production_machine: Mapped[str] = mapped_column(String(128), default="")
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
    actor_user_id: Mapped[str] = mapped_column(String(64), default="")
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    actor_role: Mapped[str] = mapped_column(String(64), default="")
    actor_roles: Mapped[str] = mapped_column(Text, default="")
    factory_scope: Mapped[str] = mapped_column(String(255), default="")
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")

    order: Mapped[MoldingSampleOrder] = relationship(back_populates="audit_logs")


class MoldingSampleNotification(Base):
    __tablename__ = "molding_sample_notifications"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("molding_sample_orders.id", ondelete="CASCADE"), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    target_module: Mapped[str] = mapped_column(String(96), index=True)
    target_role: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="未读", index=True)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    read_at: Mapped[str] = mapped_column(String(32), default="")
    handled_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")

    order: Mapped[MoldingSampleOrder] = relationship(back_populates="notifications")


class MoldingSampleProblem(Base):
    __tablename__ = "molding_sample_problems"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_type: Mapped[str] = mapped_column(String(32), default="injection", index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("molding_sample_orders.id", ondelete="CASCADE"), index=True)
    order_number: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    reported_by: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="待处理", index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    resolved_at: Mapped[str] = mapped_column(String(32), default="")

    order: Mapped[MoldingSampleOrder] = relationship(back_populates="problems")


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


class MoldingSampleSensitiveAuditLog(Base):
    __tablename__ = "molding_sample_sensitive_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), default="")
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    actor_role: Mapped[str] = mapped_column(String(64), default="")
    actor_roles: Mapped[str] = mapped_column(Text, default="")
    factory_scope: Mapped[str] = mapped_column(String(255), default="")
    target_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    target_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")


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


class MoldingSampleInventoryMovement(Base):
    __tablename__ = "molding_sample_inventory_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    batch_no: Mapped[str] = mapped_column(String(128), index=True)
    requisition_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    req_number: Mapped[str] = mapped_column(String(32), default="", index=True)
    material: Mapped[str] = mapped_column(String(255), index=True)
    movement_type: Mapped[str] = mapped_column(String(64), index=True)
    quantity_kg: Mapped[float] = mapped_column(Float)
    before_weight_kg: Mapped[float] = mapped_column(Float)
    after_weight_kg: Mapped[float] = mapped_column(Float)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
