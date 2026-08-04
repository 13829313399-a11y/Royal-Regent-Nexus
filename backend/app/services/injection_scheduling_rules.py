from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

NormalizationStatus = Literal["COMPLETE", "REVIEW_REQUIRED"]
EligibilityDecision = Literal["PASS", "REVIEW_REQUIRED", "FAIL"]

_A_CLASS_PATTERN = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*[AaＡａ](?![A-Za-z])")
_PROCESS_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dual", ("双模", "双机械手", "双臂", "双手")),
    ("mold_small", ("模小", "小模")),
    ("mold_high", ("模高", "高模", "模小/高", "模小／高")),
    ("mold_long", ("模长", "长模")),
    ("core_pull", ("行位", "抽芯")),
    ("semi_auto", ("半自动",)),
    ("electric_heat", ("电热",)),
    ("vertical", ("立式",)),
    ("two_color", ("双色",)),
)


@dataclass(frozen=True, slots=True)
class NormalizedClass:
    raw: str
    a_class: Decimal | None
    process_tags: tuple[str, ...]
    special_machine_type: str
    status: NormalizationStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MachineEligibilityProfile:
    a_class: Decimal | None
    injection_capacity_g: Decimal | None
    arm_capabilities: tuple[str, ...]
    fixture_capabilities: tuple[str, ...]
    process_capabilities: tuple[str, ...]
    process_restrictions: tuple[str, ...]
    status: str
    normalization_status: NormalizationStatus = "COMPLETE"
    special_machine_type: str = ""


@dataclass(frozen=True, slots=True)
class MoldEligibilityProfile:
    a_class: Decimal | None
    whole_shot_net_weight_g: Decimal | None
    required_arm_type: str
    required_fixture_type: str
    process_requirements: tuple[str, ...]
    status: str
    normalization_status: NormalizationStatus = "COMPLETE"
    special_machine_type: str = ""


@dataclass(frozen=True, slots=True)
class EligibilityReason:
    rule_code: str
    label: str
    detail: str


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    decision: EligibilityDecision
    hard_failures: tuple[EligibilityReason, ...]
    review_reasons: tuple[EligibilityReason, ...]
    advisories: tuple[EligibilityReason, ...]


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result > 0 else None


def _normalized_codes(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(value.strip().lower() for value in values if value.strip())
    )


def normalize_class_text(
    value: object,
    *,
    explicit_class_map: Mapping[str, Decimal | int | float | str] | None = None,
) -> NormalizedClass:
    """Normalize a legacy machine/mold class without guessing missing A values."""

    raw = "" if value is None else str(value).strip()
    compact = re.sub(r"\s+", "", raw)
    tags = tuple(
        tag
        for tag, markers in _PROCESS_TAG_RULES
        if any(marker in compact for marker in markers)
    )
    special_machine_type = "two_color" if "双色" in compact else ""
    reasons: list[str] = []
    a_class: Decimal | None = None

    explicit_value = (explicit_class_map or {}).get(raw)
    if explicit_value is not None:
        a_class = _decimal(explicit_value)
        if a_class is None:
            reasons.append("EXPLICIT_CLASS_MAP_INVALID")
    else:
        match = _A_CLASS_PATTERN.search(compact)
        if match:
            a_class = _decimal(match.group(1))

    if a_class is None:
        reasons.append("A_CLASS_MISSING_OR_AMBIGUOUS")
    if not raw:
        reasons.append("RAW_CLASS_MISSING")
    if special_machine_type and a_class is None:
        reasons.append("SPECIAL_MACHINE_CLASS_REQUIRES_REVIEW")

    return NormalizedClass(
        raw=raw,
        a_class=a_class,
        process_tags=tags,
        special_machine_type=special_machine_type,
        status="REVIEW_REQUIRED" if reasons else "COMPLETE",
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def normalize_arm(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"none", "manual", "半自动", "无", "不需要"}:
        return "none"
    if "multi" in normalized or "多" in normalized:
        return "multi"
    if "dual" in normalized or "双" in normalized:
        return "dual"
    if "single" in normalized or "单" in normalized:
        return "single"
    return normalized


def _reason(rule_code: str, label: str, detail: str) -> EligibilityReason:
    return EligibilityReason(rule_code=rule_code, label=label, detail=detail)


def evaluate_eligibility(
    machine: MachineEligibilityProfile,
    mold: MoldEligibilityProfile,
) -> EligibilityResult:
    """Evaluate only the Phase 0 hard constraints; engineering dimensions are absent."""

    failures: list[EligibilityReason] = []
    reviews: list[EligibilityReason] = []
    advisories: list[EligibilityReason] = []

    machine_class = _decimal(machine.a_class)
    mold_class = _decimal(mold.a_class)
    if machine_class is None or mold_class is None:
        reviews.append(
            _reason(
                "A_CLASS_MISSING",
                "安数",
                "机台安数或模具安数缺失/含糊，必须人工复核。",
            )
        )
    elif mold_class > machine_class:
        failures.append(
            _reason(
                "A_CLASS_EXCEEDED",
                "安数",
                f"模具 {mold_class:g}A 超过机台 {machine_class:g}A。",
            )
        )

    required_weight = _decimal(mold.whole_shot_net_weight_g)
    injection_capacity = _decimal(machine.injection_capacity_g)
    if required_weight is None or injection_capacity is None:
        reviews.append(
            _reason(
                "SHOT_CAPACITY_MISSING",
                "射胶量",
                "整啤净重或机台射胶量缺失，必须人工复核。",
            )
        )
    elif required_weight > injection_capacity:
        failures.append(
            _reason(
                "SHOT_CAPACITY_EXCEEDED",
                "射胶量",
                f"整啤净重 {required_weight:g}g 超过机台射胶量 {injection_capacity:g}g。",
            )
        )
    else:
        utilization = required_weight / injection_capacity
        if utilization > Decimal("0.95"):
            advisories.append(
                _reason(
                    "SHOT_UTILIZATION_ORANGE",
                    "射胶利用率",
                    f"射胶利用率 {utilization:.1%}，接近 100% 硬边界。",
                )
            )
        elif utilization > Decimal("0.85"):
            advisories.append(
                _reason(
                    "SHOT_UTILIZATION_YELLOW",
                    "射胶利用率",
                    f"射胶利用率 {utilization:.1%}，建议关注工艺余量。",
                )
            )

    requirement = normalize_arm(mold.required_arm_type)
    capabilities = _normalized_codes(
        normalize_arm(value) for value in machine.arm_capabilities
    )
    if not requirement:
        reviews.append(
            _reason(
                "ARM_REQUIREMENT_MISSING",
                "机械手",
                "模具机械手等级缺失，必须人工复核。",
            )
        )
    elif not capabilities:
        reviews.append(
            _reason(
                "ARM_CAPABILITY_MISSING", "机械手", "机台机械手能力缺失，必须人工复核。"
            )
        )
    else:
        coverage = {
            "none": {"none", "single", "dual", "multi"},
            "single": {"single", "dual", "multi"},
            "dual": {"dual", "multi"},
            "multi": {"multi"},
        }
        supported = coverage.get(requirement, {requirement})
        if not supported.intersection(capabilities):
            failures.append(
                _reason(
                    "ROBOT_ARM_UNSUPPORTED",
                    "机械手",
                    f"模具要求 {requirement}，机台能力为 {', '.join(capabilities)}。",
                )
            )

    fixture_requirement = mold.required_fixture_type.strip().lower()
    fixture_capabilities = set(_normalized_codes(machine.fixture_capabilities))
    if not fixture_requirement:
        reviews.append(
            _reason(
                "FIXTURE_REQUIREMENT_MISSING",
                "夹具",
                "模具夹具需求缺失，必须人工复核。",
            )
        )
    elif fixture_requirement not in {"none", "无", "不需要"}:
        if not fixture_capabilities:
            reviews.append(
                _reason(
                    "FIXTURE_CAPABILITY_MISSING",
                    "夹具",
                    "机台夹具能力缺失，必须人工复核。",
                )
            )
        elif fixture_requirement not in fixture_capabilities:
            failures.append(
                _reason(
                    "FIXTURE_UNSUPPORTED",
                    "夹具",
                    f"模具要求 {fixture_requirement}，机台未配置该夹具。",
                )
            )

    if machine.status in {"maintenance", "offline"}:
        failures.append(
            _reason(
                "MACHINE_UNAVAILABLE", "机台状态", f"机台当前状态为 {machine.status}。"
            )
        )
    if mold.status in {"maintenance", "not_arrived", "retired"}:
        failures.append(
            _reason("MOLD_UNAVAILABLE", "模具状态", f"模具当前状态为 {mold.status}。")
        )
    elif mold.status == "occupied":
        reviews.append(
            _reason(
                "MOLD_OCCUPIED",
                "模具状态",
                "模具当前被占用，必须复核实体副本和时间重叠。",
            )
        )

    if machine.normalization_status == "REVIEW_REQUIRED":
        reviews.append(
            _reason(
                "MACHINE_NORMALIZATION_REVIEW",
                "机台资料",
                "机台安数原文尚未完成可信标准化。",
            )
        )
    if mold.normalization_status == "REVIEW_REQUIRED":
        reviews.append(
            _reason(
                "MOLD_NORMALIZATION_REVIEW",
                "模具资料",
                "模具安数原文尚未完成可信标准化。",
            )
        )

    requirements = set(_normalized_codes(mold.process_requirements))
    capabilities_set = set(_normalized_codes(machine.process_capabilities))
    restrictions = set(_normalized_codes(machine.process_restrictions))
    conflicts = {
        "core_pull": "no_core_pull",
        "pvc": "no_pvc",
        "high_pressure": "high_pressure_limit",
    }
    for process_requirement in sorted(requirements):
        blocked_by = conflicts.get(process_requirement, process_requirement)
        if blocked_by in restrictions:
            failures.append(
                _reason(
                    "PROCESS_RESTRICTION",
                    "工艺限制",
                    f"模具要求 {process_requirement}，机台限制为 {blocked_by}。",
                )
            )

    special_requirement = mold.special_machine_type.strip().lower()
    machine_special = machine.special_machine_type.strip().lower()
    if (
        special_requirement
        and special_requirement != machine_special
        and special_requirement not in capabilities_set
    ):
        failures.append(
            _reason(
                "SPECIAL_MACHINE_TYPE_UNSUPPORTED",
                "专机类型",
                f"模具要求 {special_requirement}，机台不具备对应专机能力。",
            )
        )

    decision: EligibilityDecision = (
        "FAIL" if failures else "REVIEW_REQUIRED" if reviews else "PASS"
    )
    return EligibilityResult(
        decision=decision,
        hard_failures=tuple(failures),
        review_reasons=tuple(reviews),
        advisories=tuple(advisories),
    )
