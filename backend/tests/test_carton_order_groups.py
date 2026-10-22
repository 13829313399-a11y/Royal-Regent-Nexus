from copy import deepcopy
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare
from test_carton_procurement_api import _order_payload, _submit_order

BASE = "/api/carton-procurement"


def payload():
    rows = []
    for index in range(5):
        order = {**_order_payload(), "customer_po": f"PO-00{index}", "item_no": f"ITEM-{index}", "customer_due_date": "2026-10-30"}
        order["customer_code"] = "dickie"
        order["quantity_basis"] = "EXPLICIT"
        for line in order["lines"]:
            line["required_quantity"] = "30"
        rows.append({"row_id": f"ROW-{index}", "source": f"客户PO.xlsx / Sheet1 / {index + 2}", "order": order})
    return {"factory_id": "huaxing", "request_id": uuid4().hex, "name": "五PO合单", "rows": rows}


def orders(client):
    return client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"]


def test_convert_five_styles_is_atomic_replayable_and_preserves_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        body = payload()
        response = client.post(BASE + "/order-groups/convert", json=body)
        assert response.status_code == 201, response.text
        result = response.json()
        assert len(result) == 5
        assert {row["customer_po"] for row in result} == {f"PO-00{i}" for i in range(5)}
        assert all(row["status"] == "CONFIRMED" for row in result)
        assert all(row["due_date"] == "2026-10-27" for row in result)
        assert client.post(BASE + "/order-groups/convert", json=body).json() == result
        assert len(orders(client)) == 5
        changed = deepcopy(body); changed["rows"][0]["source"] = "不同来源"
        assert client.post(BASE + "/order-groups/convert", json=changed).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select
        import json
        with SessionLocal() as db:
            evidence = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == "ORDER_GROUP_SOURCE_LINKED")))
            assert len(evidence) == 5
            assert {json.loads(row.detail_json)["source"] for row in evidence} == {r["source"] for r in body["rows"]}
        assert client.get(BASE + "/inventory/movements", params={"factory_id": "huaxing"}).json()["total"] == 0


@pytest.mark.parametrize("failure", ["missing_contract", "missing_unit", "mixed_customer", "mixed_factory", "duplicate_identity", "business_rule"])
def test_incomplete_or_invalid_group_creates_no_partial_orders(monkeypatch, failure):
    with make_client(monkeypatch) as client:
        prepare(client); body = payload(); last = body["rows"][-1]["order"]
        if failure == "missing_contract": last["contract_no"] = ""
        elif failure == "missing_unit": last["lines"][0]["dimension_unit"] = ""
        elif failure == "mixed_customer": last["customer_code"] = "OTHER"
        elif failure == "mixed_factory": last["factory_id"] = "huakang-a"
        elif failure == "duplicate_identity":
            last["customer_po"] = body["rows"][0]["order"]["customer_po"]
            last["item_no"] = body["rows"][0]["order"]["item_no"]
        else: last["customer_code"] = body["rows"][0]["order"]["customer_code"]; last["master_config_id"] = "MISSING"
        response = client.post(BASE + "/order-groups/convert", json=body)
        assert response.status_code in {404, 409, 422}, response.text
        assert orders(client) == []


def test_missing_dimensions_block_supplier_issuance_without_rewriting_order(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client); body = _order_payload()
        body["lines"][0]["dimension_unit"] = ""
        created = client.post(BASE + "/orders", json=body)
        assert created.status_code == 201, created.text
        order = created.json()
        # Creation normalizes a blank unit; blank the stored line to exercise the issuance guard.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrderLine
        with SessionLocal() as db:
            line = db.get(CartonOrderLine, order["lines"][0]["id"])
            line.dimension_unit = ""
            db.commit()
        response = client.post(BASE + f"/orders/{order['order_no']}/submit-supplier", json={"factory_id": "huaxing", "expected_revision": order["revision"]})
        assert response.status_code == 422, response.text
        assert "尺寸单位" in response.text
        assert orders(client)[0]["status"] == "CONFIRMED"

        # Existing issued papers retain their original document/cancellation rules.
        legacy = client.post(BASE + "/orders", json={**_order_payload(), "customer_po": "LEGACY-UNIT-PO", "item_no": "LEGACY-UNIT-ITEM"})
        assert legacy.status_code == 201, legacy.text
        locked = _submit_order(client, legacy.json())
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrderLine
        with SessionLocal() as db:
            line = db.get(CartonOrderLine, locked["lines"][0]["id"])
            line.dimension_unit = ""
            db.commit()
        changed = client.post(BASE + f"/orders/{locked['order_no']}/dates", json={"factory_id": "huaxing", "expected_revision": locked["revision"], "customer_due_date": "2026-10-30", "reason": "客户调整历史交期"})
        assert changed.status_code == 200, changed.text
        document = client.post(BASE + f"/orders/{locked['order_no']}/purchase-order-issues.xlsx", json={"factory_id": "huaxing", "expected_revision": changed.json()["revision"]})
        assert document.status_code == 200, document.text
        cancelled = client.post(BASE + f"/orders/{locked['order_no']}/reduce", json={"factory_id": "huaxing", "expected_revision": changed.json()["revision"], "reduction_quantity": 3600, "reason": "客户取消历史订单"})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        from app.models.carton_procurement import CartonPurchaseOrderIssue
        from sqlalchemy import select
        import json
        with SessionLocal() as db:
            assert any(json.loads(issue.snapshot_json).get("cancellation") for issue in db.scalars(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id == locked["id"])))
        with SessionLocal() as db:
            assert db.get(CartonOrderLine, locked["lines"][0]["id"]).dimension_unit == ""
