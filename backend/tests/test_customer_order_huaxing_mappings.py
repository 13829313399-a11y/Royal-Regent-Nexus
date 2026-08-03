from datetime import date

import pytest

from app.services.customer_order_huaxing import (
    HUAXING_CUSTOMER_MAPPINGS,
    HuaxingCustomerOrderError,
    _dedupe_multi_orders,
    _issues,
    _record_fields,
    _validate_skips,
)
from app.services.huaxing_order_legacy import (
    edu_schedule,
    multi_schedule,
    shixin_schedule,
    three_sixty_schedule,
    yinhui_schedule,
)


def test_huaxing_customer_order_center_exposes_exactly_six_new_mappings():
    assert set(HUAXING_CUSTOMER_MAPPINGS) == {
        "edu",
        "360",
        "yinhui",
        "seasons",
        "maxx",
        "shushupapa",
    }
    assert all(spec.target_template.endswith("_V1") for spec in HUAXING_CUSTOMER_MAPPINGS.values())


def test_edu_inspection_date_is_seven_days_before_ship_date_and_avoids_weekend():
    row = {
        "customer_type": "EDU",
        "customer_po": "EDU-100",
        "item_no": "A100",
        "product_name": "Test",
        "quantity": 120,
        "case_pack": 12,
        "ship_date": "2026-08-16",
    }

    edu_schedule.add_derived_fields(row, today=date(2026, 8, 1))

    assert row["inspection_date"] == "2026-08-07"
    assert row["cartons"] == 10


def test_360_date_code_uses_factory_year_and_day_of_year():
    assert three_sixty_schedule.build_360_date_code("2026-07-02", "60350") == "60350A26183"


def test_yinhui_uses_fixed_exchange_rate_and_ship_minus_five_days():
    row = {
        "so_no": "SO-1",
        "contract_no": "YH-1",
        "customer": "YINHUI",
        "item_no": "ITEM-1",
        "product_name": "Test",
        "quantity": 10,
        "case_pack": 5,
        "po_ship_date": "2026-08-20",
        "unit_price_usd": 2,
    }

    yinhui_schedule.add_derived_fields(row, today=date(2026, 8, 1))

    assert row["unit_price_hkd"] == 15.5
    assert row["total_hkd"] == 155
    assert row["inspection_date"] == "2026-08-15"


def test_seasons_schedule_families_are_kept_in_separate_lanes():
    assert shixin_schedule.schedule_family_from_sheets(["正单评审表"]) == "seasons"
    assert shixin_schedule.schedule_family_from_sheets(["手掌", "面具"]) == "internal"


def test_maxx_and_shushupapa_apply_their_seven_day_dates():
    maxx = multi_schedule._line_values(
        {"client": "maxx", "po_number": "MAXX-1", "ship_date": "2026-08-20"},
        {"item_code": "100", "description": "Maxx item", "quantity": 10},
    )
    shushupapa = multi_schedule._line_values(
        {"client": "shushupapa", "po_number": "SSP-1", "ship_date": "2026-08-20"},
        {"item_code": "200", "description": "Shushu item", "quantity": 10},
    )

    assert maxx["complete_date"] == "2026-08-13"
    assert maxx["inspection_date"] == "2026-08-13"
    assert shushupapa["complete_date"] is None
    assert shushupapa["inspection_date"] == "2026-08-13"


def test_multi_customer_revision_dedup_keeps_highest_revision():
    selected, report = _dedupe_multi_orders([
        {"po_number": "PO-1", "filename": "PO-1.pdf"},
        {"po_number": "PO-1", "filename": "PO-1_REV2.pdf"},
    ])

    assert [item["filename"] for item in selected] == ["PO-1_REV2.pdf"]
    assert "PO-1.pdf" in report[0]


def test_common_preview_contract_maps_each_customer_and_blocks_high_risk_flags():
    assert _record_fields("edu", {"customer_po": "E-1", "item_no": "A"})["po_no"] == "E-1"
    assert _record_fields("360", {"production_no": "RL-1", "item_full": "B"})["contract_no"] == "RL-1"
    assert _record_fields("yinhui", {"contract_no": "Y-1"})["po_no"] == "Y-1"
    assert _record_fields("seasons", {"oqf_no": "QF-1"})["po_no"] == "QF-1"
    assert _record_fields("maxx", {"po_number": "M-1"})["po_no"] == "M-1"
    assert _record_fields("shushupapa", {"po_number": "S-1"})["po_no"] == "S-1"

    issues = _issues(
        {"flags": [{"level": "high", "code": "missing_item", "text": "缺货号"}]},
        "maxx-1",
    )
    assert issues[0]["severity"] == "blocked"
    assert issues[0]["can_skip"] is False


def test_existing_orders_are_test_stage_confirmable_but_data_risks_are_not():
    issues = _issues(
        {
            "po_number": "PO-EXISTING",
            "_duplicate_existing": True,
            "flags": [{"level": "high", "code": "missing_item", "text": "缺货号"}],
        },
        "maxx-1",
    )
    duplicate = next(issue for issue in issues if issue["code"] == "duplicate_existing_order")
    hard_blocker = next(issue for issue in issues if issue["code"] == "missing_item")

    assert duplicate["severity"] == "blocked"
    assert duplicate["can_skip"] is True
    assert duplicate["skip_label"] == "测试阶段确认重复导入当前或历史排期已有订单"
    assert hard_blocker["can_skip"] is False

    preview = {"rows": [{"issues": issues}]}
    with pytest.raises(HuaxingCustomerOrderError, match="缺货号"):
        _validate_skips(preview, {duplicate["skip_key"]})
    _validate_skips({"rows": [{"issues": [duplicate]}]}, {duplicate["skip_key"]})
    with pytest.raises(HuaxingCustomerOrderError, match="不允许通过"):
        _validate_skips(
            preview,
            {duplicate["skip_key"], hard_blocker["skip_key"]},
        )
