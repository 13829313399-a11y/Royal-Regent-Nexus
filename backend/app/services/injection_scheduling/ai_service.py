from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_schedule import (
    InjectionScheduleLine,
    InjectionScheduleMachine,
    InjectionScheduleOrderDemand,
)
from app.schemas.injection_schedule import (
    InjectionScheduleAiAdjustmentResult,
    InjectionScheduleAiExplainResult,
    InjectionScheduleAiFilterResult,
    InjectionScheduleAiRemarkResult,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling.ai_provider import get_ai_provider
from app.services.injection_scheduling.audit import write_audit_event


def parse_remark(remark: str) -> dict[str, object]:
    result = get_ai_provider().complete_json(
        system_prompt="你是注塑排产备注结构化助手。不得发明订单、机台或数量。",
        user_prompt=f"结构化以下备注：{remark}",
        result_model=InjectionScheduleAiRemarkResult,
    )
    return result.model_dump()


def interpret_filter(text: str) -> dict[str, object]:
    result = get_ai_provider().complete_json(
        system_prompt=(
            "你把中文自然语言转成注塑排产筛选条件。status 只能为空、PENDING、"
            "SCHEDULED、IN_PRODUCTION、COMPLETED；priority 只能为空、EXPEDITE、"
            "URGENT、NORMAL。"
        ),
        user_prompt=text,
        result_model=InjectionScheduleAiFilterResult,
    )
    return result.model_dump()


def explain_schedule(db: Session, factory_id: str, line_id: str) -> dict[str, object]:
    row = db.execute(
        select(
            InjectionScheduleLine,
            InjectionScheduleOrderDemand,
            InjectionScheduleMachine,
        )
        .join(
            InjectionScheduleOrderDemand,
            InjectionScheduleOrderDemand.id == InjectionScheduleLine.order_demand_id,
        )
        .outerjoin(
            InjectionScheduleMachine,
            InjectionScheduleMachine.id == InjectionScheduleLine.machine_id,
        )
        .where(
            InjectionScheduleLine.id == line_id,
            InjectionScheduleLine.factory_id == factory_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="排程行不存在")
    line, order, machine = row
    facts = {
        "order": {
            "priority": order.priority,
            "delivery_due_date": order.delivery_due_date,
            "required_machine_a": str(order.required_machine_a_value),
            "mold_code": order.mold_code,
            "material": order.material_name,
            "color": order.color,
        },
        "machine": {
            "code": machine.machine_code if machine else "",
            "machine_a": str(machine.machine_ounce_capacity) if machine else "",
        },
        "schedule": {
            "start": line.planned_start_at,
            "finish": line.planned_finish_at,
            "source": line.schedule_source,
            "reason_codes": json.loads(line.assignment_reason_json or "[]"),
        },
    }
    result = get_ai_provider().complete_json(
        system_prompt="你解释确定性排程事实。只能引用输入事实，不得新增约束或声称已执行调整。",
        user_prompt=json.dumps(facts, ensure_ascii=False),
        result_model=InjectionScheduleAiExplainResult,
    )
    return {"facts": facts, "explanation": result.model_dump()}


def parse_adjustment(
    db: Session, factory_id: str, text: str, actor: AuthContext
) -> dict[str, object]:
    result = get_ai_provider().complete_json(
        system_prompt=(
            "你把人工排产调整意图结构化。只允许 MOVE、LOCK、UNLOCK、PAUSE、"
            "RESUME、NOOP；建议永远需要人工确认，不能声称已写库。"
        ),
        user_prompt=text,
        result_model=InjectionScheduleAiAdjustmentResult,
    )
    payload = result.model_dump()
    if payload["action"] not in {"MOVE", "LOCK", "UNLOCK", "PAUSE", "RESUME", "NOOP"}:
        raise HTTPException(
            status_code=502, detail="千问建议包含不支持的操作，未执行任何写入"
        )
    payload["requires_confirmation"] = True
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="AI_SUGGESTION_CREATED",
        entity_type="AI_SUGGESTION",
        entity_id=f"suggestion:{actor.id}",
        entity_version=1,
        actor=actor,
        reason=text[:500],
        after=payload,
    )
    db.commit()
    return payload
