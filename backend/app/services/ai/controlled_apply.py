from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.ai_action import AIActionConfirmation
from app.models.injection_scheduling_execution import (
    InjectionSchedulingAuditEvent,
    InjectionSchedulingPlan,
)
from app.models.injection_scheduling_scheduler import (
    InjectionSchedulingRun,
    InjectionSchedulingRunAssignment,
)
from app.schemas.ai.action_confirmation import (
    AIActionVerificationData,
    AIControlledApplyResult,
    AIInjectionSchedulingApplyActionSummary,
    AIInjectionSchedulingApplyCanonicalAction,
)
from app.schemas.injection_scheduling_scheduler import InjectionSchedulingRunApply
from app.services.ai.action_registry import (
    ActionConfirmationStaleError,
    AIActionHandler,
)
from app.services.ai.actions.contracts import (
    ActionApprovalPolicy,
    ActionHandlerManifest,
    ActionVerificationError,
)
from app.services.auth import AuthContext, authorization_decision
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    current_rule_set,
)
from app.services.injection_scheduling_scheduler.run_service import apply_run

_TOOL_NAME = "injection_scheduling.apply_preview_run"


def _typed_action(value: BaseModel) -> AIInjectionSchedulingApplyCanonicalAction:
    if not isinstance(value, AIInjectionSchedulingApplyCanonicalAction):
        raise TypeError("unsupported controlled apply action")
    return value


def _run(db: Session, factory_id: str, run_id: str) -> InjectionSchedulingRun:
    record = db.scalar(
        select(InjectionSchedulingRun).where(
            InjectionSchedulingRun.factory_id == factory_id,
            InjectionSchedulingRun.id == run_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="候选排产方案不存在")
    return record


def _plan(db: Session, factory_id: str, plan_id: str) -> InjectionSchedulingPlan:
    record = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.id == plan_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="计划草案不存在")
    return record


def canonical_apply_action(
    db: Session,
    factory_id: str,
    run_id: str,
) -> AIInjectionSchedulingApplyCanonicalAction:
    run = _run(db, factory_id, run_id)
    if run.status not in {"SUCCEEDED", "PARTIAL"}:
        raise HTTPException(status_code=409, detail="只有成功的 PREVIEW Run 可以提议应用")
    plan = _plan(db, factory_id, run.plan_id)
    rules = current_rule_set(db, factory_id)
    if plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="候选方案不能覆盖已发布计划")
    if (
        plan.revision != run.expected_plan_revision
        or plan.rule_revision != run.rule_revision
        or rules.revision != run.rule_revision
    ):
        raise HTTPException(status_code=409, detail="候选方案已过期，请重新生成预览")
    assignment_count, _ = _decision_counts(db, run.id)
    if assignment_count == 0:
        raise HTTPException(status_code=409, detail="当前 PREVIEW Run 没有可应用的安排")
    return AIInjectionSchedulingApplyCanonicalAction(
        factory_id=factory_id,
        run_id=run.id,
        run_revision=run.revision,
        plan_id=plan.id,
        expected_plan_revision=plan.revision,
        expected_rule_revision=rules.revision,
    )


def _decision_counts(db: Session, run_id: str) -> tuple[int, int]:
    rows = db.execute(
        select(
            InjectionSchedulingRunAssignment.decision,
            func.count(InjectionSchedulingRunAssignment.id),
        )
        .where(InjectionSchedulingRunAssignment.run_id == run_id)
        .group_by(InjectionSchedulingRunAssignment.decision)
    ).all()
    counts = {str(decision): int(count) for decision, count in rows}
    return (
        counts.get("PASS", 0) + counts.get("REVIEW_REQUIRED", 0),
        counts.get("REVIEW_REQUIRED", 0),
    )


def apply_action_summary(
    db: Session,
    value: BaseModel,
) -> AIInjectionSchedulingApplyActionSummary:
    action = _typed_action(value)
    assignment_count, review_count = _decision_counts(db, action.run_id)
    return AIInjectionSchedulingApplyActionSummary(
        run_id=action.run_id,
        plan_id=action.plan_id,
        plan_revision=action.expected_plan_revision,
        rule_revision=action.expected_rule_revision,
        assignment_count=assignment_count,
        review_required_count=review_count,
        requires_override_reason=review_count > 0,
    )


def validate_apply_freshness(
    db: Session,
    confirmation: AIActionConfirmation,
    value: BaseModel,
) -> None:
    action = _typed_action(value)
    try:
        run = _run(db, action.factory_id, action.run_id)
        plan = _plan(db, action.factory_id, action.plan_id)
        rules = current_rule_set(db, action.factory_id)
    except HTTPException as exc:
        raise ActionConfirmationStaleError("候选方案、计划或规则已不存在") from exc
    if run.status == "APPLIED" and confirmation.execution_request_id:
        return
    if (
        run.status not in {"SUCCEEDED", "PARTIAL"}
        or run.revision != action.run_revision
        or run.plan_id != action.plan_id
        or run.expected_plan_revision != action.expected_plan_revision
        or run.rule_revision != action.expected_rule_revision
        or plan.status != "DRAFT"
        or plan.revision != action.expected_plan_revision
        or plan.rule_revision != action.expected_rule_revision
        or rules.revision != action.expected_rule_revision
    ):
        raise ActionConfirmationStaleError(
            "候选方案、计划或规则 revision 已变化，请重新生成并确认"
        )


def validate_apply_execution(
    db: Session,
    value: BaseModel,
    review_override_reason: str,
    user: AuthContext,
) -> None:
    action = _typed_action(value)
    _, review_count = _decision_counts(db, action.run_id)
    if review_count and not review_override_reason:
        raise HTTPException(status_code=409, detail="待复核安排必须由用户填写覆盖原因")
    if review_count and not any(
        authorization_decision(
            user,
            "injection_scheduling:publish",
            action.factory_id,
            department,
        )[0]
        for department in SCHEDULING_DEPARTMENTS
    ):
        raise HTTPException(status_code=403, detail="待复核安排需要发布/覆盖权限")


def execute_apply_action(
    db: Session,
    value: BaseModel,
    execution_request_id: str,
    review_override_reason: str,
    user: AuthContext,
) -> AIControlledApplyResult:
    action = _typed_action(value)
    can_override = any(
        authorization_decision(
            user,
            "injection_scheduling:publish",
            action.factory_id,
            department,
        )[0]
        for department in SCHEDULING_DEPARTMENTS
    )
    result = apply_run(
        db,
        action.run_id,
        InjectionSchedulingRunApply(
            factory_id=action.factory_id,
            expected_plan_revision=action.expected_plan_revision,
            expected_rule_revision=action.expected_rule_revision,
            request_id=execution_request_id,
            review_override_reason=review_override_reason,
        ),
        user,
        can_override_review=can_override,
    )
    return AIControlledApplyResult(
        run_id=result.run.id,
        run_status=result.run.status,
        plan_id=result.plan.id,
        plan_revision=result.plan.revision,
        plan_status=result.plan.status,
        audit_sequence=result.audit_sequence,
        idempotent_replay=result.idempotent_replay,
    )


def verify_apply_action(
    db: Session,
    value: BaseModel,
    result: AIControlledApplyResult,
) -> AIActionVerificationData:
    action = _typed_action(value)
    try:
        run = _run(db, action.factory_id, action.run_id)
        plan = _plan(db, action.factory_id, action.plan_id)
    except HTTPException as exc:
        raise ActionVerificationError(
            "正式 DRAFT 或 Run 回读不存在，不能确认执行成功"
        ) from exc
    audit = db.get(InjectionSchedulingAuditEvent, result.audit_sequence)
    if (
        result.run_id != action.run_id
        or result.plan_id != action.plan_id
        or result.run_status != "APPLIED"
        or result.plan_status != "DRAFT"
        or run.status != "APPLIED"
        or plan.status != "DRAFT"
        or plan.revision != result.plan_revision
        or audit is None
        or audit.factory_id != action.factory_id
        or audit.event_type != "auto_schedule_run_applied"
        or audit.entity_type != "auto_schedule_run"
        or audit.entity_id != action.run_id
    ):
        raise ActionVerificationError(
            "正式 DRAFT、Run 或 Domain Audit 回读与执行结果不一致"
        )
    return AIActionVerificationData(
        factory_id=action.factory_id,
        entity_id=plan.id,
        entity_revision=plan.revision,
        run_id=run.id,
        domain_audit_id=f"injection_scheduling_audit_events:{audit.sequence}",
        verified_at=business_now().isoformat(timespec="seconds"),
    )


def injection_scheduling_apply_handler() -> AIActionHandler:
    return AIActionHandler(
        tool_name=_TOOL_NAME,
        action_model=AIInjectionSchedulingApplyCanonicalAction,
        risk_level="CONSEQUENTIAL_WRITE",
        required_permission="injection_scheduling:edit",
        allowed_departments=frozenset(SCHEDULING_DEPARTMENTS),
        factory_argument="factory_id",
        entity_type="auto_schedule_run",
        entity_id_argument="run_id",
        entity_revision_argument="run_revision",
        summary_builder=apply_action_summary,
        freshness_validator=validate_apply_freshness,
        execution_validator=validate_apply_execution,
        executor=execute_apply_action,
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
        post_verifier=verify_apply_action,
    )
