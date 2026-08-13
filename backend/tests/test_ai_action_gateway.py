from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.models.ai_action import AIActionConfirmation
from app.schemas.ai.action_confirmation import (
    AIActionApproveRequest,
    AIActionExecuteRequest,
    AIActionVerificationData,
)
from app.services.ai import controlled_apply
from app.services.ai.action_confirmation import create_action_confirmation
from app.services.ai.action_registry import AIActionRegistry
from app.services.ai.actions.contracts import (
    ActionApprovalPolicy,
    ActionHandlerManifest,
    ActionVerificationError,
)
from app.services.ai.actions.gateway import (
    approve_proposal,
    execute_proposal,
    get_proposal,
    reject_proposal,
)
from app.services.ai.actions.policy import validate_approval_source
from fastapi import HTTPException
from sqlalchemy import select
from test_ai_action_confirmation import _action, _database, _handler, _user


def _gateway_handler(state: dict[str, object], *, verifier_fails: bool = False):
    legacy = _handler(state)

    def execute(db, value, request_id, reason, user):
        record = db.scalar(select(AIActionConfirmation))
        assert record is not None
        assert record.lifecycle_status == "COMMITTING"
        return legacy.executor(db, value, request_id, reason, user)

    def verify(db, value, result):
        record = db.scalar(select(AIActionConfirmation))
        assert record is not None
        assert record.lifecycle_status == "VERIFYING"
        state["verifications"] = int(state.get("verifications", 0)) + 1
        if verifier_fails:
            raise ActionVerificationError("formal DRAFT read-back mismatch")
        return AIActionVerificationData(
            factory_id=value.factory_id,
            entity_id=result.plan_id,
            entity_revision=result.plan_revision,
            run_id=result.run_id,
            domain_audit_id=f"injection_scheduling_audit_events:{result.audit_sequence}",
            verified_at="2026-08-13T09:00:00+08:00",
        )

    return replace(
        legacy,
        executor=execute,
        post_verifier=verify,
        manifest=ActionHandlerManifest(
            action_type="APPLY_INJECTION_AUTO_SCHEDULE_RUN",
            handler_version="1.0.0",
            autonomy_level="L3",
            target_state="DRAFT",
            model_may_propose=True,
            model_may_approve=False,
            model_may_execute=False,
            publish_allowed=False,
            rollback_allowed=False,
        ),
        approval_policy=ActionApprovalPolicy(
            policy_id="single-explicit-owner-approval",
            policy_version="1.0.0",
            approvals_required=1,
            approver_must_be_proposer=True,
            allowed_source="AUTHENTICATED_USER_API",
        ),
    )


def _create_gateway_record(db, handler):
    return create_action_confirmation(
        db,
        handler=handler,
        normalized_action=_action(),
        user=_user(),
        request_id="request-action-gateway-1",
    )


def test_action_gateway_uses_one_record_and_closed_human_lifecycle() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _gateway_handler(state)
        registry = AIActionRegistry((handler,))
        record = _create_gateway_record(db, handler)

        proposed = get_proposal(
            db,
            proposal_id=record.id,
            factory_id="huaxing",
            user=_user(),
            registry=registry,
        )
        assert proposed.proposal_id == proposed.compatibility_confirmation_id
        assert proposed.lifecycle_status == "WAITING_APPROVAL"
        assert proposed.legacy_status == "PENDING"
        assert proposed.manifest.model_may_propose is True
        assert proposed.manifest.model_may_approve is False
        assert proposed.manifest.model_may_execute is False
        assert proposed.manifest.target_state == "DRAFT"
        assert proposed.manifest.publish_allowed is False
        assert "normalized_action" not in proposed.model_dump_json()

        approval = AIActionApproveRequest(
            factory_id="huaxing",
            expected_args_hash=record.args_hash,
            approval_request_id="web-approval-gateway-1",
        )
        approved = approve_proposal(
            db,
            proposal_id=record.id,
            payload=approval,
            user=_user(),
            registry=registry,
        )
        replay = approve_proposal(
            db,
            proposal_id=record.id,
            payload=approval,
            user=_user(),
            registry=registry,
        )
        assert approved.lifecycle_status == replay.lifecycle_status == "APPROVED"
        assert approved.legacy_status == "CONFIRMED"
        assert approved.approval is not None
        assert approved.approval.args_hash == record.args_hash
        assert approved.approval.entity_revision == record.entity_revision

        with pytest.raises(HTTPException) as conflict:
            approve_proposal(
                db,
                proposal_id=record.id,
                payload=approval.model_copy(
                    update={"approval_request_id": "web-approval-gateway-2"}
                ),
                user=_user(),
                registry=registry,
            )
        assert conflict.value.detail["code"] == "APPROVAL_REQUEST_CONFLICT"

        executed = execute_proposal(
            db,
            proposal_id=record.id,
            payload=AIActionExecuteRequest(
                factory_id="huaxing",
                expected_args_hash=record.args_hash,
                execution_request_id="web-execute-gateway-1",
            ),
            user=_user(),
            registry=registry,
        )
        assert executed.proposal.lifecycle_status == "EXECUTED"
        assert executed.proposal.legacy_status == "EXECUTED"
        assert executed.proposal.verification is not None
        assert executed.proposal.verification.entity_status == "DRAFT"
        assert executed.proposal.verification.domain_audit_id.startswith(
            "injection_scheduling_audit_events:"
        )
        assert executed.proposal.compensation.automatic_compensation_available is False
        assert state == {
            "validated": True,
            "executions": 1,
            "execution_request_id": "web-execute-gateway-1",
            "verifications": 1,
        }
        stored = db.get(AIActionConfirmation, record.id)
        assert stored is not None
        assert stored.approval_user_id == _user().id
        assert stored.execution_user_id == _user().id
        assert stored.commit_started_at
        assert stored.verification_started_at
        assert stored.verified_at
        assert stored.domain_audit_id
    finally:
        db.close()


def test_rejected_proposal_is_terminal_and_never_executes() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _gateway_handler(state)
        registry = AIActionRegistry((handler,))
        record = _create_gateway_record(db, handler)
        rejected = reject_proposal(
            db,
            proposal_id=record.id,
            factory_id="huaxing",
            expected_args_hash=record.args_hash,
            rejection_reason="用户不接受当前影响范围",
            user=_user(),
            registry=registry,
        )
        assert rejected.lifecycle_status == "REJECTED"
        assert rejected.legacy_status == "CANCELLED"
        with pytest.raises(HTTPException) as exc_info:
            execute_proposal(
                db,
                proposal_id=record.id,
                payload=AIActionExecuteRequest(
                    factory_id="huaxing",
                    expected_args_hash=record.args_hash,
                    execution_request_id="web-rejected-execute-1",
                ),
                user=_user(),
                registry=registry,
            )
        assert exc_info.value.detail["code"] == "CONFIRMATION_STATE_INVALID"
        assert state.get("executions", 0) == 0
    finally:
        db.close()


def test_post_verification_failure_is_terminal_and_not_replayed() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _gateway_handler(state, verifier_fails=True)
        registry = AIActionRegistry((handler,))
        record = _create_gateway_record(db, handler)
        approve_proposal(
            db,
            proposal_id=record.id,
            payload=AIActionApproveRequest(
                factory_id="huaxing",
                expected_args_hash=record.args_hash,
                approval_request_id="web-approval-failed-verify-1",
            ),
            user=_user(),
            registry=registry,
        )
        payload = AIActionExecuteRequest(
            factory_id="huaxing",
            expected_args_hash=record.args_hash,
            execution_request_id="web-execute-failed-verify-1",
        )
        with pytest.raises(HTTPException) as exc_info:
            execute_proposal(
                db,
                proposal_id=record.id,
                payload=payload,
                user=_user(),
                registry=registry,
            )
        assert exc_info.value.detail["code"] == "ACTION_POST_VERIFICATION_FAILED"
        stored = db.get(AIActionConfirmation, record.id)
        assert stored is not None
        assert stored.lifecycle_status == "FAILED"
        assert stored.failure_code == "ACTION_POST_VERIFICATION_FAILED"
        assert state["executions"] == 1
        with pytest.raises(HTTPException):
            execute_proposal(
                db,
                proposal_id=record.id,
                payload=payload,
                user=_user(),
                registry=registry,
            )
        assert state["executions"] == 1
    finally:
        db.close()


def test_executor_failure_is_terminal_and_preserves_no_verification_claim() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _gateway_handler(state)

        def fail_execute(*_args, **_kwargs):
            state["executions"] = int(state.get("executions", 0)) + 1
            raise RuntimeError("domain transaction failed")

        handler = replace(handler, executor=fail_execute)
        registry = AIActionRegistry((handler,))
        record = _create_gateway_record(db, handler)
        approve_proposal(
            db,
            proposal_id=record.id,
            payload=AIActionApproveRequest(
                factory_id="huaxing",
                expected_args_hash=record.args_hash,
                approval_request_id="web-approval-transaction-failure-1",
            ),
            user=_user(),
            registry=registry,
        )
        with pytest.raises(RuntimeError, match="domain transaction failed"):
            execute_proposal(
                db,
                proposal_id=record.id,
                payload=AIActionExecuteRequest(
                    factory_id="huaxing",
                    expected_args_hash=record.args_hash,
                    execution_request_id="web-execute-transaction-failure-1",
                ),
                user=_user(),
                registry=registry,
            )
        stored = db.get(AIActionConfirmation, record.id)
        assert stored is not None
        assert stored.lifecycle_status == "FAILED"
        assert stored.failure_code == "ACTION_EXECUTION_FAILED"
        assert stored.verification_result_json == "{}"
        assert state["executions"] == 1
    finally:
        db.close()


def test_permission_is_rechecked_after_approval_before_execution() -> None:
    db = _database()
    try:
        state: dict[str, object] = {}
        handler = _gateway_handler(state)
        registry = AIActionRegistry((handler,))
        record = _create_gateway_record(db, handler)
        approve_proposal(
            db,
            proposal_id=record.id,
            payload=AIActionApproveRequest(
                factory_id="huaxing",
                expected_args_hash=record.args_hash,
                approval_request_id="web-approval-before-revoke-1",
            ),
            user=_user(),
            registry=registry,
        )

        with pytest.raises(HTTPException) as exc_info:
            execute_proposal(
                db,
                proposal_id=record.id,
                payload=AIActionExecuteRequest(
                    factory_id="huaxing",
                    expected_args_hash=record.args_hash,
                    execution_request_id="web-execute-after-revoke-1",
                ),
                user=_user(deny_edit=True),
                registry=registry,
            )
        assert exc_info.value.detail["code"] == "ACTION_PERMISSION_DENIED"
        assert state.get("executions", 0) == 0
        stored = db.get(AIActionConfirmation, record.id)
        assert stored is not None
        assert stored.lifecycle_status == "APPROVED"
        assert stored.execution_request_id == ""
    finally:
        db.close()


def test_published_plan_can_never_become_an_action_proposal(monkeypatch) -> None:
    monkeypatch.setattr(
        controlled_apply,
        "_run",
        lambda *_args: SimpleNamespace(
            id="run-published",
            status="SUCCEEDED",
            plan_id="plan-published",
            expected_plan_revision=2,
            rule_revision=3,
            revision=1,
        ),
    )
    monkeypatch.setattr(
        controlled_apply,
        "_plan",
        lambda *_args: SimpleNamespace(
            id="plan-published",
            status="PUBLISHED",
            revision=2,
            rule_revision=3,
        ),
    )
    monkeypatch.setattr(
        controlled_apply,
        "current_rule_set",
        lambda *_args: SimpleNamespace(revision=3),
    )

    with pytest.raises(HTTPException) as exc_info:
        controlled_apply.canonical_apply_action(
            None,
            "huaxing",
            "run-published",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "候选方案不能覆盖已发布计划"


def test_missing_formal_readback_fails_post_verification(monkeypatch) -> None:
    def missing_run(*_args):
        raise HTTPException(status_code=404, detail="候选排产方案不存在")

    monkeypatch.setattr(controlled_apply, "_run", missing_run)
    with pytest.raises(ActionVerificationError, match="正式 DRAFT 或 Run 回读不存在"):
        controlled_apply.verify_apply_action(
            None,
            _action(),
            _handler({}).executor(
                None,
                _action(),
                "readback-failure-execution-1",
                "",
                _user(),
            ),
        )


def test_worker_or_model_cannot_approve_or_execute_action_handler() -> None:
    handler = _gateway_handler({})
    with pytest.raises(ValueError, match="approval source"):
        validate_approval_source(
            handler.approval_policy,
            approval_source="WORKER",
            proposer_user_id="owner",
            approver_user_id="owner",
        )
    assert handler.manifest.model_may_propose is True
    assert handler.manifest.model_may_approve is False
    assert handler.manifest.model_may_execute is False


def test_action_gateway_defaults_off_independently(monkeypatch) -> None:
    monkeypatch.delenv("AI_ACTION_GATEWAY_ENABLED", raising=False)
    monkeypatch.delenv("AI_CONTROLLED_APPLY_ENABLED", raising=False)
    settings = Settings(_env_file=None)
    assert settings.ai_action_gateway_enabled is False
    assert settings.ai_controlled_apply_enabled is False
