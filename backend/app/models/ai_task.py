from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

TASK_STATES = (
    "CREATED",
    "UNDERSTOOD",
    "PLANNED",
    "RUNNING",
    "WAITING_INPUT",
    "WAITING_APPROVAL",
    "VERIFYING",
    "COMPLETED",
    "CANCELLING",
    "CANCELLED",
    "FAILED",
    "RETRY_PENDING",
)
TASK_TYPES = ("READ", "COMPUTE", "SIMULATE", "PREVIEW")
STEP_STATES = (
    "PENDING",
    "RUNNING",
    "WAITING_INPUT",
    "VERIFYING",
    "COMPLETED",
    "CANCELLED",
    "FAILED",
    "RETRY_PENDING",
)


class AITask(Base):
    __tablename__ = "ai_tasks"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('READ', 'COMPUTE', 'SIMULATE', 'PREVIEW')",
            name="ck_ai_task_type",
        ),
        CheckConstraint(
            "state IN ('CREATED', 'UNDERSTOOD', 'PLANNED', 'RUNNING', "
            "'WAITING_INPUT', 'WAITING_APPROVAL', 'VERIFYING', 'COMPLETED', "
            "'CANCELLING', 'CANCELLED', 'FAILED', 'RETRY_PENDING')",
            name="ck_ai_task_state",
        ),
        CheckConstraint(
            "maximum_risk IN ('READ_ONLY', 'PREVIEW_WITH_AUDIT')",
            name="ck_ai_task_maximum_risk",
        ),
        CheckConstraint("revision >= 1", name="ck_ai_task_revision"),
        CheckConstraint("claim_count >= 0", name="ck_ai_task_claim_count"),
        CheckConstraint(
            "next_event_sequence >= 1", name="ck_ai_task_next_event_sequence"
        ),
        CheckConstraint("step_count >= 1 AND step_count <= 6", name="ck_ai_task_steps"),
        Index(
            "uq_ai_task_owner_idempotency",
            "owner_user_id",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "ix_ai_task_owner_updated",
            "owner_user_id",
            "updated_at",
            "id",
        ),
        Index(
            "ix_ai_task_factory_state",
            "factory_scope",
            "state",
            "updated_at",
        ),
        Index(
            "ix_ai_task_retention",
            "state",
            "retention_expires_at",
        ),
        Index(
            "ix_ai_task_worker_claim",
            "state",
            "next_attempt_at",
            "lease_expires_at",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    input_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    factory_scope: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(16), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    maximum_risk: Mapped[str] = mapped_column(String(32))
    primary_skill_id: Mapped[str] = mapped_column(String(160), index=True)
    primary_skill_version: Mapped[str] = mapped_column(String(32))
    primary_skill_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    runtime_plan_json: Mapped[str] = mapped_column(Text)
    runtime_plan_hash: Mapped[str] = mapped_column(String(64), index=True)
    server_page_context_json: Mapped[str] = mapped_column(Text, default="null")
    tool_versions_json: Mapped[str] = mapped_column(Text, default="{}")
    required_access_json: Mapped[str] = mapped_column(Text, default="[]")
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    next_event_sequence: Mapped[int] = mapped_column(Integer, default=1)
    step_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)
    terminal_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    retention_expires_at: Mapped[str] = mapped_column(
        String(32), default="", index=True
    )
    backup_delete_by: Mapped[str] = mapped_column(String(32), default="")
    cancellation_requested_at: Mapped[str] = mapped_column(String(32), default="")
    resume_requested_at: Mapped[str] = mapped_column(String(32), default="")
    failure_code: Mapped[str] = mapped_column(String(96), default="")
    lease_owner_instance: Mapped[str] = mapped_column(String(128), default="")
    lease_token: Mapped[str] = mapped_column(String(64), default="")
    lease_expires_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    last_heartbeat_at: Mapped[str] = mapped_column(String(32), default="")
    next_attempt_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    claim_count: Mapped[int] = mapped_column(Integer, default=0)


class AITaskStep(Base):
    __tablename__ = "ai_task_steps"
    __table_args__ = (
        CheckConstraint(
            "ordinal >= 1 AND ordinal <= 6", name="ck_ai_task_step_ordinal"
        ),
        CheckConstraint(
            "kind IN ('READ', 'COMPUTE', 'SIMULATE', 'PREVIEW')",
            name="ck_ai_task_step_kind",
        ),
        CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'WAITING_INPUT', 'VERIFYING', "
            "'COMPLETED', 'CANCELLED', 'FAILED', 'RETRY_PENDING')",
            name="ck_ai_task_step_state",
        ),
        CheckConstraint(
            "side_effect_class IN ('NONE', 'PREVIEW_STATE')",
            name="ck_ai_task_step_side_effect",
        ),
        CheckConstraint("idempotent IN (0, 1)", name="ck_ai_task_step_idempotent"),
        CheckConstraint("revision >= 1", name="ck_ai_task_step_revision"),
        CheckConstraint("attempt_count >= 0", name="ck_ai_task_step_attempt_count"),
        CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 3",
            name="ck_ai_task_step_max_attempts",
        ),
        Index(
            "uq_ai_task_step_ordinal",
            "task_id",
            "ordinal",
            unique=True,
        ),
        Index(
            "uq_ai_task_step_key",
            "task_id",
            "step_key",
            unique=True,
        ),
        Index("ix_ai_task_step_task_state", "task_id", "state", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ai_tasks.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    step_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(32), index=True)
    tool_name: Mapped[str] = mapped_column(String(160), default="")
    tool_version: Mapped[str] = mapped_column(String(32), default="")
    arguments_json: Mapped[str] = mapped_column(Text, default="{}")
    arguments_hash: Mapped[str] = mapped_column(String(64), default="")
    side_effect_class: Mapped[str] = mapped_column(String(32), default="NONE")
    idempotent: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_attempt_id: Mapped[str] = mapped_column(String(64), default="")
    last_attempt_started_at: Mapped[str] = mapped_column(String(32), default="")
    last_attempt_finished_at: Mapped[str] = mapped_column(String(32), default="")
    result_hash: Mapped[str] = mapped_column(String(71), default="")
    result_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str] = mapped_column(String(32), default="")
    completed_at: Mapped[str] = mapped_column(String(32), default="")
    failure_code: Mapped[str] = mapped_column(String(96), default="")


class AITaskEvent(Base):
    __tablename__ = "ai_task_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_ai_task_event_sequence"),
        CheckConstraint(
            "event_type IN ('TASK_CREATED', 'STATE_TRANSITION', "
            "'STEP_STATE_TRANSITION', 'CANCEL_REQUESTED', 'RESUME_REQUESTED', "
            "'LEASE_CLAIMED', 'LEASE_RELEASED', 'RETRY_SCHEDULED')",
            name="ck_ai_task_event_type",
        ),
        CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM')",
            name="ck_ai_task_event_actor_type",
        ),
        Index(
            "uq_ai_task_event_sequence",
            "task_id",
            "sequence",
            unique=True,
        ),
        Index("ix_ai_task_event_task_created", "task_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ai_tasks.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_task_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[str] = mapped_column(String(64), default="")
    transition_from: Mapped[str] = mapped_column(String(32), default="")
    transition_to: Mapped[str] = mapped_column(String(32), default="")
    reason_code: Mapped[str] = mapped_column(String(96), default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
