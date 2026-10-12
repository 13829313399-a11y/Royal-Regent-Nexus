"""Assembly and packaging headcounts are whole people, including manual totals."""
from copy import deepcopy

import pytest

from app.services.internal_quote_calculator import CalculationInputError, calculate_section
from test_internal_quote_calculator import SNAPSHOT


def payload(category, mode, persons):
    group = {"name": "模拟组装" if category == "assembly" else "模拟包装",
             "category": category, "teams": 2, "production_qty": 1000}
    if mode == "process":
        group["processes"] = [{"name": "模拟工序", "persons": persons}]
    else:
        group.update(processes=[], total_persons=persons)
    return {"labor_base_hkd": 310, "standard_work_hours": 11, "groups": [group]}


def calculate(value):
    return calculate_section("assembly", value, SNAPSHOT, "assembly-people-test")


@pytest.mark.parametrize("category", ["assembly", "packaging"])
@pytest.mark.parametrize("mode", ["process", "manual"])
@pytest.mark.parametrize("invalid", [-1, "-0.5", 0.1, "1.99"])
def test_negative_or_fractional_headcounts_cannot_produce_a_valid_calculation(category, mode, invalid):
    value = payload(category, mode, invalid)
    before = deepcopy(value)
    with pytest.raises(CalculationInputError, match="人数"):
        calculate(value)
    # Validation must not silently clamp or migrate previously saved inputs.
    assert value == before


@pytest.mark.parametrize("category", ["assembly", "packaging"])
@pytest.mark.parametrize("mode,warning", [("process", "assembly_process_persons_missing"),
                                          ("manual", "assembly_total_persons_missing")])
def test_zero_headcount_remains_incomplete_instead_of_becoming_a_valid_zero_quote(category, mode, warning):
    result = calculate(payload(category, mode, 0))
    assert result["status"] == "blocked"
    assert result["group_summaries"][0]["total_persons"] == "0.0000"
    assert result["totals"]["total_hkd"] == "0.0000"
    assert any(row["code"] == warning and row["severity"] == "blocking" for row in result["warnings"])


@pytest.mark.parametrize("category", ["assembly", "packaging"])
@pytest.mark.parametrize("mode", ["process", "manual"])
@pytest.mark.parametrize("persons", [3, "3", "3.000"])
def test_integer_headcounts_keep_existing_cost_formula(category, mode, persons):
    result = calculate(payload(category, mode, persons))
    assert result["status"] == "valid"
    assert result["warnings"] == []
    # HKD 310 x 3 people x 2 teams / 1,000 pieces.
    assert result["totals"] == {
        "assembly_hkd": "1.8600" if category == "assembly" else "0.0000",
        "packaging_hkd": "1.8600" if category == "packaging" else "0.0000",
        "total_hkd": "1.8600",
    }
    assert result["group_summaries"][0]["total_persons"] == "3.0000"
    assert result["line_breakdown"][0]["persons"] == "3.0000"
    assert result["line_breakdown"][0]["amount_hkd_pcs"] == "1.8600"


@pytest.mark.parametrize("category", ["assembly", "packaging"])
@pytest.mark.parametrize("stale_total", [-1, "1.5"])
def test_real_processes_ignore_inactive_legacy_manual_total(category, stale_total):
    value = payload(category, "process", 3)
    group = value["groups"][0]
    group["total_persons"] = stale_total
    group["processes"].append({"name": "暂未分配人数工序", "persons": 0})
    before = deepcopy(value)
    result = calculate(value)
    assert result["status"] == "valid"
    assert result["group_summaries"][0]["total_persons"] == "3.0000"
    assert result["totals"]["total_hkd"] == "1.8600"
    assert value == before


def test_valid_group_cannot_mask_fractional_people_in_another_category():
    value = payload("assembly", "process", 3)
    value["groups"].extend(payload("packaging", "manual", "1.5")["groups"])
    with pytest.raises(CalculationInputError, match="人数"):
        calculate(value)
