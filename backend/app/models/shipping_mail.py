"""Shipping mail batches, parsed mail items and the shipping tasks they create."""
from sqlalchemy import Integer, LargeBinary, String, Text, UniqueConstraint
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
