"""A closed zero-arrival note can establish its real source before reopening."""
import json
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import BASE, setup_portal, supplier_login
from test_carton_procurement_api import _order_payload, _submit_order


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def test_closed_source_requires_complete_audit_and_no_historical_physical_arrival():
    from app.services.carton_supplier_portal import _closed_source_linkable
    shipment = SimpleNamespace(status="NOT_RECEIVED", receipt_id=None)
    paper = SimpleNamespace(id="paper", snapshot_json="{}")
    progress = {"paper": {"closed_quantity": Decimal(2)}}
    batch = {"acceptance": {"lines": [{"shipment_line_id": "paper", "received_quantity": "0"}]}}
    assert _closed_source_linkable(shipment, paper, [batch], progress)
    assert not _closed_source_linkable(shipment, paper, [], progress)
    assert not _closed_source_linkable(shipment, paper, [{"acceptance": {"lines": []}}], progress)
    assert not _closed_source_linkable(shipment, paper, [dict(batch, legacy_unsequenced=True)], progress)
    arrived = {"acceptance": {"lines": [{"shipment_line_id": "paper", "received_quantity": "1"}]}}
    assert not _closed_source_linkable(shipment, paper, [arrived], progress)
    assert not _closed_source_linkable(shipment, paper, [batch], {"paper": {"closed_quantity": Decimal(0)}})


def test_zero_arrival_note_links_real_source_then_reopens_and_posts_only_actual_arrival(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        from app.services import carton_procurement as core
        monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 11, 5, 12))
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.active.append(["送货单号", "日期", "客户", "客户单号", "客户料号", "名称", "纸质", "规格", "数量", "单价"])
        workbook.active.append(["CLOSED-UNKNOWN", "2026-09-25", "华兴", "REAL-LATER", "REAL-BOX", "外箱", "A33+B", "20*10*8 cm", 2, 2])
        stream = BytesIO(); workbook.save(stream); workbook.close()
        upload = {"file": ("原送货.xlsx", stream.getvalue())}
        preview = client.post(BASE + "/shipments/import-preview", files=upload).json()
        sent = client.post(BASE + "/shipments/import-confirm", files=upload, data={"sha256": preview["sha256"],
            "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "CLOSED-UNKNOWN"}])})
        assert sent.status_code == 200, sent.text
        original = sent.json()["shipments"][0]
        login_as(client, "admin")
        closed = client.post(BASE + f"/internal/shipments/{original['id']}/receive", json={"factory_id": "huaxing",
            "request_id": uuid4().hex, "expected_revision": original["revision"], "acceptance_date": "2026-09-26",
            "remaining_action": "CLOSE", "lines": [{"shipment_line_id": original["lines"][0]["id"],
                "received_quantity": "0", "unit_price": "2", "difference_reason": "核实整张原送货尚未到厂"}]})
        assert closed.status_code == 200, closed.text
        shipment = closed.json()
        source = shipment["lines"][0]
        assert shipment["status"] == "NOT_RECEIVED" and source["closed_source_linkable"]
        assert Decimal(source["closed_quantity"]) == 2
        group_url = "/api/carton-unified-deliveries/FORMAL:" + original["id"]
        unknown_reopen = {"factory_id": "huaxing", "request_id": uuid4().hex, "reason": "原关闭有误需要补齐来源",
            "formal": {"expected_revision": shipment["revision"], "lines": [{"shipment_line_id": source["id"], "quantity": "2"}]}}
        assert client.post(group_url + "/reopen-shortfall", json=unknown_reopen).status_code == 422

        target_body = _order_payload()
        target_body.update(contract_no="REAL-LATER", item_no="REAL-BOX")
        target_body["lines"] = [{**target_body["lines"][0], "specification": "20*10*8 cm", "dimension_unit": "cm"}]
        response = client.post("/api/carton-procurement/orders", json=target_body)
        assert response.status_code == 201, response.text
        target = _submit_order(client, response.json())
        link = {"factory_id": "huaxing", "expected_revision": shipment["revision"], "customer_code": "DICKIE",
            "expected_order_revision": target["revision"], "order_line_id": target["lines"][0]["id"],
            "reason": "原送货纸品已核实正式采购来源"}
        link_url = BASE + f"/internal/shipments/{shipment['id']}/lines/{source['id']}/link-order"
        assert client.post(link_url, json=link | {"expected_revision": 999}).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonInventoryMovement, CartonAuditEvent
        with SessionLocal() as db:
            initial = {row.id: row.detail_json for row in db.scalars(select(CartonAuditEvent))}
        response = client.post(link_url, json=link)
        assert response.status_code == 200, response.text
        linked = response.json()
        assert linked["status"] == "NOT_RECEIVED" and not linked.get("receipt_id")
        paper = linked["lines"][0]
        assert paper["source_type"] == "FORMAL_ORDER" and paper["original_unmatched_line_id"] == source["id"]
        assert Decimal(paper["received_quantity"]) == Decimal(paper["remaining_quantity"]) == 0
        assert Decimal(paper["closed_quantity"]) == 2
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonReceipt)) == 0
            assert db.scalar(select(func.count()).select_from(CartonInventoryMovement)) == 0
            assert all(db.scalar(select(CartonAuditEvent.detail_json).where(CartonAuditEvent.id == key)) == value for key, value in initial.items())
        assert client.post(link_url, json=link).status_code == 200
        supplier_login(client)
        current = next(row for row in client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"]
            if row["order_no"] == target["order_no"])
        approved = client.post(BASE + "/changes/respond", json={"factory_id": "huaxing", "source_kind": "REGULAR",
            "source_id": current["issue_id"], "expected_revision": current["revision"], "action": "ACCEPT",
            "promised_date": "2026-10-01", "request_id": uuid4().hex})
        assert approved.status_code == 200, approved.text
        login_as(client, "admin")
        body = {"factory_id": "huaxing", "request_id": uuid4().hex, "reason": "核实原关闭有误恢复两件待收",
            "formal": {"expected_revision": linked["revision"], "lines": [{"shipment_line_id": paper["id"], "quantity": "2"}]}}
        opened = client.post(group_url + "/reopen-shortfall", json=body)
        assert opened.status_code == 200, opened.text
        assert client.post(group_url + "/reopen-shortfall", json=body).json() == opened.json()
        assert Decimal(opened.json()["lines"][0]["remaining_quantity"]) == 2
        assert Decimal(opened.json()["lines"][0]["closed_quantity"]) == 0
        locations = client.get("/api/carton-procurement/inventory/locations", params={"factory_id": "huaxing"}).json()
        location = next(row["id"] for row in locations if row["bin_code"] == "A-01")
        result = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json={"factory_id": "huaxing",
            "request_id": uuid4().hex, "expected_revision": opened.json()["formal"]["revision"],
            "acceptance_date": "2026-10-02", "remaining_action": "WAIT", "lines": [{"shipment_line_id": paper["id"],
                "received_quantity": "2", "unit_price": "2", "location_allocations": [{"location_id": location, "quantity": "2"}]}]})
        assert result.status_code == 200, result.text
        assert Decimal(result.json()["lines"][0]["received_quantity"]) == 2
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonReceipt)) == 1
            assert db.scalar(select(func.count()).select_from(CartonInventoryMovement)) == 1
