import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.db import Base
from app.models.ai_action import AIActionConfirmation
from app.models.auth import AuthUser
from app.schemas.ai.action_confirmation import (
    AIActionExecuteRequest,
    AIControlledApplyResult,
    AIInjectionSchedulingApplyActionSummary,
    AIInjectionSchedulingApplyCanonicalAction,
)
from app.services.ai.action_confirmation import (
    cancel_action,
    confirm_action,
    create_action_confirmation,
    execute_action,
)
from app.services.ai.action_registry import (
    ActionConfirmationStaleError,
    AIActionHandler,
    AIActionRegistry,
)
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
)


def _user(
    user_id: str = "user-confirmation-owner",
    *,
    deny_edit: bool = False,
) -> AuthContext:
    grant = AuthGrantContext(
        role_id="role-confirmation",
        role_name="确认测试",
        factory_id="huaxing",
        department="production",
        permissions=frozenset({"injection_scheduling:edit"}),
        binding_id=f"binding-{user_id}",
    )
    overrides = (
        AuthOverrideContext(
            id=f"deny-{user_id}",
            permission_code="injection_scheduling:edit",
            effect="deny",
            factory_id="huaxing",
            department="production",
        ),
    ) if deny_edit else ()
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name="确认测试用户",
        roles=("确认测试",),
        role_codes=("confirmation-test",),
        permissions=frozenset({"injection_scheduling:edit"}),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(grant,),
        overrides=overrides,
        active_permission_codes=frozenset({"injection_scheduling:edit"}),
    )


def _database() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[AuthUser.__table__, AIActionConfirmation.__table__],
    )
    db = Session(engine)
    db.add(
        AuthUser(
            id="user-confirmation-owner",
            username="confirmation-owner",
            display_name="确认所有者",
            password_salt="salt",
            password_hash="hash",
            status="active",
            force_password_change=0,
            avatar_png=None,
            avatar_version="",
            last_login_at="",
            created_at="2026-08-12T08:00:00+08:00",
            updated_at="2026-08-12T08:00:00+08:00",
        )
    )
    db.commit()
    return db


def _action() -> AIInjectionSchedulingApplyCanonicalAction:
    return AIInjectionSchedulingApplyCanonicalAction(
        factory_id="huaxing",
        run_id="isrun-confirmation-1",
        run_revision=1,
        plan_id="plan-draft-1",
        expected_plan_revision=10,
        expected_rule_revision=3,
    )


def _handler(state: dict[str, object]) -> AIActionHandler:
    def summary(_db, value):
        assert isinstance(value, AIInjectionSchedulingApplyCanonicalAction)
        return AIInjectionSchedulingApplyActionSummary(
            run_id=value.run_id,
            plan_id=value.plan_id,
            plan_revision=value.expected_plan_revision,
            rule_revision=value.expected_rule_revision,
            assignment_count=2,
            review_required_count=0,
            requires_override_reason=False,
        )

    def fresh(_db, _confirmation, _value):
        if state.get("stale"):
            raise ActionConfirmationStaleError("revision 已变化")

    def validate(_db, _value, _reason, _user):
        state["validated"] = True

    def execute(_db, value, request_id, _reason, _user):
        assert isinstance(value, AIInjectionSchedulingApplyCanonicalAction)
        state["executions"] = int(state.get("executions", 0)) + 1
        state["execution_request_id"] = request_id
        return AIControlledApplyResult(
            run_id=value.run_id,
            run_status="APPLIED",
            plan_id=value.plan_id,
            plan_revision=value.expected_plan_revision + 1,
            plan_status="DRAFT",
            audit_sequence=1,
            idempotent_replay=False,
        )

    return AIActionHandler(
        tool_name="injection_scheduling.apply_preview_run",
        action_model=AIInjectionSchedulingApplyCanonicalAction,
        risk_level="CONSEQUENTIAL_WRITE",
        required_permission="injection_scheduling:edit",
        allowed_departments=frozenset({"production"}),
        factory_argument="factory_id",
        entity_type="auto_schedule_run",
        entity_id_argument="run_id",
        entity_revision_argument="run_revision",
        summary_builder=summary,
        freshness_validator=fresh,
        execution_validator=validate,
        executor=execute,
    )


def _create(db: Session, handler: AIActionHandler) -> AIActionConfirmation:
    return create_action_confirmation(
        db,
        handler=handler,
        normalized_action=_action(),
        user=_user(),
        request_id="request-confirmation-1",
    )


def test_confirmation_is_idempotent_minimal_and_cancellable() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _handler(state)
        first = _create(db, handler)
        replay = _create(db, handler)

        assert replay.id == first.id
        assert first.status == "PENDING"
        assert first.risk_level == "CONSEQUENTIAL_WRITE"
        assert json.loads(first.normalized_action_json) == _action().model_dump(
            mode="json"
        )
        assert "prompt" not in first.normalized_action_json.lower()
        assert len(first.args_hash) == 64
        cancelled = cancel_action(
            db,
            confirmation_id=first.id,
            factory_id="huaxing",
            expected_args_hash=first.args_hash,
            user=_user(),
        )
        assert cancelled.status == "CANCELLED"
        assert cancel_action(
            db,
            confirmation_id=first.id,
            factory_id="huaxing",
            expected_args_hash=first.args_hash,
            user=_user(),
        ).status == "CANCELLED"
    finally:
        db.close()


def test_confirmation_rejects_wrong_user_factory_hash_expiry_and_explicit_deny() -> None:
    db = _database()
    try:
        handler = _handler({})
        registry = AIActionRegistry((handler,))
        record = _create(db, handler)
        cases = (
            (_user("other-user"), "huaxing", record.args_hash, 403),
            (_user(), "huakang-a", record.args_hash, 403),
            (_user(), "huaxing", "0" * 64, 409),
            (_user(deny_edit=True), "huaxing", record.args_hash, 403),
        )
        for user, factory_id, args_hash, status_code in cases:
            with pytest.raises(HTTPException) as exc_info:
                confirm_action(
                    db,
                    confirmation_id=record.id,
                    factory_id=factory_id,
                    expected_args_hash=args_hash,
                    user=user,
                    registry=registry,
                )
            assert exc_info.value.status_code == status_code

        record.expires_at = (business_now() - timedelta(seconds=1)).isoformat(
            timespec="seconds"
        )
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            confirm_action(
                db,
                confirmation_id=record.id,
                factory_id="huaxing",
                expected_args_hash=record.args_hash,
                user=_user(),
                registry=registry,
            )
        assert exc_info.value.detail["code"] == "CONFIRMATION_EXPIRED"
        assert db.get(AIActionConfirmation, record.id).status == "EXPIRED"
    finally:
        db.close()


def test_stale_confirmation_is_terminal_before_execution() -> None:
    db = _database()
    try:
        state = {"stale": True}
        handler = _handler(state)
        registry = AIActionRegistry((handler,))
        record = _create(db, handler)
        with pytest.raises(HTTPException) as exc_info:
            confirm_action(
                db,
                confirmation_id=record.id,
                factory_id="huaxing",
                expected_args_hash=record.args_hash,
                user=_user(),
                registry=registry,
            )
        assert exc_info.value.detail["code"] == "STALE_CONFIRMATION"
        assert db.get(AIActionConfirmation, record.id).status == "STALE"
        assert state.get("executions", 0) == 0
    finally:
        db.close()


def test_confirmed_action_executes_once_and_replays_only_same_request() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _handler(state)
        registry = AIActionRegistry((handler,))
        record = _create(db, handler)
        confirmed = confirm_action(
            db,
            confirmation_id=record.id,
            factory_id="huaxing",
            expected_args_hash=record.args_hash,
            user=_user(),
            registry=registry,
        )
        assert confirmed.status == "CONFIRMED"
        payload = AIActionExecuteRequest(
            factory_id="huaxing",
            expected_args_hash=record.args_hash,
            execution_request_id="web-execute-confirmation-1",
        )
        first = execute_action(
            db,
            confirmation_id=record.id,
            payload=payload,
            user=_user(),
            registry=registry,
        )
        replay = execute_action(
            db,
            confirmation_id=record.id,
            payload=payload,
            user=_user(),
            registry=registry,
        )

        assert first.confirmation.status == "EXECUTED"
        assert first.result.outcome_label == "已应用到 DRAFT，尚未发布生产"
        assert replay.result.idempotent_replay is True
        assert state["executions"] == 1
        with pytest.raises(HTTPException) as exc_info:
            execute_action(
                db,
                confirmation_id=record.id,
                payload=payload.model_copy(
                    update={"execution_request_id": "web-execute-confirmation-2"}
                ),
                user=_user(),
                registry=registry,
            )
        assert exc_info.value.detail["code"] == "CONFIRMATION_ALREADY_EXECUTED"
        rows = db.scalars(select(AIActionConfirmation)).all()
        assert len(rows) == 1
    finally:
        db.close()
