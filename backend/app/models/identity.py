"""Identity history is append-only in meaning; current state is resolved by time."""
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class IamOrgUnit(Base):
    __tablename__ = "iam_org_units"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("iam_org_units.id"), nullable=True)
    legacy_factory_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class IamOrgDepartment(Base):
    __tablename__ = "iam_org_departments"
    org_unit_id: Mapped[str] = mapped_column(ForeignKey("iam_org_units.id"), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class IamRoleVersion(Base):
    __tablename__ = "iam_role_versions"
    __table_args__ = (UniqueConstraint("role_id", "definition_hash", name="uq_iam_role_definition"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("auth_roles.id"), index=True)
    definition_hash: Mapped[str] = mapped_column(String(64))
    definition_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(64), default="")


class EmployeeAssignment(Base):
    __tablename__ = "employee_assignments"
    __table_args__ = (
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="ck_assignment_interval"),
        CheckConstraint("assignment_type IN ('regular','part_time','temporary','acting')", name="ck_assignment_type"),
        CheckConstraint("lifecycle_state IN ('approved','revoked')", name="ck_assignment_state"),
        Index("ix_assignment_user_interval", "user_id", "valid_from", "valid_until"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    org_unit_id: Mapped[str] = mapped_column(ForeignKey("iam_org_units.id"), index=True)
    department_code: Mapped[str] = mapped_column(String(64))
    official_position_title: Mapped[str] = mapped_column(String(128))
    assignment_type: Mapped[str] = mapped_column(String(16), default="regular")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[str] = mapped_column(String(32))
    valid_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(16), default="approved")
    employment_epoch: Mapped[int] = mapped_column(Integer, default=1)
    source_request_id: Mapped[str | None] = mapped_column(ForeignKey("auth_access_requests.id"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(64))
    confirmed_by: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    ended_reason: Mapped[str] = mapped_column(Text, default="")
    revoked_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class IamDelegation(Base):
    __tablename__ = "iam_delegations"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), index=True)
    org_unit_id: Mapped[str] = mapped_column(ForeignKey("iam_org_units.id"))
    department: Mapped[str] = mapped_column(String(64))
    role_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    factory_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class IamHandoverItem(Base):
    __tablename__ = "iam_handover_items"
    __table_args__ = (UniqueConstraint("change_request_id", "adapter_key", "resource_id", "responsibility_kind", name="uq_iam_handover_responsibility"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    change_request_id: Mapped[str] = mapped_column(ForeignKey("auth_access_requests.id"), index=True)
    adapter_key: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(96))
    responsibility_kind: Mapped[str] = mapped_column(String(64))
    factory_id: Mapped[str] = mapped_column(String(64))
    previous_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    successor_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"), nullable=True)
    expected_resource_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    completed_at: Mapped[str] = mapped_column(String(32), default="")


class IamOutbox(Base):
    __tablename__ = "iam_outbox"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[str] = mapped_column(String(32), default="")
    claimed_until: Mapped[str] = mapped_column(String(32), default="")
    last_error: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32))


class IamMutationReceipt(Base):
    __tablename__ = "iam_mutation_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "operation", "idempotency_key", name="uq_iam_mutation_idempotency"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    operation: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
