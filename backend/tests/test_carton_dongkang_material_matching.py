"""Dongkang type aliases must not weaken material or unique-order checks."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
import json

import pytest

from test_carton_collaboration_corrections import delivery_file
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, accept_all, receive_payload, supplier_login, BASE


MATERIAL = {"packaging_type": "外箱", "paper_quality": "A=B",
            "specification": "30.4*21.5*30.4", "dimension_unit": "cm"}
SOURCE = {**MATERIAL, "packaging_type": "普通箱", "packaging_type_explicit": True,
          "specification": "30.4X21.5X30.4cm"}


@pytest.mark.parametrize("changes,expected", [
    ({}, []), ({"packaging_type": "内箱"}, ["纸品类型"]),
    ({"packaging_type": "隔板"}, ["纸品类型"]),
    ({"paper_quality": "H99"}, ["纸质"]),
    ({"specification": "99X21.5X30.4cm"}, ["规格"]),
    ({"dimension_unit": "inch"}, ["尺寸单位"]),
])
def test_dongkang_alias_is_explicit_and_keeps_other_identity_checks(changes, expected):
    from app.services.carton_material_identity import material_conflicts
    assert material_conflicts(SOURCE, MATERIAL | changes, dongkang_delivery=True) == expected
    assert material_conflicts(SOURCE, MATERIAL) == ["纸品类型"]
    assert SOURCE["packaging_type"] == "普通箱"


@pytest.mark.parametrize("case", ["unique", "wrong_type", "quality", "dimensions", "unit", "ambiguous", "no_order", "no_demand", "unaccepted", "over_quantity"])
def test_supplier_preview_alias_and_specific_conflicts(monkeypatch, case):
    from app.services import carton_supplier_delivery_import as service
    line = MATERIAL | {"id": "paper-1", "child_no": "P1", "required_quantity": "389",
        "remaining_to_ship": "389", "accepted": True, "shipping_blocked_reason": "", "unit": "个"}
    order = {"order_no": "ORDER-1", "contract_no": "4500223378-2", "item_no": "77903",
             "issue_id": "ISSUE-1", "revision": 1, "customer_po": "PO-1", "document_no": "ISSUE-1",
             "planned_date": "2026-10-15", "status": "PENDING_SUPPLIER", "awaiting_issue": False, "lines": [line]}
    expected_conflict = ""
    if case == "wrong_type": line["packaging_type"] = "内箱"; expected_conflict = "纸品类型"
    if case == "quality": line["paper_quality"] = "H99"; expected_conflict = "纸质"
    if case == "dimensions": line["specification"] = "99*88*77"; expected_conflict = "规格"
    if case == "unit": line["dimension_unit"] = "inch"; expected_conflict = "尺寸单位"
    if case == "unaccepted": line["accepted"] = False
    if case == "over_quantity": line["remaining_to_ship"] = "3"
    if case == "no_demand": line["required_quantity"] = "0"
    orders = [order]
    if case == "ambiguous":
        second = deepcopy(order) | {"order_no": "ORDER-2"}
        second["lines"][0]["id"] = "paper-2"
        orders.append(second)
    if case == "no_order": orders = []
    monkeypatch.setattr(service.portal, "supplier_factories", lambda *args: [SimpleNamespace(factory_id="huaxing")])
    monkeypatch.setattr(service.portal, "supplier_permission", lambda *args: True)
    monkeypatch.setattr(service.portal, "workspace", lambda *args: {"orders": orders})
    monkeypatch.setattr(service.portal, "supplier_access", lambda *args: SimpleNamespace(id="supplier-1"))
    monkeypatch.setattr(service.receipt_link, "matching_receipts", lambda *args, **kwargs: [])
    db = SimpleNamespace(scalar=lambda *args: None, get=lambda *args: SimpleNamespace(currency="CNY"))
    upload = delivery_file(order["contract_no"], order["item_no"], SOURCE)
    result = service.preview(db, None, *upload["file"])
    group = result["groups"][0]; row = group["rows"][0]
    assert row["packaging_type"] == "普通箱"
    assert group["ready"] is (case in {"unique", "no_order"})
    if expected_conflict:
        assert expected_conflict in row["reason"]
        assert "送货单：" in row["reason"] and "订单：" in row["reason"]
        if case == "wrong_type": assert "普通箱" in row["reason"] and "内箱" in row["reason"]
        else: assert "普通箱" not in row["reason"]
    elif case == "ambiguous":
        assert "多张订单" in row["reason"] and "明确选择" in row["reason"]
        assert row["status"] == "BLOCKED" and not row["order_line_id"]
        assert len(row["candidates"]) == 2
        assert {candidate["order_line_id"] for candidate in row["candidates"]} == {"paper-1", "paper-2"}
    elif case == "unaccepted": assert "接单" in row["reason"]
    elif case == "over_quantity": assert "超过剩余" in row["reason"]
    elif case == "no_demand": assert "没有需要发货的纸品" in row["reason"]
    elif case == "no_order": assert row["status"] == "AD_HOC_REVIEW" and not row["order_line_id"]
    else: assert row["order_line_id"] == "paper-1" and row["status"] == "READY"


def test_alias_import_preserves_original_and_warehouse_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        paper = next(line for line in order["lines"] if line["packaging_type"] == "外箱")
        upload = delivery_file(order["contract_no"], order["item_no"], paper, note="ALIAS-NOTE", packaging_type="普通箱", quantity=10)
        login_as(client, "warehouse_keeper")
        imported = client.post("/api/carton-procurement/receipt-imports", params={"factory_id": "huaxing"}, files=upload)
        assert imported.status_code == 201, imported.text
        legacy_row = imported.json()["parse_summary"]["rows"][0]
        assert legacy_row["match_status"] == "MATCHED" and legacy_row["order_line_id"] == paper["id"]
        assert legacy_row["source_material"]["packaging_type"] == "普通箱"
        supplier_login(client)
        preview = client.post(BASE + "/shipments/import-preview", files=upload)
        assert preview.status_code == 200 and preview.json()["groups"][0]["ready"], preview.text
        form = {"sha256": preview.json()["sha256"], "selections": json.dumps([
            {"factory_id": "huaxing", "delivery_note_no": "ALIAS-NOTE"}])}
        confirmed = client.post(BASE + "/shipments/import-confirm", data=form, files=upload)
        assert confirmed.status_code == 200, confirmed.text
        shipment = confirmed.json()["shipments"][0]
        retry = client.post(BASE + "/shipments/import-confirm", data=form, files=upload)
        assert retry.status_code == 200 and retry.json()["shipments"][0]["id"] == shipment["id"]
        login_as(client, "warehouse_keeper")
        internal = client.get(BASE + "/internal/workspace", params={"factory_id": "huaxing"}).json()
        sent = next(row for row in internal["shipments"] if row["id"] == shipment["id"])
        assert sent["lines"][0]["packaging_type"] == "外箱"
        assert sent["lines"][0]["source_material"]["packaging_type"] == "普通箱"
        assert not client.get("/api/carton-procurement/receipts", params={"factory_id": "huaxing"}).json()["items"]
        received = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=receive_payload(client, shipment))
        assert received.status_code == 200, received.text
        receipts = client.get("/api/carton-procurement/receipts", params={"factory_id": "huaxing"}).json()["items"]
        receipt = next(row for row in receipts if row["id"] == received.json()["receipt_id"])
        assert receipt["lines"][0]["packaging_type"] == "外箱"
        assert Decimal(str(receipt["lines"][0]["received_quantity"])) == 8
