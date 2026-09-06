import hashlib
import json
import os
from decimal import Decimal as D
from pathlib import Path

import pytest
from app.services.injection_scheduling.calculations import (
    co_output_shots,
    quantities,
    sequential_allocate,
    timestamp,
)
from app.services.injection_scheduling.changeover import transition
from app.services.injection_scheduling.defaults import factory_defaults
from app.services.injection_scheduling.import_plan import parse_plan
from app.services.injection_scheduling.requirement_parser import (
    machine_capabilities,
    machine_requirement,
    normalize_code,
    state_from_text,
)
from app.services.injection_scheduling.resource_calendar import consume


def test_independent_hand_calculation_a():
    q = quantities(
        {
            "planned_shots": 1000,
            "opening_shots": 100,
            "target_shots_per_day": 2400,
            "net_weight_g": 20,
            "price_per_shot": 0.5,
        },
        200,
    )
    assert (
        q["completed_shots"],
        q["remaining_shots"],
        q["shots_per_hour"],
        q["production_duration_hours"],
    ) == (300, 700, 100, 7)
    assert q["remaining_material_kg"] == D("14.14")
    assert q["remaining_processing_amount"] == 350


def test_independent_hand_calculation_b():
    end, segments = consume(
        "2026-09-05T08:00:00+08:00",
        420,
        [
            (
                timestamp("2026-09-05T10:00:00+08:00"),
                timestamp("2026-09-05T12:00:00+08:00"),
            )
        ],
    )
    assert end == timestamp("2026-09-05T17:00:00+08:00")
    assert [int((b - a).total_seconds() / 3600) for a, b in segments] == [2, 5]


def test_independent_hand_calculation_c_d():
    assert (
        co_output_shots(
            [
                {"remaining_units": 100, "outputs_per_shot": 2},
                {"remaining_units": 80, "outputs_per_shot": 1},
            ]
        )
        == 80
    )
    assert sequential_allocate(100, [60, 80]) == ([60, 40], 0)


@pytest.mark.parametrize(
    "raw,a,family",
    [
        ("12A模小/胶量大", 12, "HORIZONTAL"),
        ("7A ", 7, "HORIZONTAL"),
        ("7A立式机", 7, "VERTICAL"),
        ("双色机", None, "TWO_COLOR"),
    ],
)
def test_requirement_evidence(raw, a, family):
    r = machine_requirement(raw)
    assert r["required_machine_a"] == a
    assert r["machine_family"] == family


def test_limits_and_material_change():
    assert machine_requirement("18A(新15.16装不下）")["forbidden_machine_codes"] == [
        "新15",
        "新16",
    ]
    assert machine_requirement("12A（要排高速机）")["speed_class"] == "HIGH_SPEED"
    for note in ("检修已完成", "无需检修", "不需要检修", "机器不稳定"):
        assert state_from_text(note) == "IDLE"
    c = machine_capabilities("12A", note="不能啤PC；抽芯不行")
    assert c["restrictions"]["forbidden_resins"] == ["PC"]
    assert c["capabilities"]["CORE_PULL"] is False
    target = {
        "mold_asset_id": "a",
        "required_machine_a": 12,
        "material_raw": "PP",
        "color_name": "白色",
    }
    same = transition(target, target, factory_defaults())
    assert same["changeover_minutes"] == 0
    changed = transition(target, {**target, "material_raw": "ABS"}, factory_defaults())
    assert changed["color_change_minutes"] == 60
    assert transition(None, {**target, "required_machine_a": 10}, factory_defaults())[
        "mold_change_minutes"
    ] == D("64.8")
    assert normalize_code("  ab-01-a ") == "AB-01-A"


def test_overproduction_missing_optional_and_rate():
    q = quantities({"planned_shots": 100, "target_shots_per_day": 2400}, 120)
    assert q["remaining_shots"] == 0 and q["overproduced_shots"] == 20
    assert (
        q["remaining_material_kg"] is None and q["remaining_processing_amount"] is None
    )
    assert quantities({"planned_shots": 100})["shots_per_hour"] is None


def test_contiguous_setup_and_cross_year():
    a, b = timestamp("2026-12-31T10:00+08:00"), timestamp("2027-01-01T12:00+08:00")
    end, segments = consume("2026-12-31T09:00+08:00", 120, [(a, b)], continuous=True)
    assert end == timestamp("2027-01-01T14:00+08:00")
    assert segments == [(b, end)]


@pytest.fixture(scope="module")
def real_plan():
    path = os.getenv("INJECTION_V3_WORKBOOK")
    if not path:
        pytest.skip(
            "Set INJECTION_V3_WORKBOOK to run the private real-workbook contract"
        )
    source = Path(path)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    parsed = parse_plan(source.read_bytes())
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest()
        == before
        == "07b4878ed052598c83a103a1a4abf7cadeb5bfd4839e4a12a2452ee7724b832f"
    )
    return parsed


def test_w01_w06_real_totals(real_plan):
    s = real_plan["statistics"]
    expected = {
        "machine_count": 76,
        "old_machine_count": 39,
        "new_machine_count": 37,
        "task_candidate_count": 280,
        "machine_area_task_count": 210,
        "tail_task_count": 70,
        "numeric_order_quantity_rows": 274,
        "cached_remaining_quantity_rows": 273,
        "order_quantity_sum": 5540233,
        "cached_produced_quantity_sum": 2253660,
        "cached_remaining_quantity_sum": 3186573,
        "standard_remaining_sum": 3286573,
        "quantity_sum_gap": 100000,
        "numeric_shift_cell_count": 1449,
        "numeric_shift_quantity_sum": 2267721,
        "shift_sum_minus_cached_M": 14061,
        "formula_cell_count": 4739,
        "cached_na_cells": 40,
        "dated_shift_column_count": 570,
    }
    assert {k: s[k] for k in expected} == expected
    assert len(real_plan["read_worksheets"]) == 1
    rows = {d["source_row"]: d for d in real_plan["demands"]}
    assert 139 not in rows
    assert rows[360]["raw_fields"]["remaining_shots"] is None
    assert {r: rows[r]["numeric_shift_sum"] for r in [6, 118, 131, 132, 134]} == {
        6: 2850,
        118: 367,
        131: 5280,
        132: 5280,
        134: 284,
    }


def test_w07_w15_source_semantics(real_plan):
    rows = {d["source_row"]: d for d in real_plan["demands"]}
    for row, divisor in [(89, 2), (121, 2), (220, 4), (370, 8)]:
        assert (
            rows[row]["fields"]["planned_shots"]
            == rows[row]["fields"]["demand_sets"] / divisor
        )
    assert rows[370]["fields"]["planned_shots"] == 2025
    assert [
        d["source_row"]
        for d in real_plan["demands"]
        if any(x["code"] == "WRONG_AS_REFERENCE" for x in d["issues"])
    ] == [8, 72, 89, 134, 147, 191, 255, 256, 257]
    assert rows[329]["fields"]["color_name"] != rows[330]["fields"]["color_name"]
    assert rows[329]["fields"]["colorant_code"] != rows[330]["fields"]["colorant_code"]
    assert all(
        d["inferred_machine_block"] is None
        for d in real_plan["demands"]
        if d["source_row"] >= 301
    )
    assert (
        "AW" not in real_plan["shift_columns"]
        and "AX" not in real_plan["shift_columns"]
    )
    assert "#REF!" in real_plan["formula_cells"]["AG139"]["formula_expanded"]
    machines = {m["source_row"]: m for m in real_plan["machines"]}
    assert "抽芯不行" in machines[30]["notes"]
    assert "不能啤PC" in machines[85]["notes"]


def test_independent_forensic_formulas(real_plan):
    evidence = os.getenv("INJECTION_V3_EVIDENCE")
    if not evidence:
        pytest.skip(
            "Set INJECTION_V3_EVIDENCE for independent formula expansion comparison"
        )
    original = json.loads(Path(evidence).read_text(encoding="utf-8"))
    assert {
        k: v["formula_expanded"] for k, v in real_plan["formula_cells"].items()
    } == {k: v["formula_expanded"] for k, v in original["formula_cells"].items()}
