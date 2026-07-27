import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.injection_schedule_validation import (  # noqa: E402
    normalize_robot_level,
    validate_lane_time_overlap,
    validate_robot_requirement,
)


@pytest.mark.parametrize(
    ("required", "actual", "expected_status"),
    [
        ("双臂", "双臂五轴", "pass"),
        ("双臂", "单臂三轴", "fail"),
        ("单臂", "单臂三轴", "pass"),
        ("单臂", "双臂五轴", "pass"),
        ("半自动", "单臂三轴", "pass"),
        ("半自动", "双臂五轴", "pass"),
        ("无机械手", "", "pass"),
        ("single", "double", "pass"),
        ("double", "single", "fail"),
        ("未知规格", "双臂五轴", "unknown"),
        ("单臂", "", "unknown"),
    ],
)
def test_robot_requirement_uses_capability_hierarchy(
    required,
    actual,
    expected_status,
):
    result = validate_robot_requirement("task-1", required, actual)

    assert result["constraint_code"] == "robot_type"
    assert result["status"] == expected_status
    assert result["blocking"] is (expected_status != "pass")


def test_robot_level_normalization_matches_real_workbook_terms():
    assert normalize_robot_level("半自动") == 0
    assert normalize_robot_level("单臂") == 1
    assert normalize_robot_level("单臂三轴") == 1
    assert normalize_robot_level("双臂") == 2
    assert normalize_robot_level("双臂五轴") == 2


def test_lane_overlap_includes_current_task_setup_occupancy():
    previous = SimpleNamespace(
        id="previous",
        planned_finish_at="2026-07-24 10:00:00",
    )
    current = SimpleNamespace(
        id="current",
        planned_start_at="2026-07-24 10:30:00",
        setup_hours=1,
    )
    result = validate_lane_time_overlap(previous, current)
    assert result["status"] == "fail"
    assert result["constraint_code"] == "time_overlap"
    assert result["details_json"]

    boundary = SimpleNamespace(
        id="boundary",
        planned_start_at="2026-07-24 11:00:00",
        setup_hours=1,
    )
    assert validate_lane_time_overlap(previous, boundary)["status"] == "pass"
