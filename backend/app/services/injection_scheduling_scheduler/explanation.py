from __future__ import annotations

from typing import Any

from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
)
from app.schemas.injection_scheduling_matching import InjectionSchedulingMachineMatchOut
from app.services.injection_scheduling_scheduler.normalization import load_json
from app.services.injection_scheduling_scheduler.scoring import PlacementScore
from app.services.injection_scheduling_scheduler.transition import TransitionImpact


def assignment_explanation(
    match: InjectionSchedulingMachineMatchOut,
    score: PlacementScore,
    transition: TransitionImpact,
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold,
) -> dict[str, Any]:
    machine_arms = load_json(machine.robot_capabilities_json, [])
    machine_fixtures = load_json(machine.fixture_capabilities_json, [])
    machine_processes = load_json(machine.process_tags_json, [])
    mold_processes = list(
        dict.fromkeys(
            (
                *load_json(mold.process_requirements_json, []),
                *load_json(mold.process_tags_json, []),
            )
        )
    )
    hard_checks = [
        {
            "code": "A_CLASS_PASS",
            "label": "安数",
            "detail": f"模具 {float(mold.mold_a_class or 0):g}A ≤ 机台 {float(machine.machine_a_class or 0):g}A。",
        },
        {
            "code": "SHOT_CAPACITY_PASS",
            "label": "射胶量",
            "detail": f"整啤净重 {float(mold.whole_shot_net_weight_g or 0):g}g ≤ 机台射胶量 {float(machine.injection_capacity_g or 0):g}g。",
        },
        {
            "code": "ARM_PASS",
            "label": "机械手",
            "detail": f"需求 {mold.required_arm_type or '无'}；机台能力 {', '.join(machine_arms) or '无'}。",
        },
        {
            "code": "FIXTURE_PASS",
            "label": "夹具",
            "detail": f"需求 {mold.required_fixture_type or '无'}；机台能力 {', '.join(machine_fixtures) or '无'}。",
        },
        {
            "code": "PROCESS_PASS",
            "label": "工艺",
            "detail": f"需求 {', '.join(mold_processes) or '无'}；机台标签 {', '.join(machine_processes) or '标准'}。",
        },
        {
            "code": "MACHINE_STATUS_PASS",
            "label": "机台状态",
            "detail": f"机台状态 {machine.status}，可进入排期候选。",
        },
        {
            "code": "DIMENSION_ADVISORY_ONLY",
            "label": "工程尺寸",
            "detail": "模具尺寸仅作工程资料，不参与自动资格硬约束。",
        },
    ]
    hard_checks.extend(
        {"code": item.rule_code, "label": item.label, "detail": item.detail}
        for item in match.advisories
    )
    return {
        "summary": match.explanation,
        "hard_checks": hard_checks,
        "review_reasons": [item.model_dump(mode="json") for item in match.warnings],
        "score_breakdown": list(score.breakdown),
        "transition": {
            "type": transition.changeover_type,
            "setup_minutes": transition.setup_minutes,
            "dark_to_light": transition.dark_to_light,
        },
    }


def unassigned_explanation(
    code: str, detail: str, failures: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"summary": detail, "reason_code": code, "hard_failures": failures or []}
