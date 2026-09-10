from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from test_molding_sample_api import make_client, login_as
from test_carton_transaction_guards_api import BASE, order, draft, confirm, outbound


def clock(monkeypatch):
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 10, 5, 12, 0, 0))


def close_month(monkeypatch):
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 11, 5, 12, 0, 0))


def view(client, period="2026-10", **extra):
    response = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": period, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def payload(workspace):
    return {"factory_id": "huaxing", "supplier_id": workspace["supplier_id"], "period": workspace["period"],
            "currency": "CNY", "source_fingerprint": workspace["source_fingerprint"], "statement_no": "BILL-001",
            "same_price_basis": True, "tax_basis": "INCLUSIVE", "lines": [
                {"id": str(i), "source_key": row["source_key"], "document_no": row["document_no"],
                 "quantity": row["quantity"], "unit_price": row["unit_price"], "amount": row["amount"]}
                for i, row in enumerate(workspace["sources"])]}


def action(client, doc, name="confirm", **extra):
    return client.post(BASE + f"/supplier-settlements/{doc['id']}/{name}", json={
        "factory_id": "huaxing", "expected_revision": doc["revision"], **extra})


def post(client, row, qty=4, acceptance="2026-10-02"):
    response = draft(client, row, qty, acceptance_date=acceptance)
    assert response.status_code == 201, response.text
    response = confirm(client, response.json())
    assert response.status_code == 200, response.text
    return response.json()


def test_acceptance_month_partial_receipts_consumption_and_confirmed_guard(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_supervisor"); clock(monkeypatch)
        row = order(client)
        login_as(client, "carton_supervisor")
        september = post(client, row, 4, "2026-09-30")
        october = post(client, row, 6, "2026-10-02")
        assert len(view(client, "2026-09")["sources"]) == 1
        work = view(client)
        assert len(work["sources"]) == 1 and Decimal(work["sources"][0]["amount"]) == 12
        assert work["sources"][0]["acceptance_date"] == "2026-10-02"
        assert client.post(BASE + "/inventory/movements", json=outbound(row, 2)).status_code == 201
        assert view(client)["source_fingerprint"] == work["source_fingerprint"]
        saved = client.post(BASE + "/supplier-settlements", json=payload(work))
        assert saved.status_code == 200, saved.text
        early = action(client, saved.json())
        assert early.status_code == 409 and "本月尚未结束" in early.text
        close_month(monkeypatch)
        finished = action(client, saved.json())
        assert finished.status_code == 200, finished.text
        finished = finished.json()
        assert Decimal(finished["result"]["net_amount"]) == 12
        blocked = client.post(BASE + f"/receipts/{october['id']}/reverse", json={"factory_id": "huaxing", "expected_revision": october["revision"], "reason": "纠正原收料单据"})
        assert blocked.status_code == 409, blocked.text
        blocked = client.post(BASE + f"/receipts/{october['id']}/acceptance-date", json={"factory_id": "huaxing", "expected_revision": october["revision"], "acceptance_date": "2026-09-30", "reason": "核实实际验收日期"})
        assert blocked.status_code == 409
        assert action(client, finished, "reopen", reason="").status_code == 409
        reopened = action(client, finished, "reopen", reason="供应商补充新账单")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["version"] == 2 and reopened.json()["status"] == "DRAFT"
        assert view(client)["documents"][1]["status"] == "SUPERSEDED"


def test_missing_extra_duplicate_price_difference_stale_and_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_supervisor"); clock(monkeypatch)
        row = order(client)
        login_as(client, "carton_supervisor"); receipt = post(client, row)
        work = view(client); data = payload(work)
        data["lines"][0]["unit_price"] = "3"
        data["lines"][0]["amount"] = "12"
        data["lines"].append({"id": "extra", "document_no": "missing receipt", "quantity": "1", "unit_price": "1", "amount": "1"})
        data["lines"].append({**data["lines"][0], "id": "duplicate"})
        saved = client.post(BASE + "/supplier-settlements", json=data).json()
        assert any("差异" in msg for msg in saved["result"]["issues"])
        assert any("重复匹配" in msg for msg in saved["result"]["issues"])
        assert any("本期没有" in msg for msg in saved["result"]["issues"])
        close_month(monkeypatch)
        assert action(client, saved).status_code == 409
        correct = {**payload(work), "id": saved["id"], "expected_revision": saved["revision"]}
        saved = client.post(BASE + "/supplier-settlements", json=correct).json()
        assert client.post(BASE + "/supplier-settlements", json=correct).status_code == 409
        post(client, row, 2)
        assert action(client, saved).status_code == 409
        login_as(client, "warehouse_keeper")
        assert client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huadeng", "period": "2026-10"}).status_code == 403
        assert action(client, saved).status_code == 403


def test_legacy_acceptance_correction_missing_price_and_reversal(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_supervisor"); clock(monkeypatch)
        row = order(client)
        login_as(client, "carton_supervisor")
        receipt = confirm(client, draft(client, row, 4).json()).json()
        work = view(client)
        assert work["undated_receipts"][0]["receipt_id"] == receipt["id"]
        assert work["issues"]
        change = {"factory_id": "huaxing", "expected_revision": receipt["revision"], "reason": "实际验收签收记录", "acceptance_date": "2026-10-06"}
        assert client.post(BASE + f"/receipts/{receipt['id']}/acceptance-date", json=change).status_code == 422
        change["acceptance_date"] = "2026-09-30"
        updated = client.post(BASE + f"/receipts/{receipt['id']}/acceptance-date", json=change)
        assert updated.status_code == 200, updated.text
        assert not view(client)["sources"] and len(view(client, "2026-09")["sources"]) == 1
        updated = updated.json()
        reversed_response = client.post(BASE + f"/receipts/{receipt['id']}/reverse", json={"factory_id": "huaxing", "expected_revision": updated["revision"], "reason": "误录收料整单更正"})
        assert reversed_response.status_code == 200, reversed_response.text
        assert not view(client, "2026-09")["sources"]
        zero = draft(client, row, 2, acceptance_date="2026-10-02", lines=[{"order_line_id": row["lines"][0]["id"], "delivered_quantity": "2", "received_quantity": "2", "unit_price": "0"}])
        assert confirm(client, zero.json()).status_code == 422
        # New receipts require a positive price. Seed a legacy already-posted
        # unpriced record separately to retain the month-end compatibility check.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceiptLine, CartonInventoryMovement
        from sqlalchemy import select
        with SessionLocal() as db:
            line = db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == zero.json()["id"]))
            line.unit_price = Decimal("2")
            db.commit()
        assert confirm(client, zero.json()).status_code == 200
        with SessionLocal() as db:
            line = db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == zero.json()["id"]))
            line.unit_price = Decimal("0")
            for movement in db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.source_type == "RECEIPT", CartonInventoryMovement.source_id == zero.json()["id"])):
                movement.unit_price = Decimal("0")
            db.commit()
        work = view(client)
        assert work["sources"][0]["amount"] is None
        saved = client.post(BASE + "/supplier-settlements", json=payload(work)).json()
        assert saved["result"]["inbound_amount"] is None
        assert saved["result"]["statement_amount"] is None
        close_month(monkeypatch)
        assert action(client, saved).status_code == 409


def test_supplier_return_uses_approved_credit_not_average_cost_and_concurrent_confirm(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    with make_client(monkeypatch) as client:
        login_as(client, "admin"); clock(monkeypatch)
        row = order(client)
        login_as(client, "carton_supervisor")
        post(client, row, 10)
        returned = client.post(BASE + "/inventory/movements", json=outbound(row, 2, issue_kind="RETURN", document_no="RETURN-1"))
        assert returned.status_code == 201, returned.text
        work = view(client)
        return_source = next(source for source in work["sources"] if source["kind"] == "RETURN")
        assert return_source["unit_price"] is None  # Inventory cost is 2, not a supplier credit price.
        data = payload(work)
        return_line = next(line for line in data["lines"] if line["source_key"] == return_source["source_key"])
        return_line.update(quantity="2", unit_price="3", amount="6")
        saved = client.post(BASE + "/supplier-settlements", json=data).json()
        assert action(client, saved).status_code == 409
        return_line.update(approved_return_unit_price="3", credit_document_no="CREDIT-1", credit_date="2026-10-05", note="采购主管核实供应商退货凭证")
        data.update(id=saved["id"], expected_revision=saved["revision"])
        saved_response = client.post(BASE + "/supplier-settlements", json=data)
        assert saved_response.status_code == 200, saved_response.text
        saved = saved_response.json()
        assert Decimal(saved["result"]["net_amount"]) == 14
        close_month(monkeypatch)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: action(client, saved), range(2)))
        assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
        # More ordinary consumption does not alter supplier settlement.
        assert client.post(BASE + "/inventory/movements", json=outbound(row, 1)).status_code == 201
        assert client.post(BASE + "/inventory/movements", json=outbound(row, 1, issue_kind="RETURN")).status_code == 201
        assert view(client)["documents"][0]["stale"] is False
        original_id = returned.json()["id"]
        reverse = client.post(BASE + f"/inventory/movements/{original_id}/reverse", json={"factory_id": "huaxing", "reason": "更正错误退货记录"})
        assert reverse.status_code == 409, reverse.text


def test_whole_order_return_and_supplier_mismatch_are_not_silently_misclassified(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin"); clock(monkeypatch)
        row = order(client)
        login_as(client, "carton_supervisor")
        # A second active supplier is legal data, but cannot receive another supplier's order.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id="OTHER-SUPPLIER", factory_id="huaxing", supplier_code="OTHER", supplier_name="另一个供应商",
                status="ACTIVE", created_at="2026-10-01", updated_at="2026-10-01"))
            db.commit()
        rejected = draft(client, row, 2, acceptance_date="2026-10-02", supplier_id="OTHER-SUPPLIER")
        assert rejected.status_code == 422, rejected.text
        post(client, row, 4)
        current = client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"][0]
        returned = client.post(BASE + f"/orders/{row['order_no']}/return", json={"factory_id": "huaxing", "expected_revision": current["revision"], "reason": "全部库存退给供应商"})
        assert returned.status_code == 200, returned.text
        work = view(client)
        assert len(work["sources"]) == 2
        assert {source["kind"] for source in work["sources"]} == {"RECEIPT", "RETURN"}
        assert next(source for source in work["sources"] if source["kind"] == "RETURN")["quantity"] == "4.0000"
        assert view(client, supplier_id="OTHER-SUPPLIER")["sources"] == []
