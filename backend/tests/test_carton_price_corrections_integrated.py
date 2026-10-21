"""Independent three-account price/cost/payable journeys on disposable SQLite."""
from contextlib import ExitStack
from datetime import datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from uuid import uuid4

import pytest


BASE = "/api/carton-procurement"
PORTAL = "/api/carton-supplier"
INTERNAL = BASE + "/price-corrections"
EXTERNAL = PORTAL + "/price-corrections"
FACTORY = "huaxing"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


@pytest.fixture
def actors(monkeypatch, tmp_path):
    # Configure every guard before importing any app or app-importing helper.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "guard.db").as_posix())
    for name in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(name, str(tmp_path))
    import test_molding_sample_api as fixture_api
    monkeypatch.setattr(fixture_api, "TEST_TMP_DIR", tmp_path)
    from fastapi.testclient import TestClient
    from test_carton_supplier_portal import setup_portal, supplier_login, accept_all

    with fixture_api.make_client(monkeypatch) as seed:
        order = setup_portal(seed)
        # One app and DB, independent real login sessions; only seed owns lifespan.
        with ExitStack() as stack:
            clients = [TestClient(seed.app) for _ in range(3)]
            for client in clients:
                stack.callback(client.close)
            warehouse, supervisor, supplier = clients
            wprofile = fixture_api.login_as(warehouse, "warehouse_keeper")
            sprofile = fixture_api.login_as(supervisor, "carton_supervisor")
            vprofile = supplier_login(supplier)
            assert "carton_procurement:order_adjust" not in wprofile["permissions"]
            assert "carton_procurement:closing_manage" in sprofile["permissions"]
            assert "carton_procurement:read" not in vprofile["permissions"]
            assert warehouse.cookies is not supervisor.cookies
            assert supplier.cookies is not warehouse.cookies
            accept_all(supplier)
            from app.services import carton_procurement as core
            clock = {"day": "2026-09-24", "tick": 0}

            def now():
                clock["tick"] += 1
                return datetime.fromisoformat(clock["day"] + "T12:00:00") + timedelta(microseconds=clock["tick"])

            monkeypatch.setattr(core, "business_now", now)
            monkeypatch.setattr(core, "business_today", lambda: clock["day"])
            state = SimpleNamespace(warehouse=warehouse, supervisor=supervisor, supplier=supplier,
                order_no=order["order_no"], line_id=order["lines"][0]["id"], clock=clock)
            yield state


def order(actors):
    rows = ok(actors.warehouse.get(BASE + "/orders", params={"factory_id": FACTORY}))["items"]
    return next(row for row in rows if row["order_no"] == actors.order_no)


def receive(actors, quantity="10", *, price="2", vendor_price="2", day="2026-09-24", issue_id=None, zero_kind="FREE", raw_price=None):
    actors.clock["day"] = day
    current = ok(actors.supplier.get(PORTAL + "/workspace", params={"factory_id": FACTORY}))
    source = next(row for row in current["orders"] if row["order_no"] == actors.order_no)
    sent = ok(actors.supplier.post(PORTAL + "/shipments", json=dict(factory_id=FACTORY,
        request_id=uuid4().hex, delivery_note_no="PRICE-DN-" + uuid4().hex[:12], delivery_date=day,
        lines=[dict(order_line_id=actors.line_id, issue_id=issue_id or source["issue_id"], quantity=quantity,
            unit_price=vendor_price, free_confirmed=D(vendor_price) == 0)])), 201)
    bins = ok(actors.warehouse.get(BASE + "/inventory/locations", params={"factory_id": FACTORY}))
    location = next(row["id"] for row in bins if row["bin_code"] == "A-01")
    paper = sent["lines"][0]
    accepted = ok(actors.warehouse.post(PORTAL + f"/internal/shipments/{sent['id']}/receive", json=dict(
        factory_id=FACTORY, request_id=uuid4().hex, expected_revision=sent["revision"], acceptance_date=day,
        lines=[dict(shipment_line_id=paper["id"], received_quantity=quantity, unit_price=price,
            price_action="PENDING" if D(price) == 0 and zero_kind == "PENDING" else "MATCH" if D(price) == D(vendor_price) else "PROPOSE",
            price_reason="核对本次送货纸品价款依据", paper_quality=paper["paper_quality"],
            specification=paper["specification"], replenishment_issue_id=issue_id,
            zero_price_kind=zero_kind if D(price) == 0 else None,
            location_allocations=[dict(location_id=location, quantity=quantity)])])))
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonReceiptLine, CartonInventoryMovement
    with SessionLocal() as db:
        line = db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == accepted["receipt_id"]))
        movement = db.scalar(select(CartonInventoryMovement).where(CartonInventoryMovement.source_line_id == line.id,
            CartonInventoryMovement.source_type == "RECEIPT"))
        expected_raw = D(price if raw_price is None else raw_price)
        assert D(line.unit_price) == expected_raw
        assert D(movement.unit_price) == expected_raw
        return dict(line_id=line.id, movement_id=movement.id, receipt_id=accepted["receipt_id"],
            shipment_id=sent["id"], location_id=location, original_price=expected_raw)


def positions(actors):
    return ok(actors.warehouse.get(BASE + "/inventory/positions", params={"factory_id": FACTORY}))


def movements(actors):
    return ok(actors.warehouse.get(BASE + "/inventory/movements", params={"factory_id": FACTORY}))["items"]


def outbound(actors, quantity, *, line_id=None, kind="USAGE"):
    selected = next(row for row in positions(actors) if row["order_line_id"] == (line_id or actors.line_id))
    data = dict(factory_id=FACTORY, request_id=uuid4().hex, movement_type="OUTBOUND",
        order_line_id=line_id or actors.line_id, location_id=selected["location_id"], quantity=str(quantity),
        document_no="PRICE-USE-" + uuid4().hex[:8], reason="核实实际纸品领用", issue_kind=kind)
    if kind == "RETURN": data["return_date"] = actors.clock["day"]
    return ok(actors.warehouse.post(BASE + "/inventory/movements", json=data), 201)


def raw_snapshot():
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonReceipt, CartonReceiptLine, CartonInventoryMovement, CartonOrder, CartonOrderLine
    from app.models.carton_positions import CartonPositionEntry
    from app.models.carton_supplier_portal import SupplierShipmentLine
    result = {}
    with SessionLocal() as db:
        for model in (CartonReceipt, CartonReceiptLine, CartonInventoryMovement, CartonPositionEntry,
                      CartonOrder, CartonOrderLine, SupplierShipmentLine):
            table = model.__table__
            result[table.name] = [dict(row) for row in db.execute(select(table).order_by(table.c.id)).mappings()]
    return result


def financial_facts():
    """Actual bank facts exclude deliberate assignment/reopen bookkeeping."""
    import json
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonAuditEvent
    actions = {"RECORD_PAYMENT", "RECEIVE_PAYMENT", "DECLARE_PAYMENT_RETURN", "CONFIRM_PAYMENT_RETURN"}
    with SessionLocal() as db:
        return [(event.id, event.detail_json) for event in db.scalars(select(CartonAuditEvent).order_by(CartonAuditEvent.sequence))
            if json.loads(event.detail_json or "{}").get("action") in actions]


def detail(actors, source, *, external=False, client=None):
    client = client or (actors.supplier if external else actors.warehouse)
    return ok(client.get((EXTERNAL if external else INTERNAL) + f"/{source['line_id']}", params={"factory_id": FACTORY}))


def command(current, action, **changes):
    return dict(factory_id=FACTORY, request_id=uuid4().hex, expected_revision=current["revision"],
        source_fingerprint=current["source_fingerprint"], action=action, reason="三方核实原凭证及本次单价更正") | changes


def act(actors, source, action, *, client=None, external=False, expected=200, current=None, **changes):
    client = client or (actors.supplier if external else actors.supervisor if action == "FINAL_CONFIRM" else actors.warehouse)
    current = current or detail(actors, source, external=external, client=client)
    body = command(current, action, **changes)
    response = client.post((EXTERNAL if external else INTERNAL) + f"/{source['line_id']}/actions", json=body)
    assert response.status_code == expected, response.text
    return response.json(), body


def propose(actors, source, price, **changes):
    return act(actors, source, "PROPOSE", proposed_unit_price=str(price),
        document_no="CREDIT-PRICE-" + uuid4().hex[:8], document_date=actors.clock["day"], free_confirmed=D(price) == 0, **changes)


def approve(actors, source, price):
    propose(actors, source, price)
    return act(actors, source, "SUPPLIER_CONFIRM", external=True)[0]


def preview(actors, source, **changes):
    current = detail(actors, source, client=actors.supervisor)
    return ok(actors.supervisor.post(INTERNAL + f"/{source['line_id']}/preview", json=dict(
        factory_id=FACTORY, expected_revision=current["revision"], source_fingerprint=current["source_fingerprint"], **changes)))


def finish(actors, source, *, expected=200):
    impact = preview(actors, source)
    return act(actors, source, "FINAL_CONFIRM", expected=expected,
        impact_fingerprint=impact["impact"]["impact_fingerprint"])[0]


def goods(actors, period="2026-09"):
    from test_carton_settlement_collaboration import workspace
    return workspace(actors.supervisor, period)


def settle(actors, period="2026-09", document=None):
    from test_carton_settlement_collaboration import save, review
    from test_carton_supplier_settlement_api import action
    current = save(actors.supervisor, goods(actors, period), doc=document)
    assert not current["result"]["issues"], current["result"]
    current = ok(review(actors.supplier, current))
    return ok(action(actors.supervisor, current))


def payables(actors):
    return ok(actors.supervisor.get(BASE + "/payables/workspace", params=dict(factory_id=FACTORY, currency="CNY")))


def pay_action(actors, name, *, external=False, **changes):
    client = actors.supplier if external else actors.supervisor
    current = ok(client.get((PORTAL if external else BASE) + "/payables/workspace", params=dict(factory_id=FACTORY, currency="CNY")))
    body = dict(factory_id=FACTORY, currency="CNY", supplier_id=current["supplier_id"], request_id=uuid4().hex,
        expected_revision=current["revision"], source_fingerprint=current["source_fingerprint"], action=name,
        reason="核对真实付款及单价更正依据", **changes)
    return ok(client.post((PORTAL if external else BASE) + "/payables/actions", json=body))


def opening(actors, amount="0", cutoff="2026-09-01", document="PRICE-OPENING"):
    current = pay_action(actors, "PROPOSE_OPENING", amount=amount, direction="PAYABLE", cutoff_date=cutoff,
        document_no=document, acknowledge_unknown_sources=False)
    identifier = current["changed_record_id"]
    pay_action(actors, "REVIEW_OPENING", external=True, target_id=identifier, decision="CONFIRMED")
    return pay_action(actors, "CONFIRM_OPENING", target_id=identifier)


def assert_price(actors, source, *, qty, amount, payable):
    rows = [row for row in positions(actors) if row["order_line_id"] == actors.line_id]
    assert sum(D(row["balance"]) for row in rows) == D(qty)
    assert sum(D(row["cost_amount"]) for row in rows) == D(amount)
    current = goods(actors)
    price_source = next(row for row in current["sources"] if row["source_key"] == "RECEIPT:" + source["line_id"])
    assert D(price_source["amount"]) == D(payable)


def test_raw_receipt_and_movement_use_acceptance_price_not_supplier_original(actors):
    source = receive(actors, price="3", vendor_price="2")
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_price_review import CartonPriceReview
    from app.models.carton_supplier_portal import SupplierShipmentLine
    import json
    with SessionLocal() as db:
        row = db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id == source["line_id"]))
        original = db.scalar(select(SupplierShipmentLine).where(SupplierShipmentLine.shipment_id == source["shipment_id"]))
        assert D(json.loads(original.snapshot_json)["delivery_unit_price"]) == 2
        assert D(row.original_unit_price) == 2
        assert D(row.proposed_unit_price) == 3
        review_id, revision = row.id, row.revision
    confirmed = ok(actors.supplier.post(f"/api/carton-price-reviews/supplier/{review_id}/decide", json=dict(
        factory_id=FACTORY, expected_revision=revision, request_id=uuid4().hex, decision="CONFIRM")))
    assert confirmed["status"] == "CONFIRMED"
    assert_price(actors, source, qty="10", amount="30", payable="30")


def test_three_roles_consumption_preview_expiry_and_original_evidence(actors):
    source = receive(actors)
    used = outbound(actors, "4")
    before = raw_snapshot()
    assert_price(actors, source, qty="6", amount="12", payable="20")
    proposed, propose_body = propose(actors, source, "3")
    assert proposed["status"] == "PENDING_SUPPLIER"
    assert_price(actors, source, qty="6", amount="12", payable="20")
    act(actors, source, "SUPPLIER_DISPUTE", external=True, reason="供应商要求先核对原单据")
    assert_price(actors, source, qty="6", amount="12", payable="20")
    approve(actors, source, "3")
    old = preview(actors, source)
    assert D(old["impact"]["summary"]["bridge_difference"]) == 0
    supplier_fp = detail(actors, source, external=True)["source_fingerprint"]
    outbound(actors, "1")
    current = detail(actors, source)
    assert current["status"] == "SUPPLIER_CONFIRMED"
    assert detail(actors, source, external=True)["source_fingerprint"] == supplier_fp
    stale, _ = act(actors, source, "FINAL_CONFIRM", expected=409,
        impact_fingerprint=old["impact"]["impact_fingerprint"])
    before = raw_snapshot()
    applied = finish(actors, source)
    assert applied["status"] == "APPLIED"
    assert raw_snapshot() == before
    assert_price(actors, source, qty="5", amount="15", payable="30")
    changed = next(row for row in movements(actors) if row["id"] == used["id"])
    assert D(changed["cost_amount"]) == -12
    # Historical approval is never reusable after later applied versions (ABA).
    approve(actors, source, "2")
    finish(actors, source)
    assert_price(actors, source, qty="5", amount="10", payable="20")
    assert actors.warehouse.post(INTERNAL + f"/{source['line_id']}/actions", json=propose_body).status_code == 200
    assert detail(actors, source)["status"] == "APPLIED"


def test_mixed_price_history_full_depletion_and_exact_reversal(actors):
    source = receive(actors)
    outbound(actors, "4")
    receive(actors, "6", price="4", vendor_price="4", day="2026-09-25")
    used = outbound(actors, "3")
    approve(actors, source, "3")
    before = raw_snapshot()
    finish(actors, source)
    assert raw_snapshot() == before
    assert_price(actors, source, qty="9", amount="31.50", payable="30")
    assert sum(D(row["amount"]) for row in goods(actors)["sources"]) == 54
    revised = next(row for row in movements(actors) if row["id"] == used["id"])
    assert D(revised["cost_amount"]) == D("-10.5")
    reversal = ok(actors.warehouse.post(BASE + f"/inventory/movements/{used['id']}/reverse", json=dict(
        factory_id=FACTORY, reason="核实原领用单据需冲销")), 201)
    assert D(next(row for row in movements(actors) if row["id"] == reversal["id"])["cost_amount"]) == D("10.5")
    outbound(actors, "12")
    approve(actors, source, "2")
    finish(actors, source)
    assert sum(D(row["balance"]) for row in positions(actors)) == 0
    ledger = movements(actors)
    assert sum(D(row["cost_amount"]) for row in ledger) == 0


@pytest.mark.parametrize("new_price,remaining", [("1", "-10"), ("3", "10")])
def test_locked_paid_month_requires_explicit_release_and_keeps_payment(actors, new_price, remaining):
    source = receive(actors)
    outbound(actors, "4")
    actors.clock["day"] = "2026-11-05"
    opening(actors)
    bill = settle(actors)
    paid = pay_action(actors, "RECORD_PAYMENT", amount="20", payment_date="2026-10-20",
        document_no="PRICE-PAID-20", bank_reference="PRICE-BANK-20")
    payment_id = paid["changed_record_id"]
    pay_action(actors, "RECEIVE_PAYMENT", external=True, target_id=payment_id, decision="CONFIRMED")
    current = payables(actors)
    target = next(row for row in current["obligations"] if row["record_id"] == bill["id"])
    pay_action(actors, "ALLOCATE", source_kind="PAYMENT", source_id=payment_id,
        targets=[dict(target_kind="SETTLEMENT", target_id=target["id"], amount="20")])
    cash_facts = financial_facts()
    assert len(cash_facts) == 2
    locked = []
    for month in ("2026-09", "2026-10"):
        closing = ok(actors.supervisor.post(BASE + "/closings/generate", json=dict(factory_id=FACTORY, period=month)))[0]
        for status in ("PENDING", "CONFIRMED", "LOCKED"):
            closing = ok(actors.supervisor.post(BASE + f"/closings/{closing['id']}/status", json=dict(
                factory_id=FACTORY, expected_revision=closing["revision"], status=status)))
        locked.append(closing)
    approve(actors, source, new_price)
    impact = preview(actors, source)["impact"]
    assert not impact["can_apply"]
    assert {row["code"] for row in impact["blockers"]} >= {"LOCKED_CLOSING", "CONFIRMED_SUPPLIER_MONTH"}
    before = raw_snapshot()
    finish(actors, source, expected=409)
    assert raw_snapshot() == before
    from test_carton_supplier_settlement_api import action
    assert action(actors.supervisor, bill, "reopen", reason="更正本月错误单价原依据").status_code == 409
    payload = dict(factory_id=FACTORY, expected_revision=locked[0]["revision"], reason="主管核对错误单价影响")
    assert actors.supervisor.post(BASE + f"/closings/{locked[0]['id']}/unlock", json=payload).status_code == 409
    for closing in reversed(locked):
        ok(actors.supervisor.post(BASE + f"/closings/{closing['id']}/unlock", json=dict(factory_id=FACTORY,
            expected_revision=closing["revision"], reason="主管核对错误单价影响")))
    current = payables(actors)
    pay_action(actors, "DEALLOCATE", allocation_ids=[row["id"] for row in current["allocations"] if row["status"] == "ACTIVE"])
    reopened = ok(action(actors.supervisor, bill, "reopen", reason="更正本月错误单价原依据"))
    assert D(payables(actors)["summary"]["confirmed_settlements"]) == 20
    before = raw_snapshot()
    finish(actors, source)
    assert raw_snapshot() == before
    for previous in locked:  # Rebuilt September, then its October carry.
        rows = ok(actors.supervisor.get(BASE + "/closings", params=dict(factory_id=FACTORY, period=previous["period"])))
        rebuilt = next(row for row in rows if row["id"] == previous["id"])
        assert rebuilt["status"] == "DRAFT" and rebuilt["revision"] > previous["revision"]
        assert D(rebuilt["ending_quantity"]) == 6
        assert D(rebuilt["ending_amount"]) == D(new_price) * 6
        assert rebuilt["snapshot_stale"] is False
        assert rebuilt["quantity_snapshot_missing"] is False
        assert rebuilt["pricing_issues"] == []
        assert len(rebuilt["quantities_by_unit"]) == 1
        unit = rebuilt["quantities_by_unit"][0]
        assert unit["unit"] == "个" and D(unit["ending_quantity"]) == 6
        september = previous["period"] == "2026-09"
        assert D(unit["opening_quantity"]) == (0 if september else 6)
        assert D(unit["inbound_quantity"]) == (10 if september else 0)
        assert D(unit["outbound_quantity"]) == (4 if september else 0)
        assert D(unit["adjustment_quantity"]) == 0
        for status in ("PENDING", "CONFIRMED", "LOCKED"):
            rebuilt = ok(actors.supervisor.post(BASE + f"/closings/{rebuilt['id']}/status", json=dict(
                factory_id=FACTORY, expected_revision=rebuilt["revision"], status=status)))
        assert rebuilt["status"] == "LOCKED"
        assert D(rebuilt["ending_amount"]) == D(new_price) * 6
    hold = payables(actors)
    assert D(hold["summary"]["internal_paid"]) == 20
    assert D(hold["summary"]["balance_due_signed"]) == 0
    corrected = settle(actors, document=reopened)
    assert D(corrected["result"]["net_amount"]) == D(new_price) * 10
    current = payables(actors)
    assert D(current["summary"]["internal_paid"]) == 20
    assert D(current["summary"]["balance_due_signed"]) == D(remaining)
    assert D(current["summary"]["unapplied_payment"]) == 20
    assert not any(row["status"] == "ACTIVE" for row in current["allocations"])
    target = next(row for row in current["obligations"] if row["record_id"] == corrected["id"])
    allocated = min(D("20"), D(new_price) * 10)
    current = pay_action(actors, "ALLOCATE", source_kind="PAYMENT", source_id=payment_id,
        targets=[dict(target_kind="SETTLEMENT", target_id=target["id"], amount=str(allocated))])
    active = [row for row in current["allocations"] if row["status"] == "ACTIVE"]
    assert len(active) == 1
    assert active[0]["target_id"] == target["id"] and active[0]["target_version"] == corrected["version"]
    assert D(active[0]["amount"]) == allocated
    refreshed_target = next(row for row in current["obligations"] if row["record_id"] == corrected["id"])
    assert D(refreshed_target["remaining_amount"]) == max(D(new_price) * 10 - 20, D(0))
    assert D(current["summary"]["unapplied_payment"]) == 20 - allocated
    assert D(current["summary"]["internal_paid"]) == 20
    assert D(current["summary"]["balance_due_signed"]) == D(remaining)
    assert raw_snapshot() == before
    assert financial_facts() == cash_facts


def test_pre_cutoff_correction_requires_bilateral_opening_recheck_without_double_count(actors):
    source = receive(actors)
    actors.clock["day"] = "2026-11-05"
    opening(actors, "20", cutoff="2026-10-01")
    approve(actors, source, "3")
    finish(actors, source)
    current = payables(actors)
    assert current["summary"]["needs_reconfirmation"] is True
    assert D(current["summary"]["opening_signed"]) == 20
    assert D(current["summary"]["confirmed_settlements"]) == 0
    pay_action(actors, "RECORD_PAYMENT", amount="1", payment_date="2026-10-20",
        document_no="PRICE-DRIFT-PAY", bank_reference="PRICE-DRIFT-BANK")
    assert D(payables(actors)["summary"]["balance_due_signed"]) == 19
    opening(actors, "30", cutoff="2026-10-01", document="PRICE-OPENING-RECHECK")
    current = payables(actors)
    assert current["summary"]["needs_reconfirmation"] is False
    assert D(current["summary"]["balance_due_signed"]) == 29
    assert D(current["summary"]["confirmed_settlements"]) == 0


def test_free_supplier_b_restores_replayed_cost_without_creating_payable(actors):
    source = receive(actors)
    from test_carton_replenishment_api import body, replenish
    from test_carton_p1_lifecycle import task_for, respond
    current = order(actors)
    issued = ok(replenish(actors.warehouse, current, body(current, positions(actors), "SUPPLIER", 2)), 201)
    task = task_for(actors.supplier, "REPLENISHMENT", current["id"])
    ok(respond(actors.supplier, task, "ACCEPT", promised_date=actors.clock["day"]))
    replacement = receive(actors, "2", price="0", vendor_price="0", raw_price="2", issue_id=issued["issue"]["id"])
    assert_price(actors, source, qty="10", amount="20", payable="20")
    assert not any(row["source_key"] == "RECEIPT:" + replacement["line_id"] for row in goods(actors)["sources"])
    approve(actors, source, "3")
    before = raw_snapshot()
    impact = preview(actors, source)["impact"]
    assert impact["can_apply"], impact["blockers"]
    assert D(impact["summary"]["bridge_difference"]) == 0
    finish(actors, source)
    assert raw_snapshot() == before
    assert_price(actors, source, qty="10", amount="30", payable="30")
    incoming = next(row for row in movements(actors) if row["id"] == replacement["movement_id"])
    assert D(incoming["unit_price"]) == 2  # Original frozen evidence remains.
    assert D(incoming["cost_amount"]) == 6  # Current cost follows the exact B outbound.
    assert not detail(actors, replacement)["can_propose"]
    propose(actors, replacement, "1", expected=409)


def test_split_child_and_reversal_inherit_repriced_source_without_quantity_changes(actors):
    source = receive(actors)
    from test_carton_order_split import context, split_body, save, action
    current = order(actors)
    position = context(actors.warehouse, current)["lines"][0]["positions"][0]
    data = split_body(current, pending="0", product="480", stock=[dict(
        location_id=position["location_id"], expected_position_revision=position["position_revision"], quantity="4")])
    # The original order has a second paper: product splits allocate its genuine
    # pending demand too, without inventing physical inventory for that sibling.
    data["targets"][0]["lines"].append(dict(order_line_id=current["lines"][1]["id"], pending_quantity="480", stock=[]))
    split = save(actors.supervisor, current, data)
    split = ok(action(actors.warehouse, split, "confirm"))
    child = next(row for row in positions(actors) if row["order_line_id"].startswith("CSL-"))
    used = outbound(actors, "1", line_id=child["order_line_id"])
    approve(actors, source, "3")
    before = raw_snapshot()
    impact = preview(actors, source)["impact"]
    finish(actors, source)
    assert raw_snapshot() == before
    rows = positions(actors)
    assert sum(D(row["balance"]) for row in rows) == 9
    assert sum(D(row["cost_amount"]) for row in rows) == 27
    pairs = [row for row in impact["movements"] if row["source_type"] == "ORDER_SPLIT"]
    assert len(pairs) == 2
    assert sum(D(row["cost_difference"]) for row in pairs) == 0
    child_row = next(row for row in rows if row["order_line_id"] == child["order_line_id"])
    assert D(child_row["cost_amount"]) == 9
    reverse = ok(actors.warehouse.post(BASE + f"/inventory/movements/{used['id']}/reverse", json=dict(
        factory_id=FACTORY, reason="核实拆单后的原领用需冲销")), 201)
    assert D(next(row for row in movements(actors) if row["id"] == reverse["id"])["cost_amount"]) == 3
    assert sum(D(row["cost_amount"]) for row in positions(actors)) == 30


def review_row(actors, source):
    rows = ok(actors.warehouse.get("/api/carton-price-reviews/internal", params={"factory_id": FACTORY}))["items"]
    return next(row for row in rows if row["receipt_line_id"] == source["line_id"])


def old_proposal(actors, row, price):
    return actors.warehouse.post(f"/api/carton-price-reviews/internal/{row['id']}/propose", json=dict(
        factory_id=FACTORY, expected_revision=row["revision"], request_id=uuid4().hex,
        proposed_unit_price=price, reason="独立验证旧核价入口是否绕过"))


def test_old_review_cannot_bypass_known_cost_including_raw_zero_with_price_evidence(actors):
    source = receive(actors)
    before = raw_snapshot()
    assert old_proposal(actors, review_row(actors, source), "3").status_code == 409
    assert raw_snapshot() == before
    pending = receive(actors, "2", price="0", zero_kind="PENDING")
    ok(actors.supervisor.post(BASE + f"/inventory/movements/{pending['movement_id']}/price-confirmation", json=dict(
        factory_id=FACTORY, unit_price="2", zero_price_confirmed=False, reason="依据原凭证明确核实缺价")), 204)
    row = ok(old_proposal(actors, review_row(actors, pending), "2"))
    ok(actors.supplier.post(f"/api/carton-price-reviews/supplier/{row['id']}/decide", json=dict(
        factory_id=FACTORY, expected_revision=row["revision"], request_id=uuid4().hex, decision="CONFIRM")))
    before = raw_snapshot()
    assert old_proposal(actors, review_row(actors, pending), "3").status_code == 409
    assert raw_snapshot() == before
    approve(actors, source, "3")
    # A same-cost legacy verification stays legal, but its new evidence version
    # invalidates the already-signed correction source and requires a new ack.
    same = ok(old_proposal(actors, review_row(actors, source), "2"))
    ok(actors.supplier.post(f"/api/carton-price-reviews/supplier/{same['id']}/decide", json=dict(
        factory_id=FACTORY, expected_revision=same["revision"], request_id=uuid4().hex, decision="CONFIRM")))
    assert detail(actors, source)["status"] == "STALE"
    finish(actors, source, expected=409)
    approve(actors, source, "3")
    finish(actors, source)
    assert old_proposal(actors, review_row(actors, source), "2").status_code == 409
    assert_price(actors, source, qty="12", amount="34", payable="30")


def test_legacy_ap_only_difference_allows_same_payable_price_cost_correction(actors):
    source = receive(actors)
    # Explicit upgrade fixture: old AP-only agreement existed before full workflow.
    # This is distinct from vendor original=2 / warehouse acceptance=3 (both raw=3).
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_price_review import CartonPriceReview
    from app.models.carton_supplier_settlement import CartonSupplierSettlement
    with SessionLocal() as db:
        row = db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id == source["line_id"]))
        row.proposed_unit_price = D("3")
        row.status = "CONFIRMED"
        row.revision += 1
        # Independent historical HKD agreement is outside this CNY price change.
        db.add(CartonSupplierSettlement(id="UNRELATED-HKD", factory_id=FACTORY, supplier_id=row.supplier_id,
            period="2026-09", currency="HKD", version=1, revision=1, status="CONFIRMED",
            source_fingerprint="0"*64, sources_json="[]", statement_json="{}", result_json='{"net_amount":"99"}',
            created_at="2026-10-01T12:00:00+08:00", updated_at="2026-10-01T12:00:00+08:00",
            created_by="legacy", confirmed_at="2026-10-01T12:00:00+08:00", confirmed_by="legacy"))
        db.commit()
    assert_price(actors, source, qty="10", amount="20", payable="30")
    current = detail(actors, source)
    assert D(current["current_cost_unit_price"]) == 2
    assert D(current["current_unit_price"]) == 3
    approve(actors, source, "3")
    impact = preview(actors, source)["impact"]
    assert not any(row["code"] in {"CONFIRMED_SUPPLIER_MONTH", "ACTIVE_ALLOCATION"} for row in impact["blockers"])
    assert D(impact["summary"]["payable_difference"]) == 0
    assert D(impact["summary"]["source_cost_difference"]) == 10
    before = raw_snapshot()
    finish(actors, source)
    assert raw_snapshot() == before
    assert_price(actors, source, qty="10", amount="30", payable="30")
    with SessionLocal() as db:
        unchanged = db.get(CartonSupplierSettlement, "UNRELATED-HKD")
        assert unchanged.status == "CONFIRMED" and unchanged.revision == 1
        assert unchanged.result_json == '{"net_amount":"99"}'


def test_return_credit_and_real_cash_remain_independent_of_replayed_purchase_cost(actors):
    source = receive(actors)
    returned = outbound(actors, "2", kind="RETURN")
    from test_carton_return_collaboration import detail as return_detail, command as return_action
    identifier = returned["id"]
    current = return_detail(actors.supplier, identifier, True)
    current, _ = return_action(actors.supplier, current, "RECEIVE", external=True,
        quantity="2", receipt_date="2026-09-24", document_no="PRICE-RETURN-SIGNED")
    current, _ = return_action(actors.supplier, current, "PROPOSE_CREDIT", external=True,
        unit_price="3", credit_date="2026-09-24", document_no="PRICE-RETURN-INDEPENDENT-CREDIT")
    current = return_detail(actors.supervisor, identifier)
    return_action(actors.supervisor, current, "CONFIRM_CREDIT", target_event_id=current["credit"]["id"])
    actors.clock["day"] = "2026-10-05"
    current = return_detail(actors.supplier, identifier, True)
    current, _ = return_action(actors.supplier, current, "DECLARE_REFUND", external=True,
        kind="CASH", amount="2", refund_date="2026-10-02", document_no="PRICE-REAL-CASH-TWO")
    current = return_detail(actors.supervisor, identifier)
    return_action(actors.supervisor, current, "CONFIRM_REFUND", target_event_id=current["refunds"][-1]["id"],
        confirmation_reference="PRICE-REAL-CASH-BANK-TWO")
    september = goods(actors)
    old_return = next(row for row in september["sources"] if row["kind"] == "RETURN")
    assert D(old_return["amount"]) == 6
    october = goods(actors, "2026-10")
    assert len(october["sources"]) == 1 and D(october["sources"][0]["amount"]) == 2
    before = raw_snapshot()
    return_facts = return_detail(actors.supervisor, identifier)
    approve(actors, source, "3")
    impact = preview(actors, source)["impact"]
    changed_return = next(row for row in impact["movements"] if row["movement_id"] == identifier)
    assert D(changed_return["old_cost_amount"]) == -4 and D(changed_return["new_cost_amount"]) == -6
    finish(actors, source)
    assert raw_snapshot() == before
    assert_price(actors, source, qty="8", amount="24", payable="30")
    assert next(row for row in goods(actors)["sources"] if row["kind"] == "RETURN") == old_return
    assert goods(actors, "2026-10")["source_fingerprint"] == october["source_fingerprint"]
    after = return_detail(actors.supervisor, identifier)
    for key in ("receipts", "credit", "refunds", "date_evidence"):
        assert after[key] == return_facts[key]


def test_pre_review_legacy_source_updates_vendor_agreement_and_keeps_monthly_aba_stale(actors):
    source = receive(actors)
    # Explicit upgrade fixture: this receipt predates per-line price reviews.
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_price_review import CartonPriceReview
    with SessionLocal() as db:
        old = db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id == source["line_id"]))
        db.delete(old)
        db.commit()
    actors.clock["day"] = "2026-11-05"
    from test_carton_settlement_collaboration import save, review
    original = goods(actors)
    draft = save(actors.supervisor, original)
    signed = ok(review(actors.supplier, draft))
    original_fp = original["collaboration"]["source_fingerprint"]
    approve(actors, source, "3")
    finish(actors, source)
    updated = goods(actors)
    agreed = next(row for row in updated["collaboration"]["lines"] if row["source_key"] == "RECEIPT:" + source["line_id"])
    assert D(agreed["unit_price"]) == 3
    assert D(agreed["amount"]) == 30
    approve(actors, source, "2")
    finish(actors, source)
    restored = goods(actors)
    assert restored["collaboration"]["source_fingerprint"] != original_fp
    previous = next(row for row in restored["documents"] if row["id"] == signed["id"])
    assert previous["stale"] is True
    from test_carton_supplier_settlement_api import action
    assert action(actors.supervisor, signed).status_code == 409


def test_supplier_projection_permissions_replay_and_fresh_actor_after_lock(actors, monkeypatch):
    source = receive(actors)
    assert actors.supplier.get(EXTERNAL + f"/{source['line_id']}", params={"factory_id": FACTORY}).status_code == 404
    proposed, _ = propose(actors, source, "3")
    exposed = detail(actors, source, external=True)
    forbidden = {"raw_unit_price", "current_cost_unit_price", "impact", "movements", "pools", "closings",
        "old_cost_amount", "new_cost_amount", "cost_difference", "impact_fingerprint", "location_id", "location", "applied_by"}
    def inspect(value):
        if isinstance(value, dict):
            assert not (forbidden & set(value)), forbidden & set(value)
            for child in value.values(): inspect(child)
        elif isinstance(value, list):
            for child in value: inspect(child)
    inspect(exposed)
    assert actors.warehouse.post(INTERNAL + f"/{source['line_id']}/actions", json=command(proposed, "SUPPLIER_CONFIRM")).status_code == 403
    assert actors.supplier.post(EXTERNAL + f"/{source['line_id']}/actions", json=command(exposed, "FINAL_CONFIRM", impact_fingerprint="x")).status_code == 403
    for client, prefix in ((actors.warehouse, INTERNAL), (actors.supplier, EXTERNAL)):
        assert client.get(prefix + f"/{source['line_id']}", params={"factory_id": "huakang-a"}).status_code in {403, 404}
    act(actors, source, "SUPPLIER_CONFIRM", external=True)
    impact = preview(actors, source)["impact"]
    current = detail(actors, source)
    payload = command(current, "FINAL_CONFIRM", impact_fingerprint=impact["impact_fingerprint"])
    assert actors.warehouse.post(INTERNAL + f"/{source['line_id']}/actions", json=payload).status_code == 403
    before = raw_snapshot()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.services import carton_procurement as core
    original_lock = core._lock_receipt_factory
    touched = []
    def revoke_after_lock(db, factory):
        original_lock(db, factory)
        actor = db.scalar(select(AuthUser).where(AuthUser.username == "carton_supervisor"))
        actor.status = "disabled"
        db.flush()
        touched.append(True)
    monkeypatch.setattr(core, "_lock_receipt_factory", revoke_after_lock)
    response = actors.supervisor.post(INTERNAL + f"/{source['line_id']}/actions", json=payload)
    assert response.status_code == 403, response.text
    assert touched
    monkeypatch.setattr(core, "_lock_receipt_factory", original_lock)
    assert raw_snapshot() == before
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    second = {**payload, "request_id": uuid4().hex}
    def send(body):
        barrier.wait(timeout=15)
        return actors.supervisor.post(INTERNAL + f"/{source['line_id']}/actions", json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, (payload, second)))
    assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
    winning = payload if responses[0].status_code == 200 else second
    applied = next(response.json() for response in responses if response.status_code == 200)
    assert applied["status"] == "APPLIED"
    after = raw_snapshot()
    replay = ok(actors.supervisor.post(INTERNAL + f"/{source['line_id']}/actions", json=winning))
    assert replay.get("replayed") is True
    assert raw_snapshot() == after
    assert actors.supervisor.post(INTERNAL + f"/{source['line_id']}/actions", json={**winning, "reason": "同一提交标识改变内容"}).status_code == 409
    inspect(detail(actors, source, external=True))
    exposed_workspace = ok(actors.supplier.get(EXTERNAL + "/workspace", params=dict(factory_id=FACTORY, status="ALL")))
    inspect(exposed_workspace)
    import json
    assert "华兴纸箱主管" not in json.dumps(exposed_workspace, ensure_ascii=False)


@pytest.mark.parametrize("received_after_first", [False, True])
def test_b_frozen_rounding_first_correction_timing_aba_and_multiple_generations(monkeypatch, tmp_path, received_after_first):
    # Pure valuation still receives an isolated guard before app-model imports.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "pure-guard.db").as_posix())
    for name in ("TEMP", "TMP", "TMPDIR"): monkeypatch.setenv(name, str(tmp_path))
    from decimal import localcontext
    from fractions import Fraction
    from app.models.carton_procurement import CartonInventoryMovement as Movement
    from app.services.carton_inventory_valuation import value_movements
    import json

    def row(identifier, qty, price, minute, **changes):
        data = dict(id=identifier, factory_id=FACTORY, order_line_id="PAPER", customer_code="DICKIE", customer_name="Dickie",
            contract_no="ROUNDING", item_no="001", packaging_type="外箱", paper_quality="A33", specification="1x1x1",
            unit="个", currency="CNY", movement_type="INBOUND" if D(qty) > 0 else "OUTBOUND", quantity=D(qty),
            unit_price=D(price), location="A", document_no=identifier, source_type="RECEIPT" if D(qty)>0 else "ORDER_REPLENISHMENT",
            source_id=identifier, source_line_id=identifier, actor_user_id="fixture", actor_name="Fixture",
            occurred_at=f"2026-09-01T09:{minute:02}:00+08:00", reversal_of_movement_id=None)
        return Movement(**(data | changes))

    def event(identifier, seq, kind="INVENTORY_MOVEMENT_CREATED", **data):
        return SimpleNamespace(id=f"E-{seq}", entity_id=identifier, sequence=seq, event_type=kind,
            detail_json=json.dumps(data), created_at="2026-10-05T12:00:00+08:00")

    def link(identifier, issue, seq):
        return event(identifier, seq, "RECEIPT_REPLENISHMENT_LINKED", responsibility="SUPPLIER", replenishment_issue_id=issue)

    def amount(value):
        with localcontext() as context:
            context.prec=48
            return D(value.numerator)/D(value.denominator)

    base = [row("A", "1", "1", 0), row("OTHER", "2", "2", 1), row("B1-OUT", "-1", "0", 2)]
    initial = [event(item.id, i+1) for i,item in enumerate(base)]
    if received_after_first:
        first = event("A", 4, "INVENTORY_PRICE_CORRECTED", unit_price="4")
        b1 = row("B1-IN", "1", "2.666667", 3)
        history = initial + [first, event(b1.id, 5), link(b1.id, "B1-OUT", 6)]
        rows = base + [b1]
        current = value_movements(rows, history)
        assert not current.errors
        assert current.amounts[b1.id] == D("2.666667")  # No duplicate first delta.
        assert abs(sum(pool.amount for pool in current.balances.values()) - amount(Fraction(8) + Fraction(1, 3_000_000))) < D("1e-24")
        reverted = value_movements(rows, history + [event("A", 7, "INVENTORY_PRICE_CORRECTED", unit_price="1")])
        assert not reverted.errors
        assert reverted.amounts[b1.id] == D("1.666667")
        assert abs(sum(pool.amount for pool in reverted.balances.values()) - amount(Fraction(5) + Fraction(1, 3_000_000))) < D("1e-24")
    else:
        b1 = row("B1-IN", "1", "1.666667", 3)
        b2_out = row("B2-OUT", "-1", "0", 4)
        b2 = row("B2-IN", "1", "1.666667", 5)
        rows = base + [b1, b2_out, b2]
        history = initial + [event(b1.id,4),link(b1.id,"B1-OUT",5),event(b2_out.id,6),event(b2.id,7),link(b2.id,"B2-OUT",8)]
        before = value_movements(rows, history)
        assert not before.errors
        assert before.amounts[b1.id] == before.amounts[b2.id] == D("1.666667")
        # Two successive restores preserve their original six-place freeze.
        expected = Fraction(5) + Fraction(1, 1_800_000)
        assert abs(sum(pool.amount for pool in before.balances.values()) - amount(expected)) < D("1e-24")
        first = event("A",9,"INVENTORY_PRICE_CORRECTED",unit_price="4")
        changed = value_movements(rows,history+[first])
        assert not changed.errors
        assert changed.amounts[b1.id] == changed.amounts[b2.id] == D("2.666667")
        assert abs(sum(pool.amount for pool in changed.balances.values()) - amount(expected+3)) < D("1e-24")
        reverted = value_movements(rows,history+[first,event("A",10,"INVENTORY_PRICE_CORRECTED",unit_price="1")])
        assert not reverted.errors
        assert reverted.amounts == before.amounts
    assert b1.unit_price == D("2.666667" if received_after_first else "1.666667")
