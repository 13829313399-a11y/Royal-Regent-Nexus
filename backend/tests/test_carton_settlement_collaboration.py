import json
from datetime import datetime
from decimal import Decimal
import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import (BASE as PORTAL, setup_portal, accept_all, supplier_login,
    receive_payload, _dongkang_delivery_file, revoke_supplier_permission)
from test_carton_supplier_settlement_api import BASE, action


def received(client, monkeypatch, *, quantity=10, vendor_price=2, acceptance_date="2026-09-24", reject_last=False):
    setup_portal(client)
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 10, 5, 12))
    order = accept_all(client)
    upload = {"file": ("东康送货.xlsx", _dongkang_delivery_file(order, source_price=vendor_price))}
    preview = client.post(PORTAL + "/shipments/import-preview", files=upload)
    assert preview.status_code == 200, preview.text
    sent = client.post(PORTAL + "/shipments/import-confirm", files=upload, data={
        "sha256": preview.json()["sha256"], "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "DK-IMPORT-01"}])})
    assert sent.status_code == 200, sent.text
    shipment = sent.json()["shipments"][0]
    login_as(client, "warehouse_keeper")
    data = receive_payload(client, shipment)
    data["acceptance_date"] = acceptance_date
    for line in data["lines"]:
        line.update(received_quantity=quantity, difference_reason="供应商少送两件" if quantity != 10 else "",
                    location_allocations=[{**line["location_allocations"][0], "quantity": quantity}])
    if reject_last:
        data["lines"][-1].update(rejected_quantity=quantity, location_allocations=[], difference_reason="全部破损拒收不结款")
    posted = client.post(PORTAL + f"/internal/shipments/{shipment['id']}/receive", json=data)
    assert posted.status_code == 200, posted.text
    login_as(client, "carton_supervisor")
    return posted.json()


def workspace(client, period="2026-09"):
    response = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": period})
    assert response.status_code == 200, response.text
    return response.json()


def save(client, work, *, doc=None, lines=None):
    data = {"factory_id": "huaxing", "supplier_id": work["supplier_id"], "period": work["period"], "currency": "CNY",
        "origin": "COLLABORATION", "source_fingerprint": work["collaboration"]["source_fingerprint"],
        "statement_no": "协同月结-001", "same_price_basis": True,
        "lines": lines if lines is not None else work["collaboration"]["lines"]}
    if doc:
        data.update(id=doc["id"], expected_revision=doc["revision"])
    response = client.post(BASE + "/supplier-settlements", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def review(client, doc, decision="CONFIRMED", reason=""):
    return client.post(PORTAL + f"/settlements/{doc['id']}/review", json={"factory_id": "huaxing",
        "expected_revision": doc["revision"], "decision": decision, "reason": reason})


def test_auto_vendor_evidence_short_receipt_and_bilateral_confirmation(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch, quantity=8)
        work = workspace(client)
        assert all(Decimal(line["quantity"]) == 10 for line in work["collaboration"]["lines"])
        assert all(Decimal(row["quantity"]) == 8 for row in work["sources"])
        assert all(row["supplier_delivery"]["difference_reason"] == "供应商少送两件" for row in work["collaboration"]["sources"])
        doc = save(client, work)
        assert any("数量、单价或金额存在差异" in issue for issue in doc["result"]["issues"])
        supplier_login(client)
        assert review(client, doc).status_code == 409
        disputed = review(client, doc, "DISPUTED", "请核实少送数量")
        assert disputed.status_code == 200, disputed.text
        login_as(client, "carton_supervisor")
        lines = work["collaboration"]["lines"]
        for line in lines:
            line.update(quantity="8", amount="16.00")
        doc = save(client, work, doc=disputed.json(), lines=lines)
        assert any("核对依据" in issue for issue in doc["result"]["issues"])
        for line in lines:
            line["note"] = "供应商确认按实际验收量结算"
        doc = save(client, work, doc=doc, lines=lines)
        assert not doc["result"]["issues"] and "supplier_review" not in doc["result"]
        assert action(client, doc).status_code == 409
        supplier_login(client)
        listing = client.get(PORTAL + "/settlements/workspace", params={"factory_id": "huaxing", "period": "2026-09"})
        assert listing.status_code == 200 and listing.json()["documents"][0]["id"] == doc["id"]
        approved = review(client, doc)
        assert approved.status_code == 200, approved.text
        assert review(client, doc).status_code == 409  # Optimistic revision fences repeated reviews.
        login_as(client, "carton_supervisor")
        assert action(client, doc).status_code == 409
        finished = action(client, approved.json())
        assert finished.status_code == 200, finished.text
        assert finished.json()["result"]["supplier_review"]["decision"] == "CONFIRMED"
        reopened = action(client, finished.json(), "reopen", reason="核对供应商补充账单")
        assert reopened.status_code == 200 and "supplier_review" not in reopened.json()["result"]
        assert workspace(client)["documents"][1]["result"]["supplier_review"]["decision"] == "CONFIRMED"


def test_missing_vendor_price_never_copies_factory_price(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch, vendor_price=None)
        work = workspace(client)
        assert all(row["unit_price"] is not None for row in work["sources"])
        assert all(line["unit_price"] is None and line["amount"] is None for line in work["collaboration"]["lines"])
        doc = save(client, work)
        assert doc["result"]["statement_amount"] is None
        supplier_login(client)
        assert review(client, doc).status_code == 409


def test_cross_month_unsettled_and_manual_history_fallback(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch, acceptance_date="2026-10-02")
        september = workspace(client)
        assert september["sources"] == []
        assert september["collaboration"]["unsettled_shipments"][0]["reason"] == "按验收日期计入 2026-10"
        october = workspace(client, "2026-10")
        assert october["collaboration"]["sources"][0]["supplier_delivery"]["delivery_date"] == "2026-09-24"
        doc = save(client, october)
        supplier_login(client)
        assert review(client, doc).status_code == 409  # Current month cannot be finally acknowledged.
        login_as(client, "carton_supervisor")
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipment
        with SessionLocal() as db:
            shipment = db.get(SupplierShipment, october["collaboration"]["sources"][0]["supplier_delivery"]["shipment_id"])
            shipment.receipt_id = None
            db.commit()
        fallback = workspace(client, "2026-10")
        assert all(line["quantity"] is None for line in fallback["collaboration"]["lines"])
        assert all(row["supplier_delivery"] is None for row in fallback["collaboration"]["sources"])


def test_supplier_scope_read_only_permission_and_review_invalidation(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch)
        work = workspace(client)
        doc = save(client, work)
        supplier_login(client)
        assert client.get(PORTAL + "/settlements/workspace", params={"factory_id": "huadeng", "period": "2026-09"}).status_code == 403
        assert client.post(BASE + "/supplier-settlements", json={}).status_code == 422
        assert action(client, doc).status_code == 403
        revoke_supplier_permission("carton_supplier:approve")
        assert review(client, doc).status_code == 403
        assert client.get(PORTAL + "/settlements/workspace", params={"factory_id": "huaxing", "period": "2026-09"}).status_code == 200
        from test_carton_supplier_portal import restore_supplier_permission
        restore_supplier_permission("carton_supplier:approve")
        approved = review(client, doc)
        assert approved.status_code == 200, approved.text
        login_as(client, "carton_supervisor")
        revised = save(client, work, doc=approved.json())
        assert "supplier_review" not in revised["result"] and action(client, revised).status_code == 409
        supplier_login(client)
        approved = review(client, revised)
        assert approved.status_code == 200
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipmentLine
        with SessionLocal() as db:
            line = db.get(SupplierShipmentLine, doc["sources"][0]["supplier_delivery"]["line_id"])
            snapshot = json.loads(line.snapshot_json)
            snapshot["delivery_unit_price"] = "3"
            line.snapshot_json = json.dumps(snapshot)
            db.commit()
        assert review(client, approved.json()).status_code == 409
        login_as(client, "carton_supervisor")
        assert workspace(client)["documents"][0]["stale"] is True
        assert action(client, approved.json()).status_code == 409


def test_zero_effective_paper_remains_bilateral_evidence_and_internal_notes_stay_private(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch, reject_last=True)
        work = workspace(client)
        assert len(work["sources"]) == 1
        excluded = work["collaboration"]["unsettled_shipments"]
        assert len(excluded) == 1 and Decimal(excluded[0]["quantity"]) == 10
        assert excluded[0]["difference_reason"] == "全部破损拒收不结款"
        assert excluded[0]["reason"] == "有效验收为零，不计应结"
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceiptLine
        with SessionLocal() as db:
            line = db.get(CartonReceiptLine, work["sources"][0]["source_key"].split(":", 1)[1])
            line.feedback_note = "内部用途：秘密样品；需求人：内部张三"
            db.commit()
        work = workspace(client)
        doc = save(client, work)
        assert not doc["result"]["issues"]
        supplier_login(client)
        listing = client.get(PORTAL + "/settlements/workspace", params={"factory_id": "huaxing", "period": "2026-09"})
        assert listing.status_code == 200 and "秘密样品" not in listing.text and "内部张三" not in listing.text
        assert listing.json()["documents"][0]["result"]["unsettled_shipments"] == excluded
        assert review(client, doc).status_code == 200  # Acknowledges the explicit zero-payable evidence as well.


@pytest.mark.parametrize("raw_price", ["1e100", "2.1234567"])
def test_unsupported_original_vendor_price_stays_visible_and_saveable(monkeypatch, raw_price):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch, vendor_price=raw_price)
        work = workspace(client)
        for source in work["collaboration"]["sources"]:
            assert Decimal(source["supplier_delivery"]["original_unit_price"]) == Decimal(raw_price)
            assert source["supplier_delivery"]["unit_price"] is None
            assert "请按凭证核实" in source["supplier_delivery"]["price_warning"]
        doc = save(client, work)
        assert doc["result"]["statement_amount"] is None and doc["result"]["issues"]


def test_other_supplier_keeps_manual_flow_and_linked_vendor_cannot_bypass_review(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch)
        work = workspace(client)
        manual = {"factory_id": "huaxing", "supplier_id": work["supplier_id"], "period": "2026-09", "currency": "CNY",
            "origin": "MANUAL", "source_fingerprint": work["source_fingerprint"], "statement_no": "手工账单", "same_price_basis": True}
        assert client.post(BASE + "/supplier-settlements", json=manual).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id="OTHER-SUPPLIER", factory_id="huaxing", supplier_code="OTHER", supplier_name="未接入供方",
                status="ACTIVE", created_at="2026-09-01", updated_at="2026-09-01"))
            db.commit()
        response = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "supplier_id": "OTHER-SUPPLIER", "period": "2026-09"})
        assert response.status_code == 200 and response.json()["collaboration"] is None
        manual.update(supplier_id="OTHER-SUPPLIER", source_fingerprint=response.json()["source_fingerprint"])
        saved = client.post(BASE + "/supplier-settlements", json=manual)
        assert saved.status_code == 200 and saved.json()["statement"]["origin"] == "MANUAL"
