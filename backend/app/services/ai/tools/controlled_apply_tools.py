from __future__ import annotations

import hashlib

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.action_confirmation import (
    AIActionConfirmationData,
    InjectionSchedulingApplyProposalInput,
)
from app.services.ai.action_confirmation import (
    confirmation_data,
    create_action_confirmation,
)
from app.services.ai.action_registry import AIActionRegistry
from app.services.ai.controlled_apply import (
    canonical_apply_action,
    injection_scheduling_apply_handler,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS


def _proposal_request_id(context: ToolExecutionContext, run_id: str) -> str:
    digest = hashlib.sha256(
        f"{context.request_id}:{context.tool_call_id}:{run_id}".encode()
    ).hexdigest()[:40]
    return f"ai-confirm-{digest}"


def propose_apply(
    context: ToolExecutionContext,
    arguments: InjectionSchedulingApplyProposalInput,
) -> AIActionConfirmationData:
    if context.db is None:
        raise RuntimeError("a database session is required")
    handler = injection_scheduling_apply_handler()
    action = canonical_apply_action(context.db, arguments.factory_id, arguments.run_id)
    record = create_action_confirmation(
        context.db,
        handler=handler,
        normalized_action=action,
        user=context.user,
        request_id=_proposal_request_id(context, arguments.run_id),
    )
    return confirmation_data(
        context.db,
        record,
        AIActionRegistry((handler,)),
    )


def _serialize_confirmation(value: object) -> AIActionConfirmationData:
    if not isinstance(value, AIActionConfirmationData):
        raise TypeError("action confirmation serializer received an unsupported value")
    return value


def controlled_apply_proposal_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="injection_scheduling.propose_apply",
        description=(
            "为一个既有、未过期的 PREVIEW Run 创建单次人工确认记录。"
            "该工具本身不 Apply、不 Publish；模型不得填写人工覆盖原因，"
            "后续执行只能来自确认卡上的用户明确操作。"
        ),
        input_model=InjectionSchedulingApplyProposalInput,
        risk_level=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
        executor=propose_apply,
        serializer=_serialize_confirmation,
        display_label="正在准备正式 Apply 确认（尚未执行）",
        tool_group="injection_scheduling",
        required_permission="injection_scheduling:edit",
        allowed_departments=frozenset(SCHEDULING_DEPARTMENTS),
        factory_argument="factory_id",
        requires_db=True,
        max_result_rows=4,
        timeout_seconds=10,
        audit_policy=AIToolAuditPolicy.METADATA_ONLY,
    )
