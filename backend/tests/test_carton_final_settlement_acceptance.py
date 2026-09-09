"""Independent supplier acceptance oracles: evidence, not net totals, is authoritative."""
from decimal import Decimal as D
from test_molding_sample_api import make_client, login_as
from test_carton_transaction_guards_api import BASE, order, draft, confirm, outbound
from test_carton_supplier_settlement_api import clock, close_month, view, payload, action, post


def save(client, data):
    response = client.post(BASE + "/supplier-settlements", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_return_credit_needs_both_vendor_values_and_local_approval_and_cannot_overdraw(monkeypatch):
    with make_client(monkeypatch) as client:
        clock(monkeypatch)
        login_as(client, "carton_supervisor")
        row = order(client)
        login_as(client, "carton_supervisor")
        post(client, row, 10)
        returned = client.post(BASE + "/inventory/movements", json=outbound(row, 2, issue_kind="RETURN", document_no="FINAL-RETURN"))
        assert returned.status_code == 201, returned.text
        excessive = client.post(BASE + "/inventory/movements", json=outbound(row, 9, issue_kind="RETURN"))
        assert excessive.status_code == 409, excessive.text
        work = view(client)
        data = payload(work)
        credit = next(line for line in data["lines"] if line["source_key"].startswith("RETURN:"))
        credit.update(approved_return_unit_price="3", credit_document_no="FINAL-CREDIT", credit_date="2026-10-05", note="供应商签字认可退货单价")
        doc = save(client, data)
        assert D(doc["result"]["inbound_amount"]) == 20
        assert D(doc["result"]["return_amount"]) == 6
        assert D(doc["result"]["net_amount"]) == 14
        assert doc["result"]["statement_amount"] is None
        close_month(monkeypatch)
        blocked = action(client, doc)
        assert blocked.status_code == 409 and "尚未填齐" in blocked.text
        credit.update(quantity="2", unit_price="3", amount="5")
        data.update(id=doc["id"], expected_revision=doc["revision"])
        doc = save(client, data)
        blocked = action(client, doc)
        assert blocked.status_code == 409 and "差异" in blocked.text
        credit["amount"] = "6"
        data["expected_revision"] = doc["revision"]
        doc = save(client, data)
        assert not doc["result"]["issues"]
        done = action(client, doc)
        assert done.status_code == 200, done.text
        assert D(done.json()["result"]["statement_amount"]) == 14


def test_same_quantity_same_amount_receipt_replacement_invalidates_saved_evidence(monkeypatch):
    with make_client(monkeypatch) as client:
        clock(monkeypatch)
        login_as(client, "carton_supervisor")
        row = order(client)
        login_as(client, "carton_supervisor")
        receipt = post(client, row, 4)
        initial = view(client)
        doc = save(client, payload(initial))
        # Internal issue + its reversal changes inventory history, not supplier debt.
        issued = client.post(BASE + "/inventory/movements", json=outbound(row, 1))
        assert issued.status_code == 201, issued.text
        undo_issue = client.post(BASE + f"/inventory/movements/{issued.json()['id']}/reverse", json={"factory_id":"huaxing", "reason":"领料单误填撤销"})
        assert undo_issue.status_code == 201, undo_issue.text
        assert view(client)["source_fingerprint"] == initial["source_fingerprint"]
        reverse = client.post(BASE + f"/receipts/{receipt['id']}/reverse", json={"factory_id":"huaxing", "expected_revision":receipt["revision"], "reason":"收料凭据更正重录"})
        assert reverse.status_code == 200, reverse.text
        post(client, row, 4)
        replacement = view(client)
        assert D(replacement["sources"][0]["quantity"]) == D(initial["sources"][0]["quantity"]) == 4
        assert D(replacement["sources"][0]["amount"]) == D(initial["sources"][0]["amount"]) == 8
        assert replacement["source_fingerprint"] != initial["source_fingerprint"]
        assert replacement["documents"][0]["stale"] is True
        close_month(monkeypatch)
        blocked = action(client, doc)
        assert blocked.status_code == 409 and "来源已变化" in blocked.text
        updated = payload(replacement)
        updated.update(id=doc["id"], expected_revision=doc["revision"])
        doc = save(client, updated)
        done = action(client, doc)
        assert done.status_code == 200, done.text
        original_done = done.json()
        reopened = action(client, original_done, "reopen", reason="供应商补充凭据重新核对")
        assert reopened.status_code == 200, reopened.text
        versions = view(client)["documents"]
        assert [(version["version"], version["status"]) for version in versions] == [(2,"DRAFT"),(1,"SUPERSEDED")]
        assert versions[1]["sources"] == original_done["sources"]
        assert versions[1]["statement"] == original_done["statement"]
        assert versions[1]["result"] == original_done["result"]


def test_legacy_utc_return_timestamp_uses_shanghai_business_month(monkeypatch):
    from datetime import datetime
    with make_client(monkeypatch) as client:
        from app.services import carton_procurement as core
        monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 9, 30, 12, 0, 0))
        login_as(client, "carton_supervisor")
        row = order(client)
        login_as(client, "carton_supervisor")
        post(client, row, 4, "2026-09-30")
        clock(monkeypatch)
        returned = client.post(BASE + "/inventory/movements", json=outbound(row, 1, issue_kind="RETURN"))
        assert returned.status_code == 201, returned.text
        # A supported persisted ISO timestamp: 00:30 on October 1 in Shanghai.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement
        with SessionLocal() as db:
            movement = db.get(CartonInventoryMovement, returned.json()["id"])
            movement.occurred_at = "2026-09-30T16:30:00+00:00"
            db.commit()
        september = view(client, "2026-09")
        october = view(client, "2026-10")
        assert not [source for source in september["sources"] if source["kind"] == "RETURN"]
        returns = [source for source in october["sources"] if source["kind"] == "RETURN"]
        assert len(returns) == 1
        assert returns[0]["acceptance_date"] == "2026-10-01"
        data = payload(october)
        data["lines"][0].update(unit_price="2", amount="2", approved_return_unit_price="2",
            credit_document_no="UTC-CREDIT", credit_date="2026-10-01", note="核实跨月退货凭证")
        doc = save(client, data)
        close_month(monkeypatch)
        settled = action(client, doc)
        assert settled.status_code == 200, settled.text
        reverse = client.post(BASE + f"/inventory/movements/{returned.json()['id']}/reverse", json={"factory_id":"huaxing", "reason":"测试跨月锁账保护"})
        assert reverse.status_code == 409 and "供应商月份已确认" in reverse.text


def test_legacy_confirmation_guard_and_timestamp_variants_use_the_same_business_date(monkeypatch):
    from types import SimpleNamespace
    from app.services import carton_supplier_settlement as service
    for timestamp in ("2026-09-30T16:30:00Z", "2026-09-30T16:30:00+00:00", "2026-10-01T00:30:00+08:00", "2026-10-01T00:30:00"):
        assert service._posting_date(timestamp) == "2026-10-01"
    checked = []
    monkeypatch.setattr(service, "ensure_open", lambda db, factory, supplier, period: checked.append((factory,supplier,period)))
    receipt = SimpleNamespace(status="POSTED", acceptance_date=None, confirmed_at="2026-09-30T16:30:00Z", factory_id="huaxing", supplier_id="SUPPLIER")
    service.receipt_guard(None, receipt)
    assert checked == [("huaxing","SUPPLIER","2026-10")]
