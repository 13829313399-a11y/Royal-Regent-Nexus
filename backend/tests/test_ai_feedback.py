from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from app.core.config import Settings
from app.db import Base
from app.models.ai_observability import AIFeedback, AIMetricEvent
from app.models.auth import AuthUser
from app.schemas.ai.feedback import AIFeedbackCreate, AIFeedbackReview
from app.services.ai.feedback import (
    FeedbackError,
    create_feedback,
    feedback_data,
    review_feedback,
)
from app.services.ai.observability.metrics import (
    AIObservabilityEvent,
    record_metric_event,
)
from app.services.auth import AuthContext, AuthGrantContext
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _user(user_id: str) -> AuthContext:
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name=user_id,
        roles=("测试",),
        role_codes=("test",),
        permissions=frozenset(),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
    )


def _session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(
        engine,
        tables=[AuthUser.__table__, AIMetricEvent.__table__, AIFeedback.__table__],
    )
    db = Session(engine)
    db.add_all(
        [
            AuthUser(
                id=user_id,
                username=user_id,
                display_name=user_id,
                password_salt="salt",
                password_hash="hash",
                status="active",
            )
            for user_id in ("feedback-user", "other-user", "admin-user")
        ]
    )
    db.commit()
    return db


def _payload(**updates: object) -> AIFeedbackCreate:
    value: dict[str, object] = {
        "factory_id": "huaxing",
        "target_type": "RESPONSE",
        "target_id": "request-feedback-0001",
        "rating": "NOT_HELPFUL",
        "issue_category": "WRONG_ARGUMENTS",
        "comment": "日期范围使用错误",
        "idempotency_key": "feedback-request-0001",
    }
    value.update(updates)
    return AIFeedbackCreate.model_validate(value)


def _source_hashes() -> dict[str, str]:
    roots = [
        REPOSITORY_ROOT / "backend" / "app" / "services" / "ai" / "prompts",
        REPOSITORY_ROOT / "docs" / "ai" / "modules",
        REPOSITORY_ROOT / "docs" / "ai" / "knowledge-manifest.yaml",
    ]
    files = []
    for root in roots:
        files.extend(root.rglob("*") if root.is_dir() else [root])
    return {
        str(path.relative_to(REPOSITORY_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in files
        if path.is_file()
    }


def test_feedback_is_owned_idempotent_and_only_proposes_manual_eval_case() -> None:
    db = _session()
    try:
        record_metric_event(
            db,
            AIObservabilityEvent(
                request_id="request-feedback-0001",
                event_type="MODEL_RUN",
                event_key="terminal",
                owner_user_id="feedback-user",
                factory_id="huaxing",
                status="SUCCESS",
            ),
            settings=Settings(_env_file=None),
        )
        before = _source_hashes()
        created = create_feedback(db, payload=_payload(), user=_user("feedback-user"))
        replay = create_feedback(db, payload=_payload(), user=_user("feedback-user"))

        assert replay.id == created.id
        assert feedback_data(created).auto_applied_to_prompt_or_knowledge is False
        reviewed = review_feedback(
            db,
            feedback_id=created.id,
            payload=AIFeedbackReview(
                status="EVAL_CANDIDATE",
                review_note="已复核，人工加入下一版离线数据集",
                eval_suite_id="business_current_page_v1",
                eval_case_id="wrong_date_range_candidate",
            ),
            reviewer=_user("admin-user"),
        )

        assert reviewed.status == "EVAL_CANDIDATE"
        assert reviewed.eval_suite_id == "business_current_page_v1"
        assert reviewed.eval_case_id == "wrong_date_range_candidate"
        assert _source_hashes() == before
    finally:
        db.close()


def test_feedback_rejects_cross_owner_factory_and_conflicting_replay() -> None:
    db = _session()
    try:
        record_metric_event(
            db,
            AIObservabilityEvent(
                request_id="request-feedback-0001",
                event_type="MODEL_RUN",
                event_key="terminal",
                owner_user_id="feedback-user",
                factory_id="huaxing",
                status="SUCCESS",
            ),
            settings=Settings(_env_file=None),
        )
        with pytest.raises(FeedbackError) as owner_error:
            create_feedback(db, payload=_payload(), user=_user("other-user"))
        assert owner_error.value.code == "AI_FEEDBACK_TARGET_NOT_FOUND"

        with pytest.raises(FeedbackError) as factory_error:
            create_feedback(
                db,
                payload=_payload(factory_id="other-factory"),
                user=_user("feedback-user"),
            )
        assert factory_error.value.code == "AI_FEEDBACK_FACTORY_MISMATCH"

        create_feedback(db, payload=_payload(), user=_user("feedback-user"))
        with pytest.raises(FeedbackError) as replay_error:
            create_feedback(
                db,
                payload=_payload(comment="不同内容"),
                user=_user("feedback-user"),
            )
        assert replay_error.value.code == "AI_FEEDBACK_REQUEST_CONFLICT"
    finally:
        db.close()


def test_feedback_schema_requires_meaningful_not_helpful_category() -> None:
    with pytest.raises(ValidationError):
        _payload(issue_category="NONE")
    with pytest.raises(ValidationError):
        _payload(rating="HELPFUL", issue_category="WRONG_TOOL")


def test_metric_export_is_default_off_and_wildcard_admin_only(monkeypatch) -> None:
    from app.api import ai_feedback as api

    admin = AuthContext(
        **{
            **_user("admin-user").__dict__,
            "grants": (
                AuthGrantContext(
                    role_id="admin",
                    role_name="系统管理员",
                    role_code="admin",
                    factory_id="*",
                    department="system",
                    permissions=frozenset(),
                ),
            ),
        }
    )
    monkeypatch.setattr(api.settings, "ai_metric_export_enabled", False)
    with pytest.raises(HTTPException) as disabled:
        api._require_admin_export(admin)
    assert disabled.value.status_code == 404

    monkeypatch.setattr(api.settings, "ai_metric_export_enabled", True)
    with pytest.raises(HTTPException) as denied:
        api._require_admin_export(_user("feedback-user"))
    assert denied.value.status_code == 403
    assert api._require_admin_export(admin) is None
