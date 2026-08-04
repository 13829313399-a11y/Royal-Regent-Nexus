import json
from pathlib import Path

import pytest

from app.api import customer_order as api
from app.services import customer_order_huadeng as huadeng
from app.services import customer_order_huakang_a as huakang_a
from app.services import customer_order_huakang_c as huakang_c
from app.services import customer_order_huaxing as huaxing


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "customer_order_duplicate_contract_v1.json"
)
GOLDEN = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _issue_by_code(issues: list[dict], code: str) -> dict:
    return next(issue for issue in issues if issue["code"] == code)


def test_factory_customer_routing_matches_versioned_golden_contract():
    actual = {
        factory_id: sorted(
            customer_code
            for customer_code, factory_ids in api.CUSTOMER_FACTORY_OPTIONS.items()
            if factory_id in factory_ids
        )
        for factory_id in GOLDEN["factory_customer_codes"]
    }
    expected = {
        factory_id: sorted(customer_codes)
        for factory_id, customer_codes in GOLDEN["factory_customer_codes"].items()
    }
    assert actual == expected


@pytest.mark.parametrize("adapter", ["huaxing", "huadeng", "huakang-a", "huakang-c"])
def test_all_factory_adapters_emit_the_same_duplicate_and_quantity_conflict_contract(adapter):
    if adapter == "huaxing":
        duplicate_issues = huaxing._issues(
            {"contract_no": "SC-100", "product_no": "ITEM-1", "_duplicate_existing": True},
            "golden-row",
        )
        conflict_issues = huaxing._issues(
            {
                "flags": [{
                    "level": "high",
                    "code": "existing_quantity_conflict",
                    "text": "quantity differs",
                }],
                "risk_level": "high",
            },
            "golden-row",
        )
    elif adapter == "huadeng":
        duplicate_issues = huadeng._issues(
            {"contract_no": "SC-100", "product_no": "ITEM-1", "_duplicate_existing": True},
            "golden-row",
        )
        conflict_issues = huadeng._issues(
            {"flags": [{
                "level": "high",
                "code": "existing_quantity_conflict",
                "text": "quantity differs",
            }]},
            "golden-row",
        )
    elif adapter == "huakang-a":
        duplicate_issues = huakang_a._issues(
            {
                "parse_ok": True,
                "contract_no": "SC-100",
                "item_no": "ITEM-1",
                "_duplicate_existing": True,
            },
            "golden-row",
        )
        conflict_issues = huakang_a._issues(
            {"parse_ok": True, "_existing_quantity_conflict": True},
            "golden-row",
        )
    else:
        order = {"contract_no": "SC-100", "customer_code": "index"}
        duplicate_issues = huakang_c._issues(
            order,
            {"item_code": "ITEM-1", "_duplicate_existing": True},
            "golden-row",
        )
        conflict_issues = huakang_c._issues(
            order,
            {"item_code": "ITEM-1", "_existing_quantity_conflict": True},
            "golden-row",
        )

    duplicate = _issue_by_code(duplicate_issues, GOLDEN["duplicate_issue"]["code"])
    assert duplicate["severity"] == GOLDEN["duplicate_issue"]["severity_before_environment_policy"]
    assert duplicate["can_skip"] is GOLDEN["duplicate_issue"]["can_skip_before_environment_policy"]
    assert duplicate["skip_key"]

    conflict = _issue_by_code(
        conflict_issues,
        GOLDEN["quantity_conflict_issue"]["code"],
    )
    assert conflict["severity"] == GOLDEN["quantity_conflict_issue"]["severity"]
    assert conflict["can_skip"] is GOLDEN["quantity_conflict_issue"]["can_skip"]


def test_huaxing_duplicate_detector_normalizes_identity_and_distinguishes_quantity_change():
    records = [
        {"contract_no": "SC-100", "product_no": "ITEM 1", "quantity": "100.0"},
        {"contract_no": "SC-100", "product_no": "ITEM-1", "quantity": "120"},
    ]
    duplicate_count, conflict_count = huaxing._mark_existing_order_lines(
        records,
        [{"contract_no": "sc100", "product_no": "item1", "quantity": 100}],
        identity_fields=("contract_no", "product_no"),
    )

    assert (duplicate_count, conflict_count) == (1, 1)
    assert records[0]["_duplicate_existing"] is True
    assert records[1]["flags"][0]["code"] == "existing_quantity_conflict"


def test_huadeng_duplicate_detector_normalizes_identity_and_distinguishes_quantity_change():
    records = [
        {"contract_no": "SC-100", "product_no": "ITEM 1", "quantity": "100.0"},
        {"contract_no": "SC-100", "product_no": "ITEM-1", "quantity": "120"},
    ]
    duplicate_count, conflict_count = huadeng._mark_records_from_schedule(
        records,
        [{"contract_no": "sc100", "product_no": "item1", "quantity": 100}],
        record_order_fields=("contract_no",),
        record_item_fields=("product_no",),
        schedule_order_fields=("contract_no",),
        schedule_item_fields=("product_no",),
    )

    assert (duplicate_count, conflict_count) == (1, 1)
    assert records[0]["_duplicate_existing"] is True
    assert records[1]["flags"][0]["code"] == "existing_quantity_conflict"
    assert "duplicate_existing_order" in api.TEST_DUPLICATE_ISSUE_CODES
