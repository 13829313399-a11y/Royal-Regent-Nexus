"""Material grouping must preserve every purchase source and exact chase quantities."""
from copy import deepcopy
from decimal import Decimal

import pytest

from test_fabric_procurement import BASE, book, row, stored
from test_fabric_procurement_tracking import save
from test_molding_sample_api import login_as, make_client


def item(identifier, quantity="0.1", **facts):
    return {"id": identifier, "facts": {"supplier": "甲厂", "material_code": "001", "material_name": "白布", "unit": "码", "order_no": identifier, **facts},
            "warehouse_outstanding_quantity": quantity, "warehouse_received_quantity": "0.2", "promise_date": None, "tracking": {}}


def test_exact_identity_unknowns_conflicts_and_units_are_not_merged():
    from app.services.fabric_procurement_groups import material_groups
    rows = [item("1"), item("2", "0.2"), item("3", None), item("4", "8"),
            item("5", supplier="乙厂"), item("6", unit="米"), item("7", material_name="蓝布"),
            item("8", material_code=""), item("9", material_code="")]
    rows[3]["receipt_identity_review_required"] = True
    before = deepcopy(rows)
    groups = material_groups(rows, "OVERDUE")
    assert len(groups) == 6
    group = groups[0]
    assert group["line_count"] == 4 and group["order_count"] == 4
    assert group["remaining_quantity"] is None
    assert group["known_remaining_quantity"] == "0.3" and group["unknown_quantity_count"] == 2
    assert group["warehouse_received_quantity"] is None
    assert group["known_received_quantity"] == "0.6" and group["unknown_received_count"] == 1
    assert rows == before


def test_quantity_sort_uses_whole_group_sum_and_retains_unknown_last():
    from app.services.fabric_procurement_groups import material_groups
    rows = [item("A1", "6"), item("A2", "6"), item("B", "10", material_code="002"), item("C", None, material_code="003")]
    assert [g["material_code"] for g in material_groups(rows, "QUANTITY_DESC")] == ["001", "002", "003"]
    assert [g["material_code"] for g in material_groups(rows, "QUANTITY_ASC")] == ["002", "001", "003"]
    large = material_groups([item(str(n), "999999999999999.123456") for n in range(60)], "UPDATED")[0]
    assert large["remaining_quantity"] == "59999999999999947.40736"


def test_dates_counts_and_blank_identity_are_explicit():
    from app.services.fabric_procurement_groups import material_groups
    rows = [item("1", "0", order_no="PO1", production_no="P1"), item("2", "2", order_no="PO1", production_no="P2"),
            item("3", "3", source_category="SUPPLEMENT", supplement_no="SUP1")]
    rows[0].update(promise_date="2026-10-01", tracking={"overdue": True})
    rows[1].update(promise_date="2026-10-20", tracking={"changed": True})
    rows[2]["tracking"] = {"awaiting_date": True}
    group = material_groups(rows, "PROMISE")[0]
    assert (group["order_count"], group["production_count"], group["supplement_count"]) == (2, 2, 1)
    assert (group["earliest_promise"], group["latest_promise"]) == ("2026-10-01", "2026-10-20")
    assert group["remaining_quantity"] == "5" and group["unknown_quantity_count"] == 0
    assert group["overdue_count"] == group["changed_count"] == group["awaiting_date_count"] == 1


@pytest.mark.parametrize("field,value", [("unit", "米"), ("supplier", "乙厂"), ("material_code", "002"), ("material_name", "蓝布")])
def test_changed_source_identity_does_not_relabel_historical_receipts(field, value):
    from app.services.fabric_receiving import receipt_progress
    from app.services.fabric_procurement_groups import material_groups
    original = item("old", ordered_quantity="100", reported_received_quantity="0")
    changed = deepcopy(original)
    changed["facts"][field] = value
    changed.update(receipt_progress(changed["facts"], {"source_facts": original["facts"], "receipt_count": 1,
                    "prior_received_quantity": Decimal(0), "warehouse_received_quantity": Decimal(10)}))
    normal = item("new", **{field: value})
    normal["warehouse_received_quantity"] = "5"
    group = material_groups([changed, normal], "UPDATED")[0]
    assert group["line_count"] == 2
    assert group["warehouse_received_quantity"] is None
    assert group["known_received_quantity"] == "5" and group["unknown_received_count"] == 1


def test_group_endpoint_aggregates_before_pagination_and_drills_to_exact_originals(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        save(client, book([row(订单号=f"PO-{i:03d}", 订单数量="0.1", 入库数量=0, 交货明细="", 送货单号="") for i in range(60)]
                          + [row(订单号="OTHER", 物料编码="000124", 订单数量=10, 入库数量=0, 交货明细="", 送货单号="")]))
        originals = stored(client, view="OUTSTANDING", limit=200)
        groups = stored(client, view="OUTSTANDING", group_by="MATERIAL", sort="ORDER", limit=1)
        assert groups["total"] == 2 and groups["line_total"] == 61
        # ORDER selects OTHER first; the large material remains complete on page two.
        group = stored(client, view="OUTSTANDING", group_by="MATERIAL", sort="ORDER", offset=1, limit=1)["groups"][0]
        assert group["line_count"] == group["order_count"] == 60
        assert group["remaining_quantity"] == "6"
        detail = stored(client, view="OUTSTANDING", group_key=group["key"], limit=50)
        tail = stored(client, view="OUTSTANDING", group_key=group["key"], offset=50, limit=50)
        assert detail["total"] == tail["total"] == 60 and len(tail["items"]) == 10
        assert {v["id"] for v in detail["items"] + tail["items"]} == {v["id"] for v in originals["items"] if v["facts"]["material_code"] == "000123"}
        filtered = stored(client, view="OUTSTANDING", group_by="MATERIAL", search="PO-00")
        assert filtered["line_total"] == 10 and filtered["groups"][0]["remaining_quantity"] == "1"
        assert stored(client, view="OUTSTANDING", group_key="missing")["total"] == 0
        assert stored(client, view="OUTSTANDING", group_by="MATERIAL", supplier="不存在")["groups"] == []
        assert client.get(BASE + "/lines", params={"factory_id": "huakang-a", "group_by": "MATERIAL"}).status_code == 422
        login_as(client, "engineer")
        assert client.get(BASE + "/lines", params={"factory_id": "huakang-c", "group_by": "MATERIAL"}).status_code == 403
