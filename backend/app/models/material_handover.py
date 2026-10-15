"""Material handover drafts and immutable original files/audit evidence."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, LargeBinary, String, Text, UniqueConstraint, DDL, event, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class HandoverIssuer(Base):
    __tablename__ = 'material_handover_issuers'
    __table_args__ = (UniqueConstraint('id', 'factory_id'), CheckConstraint("factory_id = 'huakang-c'"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[str] = mapped_column(String(40))
    active: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(96))
    created_at: Mapped[str] = mapped_column(String(40))


class HandoverDocument(Base):
    __tablename__ = 'material_handover_documents'
    __table_args__ = (UniqueConstraint('id', 'factory_id'),
        ForeignKeyConstraint(['issuer_id', 'factory_id'], ['material_handover_issuers.id', 'material_handover_issuers.factory_id']),
        CheckConstraint("factory_id = 'huakang-c'"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED','VOID')"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    issuer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    owner_key: Mapped[str] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    code_version: Mapped[int] = mapped_column(Integer, default=0)
    data_json: Mapped[str] = mapped_column(Text)
    extraction_json: Mapped[str] = mapped_column(Text)
    confirmed_by: Mapped[str] = mapped_column(String(96), default='')
    confirmed_at: Mapped[str] = mapped_column(String(40), default='')
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class HandoverSource(Base):
    __tablename__ = 'material_handover_sources'
    __table_args__ = (ForeignKeyConstraint(['document_id', 'factory_id'], ['material_handover_documents.id', 'material_handover_documents.factory_id']),)
    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(96))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class HandoverEvent(Base):
    __tablename__ = 'material_handover_events'
    __table_args__ = (ForeignKeyConstraint(['document_id', 'factory_id'], ['material_handover_documents.id', 'material_handover_documents.factory_id']),
        UniqueConstraint('factory_id', 'actor_key', 'request_id'), UniqueConstraint('document_id', 'revision'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    actor_key: Mapped[str] = mapped_column(String(96))
    actor_name: Mapped[str] = mapped_column(String(255))
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    detail_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[str] = mapped_column(String(40))


class HandoverSupplierBinding(Base):
    __tablename__ = 'material_handover_supplier_bindings'
    __table_args__ = (
        ForeignKeyConstraint(['issuer_id', 'factory_id'], ['material_handover_issuers.id', 'material_handover_issuers.factory_id']),
        ForeignKeyConstraint(['supplier_id', 'factory_id'], ['fabric_master_records.id', 'fabric_master_records.factory_id']),
        CheckConstraint("factory_id = 'huakang-c'"),)
    issuer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_snapshot_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(96))
    created_at: Mapped[str] = mapped_column(String(40))


class HandoverLinkCommand(Base):
    __tablename__ = 'material_handover_link_commands'
    __table_args__ = (UniqueConstraint('factory_id', 'actor_key', 'request_id'),
        ForeignKeyConstraint(['issuer_id', 'factory_id'], ['material_handover_issuers.id', 'material_handover_issuers.factory_id']),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    issuer_id: Mapped[str] = mapped_column(String(64))
    actor_key: Mapped[str] = mapped_column(String(96))
    actor_name: Mapped[str] = mapped_column(String(255))
    request_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    detail_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[str] = mapped_column(String(40))


def install_immutable_guards(connection, names=('material_handover_sources', 'material_handover_events')):
    for name in names:
        if connection.dialect.name == 'sqlite':
            for action in ('update', 'delete'):
                connection.execute(text(f"CREATE TRIGGER {name}_no_{action} BEFORE {action.upper()} ON {name} BEGIN SELECT RAISE(ABORT, 'handover evidence is immutable'); END"))
        elif connection.dialect.name == 'postgresql':
            connection.execute(text("CREATE OR REPLACE FUNCTION material_handover_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'handover evidence is immutable'; END; $$ LANGUAGE plpgsql"))
            connection.execute(text(f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION material_handover_immutable()"))


for _table in (HandoverSource.__table__, HandoverEvent.__table__, HandoverSupplierBinding.__table__, HandoverLinkCommand.__table__):
    event.listen(_table, 'after_create', DDL("CREATE OR REPLACE FUNCTION material_handover_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'handover evidence is immutable'; END; $$ LANGUAGE plpgsql").execute_if(dialect='postgresql'))
    event.listen(_table, 'after_create', DDL(f"CREATE TRIGGER {_table.name}_immutable BEFORE UPDATE OR DELETE ON {_table.name} FOR EACH ROW EXECUTE FUNCTION material_handover_immutable()").execute_if(dialect='postgresql'))
    for _action in ('update', 'delete'):
        event.listen(_table, 'after_create', DDL(f"CREATE TRIGGER {_table.name}_no_{_action} BEFORE {_action.upper()} ON {_table.name} BEGIN SELECT RAISE(ABORT, 'handover evidence is immutable'); END").execute_if(dialect='sqlite'))
