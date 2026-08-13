from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIFeedback(Base):
    __tablename__ = "ai_feedback"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('RESPONSE', 'MESSAGE', 'TASK', 'ACTION')",
            name="ck_ai_feedback_target_type",
        ),
        CheckConstraint(
            "rating IN ('HELPFUL', 'NOT_HELPFUL')",
            name="ck_ai_feedback_rating",
        ),
        CheckConstraint(
            "issue_category IN ('NONE', 'INCORRECT', 'MISSING_CONTEXT', "
            "'WRONG_TOOL', 'WRONG_ARGUMENTS', 'UNSUPPORTED_CLAIM', "
            "'PERMISSION', 'PREVIEW_MISLABEL', 'UNSAFE', 'OTHER')",
            name="ck_ai_feedback_issue_category",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'TRIAGED', 'EVAL_CANDIDATE', 'DISMISSED')",
            name="ck_ai_feedback_status",
        ),
        Index(
            "uq_ai_feedback_owner_target",
            "owner_user_id",
            "target_type",
            "target_id",
            unique=True,
        ),
        Index(
            "uq_ai_feedback_owner_request",
            "owner_user_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_ai_feedback_status_created", "status", "created_at", "id"),
        Index("ix_ai_feedback_factory_created", "factory_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(16), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    rating: Mapped[str] = mapped_column(String(24), index=True)
    issue_category: Mapped[str] = mapped_column(String(32), default="NONE")
    comment_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="SUBMITTED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=True
    )
    review_note: Mapped[str] = mapped_column(Text, default="")
    eval_suite_id: Mapped[str] = mapped_column(String(128), default="")
    eval_case_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    reviewed_at: Mapped[str] = mapped_column(String(40), default="")


class AIMetricEvent(Base):
    __tablename__ = "ai_metric_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('MODEL_RUN', 'TOOL_CALL')",
            name="ck_ai_metric_event_type",
        ),
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILURE', 'DENIED', 'CANCELLED')",
            name="ck_ai_metric_status",
        ),
        CheckConstraint(
            "cost_basis IN ('UNAVAILABLE', 'CONFIGURED_ESTIMATE', 'PROVIDER_REPORTED')",
            name="ck_ai_metric_cost_basis",
        ),
        CheckConstraint(
            "duration_ms >= 0 AND input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= 0 AND estimated_cost_microusd >= 0 "
            "AND retry_count >= 0 AND evidence_count >= 0",
            name="ck_ai_metric_nonnegative",
        ),
        CheckConstraint(
            "truncated IN (0, 1) AND unauthorized_action IN (0, 1) "
            "AND cross_factory_leakage IN (0, 1) "
            "AND preview_executed_mislabel IN (0, 1)",
            name="ck_ai_metric_booleans",
        ),
        Index(
            "uq_ai_metric_event_key",
            "request_id",
            "event_type",
            "event_key",
            unique=True,
        ),
        Index("ix_ai_metric_created", "created_at", "id"),
        Index("ix_ai_metric_skill_created", "skill_id", "created_at", "id"),
        Index("ix_ai_metric_factory_created", "factory_id", "created_at", "id"),
        Index("ix_ai_metric_status_created", "status", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(16), index=True)
    event_key: Mapped[str] = mapped_column(String(160))
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), default="")
    task_id: Mapped[str] = mapped_column(String(64), default="")
    action_id: Mapped[str] = mapped_column(String(96), default="")
    skill_id: Mapped[str] = mapped_column(String(160), default="", index=True)
    skill_version: Mapped[str] = mapped_column(String(32), default="")
    skill_hash: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    tool_name: Mapped[str] = mapped_column(String(160), default="", index=True)
    tool_version: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    cost_basis: Mapped[str] = mapped_column(String(32), default="UNAVAILABLE")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(96), default="")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[int] = mapped_column(Integer, default=0)
    unauthorized_action: Mapped[int] = mapped_column(Integer, default=0)
    cross_factory_leakage: Mapped[int] = mapped_column(Integer, default=0)
    preview_executed_mislabel: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40), index=True)


class AIEvalRun(Base):
    __tablename__ = "ai_eval_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('OFFLINE_FAKE', 'LIVE_PROVIDER')",
            name="ck_ai_eval_run_mode",
        ),
        CheckConstraint(
            "status IN ('PASSED', 'FAILED', 'ERROR')",
            name="ck_ai_eval_run_status",
        ),
        CheckConstraint(
            "case_count >= 0 AND passed_count >= 0 AND failed_count >= 0",
            name="ck_ai_eval_run_counts",
        ),
        Index("ix_ai_eval_suite_created", "suite_id", "created_at", "id"),
        Index("ix_ai_eval_skill_created", "skill_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_id: Mapped[str] = mapped_column(String(128), index=True)
    dataset_version: Mapped[str] = mapped_column(String(32))
    dataset_hash: Mapped[str] = mapped_column(String(64), index=True)
    runner_version: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(24), index=True)
    skill_id: Mapped[str] = mapped_column(String(160), index=True)
    skill_version: Mapped[str] = mapped_column(String(32))
    skill_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64), default="fake")
    model: Mapped[str] = mapped_column(String(128), default="offline-fixture")
    status: Mapped[str] = mapped_column(String(16), index=True)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), default="ci")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    completed_at: Mapped[str] = mapped_column(String(40), default="")
