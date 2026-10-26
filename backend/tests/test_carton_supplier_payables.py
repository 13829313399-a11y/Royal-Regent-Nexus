"""Owner regressions for evidence identity, replacement holds and account isolation."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login
from test_carton_settlement_collaboration import received

BASE = "/api/carton-procurement/payables"
VENDOR = "/api/carton-supplier/payables"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def workspace(client, external=False):
    response = client.get((VENDOR if external else BASE) + "/workspace", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def action(client, name, *, external=False, status=200, **values):
    current = workspace(client, external)
    command = dict(factory_id="huaxing", supplier_id=current["supplier_id"], currency="CNY", expected_revision=current["revision"],
        source_fingerprint=current["source_fingerprint"], request_id=uuid4().hex, reason="双方核对本笔真实往来凭证", action=name, **values)
    response = client.post((VENDOR if external else BASE) + "/actions", json=command)
    assert response.status_code == status, response.text
    return response.json(), command


def bilateral(client, kind, **values):
    login_as(client, "carton_supervisor")
    proposed, _ = action(client, "PROPOSE_" + kind, **values)
    identifier = proposed["changed_record_id"]
    supplier_login(client)
    action(client, "REVIEW_" + kind, external=True, target_id=identifier, decision="CONFIRMED")
    login_as(client, "carton_supervisor")
    result, _ = action(client, "CONFIRM_" + kind, target_id=identifier)
    return result, identifier


def clock(monkeypatch):
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 11, 5, 12))


def test_payment_identity_fee_replacement_hold_and_preserved_cash(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); clock(monkeypatch)
        login_as(client, "carton_supervisor")
        unopened = workspace(client)
        assert unopened["opening"] is None and unopened["issues"]
        assert client.get(BASE + "/workspace", params={"factory_id": "huaxing", "kind": "NONSENSE"}).status_code == 422
        action(client, "RECORD_PAYMENT", status=409, amount="20", payment_date="2026-10-02", document_no="pre-open", bank_reference="pre-bank")
        opened, _ = bilateral(client, "OPENING", cutoff_date="2026-10-01", direction="PAYABLE", amount="10", document_no="O-1")
        assert Decimal(opened["summary"]["balance_due_signed"]) == 10
        from app.services import carton_procurement as core
        original_lock, calls = core._lock_receipt_factory, []
        def observed_lock(db, factory):
            calls.append(factory); return original_lock(db, factory)
        with monkeypatch.context() as scoped:
            scoped.setattr(core, "_lock_receipt_factory", observed_lock)
            snapshot = workspace(client)
            read_detail = client.get(BASE + "/records/" + snapshot["opening"]["id"], params={"factory_id": "huaxing"})
            assert read_detail.status_code == 200 and read_detail.json()["account_revision"] == snapshot["revision"]
            assert calls == ["huaxing", "huaxing"]
        fee, fee_id = bilateral(client, "FEE", fee_date="2026-10-02", direction="ADD_PAYABLE", category="FREIGHT", amount="5", document_no="Fee-001")
        action(client, "PROPOSE_FEE", status=409, fee_date="2026-10-02", direction="ADD_PAYABLE", category="OTHER", amount="5", document_no="ＦＥＥ-００１")
        paid, original = action(client, "RECORD_PAYMENT", amount="30", payment_date="2026-10-03", document_no="Pay-001", bank_reference="BANK-001")
        payment_id = paid["changed_record_id"]
        pending = client.get(BASE + "/workspace", params={"factory_id": "huaxing", "status": "PENDING"})
        assert pending.status_code == 200 and payment_id in {row["id"] for row in pending.json()["records"]["items"]}
        action(client, "RECORD_PAYMENT", status=409, amount="30", payment_date="2026-10-03", document_no="different-no", bank_reference="ｂａｎｋ-００１")
        replay = client.post(BASE + "/actions", json=original)
        assert replay.status_code == 200 and replay.json()["replayed"]
        supplier_login(client)
        action(client, "RECEIVE_PAYMENT", external=True, target_id=payment_id, decision="CONFIRMED")
        action(client, "DECLARE_PAYMENT_RETURN", external=True, status=422, parent_payment_id=payment_id, amount="1", return_date="2026-10-02", document_no="R-too-early", bank_reference="IN-too-early")
        login_as(client, "carton_supervisor")
        revised, _ = action(client, "REVISE_FEE", target_id=fee_id, fee_date="2026-10-02", direction="ADD_PAYABLE", category="FREIGHT", amount="7", document_no="Fee-001")
        obligation = next(row for row in revised["obligations"] if row["kind"] == "FEE")
        assert obligation["status"] == "REOPENED_HOLD" and not obligation["can_allocate"]
        assert Decimal(revised["summary"]["fees_signed"]) == 5
        action(client, "ALLOCATE", status=409, source_kind="PAYMENT", source_id=payment_id, targets=[dict(target_kind="FEE", target_id=obligation["id"], amount="1")])
        supplier_login(client)
        action(client, "REVIEW_FEE", external=True, target_id=fee_id, decision="CONFIRMED")
        login_as(client, "carton_supervisor")
        final, _ = action(client, "CONFIRM_FEE", target_id=fee_id)
        obligation = next(row for row in final["obligations"] if row["kind"] == "FEE")
        assigned, _ = action(client, "ALLOCATE", source_kind="PAYMENT", source_id=payment_id, targets=[dict(target_kind="FEE", target_id=obligation["id"], amount="7")])
        allocation = assigned["allocations"][0]
        assert allocation["source_document_no"] == "Pay-001" and allocation["target_document_no"] == "Fee-001" and allocation["target_version"] == 2
        assert Decimal(assigned["summary"]["balance_due_signed"]) == -13
        action(client, "DEALLOCATE", allocation_ids=[allocation["id"]])
        before = workspace(client)["summary"]["internal_paid"]
        requested, _ = action(client, "REQUEST_VOID", target_id=payment_id, correction_reference="ERR-1")
        assert requested["summary"]["internal_paid"] == before
        supplier_login(client)
        action(client, "REVIEW_VOID", external=True, target_id=payment_id, decision="CONFIRMED")
        login_as(client, "carton_supervisor")
        voided, _ = action(client, "CONFIRM_VOID", target_id=payment_id, correction_reference="ERR-1-FINAL")
        assert Decimal(voided["summary"]["internal_paid"]) == 0
        exported = client.get(BASE + "/export", params={"factory_id": "huaxing"})
        assert exported.status_code == 200 and "Pay-001" in exported.text and "Fee-001" in exported.text
        pending_fee, _ = action(client, "PROPOSE_FEE", fee_date="2026-10-02", direction="ADD_PAYABLE", category="OTHER", amount="20", document_no="WITHDRAW-UNAPPROVED")
        pending_id = pending_fee["changed_record_id"]
        action(client, "VOID_FEE", target_id=pending_id)
        supplier_login(client)
        action(client, "REVIEW_FEE", external=True, target_id=pending_id, decision="CONFIRMED")
        login_as(client, "carton_supervisor")
        withdrawn, _ = action(client, "CONFIRM_FEE", target_id=pending_id)
        assert Decimal(withdrawn["summary"]["fees_signed"]) == 7
        assert next(row for row in withdrawn["records"]["items"] if row["id"] == pending_id)["status"] == "VOID"


def test_opening_unknown_currency_price_and_proposal_freshness(monkeypatch):
    with make_client(monkeypatch) as client:
        received(client, monkeypatch); clock(monkeypatch)
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonReceiptLine
        with SessionLocal() as db:
            original = db.scalar(select(CartonReceipt).where(CartonReceipt.status == "POSTED"))
            original.acceptance_date = None
            original_id, original_revision = original.id, original.revision
            db.commit()
        def add_unknown(currency, number):
            with SessionLocal() as db:
                receipt = db.scalar(select(CartonReceipt).where(CartonReceipt.status == "POSTED"))
                line = db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == receipt.id))
                r = {column.name: getattr(receipt, column.name) for column in receipt.__table__.columns}
                r.update(id="CR-" + uuid4().hex, delivery_note_no=number, acceptance_date=None, confirmed_at="2026-11-02T00:00:00Z")
                p = {column.name: getattr(line, column.name) for column in line.__table__.columns}
                p.update(id="CRL-" + uuid4().hex, receipt_id=r["id"], currency=currency)
                db.add(CartonReceipt(**r)); db.add(CartonReceiptLine(**p)); db.commit()
                return p["id"]
        baseline, opening_id = bilateral(client, "OPENING", cutoff_date="2026-10-01", direction="PAYABLE", amount="30", document_no="O-BASE", acknowledge_unknown_sources=True)
        assert baseline["opening"]["active"]["baseline_periods"] == []
        from app.services import carton_supplier_settlement as settlement
        source_reader = settlement.sources
        def navigation_only(*args):
            rows, fingerprint, issues, undated = source_reader(*args)
            for row in rows: row["delivery_id"] = "ONLY-A-NAVIGATION-CHANGE"
            return rows, fingerprint, issues, undated
        with monkeypatch.context() as scoped:
            scoped.setattr(settlement, "sources", navigation_only)
            assert workspace(client)["source_fingerprint"] == baseline["source_fingerprint"]
        add_unknown("HKD", "HKD-UNKNOWN")
        stable = workspace(client)
        assert stable["source_fingerprint"] == baseline["source_fingerprint"] and not stable["summary"]["needs_reconfirmation"]
        unknown_id = add_unknown("CNY", "CNY-UNKNOWN")
        drift = workspace(client)
        assert drift["summary"]["needs_reconfirmation"] and len(drift["opening"]["unknown_sources"]) == 2
        action(client, "PROPOSE_OPENING", status=409, cutoff_date="2026-10-01", direction="PAYABLE", amount="30", document_no="O-NO-ACK")
        action(client, "PROPOSE_OPENING", cutoff_date="2026-10-01", direction="PAYABLE", amount="30", document_no="O-ACK", acknowledge_unknown_sources=True)
        supplier_login(client)
        action(client, "REVIEW_OPENING", external=True, target_id=opening_id, decision="CONFIRMED")
        with SessionLocal() as db:
            db.get(CartonReceiptLine, unknown_id).unit_price = Decimal("9")
            db.commit()
        login_as(client, "carton_supervisor")
        action(client, "CONFIRM_OPENING", status=409, target_id=opening_id)
        before_date = workspace(client)["source_fingerprint"]
        dated = client.post("/api/carton-procurement/receipts/" + original_id + "/acceptance-date", json=dict(factory_id="huaxing",
            expected_revision=original_revision, acceptance_date="2026-09-24", reason="核实原始实际验收日期"))
        assert dated.status_code == 200, dated.text
        after_date = workspace(client)
        assert after_date["summary"]["needs_reconfirmation"] and after_date["source_fingerprint"] != before_date
        assert len(after_date["opening"]["unknown_sources"]) == 1


def test_csv_text_formula_escaping_preserves_signed_amounts(monkeypatch):
    from app.services import carton_supplier_payables as service
    summary = {key: "-12.00" for key in ("opening_signed", "confirmed_settlements", "fees_signed", "internal_paid", "payment_returns_confirmed", "balance_due_signed")}
    value = dict(supplier_name="=SUPPLIER", currency="CNY", summary=summary, issues=[], records={"items": [dict(id="ID", kind="FEE", status="PENDING_SUPPLIER",
        document_no="=SUM(1)", amount="12.00", signed_amount="-12.00", reason="@command", active=dict(version=1, signed_amount="-10.00"), proposal=dict(version=2, signed_amount="-12.00"))]}, obligations=[], allocations=[])
    monkeypatch.setattr(service, "workspace", lambda *args, **kwargs: value)
    output = service.export_csv(None, None, "huaxing")
    assert "'=SUPPLIER" in output and "'=SUM(1)" in output and "'@command" in output
    assert "-12.00" in output and "'-12.00" not in output


def test_initial_opening_publishes_only_its_authorized_factory_without_purchase_order(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); clock(monkeypatch)
        assert client.get(VENDOR + "/workspace", params={"factory_id": "huadeng"}).status_code == 403
        memberships = client.get("/api/carton-supplier/memberships").json()
        assert "huadeng" not in {row["factory_id"] for row in memberships}
        login_as(client, "admin")
        initial = client.get(BASE + "/workspace", params={"factory_id": "huadeng"})
        assert initial.status_code == 200, initial.text
        current = initial.json()
        def command(name, values):
            return dict(factory_id="huadeng", supplier_id=current["supplier_id"], currency="CNY", expected_revision=current["revision"],
                source_fingerprint=current["source_fingerprint"], request_id=uuid4().hex, reason="双方书面确认华登切账期初", action=name, **values)
        proposal = client.post(BASE + "/actions", json=command("PROPOSE_OPENING", dict(cutoff_date="2026-10-01", amount="0", direction="PAYABLE", document_no="HD-OPENING")))
        assert proposal.status_code == 200, proposal.text
        identifier = proposal.json()["changed_record_id"]
        supplier_login(client)
        memberships = client.get("/api/carton-supplier/memberships").json()
        assert "huadeng" in {row["factory_id"] for row in memberships}
        current = client.get(VENDOR + "/workspace", params={"factory_id": "huadeng"}).json()
        signed = client.post(VENDOR + "/actions", json=command("REVIEW_OPENING", dict(target_id=identifier, decision="CONFIRMED")))
        assert signed.status_code == 200, signed.text
        login_as(client, "admin")
        current = client.get(BASE + "/workspace", params={"factory_id": "huadeng"}).json()
        confirmed = client.post(BASE + "/actions", json=command("CONFIRM_OPENING", dict(target_id=identifier)))
        assert confirmed.status_code == 200 and confirmed.json()["opening"]["active"]


def test_opening_ignores_non_economic_candidates_but_keeps_effective_removal_evidence(monkeypatch):
    from test_carton_return_collaboration import returned, detail, command
    with make_client(monkeypatch) as client:
        movement, _ = returned(client, monkeypatch)
        identifier = movement["movement_id"]
        supplier_login(client)
        current = detail(client, identifier, True)
        current, _ = command(client, current, "RECEIVE", external=True, quantity="2", receipt_date="2026-09-29", document_no="SIGN-ECONOMIC")
        current, _ = command(client, current, "PROPOSE_CREDIT", external=True, unit_price="3", credit_date="2026-09-30", document_no="CREDIT-ECONOMIC")
        login_as(client, "carton_supervisor")
        current = detail(client, identifier)
        command(client, current, "CONFIRM_CREDIT", target_event_id=current["credit"]["id"])
        initial, _ = bilateral(client, "OPENING", cutoff_date="2026-10-01", direction="PAYABLE", amount="30", document_no="O-ECONOMIC")
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonReceiptLine
        from app.services import carton_supplier_payables as service
        supplier_id = initial["supplier_id"]
        def proof():
            with SessionLocal() as db: return service.baseline(db, "huaxing", supplier_id, "CNY", "2026-10-01", initial["opening"]["active"]["baseline_periods"])["fingerprint"]
        original_proof = proof()
        with SessionLocal() as db:
            source = db.scalar(select(CartonReceipt).where(CartonReceipt.status == "POSTED"))
            original_source_id = source.id
            paper = db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == source.id))
            receipt = {column.name: getattr(source, column.name) for column in source.__table__.columns}
            receipt.update(id="CR-DRAFT-ECONOMIC", delivery_note_no="DRAFT-ECONOMIC", acceptance_date="2026-08-01", status="PENDING_CONFIRMATION")
            line = {column.name: getattr(paper, column.name) for column in paper.__table__.columns}
            line.update(id="CRL-DRAFT-ECONOMIC", receipt_id=receipt["id"])
            db.add(CartonReceipt(**receipt)); db.add(CartonReceiptLine(**line)); db.commit()
        assert proof() == original_proof
        supplier_login(client)
        current = detail(client, identifier, True)
        current, _ = command(client, current, "DECLARE_REFUND", external=True, kind="CASH", amount="1", refund_date="2026-07-31", document_no="PENDING-CASH-ECONOMIC")
        cash_id = current["refunds"][-1]["id"]
        assert proof() == original_proof
        login_as(client, "carton_supervisor")
        current = detail(client, identifier)
        current, _ = command(client, current, "CONFIRM_REFUND", target_event_id=cash_id, confirmation_reference="CONFIRMED-CASH-ECONOMIC")
        confirmed_proof = proof()
        assert confirmed_proof != original_proof and workspace(client)["summary"]["needs_reconfirmation"]
        with SessionLocal() as db:
            confirmed_snapshot = service.baseline(db, "huaxing", supplier_id, "CNY", "2026-10-01", initial["opening"]["active"]["baseline_periods"])
        current, _ = command(client, current, "VOID", target_event_id=cash_id, confirmation_reference="WRONG-CASH-REGISTERED")
        assert proof() == original_proof
        with SessionLocal() as db:
            after_void = service.baseline(db, "huaxing", supplier_id, "CNY", "2026-10-01", confirmed_snapshot["periods"])
            assert after_void["fingerprint"] != confirmed_snapshot["fingerprint"] and "2026-07" in after_void["periods"]
        with SessionLocal() as db:
            # The original effective month remains in baseline_periods after a reversal.
            db.get(CartonReceipt, original_source_id).status = "REVERSED"
            db.commit()
        assert proof() != original_proof
