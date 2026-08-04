import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.injection_scheduling_rules import (
    MachineEligibilityProfile,
    MoldEligibilityProfile,
    evaluate_eligibility,
    normalize_class_text,
)


@pytest.mark.parametrize(
    ("raw", "expected_class", "expected_tags"),
    (
        ("14A双模小/高", Decimal(14), {"dual", "mold_small", "mold_high"}),
        ("7A行位", Decimal(7), {"core_pull"}),
        ("5A半自动", Decimal(5), {"semi_auto"}),
    ),
)
def test_normalizer_preserves_raw_and_extracts_numeric_a_class_and_tags(
    raw,
    expected_class,
    expected_tags,
):
    result = normalize_class_text(raw)

    assert result.raw == raw
    assert result.a_class == expected_class
    assert set(result.process_tags) == expected_tags
    assert result.status == "COMPLETE"


@pytest.mark.parametrize("raw", ("32电热", "18"))
def test_normalizer_does_not_guess_numeric_class_without_a_marker(raw):
    result = normalize_class_text(raw)

    assert result.a_class is None
    assert result.status == "REVIEW_REQUIRED"
    assert "A_CLASS_MISSING_OR_AMBIGUOUS" in result.reason_codes


def test_normalizer_supports_explicit_map_without_changing_raw():
    result = normalize_class_text("32电热", explicit_class_map={"32电热": 32})

    assert result.raw == "32电热"
    assert result.a_class == Decimal(32)
    assert result.process_tags == ("electric_heat",)
    assert result.status == "COMPLETE"


def test_two_color_is_special_type_and_not_arbitrarily_assigned_a_class():
    result = normalize_class_text("双色机")

    assert result.a_class is None
    assert result.special_machine_type == "two_color"
    assert result.status == "REVIEW_REQUIRED"


def _machine(**overrides) -> MachineEligibilityProfile:
    values = {
        "a_class": Decimal(12),
        "injection_capacity_g": Decimal(100),
        "arm_capabilities": ("dual",),
        "fixture_capabilities": ("suction_cup",),
        "process_capabilities": (),
        "process_restrictions": (),
        "status": "available",
        "normalization_status": "COMPLETE",
        "special_machine_type": "",
    }
    values.update(overrides)
    return MachineEligibilityProfile(**values)


def _mold(**overrides) -> MoldEligibilityProfile:
    values = {
        "a_class": Decimal(7),
        "whole_shot_net_weight_g": Decimal(90),
        "required_arm_type": "single",
        "required_fixture_type": "suction_cup",
        "process_requirements": (),
        "status": "available",
        "normalization_status": "COMPLETE",
        "special_machine_type": "",
    }
    values.update(overrides)
    return MoldEligibilityProfile(**values)


@pytest.mark.parametrize("mold_class", (Decimal(7), Decimal(10)))
def test_a_class_at_or_below_machine_passes(mold_class):
    result = evaluate_eligibility(_machine(), _mold(a_class=mold_class))

    assert result.decision == "PASS"


def test_14a_mold_cannot_run_on_12a_machine():
    result = evaluate_eligibility(_machine(), _mold(a_class=Decimal(14)))

    assert result.decision == "FAIL"
    assert {reason.rule_code for reason in result.hard_failures} == {"A_CLASS_EXCEEDED"}


def test_injection_capacity_uses_exact_100_percent_hard_boundary():
    exact = evaluate_eligibility(
        _machine(injection_capacity_g=Decimal(100)),
        _mold(whole_shot_net_weight_g=Decimal(100)),
    )
    exceeded = evaluate_eligibility(
        _machine(injection_capacity_g=Decimal(100)),
        _mold(whole_shot_net_weight_g=Decimal("100.001")),
    )

    assert exact.decision == "PASS"
    assert {reason.rule_code for reason in exact.advisories} == {
        "SHOT_UTILIZATION_ORANGE"
    }
    assert exceeded.decision == "FAIL"
    assert {reason.rule_code for reason in exceeded.hard_failures} == {
        "SHOT_CAPACITY_EXCEEDED"
    }


def test_dual_arm_machine_covers_single_but_single_does_not_cover_dual():
    covered = evaluate_eligibility(_machine(), _mold(required_arm_type="single"))
    rejected = evaluate_eligibility(
        _machine(arm_capabilities=("single",)),
        _mold(required_arm_type="dual"),
    )

    assert covered.decision == "PASS"
    assert rejected.decision == "FAIL"
    assert {reason.rule_code for reason in rejected.hard_failures} == {
        "ROBOT_ARM_UNSUPPORTED"
    }


@pytest.mark.parametrize(
    ("machine_overrides", "mold_overrides", "reason_code"),
    (
        ({"a_class": None}, {}, "A_CLASS_MISSING"),
        ({"injection_capacity_g": None}, {}, "SHOT_CAPACITY_MISSING"),
        ({"arm_capabilities": ()}, {}, "ARM_CAPABILITY_MISSING"),
        ({}, {"required_fixture_type": ""}, "FIXTURE_REQUIREMENT_MISSING"),
    ),
)
def test_missing_critical_inputs_require_review(
    machine_overrides,
    mold_overrides,
    reason_code,
):
    result = evaluate_eligibility(
        _machine(**machine_overrides),
        _mold(**mold_overrides),
    )

    assert result.decision == "REVIEW_REQUIRED"
    assert reason_code in {reason.rule_code for reason in result.review_reasons}


def test_two_color_mold_requires_two_color_machine_capability():
    rejected = evaluate_eligibility(
        _machine(),
        _mold(special_machine_type="two_color"),
    )
    accepted = evaluate_eligibility(
        _machine(special_machine_type="two_color"),
        _mold(special_machine_type="two_color"),
    )

    assert rejected.decision == "FAIL"
    assert accepted.decision == "PASS"
