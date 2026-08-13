from __future__ import annotations

from dataclasses import replace

import pytest
from app.schemas.ai.action_confirmation import AIActionApproveRequest
from app.services.ai.action_confirmation import (
    action_proposal_data,
    confirmation_data,
    create_action_confirmation,
)
from app.services.ai.action_registry import AIActionRegistry
from app.services.ai.actions.contracts import ActionHandlerManifest
from app.services.ai.actions.gateway import approve_proposal
from fastapi import HTTPException
from test_ai_action_confirmation import _action, _database, _handler, _user


def test_v1_confirmation_and_v2_proposal_are_the_same_persisted_record() -> None:
    db = _database()
    try:
        handler = _handler({})
        registry = AIActionRegistry((handler,))
        record = create_action_confirmation(
            db,
            handler=handler,
            normalized_action=_action(),
            user=_user(),
            request_id="compatibility-record-1",
        )
        v1 = confirmation_data(db, record, registry)
        v2 = action_proposal_data(db, record, registry)
        assert v1.confirmation_id == v2.proposal_id == record.id
        assert v1.status == "PENDING"
        assert v2.legacy_status == "PENDING"
        assert v2.lifecycle_status == "WAITING_APPROVAL"
    finally:
        db.close()


def test_handler_version_change_fails_closed_before_approval() -> None:
    db = _database()
    try:
        original = _handler({})
        record = create_action_confirmation(
            db,
            handler=original,
            normalized_action=_action(),
            user=_user(),
            request_id="compatibility-version-1",
        )
        record.gateway_contract_version = "action-gateway-v1"
        record.handler_version = "1.0.0"
        record.approval_policy_version = "legacy-confirmation-v1"
        db.commit()
        changed = replace(
            original,
            manifest=ActionHandlerManifest(
                action_type="APPLY_INJECTION_AUTO_SCHEDULE_RUN",
                handler_version="2.0.0",
                autonomy_level="L3",
                target_state="DRAFT",
                model_may_propose=True,
                model_may_approve=False,
                model_may_execute=False,
                publish_allowed=False,
                rollback_allowed=False,
            ),
        )
        with pytest.raises(HTTPException) as exc_info:
            approve_proposal(
                db,
                proposal_id=record.id,
                payload=AIActionApproveRequest(
                    factory_id="huaxing",
                    expected_args_hash=record.args_hash,
                    approval_request_id="compatibility-version-approval-1",
                ),
                user=_user(),
                registry=AIActionRegistry((changed,)),
            )
        assert exc_info.value.detail["code"] == "ACTION_HANDLER_VERSION_STALE"
    finally:
        db.close()


def test_unregistered_handler_fails_closed_without_exposing_canonical_args() -> None:
    db = _database()
    try:
        handler = _handler({})
        record = create_action_confirmation(
            db,
            handler=handler,
            normalized_action=_action(),
            user=_user(),
            request_id="compatibility-unregistered-1",
        )
        with pytest.raises(HTTPException) as exc_info:
            action_proposal_data(db, record, AIActionRegistry(()))
        assert exc_info.value.detail["code"] == "ACTION_NOT_AVAILABLE"
    finally:
        db.close()
