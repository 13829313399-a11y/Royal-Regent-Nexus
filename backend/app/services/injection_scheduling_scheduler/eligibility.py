from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
)
from app.models.injection_scheduling_execution import InjectionSchedulingOrder
from app.schemas.injection_scheduling_matching import (
    InjectionSchedulingMachineMatchOut,
    InjectionSchedulingMatchBatchOut,
    InjectionSchedulingMatchEvaluationOut,
    InjectionSchedulingMatchReasonOut,
    InjectionSchedulingScoreBreakdownOut,
)
from app.services.injection_scheduling import DEFAULT_RULE_CONFIG, current_rule_set
from app.services.injection_scheduling_matching import _queue_context, _score
from app.services.injection_scheduling_rules import (
    MachineEligibilityProfile,
    MoldEligibilityProfile,
    evaluate_eligibility,
)
from app.services.injection_scheduling_scheduler.normalization import load_json


def _reason(reason: Any) -> InjectionSchedulingMatchReasonOut:
    return InjectionSchedulingMatchReasonOut(
        rule_code=reason.rule_code,
        label=reason.label,
        detail=reason.detail,
    )


def evaluate_batch_matches(
    db: Session,
    *,
    factory_id: str,
    order_ids: list[str],
    machine_ids: list[str] | None = None,
    expected_rule_revision: int,
) -> InjectionSchedulingMatchBatchOut:
    rules = current_rule_set(db, factory_id)
    if rules.revision != expected_rule_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "排产规则版本已变化，请重新评估",
                "expected_rule_revision": expected_rule_revision,
                "current_rule_revision": rules.revision,
            },
        )
    orders = list(
        db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id,
                InjectionSchedulingOrder.id.in_(order_ids),
            )
        ).all()
    )
    if len(orders) != len(order_ids):
        found = {item.id for item in orders}
        raise HTTPException(
            status_code=404,
            detail={
                "message": "部分订单不存在或不属于当前厂区",
                "order_ids": [item for item in order_ids if item not in found],
            },
        )
    invalid = [item.id for item in orders if item.status in {"COMPLETED", "CANCELLED"}]
    if invalid:
        raise HTTPException(
            status_code=409,
            detail={"message": "已完成或已取消订单不可评估", "order_ids": invalid},
        )

    machine_statement = select(InjectionSchedulingMachine).where(
        InjectionSchedulingMachine.factory_id == factory_id
    )
    requested_machine_ids = machine_ids or []
    if requested_machine_ids:
        machine_statement = machine_statement.where(
            InjectionSchedulingMachine.id.in_(requested_machine_ids)
        )
    machines = list(
        db.scalars(
            machine_statement.order_by(InjectionSchedulingMachine.machine_code)
        ).all()
    )
    if requested_machine_ids and len(machines) != len(requested_machine_ids):
        raise HTTPException(
            status_code=404, detail="部分候选机台不存在或不属于当前厂区"
        )

    mold_ids = {item.mold_id for item in orders if item.mold_id}
    molds = (
        {
            item.id: item
            for item in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == factory_id,
                    InjectionSchedulingMold.id.in_(mold_ids),
                )
            ).all()
        }
        if mold_ids
        else {}
    )
    queues, queue_molds = _queue_context(db, factory_id)
    max_queue_count = max((len(items) for items in queues.values()), default=0)
    config = {**DEFAULT_RULE_CONFIG, **load_json(rules.config_json, {})}
    order_by_id = {item.id: item for item in orders}
    evaluations: list[InjectionSchedulingMatchEvaluationOut] = []
    for order_id in order_ids:
        order = order_by_id[order_id]
        mold = molds.get(order.mold_id or "")
        results: list[InjectionSchedulingMachineMatchOut] = []
        for machine in machines:
            if mold is None:
                failures: list[InjectionSchedulingMatchReasonOut] = []
                warnings = [
                    InjectionSchedulingMatchReasonOut(
                        rule_code="MOLD_MISSING",
                        label="模具资料",
                        detail="订单未关联有效模具，必须人工复核。",
                    )
                ]
                advisories: list[InjectionSchedulingMatchReasonOut] = []
                decision = "REVIEW_REQUIRED"
            else:
                eligibility = evaluate_eligibility(
                    MachineEligibilityProfile(
                        a_class=machine.machine_a_class,
                        injection_capacity_g=machine.injection_capacity_g,
                        arm_capabilities=tuple(
                            load_json(machine.robot_capabilities_json, [])
                        ),
                        fixture_capabilities=tuple(
                            load_json(machine.fixture_capabilities_json, [])
                        ),
                        process_capabilities=tuple(
                            load_json(machine.process_tags_json, [])
                        ),
                        process_restrictions=tuple(
                            load_json(machine.process_restrictions_json, [])
                        ),
                        status=machine.status,
                        normalization_status=machine.normalization_status,
                        special_machine_type=machine.special_machine_type,
                    ),
                    MoldEligibilityProfile(
                        a_class=mold.mold_a_class,
                        whole_shot_net_weight_g=mold.whole_shot_net_weight_g,
                        required_arm_type=mold.required_arm_type,
                        required_fixture_type=mold.required_fixture_type,
                        process_requirements=tuple(
                            dict.fromkeys(
                                (
                                    *load_json(mold.process_requirements_json, []),
                                    *load_json(mold.process_tags_json, []),
                                )
                            )
                        ),
                        status=mold.status,
                        normalization_status=mold.normalization_status,
                        special_machine_type=mold.special_machine_type,
                    ),
                )
                failures = [_reason(item) for item in eligibility.hard_failures]
                warnings = [_reason(item) for item in eligibility.review_reasons]
                advisories = [_reason(item) for item in eligibility.advisories]
                decision = eligibility.decision
            breakdown: list[InjectionSchedulingScoreBreakdownOut] = (
                []
                if failures
                else _score(
                    machine,
                    mold,
                    order,
                    config,
                    queues.get(machine.id, []),
                    queue_molds,
                    max_queue_count,
                )
            )
            score = (
                None if failures else round(sum(item.delta for item in breakdown), 1)
            )
            result_label = (
                "硬约束失败" if failures else "资料待复核" if warnings else "硬约束通过"
            )
            results.append(
                InjectionSchedulingMachineMatchOut(
                    machine_id=machine.id,
                    machine_code=machine.machine_code,
                    decision=decision,
                    score=score,
                    hard_failures=failures,
                    warnings=warnings,
                    advisories=advisories,
                    score_breakdown=breakdown,
                    explanation=f"{machine.machine_code}：{result_label}；规则 revision {rules.revision}。",
                    rule_set_id=rules.id,
                    rule_set_revision=rules.revision,
                )
            )
        decision_rank = {"PASS": 0, "REVIEW_REQUIRED": 1, "FAIL": 2}
        results.sort(
            key=lambda item: (
                decision_rank[item.decision],
                -(item.score or -1),
                item.machine_code,
            )
        )
        evaluations.append(
            InjectionSchedulingMatchEvaluationOut(
                factory_id=factory_id,
                order_id=order.id,
                mold_id=mold.id if mold is not None else "",
                rule_set_id=rules.id,
                rule_set_revision=rules.revision,
                results=results,
            )
        )
    return InjectionSchedulingMatchBatchOut(
        factory_id=factory_id,
        rule_set_id=rules.id,
        rule_set_revision=rules.revision,
        evaluations=evaluations,
    )
