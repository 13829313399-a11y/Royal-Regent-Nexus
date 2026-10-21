"""Return evidence is append-only, scoped and independent of stock value."""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from threading import Barrier
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_settlement_collaboration import received
from test_carton_supplier_portal import supplier_login, revoke_supplier_permission, restore_supplier_permission
from test_carton_transaction_guards_api import BASE, outbound, ledger


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def detail(client, identifier, external=False):
    base = "/api/carton-supplier" if external else BASE
    response = client.get(f"{base}/returns/{identifier}", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def command(client, row, name, *, external=False, expected=200, **values):
    base = "/api/carton-supplier" if external else BASE
    payload = dict(factory_id="huaxing", request_id=uuid4().hex, expected_revision=row["revision"],
        source_fingerprint=row["source_fingerprint"], action=name, reason="核对真实退货及回款依据", **values)
    response = client.post(f"{base}/returns/{row['movement_id']}/actions", json=payload)
    assert response.status_code == expected, response.text
    return response.json(), payload


def returned(client, monkeypatch):
    received(client, monkeypatch)
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 12, 5, 12))
    order = client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"][0]
    response = client.post(BASE + "/inventory/movements", json=outbound(order, 2,
        issue_kind="RETURN", return_date="2026-09-28"))
    assert response.status_code == 201, response.text
    return detail(client, response.json()["id"]), order


def test_pending_date_chain_retains_earliest_unconfirmed_month_and_advances_after_recheck():
    from app.services import carton_return_collaboration as service
    state = dict(receipts=[dict(status="ACTIVE", date_fingerprint="A")],
        credits=[dict(status="CONFIRMED", confirmation_id="credit", confirmed_date_fingerprint="A")],
        supplier_date=None, internal_date=None)
    current = dict(return_date="2026-09-30", posting_date="2026-10-05", fingerprint="C")
    history = [dict(return_date="2026-07-30"),
        dict(before_date="2026-07-30", return_date="2026-08-31", before_fingerprint="A"),
        dict(before_date="2026-08-31", return_date="2026-09-30", before_fingerprint="B")]
    assert service._date_pending_periods(state, current, history) == {"2026-07", "2026-08", "2026-09"}
    state["supplier_date"] = dict(fingerprint="B")
    state["internal_date"] = dict(fingerprint="B", credit_event_id="credit")
    assert service._date_pending_periods(state, current, history) == {"2026-08", "2026-09"}
    # B's before_date belongs to the already rechecked A→B leg; only the
    # B→C transition remains unresolved once both parties confirmed B.
    history.append(dict(before_date="2026-09-30", return_date="2026-11-01", before_fingerprint="C"))
    current.update(return_date="2026-11-01", fingerprint="D")
    state["supplier_date"] = dict(fingerprint="C")
    state["internal_date"] = dict(fingerprint="C", credit_event_id="credit")
    assert service._date_pending_periods(state, current, history) == {"2026-09", "2026-11"}


def test_partial_dispute_credit_versions_and_refund_corrections_do_not_post_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        row, _ = returned(client, monkeypatch)
        initial_stock = ledger(client)
        identifier = row["movement_id"]
        supplier_login(client)
        row = detail(client, identifier, True)
        row, first = command(client, row, "RECEIVE", external=True,
            quantity="1", receipt_date="2026-09-29", document_no="SIGN-ONE")
        assert "PROPOSE_CREDIT" not in row["allowed_actions"]
        stale = dict(row, revision=row["revision"] - 1)
        command(client, stale, "DISPUTE", external=True, expected=409,
            quantity="1", receipt_date="2026-09-29", document_no="STALE")
        row, _ = command(client, row, "DISPUTE", external=True,
            quantity="1", receipt_date="2026-09-29", document_no="DAMAGED")
        assert row["receipt_status"] == "DISPUTED" and "PROPOSE_CREDIT" not in row["allowed_actions"]
        row, _ = command(client, row, "VOID", external=True, target_event_id=row["receipts"][-1]["id"])
        row, _ = command(client, row, "RECEIVE", external=True,
            quantity="1", receipt_date="2026-09-30", document_no="SIGN-TWO")
        row, _ = command(client, row, "PROPOSE_CREDIT", external=True,
            unit_price="3", credit_date="2026-09-30", document_no="CREDIT-OLD")
        row, _ = command(client, row, "PROPOSE_CREDIT", external=True,
            unit_price="4", credit_date="2026-09-30", document_no="CREDIT-NEW")
        assert [item["status"] for item in row["credits"]] == ["SUPERSEDED", "PROPOSED"]
        login_as(client, "carton_supervisor")
        row = detail(client, identifier)
        row, _ = command(client, row, "CONFIRM_CREDIT", target_event_id=row["credit"]["id"])
        assert row["credit"]["confirmation_id"] and "CONFIRM_CREDIT" not in row["allowed_actions"]
        supplier_login(client)
        row = detail(client, identifier, True)
        row, _ = command(client, row, "DECLARE_REFUND", external=True,
            kind="CASH", amount="3", refund_date="2026-10-01", document_no="CASH   THREE")
        cash_id = row["refunds"][0]["id"]
        command(client, row, "DECLARE_REFUND", external=True, expected=409,
            kind="CASH", amount="1", refund_date="2026-10-01", document_no=" CASH\tTHREE ")
        assert detail(client, identifier, True)["revision"] == row["revision"]
        row, _ = command(client, row, "DECLARE_REFUND", external=True,
            kind="CASH", amount="1", refund_date="2026-10-02", document_no="CASH-SECOND")
        second_id = row["refunds"][-1]["id"]
        login_as(client, "carton_supervisor")
        row = detail(client, identifier)
        row, _ = command(client, row, "CONFIRM_REFUND", target_event_id=cash_id,
            confirmation_reference="BANK  THREE")
        command(client, row, "CONFIRM_REFUND", target_event_id=second_id,
            confirmation_reference=" BANK\tTHREE ", expected=409)
        assert detail(client, identifier)["revision"] == row["revision"]
        supplier_login(client)
        row = detail(client, identifier, True)
        row, _ = command(client, row, "VOID", external=True, target_event_id=second_id)
        for amount in ("2", "3"):
            row, _ = command(client, row, "DECLARE_REFUND", external=True,
                kind="OFFSET", amount=amount, refund_date="2026-10-01", document_no="OFFSET-SAME-CREDIT")
        assert "DECLARE_REFUND" not in row["allowed_actions"]
        command(client, row, "DECLARE_REFUND", external=True, expected=422,
            kind="CASH", amount="1", refund_date="2026-10-01", document_no="OVER-ALLOCATED")
        login_as(client, "carton_supervisor")
        row = detail(client, identifier)
        assert cash_id in row["void_confirmation_required_event_ids"]
        command(client, row, "VOID", target_event_id=cash_id, expected=422)
        assert detail(client, identifier)["revision"] == row["revision"]
        supplier_login(client)
        row = detail(client, identifier, True)
        assert cash_id not in row["voidable_event_ids"]
        command(client, row, "VOID", external=True, target_event_id=cash_id, expected=403)
        row, _ = command(client, row, "PROPOSE_CREDIT", external=True,
            unit_price="5", credit_date="2026-09-30", document_no="MISTAKEN-REVISION")
        assert row["credit"]["id"] in row["voidable_event_ids"]
        row, _ = command(client, row, "VOID", external=True, target_event_id=row["credit"]["id"])
        assert D(row["credit"]["amount"]) == 8 and D(row["cash_confirmed_amount"]) == 3
        revoke_supplier_permission("carton_supplier:approve")
        # Current permissions apply even to a previously successful request.
        replay = client.post(f"/api/carton-supplier/returns/{identifier}/actions", json=first)
        assert replay.status_code == 403
        restore_supplier_permission("carton_supplier:approve")
        replay = client.post(f"/api/carton-supplier/returns/{identifier}/actions", json=first)
        assert replay.status_code == 200 and replay.json()["replayed"]
        assert replay.json()["revision"] == row["revision"]
        login_as(client, "carton_supervisor")
        row = detail(client, identifier)
        row, _ = command(client, row, "VOID", target_event_id=cash_id,
            confirmation_reference="BANK-CORRECTION-REFERENCE")
        assert D(row["cash_confirmed_amount"]) == 0
        assert row["refunds"][0]["status"] == "VOID" and row["refunds"][0]["confirmation_id"]
        supplier_login(client)
        row = detail(client, identifier, True)
        barrier = Barrier(2)
        def submit(index):
            payload = dict(factory_id="huaxing", request_id=uuid4().hex, expected_revision=row["revision"],
                source_fingerprint=row["source_fingerprint"], action="DECLARE_REFUND", kind="CASH", amount="3",
                refund_date="2026-11-01", document_no=f"CONCURRENT-{index}", reason="并发核对真实退货退款凭证")
            barrier.wait(timeout=10)
            return client.post(f"/api/carton-supplier/returns/{identifier}/actions", json=payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, (1, 2)))
        assert sorted(response.status_code for response in responses) == [200, 409]
        current = detail(client, identifier, True)
        assert current["revision"] == row["revision"] + 1
        assert sum(D(item["amount"]) for item in current["refunds"] if item["status"] in {"PROPOSED", "CONFIRMED"}) == 8
        login_as(client, "carton_supervisor")
        assert ledger(client) == initial_stock


def test_large_credit_and_cash_evidence_fail_atomically_and_other_supplier_stays_manual(monkeypatch):
    with make_client(monkeypatch) as client:
        row, order = returned(client, monkeypatch)
        identifier = row["movement_id"]
        supplier_login(client)
        row = detail(client, identifier, True)
        row, _ = command(client, row, "RECEIVE", external=True,
            quantity="2", receipt_date="2026-09-29", document_no="SIGN-LARGE")
        # Deliberately seed a valid large source in this disposable test DB.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement, CartonSupplier
        from app.services import carton_return_collaboration as service
        with SessionLocal() as db:
            movement = db.get(CartonInventoryMovement, identifier)
            movement.quantity = D("10001") * -1
            receipt = service.events(db, "huaxing", identifier)[-1]
            import json
            evidence = json.loads(receipt.detail_json)
            evidence["data"]["quantity"] = "10001"
            receipt.detail_json = json.dumps(evidence)
            db.commit()
        row = detail(client, identifier, True)
        command(client, row, "PROPOSE_CREDIT", external=True, expected=422,
            unit_price="999999999999.999999", credit_date="2026-09-30", document_no="OVERFLOW-CREDIT")
        assert detail(client, identifier, True)["revision"] == row["revision"]
        with SessionLocal() as db:
            db.get(CartonInventoryMovement, identifier).quantity = D("-2")
            receipt = service.events(db, "huaxing", identifier)[-1]
            evidence = json.loads(receipt.detail_json); evidence["data"]["quantity"] = "2"
            receipt.detail_json = json.dumps(evidence); db.commit()
        row = detail(client, identifier, True)
        row, _ = command(client, row, "PROPOSE_CREDIT", external=True,
            unit_price="999999999999", credit_date="2026-09-30", document_no="LARGE-CREDIT")
        login_as(client, "carton_supervisor")
        row = detail(client, identifier)
        row, _ = command(client, row, "CONFIRM_CREDIT", target_event_id=row["credit"]["id"])
        supplier_login(client)
        row = detail(client, identifier, True)
        command(client, row, "DECLARE_REFUND", external=True, expected=422,
            kind="CASH", amount="1000000000000", refund_date="2026-10-01", document_no="OVERFLOW-CASH")
        assert detail(client, identifier, True)["revision"] == row["revision"]
        login_as(client, "carton_supervisor")
        with SessionLocal() as db:
            supplier = db.get(CartonSupplier, order["supplier_id"])
            supplier.supplier_code = "MANUAL-ONLY-TEST"
            db.commit()
        made = client.post(BASE + "/inventory/movements", json=outbound(order, 1,
            issue_kind="RETURN", return_date="2026-09-28", document_no="OTHER-SUPPLIER-RETURN"))
        assert made.status_code == 201, made.text
        other = detail(client, made.json()["id"])
        assert other["legacy"] and not other["pending"] and "ENROLL" not in other["allowed_actions"]
        command(client, other, "ENROLL", expected=409)
