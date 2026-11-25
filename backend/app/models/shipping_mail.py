"""Shipping mail batches, parsed mail items and the shipping tasks they create."""
from sqlalchemy import Float, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ShippingMailBatch(Base):
    __tablename__ = 'shipping_mail_batches'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(24))
    filename: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24))
    total_count: Mapped[int] = mapped_column(Integer)
    parsed_count: Mapped[int] = mapped_column(Integer)
    failed_count: Mapped[int] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class ShippingMailItem(Base):
    __tablename__ = 'shipping_mail_items'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(500))
    sender: Mapped[str] = mapped_column(String(500))
    received_at: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24))
    fields_json: Mapped[str] = mapped_column(Text)
    items_json: Mapped[str] = mapped_column(Text)
    warnings_json: Mapped[str] = mapped_column(Text)
    trace_json: Mapped[str] = mapped_column(Text)
    task_ids_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ShippingTask(Base):
    __tablename__ = 'shipping_tasks'
    __table_args__ = (UniqueConstraint('mail_item_id', 'source_group_key', name='uq_shipping_task_source'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mail_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_group_key: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(24))
    so_number: Mapped[str] = mapped_column(String(64), index=True)
    customer: Mapped[str] = mapped_column(String(200))
    container_type: Mapped[str] = mapped_column(String(64))
    port: Mapped[str] = mapped_column(String(64))
    destination_country: Mapped[str] = mapped_column(String(64))
    shipment_mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), index=True)
    planned_ship_date: Mapped[str] = mapped_column(String(10))
    si_deadline: Mapped[str] = mapped_column(String(20))
    cutoff_date: Mapped[str] = mapped_column(String(20))
    items_json: Mapped[str] = mapped_column(Text)
    warnings_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ShippingMailAccount(Base):
    """Per-factory IMAP mailbox used by the weekly automatic collector."""
    __tablename__ = 'shipping_mail_accounts'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=993)
    username: Mapped[str] = mapped_column(String(255))
    password_enc: Mapped[str] = mapped_column(Text)
    use_ssl: Mapped[bool] = mapped_column(default=True)
    folder: Mapped[str] = mapped_column(String(120), default='INBOX')
    enabled: Mapped[bool] = mapped_column(default=True)
    last_uid: Mapped[str] = mapped_column(String(32), default='')
    last_sync_at: Mapped[str] = mapped_column(String(40), default='')
    last_status: Mapped[str] = mapped_column(String(24), default='idle')
    last_error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ShippingMailSyncRun(Base):
    __tablename__ = 'shipping_mail_sync_runs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default='')
    started_at: Mapped[str] = mapped_column(String(40))
    finished_at: Mapped[str] = mapped_column(String(40), default='')


class ShippingLoadingSheet(Base):
    """Generated DK container loading sheet (W-series) with daily sequence."""
    __tablename__ = 'shipping_loading_sheets'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    number: Mapped[str] = mapped_column(String(16))
    sheet_date: Mapped[str] = mapped_column(String(10), index=True)
    task_id: Mapped[str] = mapped_column(String(64), default='')
    header_json: Mapped[str] = mapped_column(Text)
    lines_json: Mapped[str] = mapped_column(Text)
    totals_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class ShippingProductHistory(Base):
    """Per-customer 货号 history (类别 / 每箱毛重 / 每箱净重) imported from 柜单 workbooks."""
    __tablename__ = 'shipping_product_history'
    __table_args__ = (UniqueConstraint('factory_id', 'customer', 'product_code', name='uq_shipping_product_history'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer: Mapped[str] = mapped_column(String(64), index=True)
    product_code: Mapped[str] = mapped_column(String(120))
    product_name: Mapped[str] = mapped_column(String(300), default='')
    category: Mapped[str] = mapped_column(String(120), default='')
    gross_per_carton: Mapped[str] = mapped_column(String(32), default='')
    net_per_carton: Mapped[str] = mapped_column(String(32), default='')
    source: Mapped[str] = mapped_column(String(32), default='daily')
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ShippingCustomsDoc(Base):
    """附件：出货资料 / 通关一体化资料（柜装箱单等）。"""
    __tablename__ = 'shipping_customs_docs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mail_item_id: Mapped[str] = mapped_column(String(64), index=True, default='')
    subject: Mapped[str] = mapped_column(String(500), default='')
    port: Mapped[str] = mapped_column(String(120), default='')
    container_type: Mapped[str] = mapped_column(String(60), default='')
    si_cutoff: Mapped[str] = mapped_column(String(40), default='')
    special_note: Mapped[str] = mapped_column(String(300), default='')
    filename: Mapped[str] = mapped_column(String(500))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(String(40))
    read_at: Mapped[str] = mapped_column(String(40), default='')


class ShippingGeneratedDoc(Base):
    """Auto-generated shipping sheets (SO / truck / supplement) from a confirmed email task."""
    __tablename__ = 'shipping_generated_docs'
    __table_args__ = (UniqueConstraint('task_id', 'module', name='uq_shipping_generated_doc'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    header_json: Mapped[str] = mapped_column(Text)
    lines_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(64), default='')


class ShippingPalletRecord(Base):
    """Manual pallet usage records retained across years per factory."""
    __tablename__ = 'shipping_pallet_records'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    ship_date: Mapped[str] = mapped_column(String(10), index=True)
    customer: Mapped[str] = mapped_column(String(120), index=True)
    container_no: Mapped[str] = mapped_column(String(120), default='')
    container_type: Mapped[str] = mapped_column(String(40), default='40HQ')
    so_no: Mapped[str] = mapped_column(String(80), default='')
    contract_no: Mapped[str] = mapped_column(String(120), default='')
    filing_codes: Mapped[str] = mapped_column(String(300), default='')
    spec: Mapped[str] = mapped_column(String(120), default='标准木卡板 (1200×1000)')
    cartons: Mapped[float] = mapped_column(Float, default=0.0)
    pallets: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=65.0)
    is_container: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(String(300), default='')
    created_by: Mapped[str] = mapped_column(String(64), default='')
    created_at: Mapped[str] = mapped_column(String(40), default='')
    updated_at: Mapped[str] = mapped_column(String(40), default='')


class ShippingPalletExclusion(Base):
    """Exclusions for synced loading sheets / generated docs removed from pallet stats."""
    __tablename__ = 'shipping_pallet_exclusions'
    __table_args__ = (UniqueConstraint('factory_id', 'source_kind', 'source_id', name='uq_shipping_pallet_exclusion'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    excluded_by: Mapped[str] = mapped_column(String(64), default='')
    excluded_at: Mapped[str] = mapped_column(String(40), default='')


class ShippingPalletOverride(Base):
    """Persistent overrides for pallet summary groups and synced detail rows."""
    __tablename__ = 'shipping_pallet_overrides'
    __table_args__ = (UniqueConstraint('factory_id', 'source_kind', 'source_id', name='uq_shipping_pallet_override'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    target_factory_id: Mapped[str] = mapped_column(String(64), default='', index=True)
    ship_date: Mapped[str] = mapped_column(String(10), default='')
    customer: Mapped[str] = mapped_column(String(120), default='')
    container_no: Mapped[str] = mapped_column(String(120), default='')
    container_type: Mapped[str] = mapped_column(String(40), default='')
    so_no: Mapped[str] = mapped_column(String(80), default='')
    contract_no: Mapped[str] = mapped_column(String(120), default='')
    filing_codes: Mapped[str] = mapped_column(String(300), default='')
    spec: Mapped[str] = mapped_column(String(120), default='')
    cartons: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    pallets: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    estimated_cost_override: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    container_count_override: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_container: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    remark: Mapped[str] = mapped_column(String(300), default='')
    updated_by: Mapped[str] = mapped_column(String(64), default='')
    updated_at: Mapped[str] = mapped_column(String(40), default='')
