from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _freeze_carton_time
from test_carton_transaction_guards_api import BASE, order, ledger
from test_carton_direct_receipt_api import payload as receipt_payload
from test_carton_history_identity_api import _orders


def setup(client, monkeypatch):
    login_as(client, "admin")
    _freeze_carton_time(monkeypatch)
    row = order(client)
    issued = client.post(f"{BASE}/orders/{row['order_no']}/purchase-order-issues.xlsx", json={"factory_id": "huaxing", "expected_revision": row["revision"]})
    assert issued.status_code == 200, issued.text
    response = client.post(BASE + "/receipts", json={**receipt_payload(row), "acceptance_date": "2026-08-05"})
    assert response.status_code == 201, response.text
    row = _orders(client)[0]
    stocks = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"}).json()
    return row, stocks


def body(row, stocks, responsibility="OWN", qty=2):
    return {"factory_id": "huaxing", "expected_revision": row["revision"], "request_id": uuid4().hex,
            "responsibility": responsibility, "lines": [{"order_line_id": row["lines"][0]["id"],
                "location_id": next(s["location_id"] for s in stocks if s["order_line_id"] == row["lines"][0]["id"]),
                "quantity": qty}]}


def replenish(client, row, request):
    return client.post(f"{BASE}/orders/{row['order_no']}/replenish", json=request)


@pytest.mark.parametrize("responsibility", ["OWN", "SUPPLIER"])
def test_replenishment_issues_now_receives_later_keeps_demand_and_purchase_baseline(monkeypatch, responsibility):
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        request = body(row, stocks, responsibility)
        first = replenish(client, row, request)
        assert first.status_code == 201, first.text
        result = first.json(); updated = result["order"]
        assert updated["product_order_quantity"] == row["product_order_quantity"]
        assert [r["required_quantity"] for r in updated["lines"]] == [r["required_quantity"] for r in row["lines"]]
        assert updated["status"] == "PARTIALLY_RECEIVED"
        assert D(updated["lines"][0]["received_quantity"]) == 8
        assert D(updated["lines"][0]["remaining_quantity"]) == 2
        assert result["issue"]["is_replenishment"] and result["issue"]["document_no"].endswith("-B01")
        assert replenish(client, row, request).json() == result
        assert replenish(client, row, {**request, "responsibility": "SUPPLIER" if responsibility == "OWN" else "OWN"}).status_code == 409
        movements = ledger(client)
        outbound = [r for r in movements if r["source_type"] == "ORDER_REPLENISHMENT"]
        assert len(outbound) == 1 and D(outbound[0]["quantity"]) == -2
        assert updated["usage_status"] == "UNUSED"
        assert sum(D(r["quantity"]) for r in movements if r["order_line_id"] == row["lines"][0]["id"]) == 8
        assert client.post(f"{BASE}/inventory/movements/{outbound[0]['id']}/reverse", json={"factory_id": "huaxing", "reason": "测试不允许单独冲销"}).status_code == 409
        issue_id = result["issue"]["id"]
        file = client.get(f"{BASE}/orders/{row['order_no']}/purchase-order-issues/{issue_id}.xlsx", params={"factory_id": "huaxing"})
        assert file.status_code == 200, file.text
        wb = load_workbook(BytesIO(file.content)); sheet = wb.active
        assert sheet["F10"].value == 10 and sheet["G10"].value == 2 and sheet["H10"].value == 10
        assert "补单" in sheet["A1"].value
        context = client.get(f"{BASE}/orders/{row['order_no']}/purchase-order-context", params={"factory_id": "huaxing"}).json()
        assert context["pending_type"] == "NONE"
        receipt = receipt_payload(updated); receipt["lines"] = receipt["lines"][:1]
        receipt["lines"][0].update(delivered_quantity=2, received_quantity=2)
        posted = client.post(BASE + "/receipts", json=receipt)
        assert posted.status_code == 201, posted.text
        replacement_line = posted.json()["lines"][0]
        assert replacement_line["replenishment_issue_id"] == issue_id
        assert replacement_line["responsibility"] == responsibility
        assert D(replacement_line["unit_price"]) == 2  # Inventory retains original cost even when payable is zero.
        assert D(replacement_line["settlement_unit_price"]) == (0 if responsibility == "SUPPLIER" else 2)
        statement = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": "2026-08", "currency": "CNY"})
        assert statement.status_code == 200, statement.text
        source = [s for s in statement.json()["sources"] if s["source_key"] == "RECEIPT:" + replacement_line["id"]]
        assert len(source) == (0 if responsibility == "SUPPLIER" else 1)
        if source:
            assert D(source[0]["amount"]) == 4
        current = _orders(client)[0]
        assert current["status"] == "COMPLETED"
        assert D(current["lines"][0]["received_quantity"]) == 10
        assert D(current["lines"][0]["replenished_quantity"]) == 2
        assert sum(D(r["quantity"]) for r in ledger(client) if r["order_line_id"] == row["lines"][0]["id"]) == 10
        # Additional receipts cannot exceed original demand plus the exact replacement allowance.
        receipt.update(request_id=uuid4().hex, delivery_note_no=uuid4().hex)
        assert client.post(BASE + "/receipts", json=receipt).status_code == 409


def test_invalid_replenishment_rolls_back_all_lines_and_requires_responsibility(monkeypatch):
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        request = body(row, stocks)
        before = ledger(client)
        assert replenish(client, row, {k: v for k, v in request.items() if k != "responsibility"}).status_code == 422
        assert replenish(client, row, {**request, "responsibility": ""}).status_code == 422
        invalid = {**request, "lines": request["lines"] + [{"order_line_id": row["lines"][1]["id"], "location_id": "MISSING", "quantity": 1}]}
        assert replenish(client, row, invalid).status_code in {404, 409, 422}
        assert ledger(client) == before
        assert _orders(client)[0]["revision"] == row["revision"]
        assert replenish(client, row, {**request, "lines": [{**request["lines"][0], "quantity": 11}]}).status_code == 409
        assert replenish(client, row, {**request, "expected_revision": 999}).status_code == 409
        assert replenish(client, row, {**request, "factory_id": "huadeng"}).status_code in {403, 404}
        login_as(client, "qc_inspector")
        assert replenish(client, row, request).status_code == 403


def test_concurrent_replenishment_retry_only_posts_once(monkeypatch):
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        request = body(row, stocks)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: replenish(client, row, request), range(2)))
        assert [r.status_code for r in results] == [201, 201], [r.text for r in results]
        assert results[0].json() == results[1].json()
        assert len([r for r in ledger(client) if r["source_type"] == "ORDER_REPLENISHMENT"]) == 1


def test_replacement_receipts_do_not_inflate_reduction_floor_or_complete_missing_stock(monkeypatch):
    from test_carton_explicit_quantity_api import explicit_payload, create
    from test_carton_procurement_api import _ensure_dickie_customer, _submit_order
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        _ensure_dickie_customer(client)
        login_as(client, "carton_supervisor")
        data = explicit_payload()
        data["lines"] = data["lines"][:1]
        row = _submit_order(client, create(client, data))
        url = f"{BASE}/orders/{row['order_no']}"
        def issue():
            result = client.post(url + "/purchase-order-issues.xlsx", json={"factory_id": "huaxing", "expected_revision": row["revision"]})
            assert result.status_code == 200, result.text
        def receive(qty):
            request = receipt_payload(row)
            request["lines"][0].update(delivered_quantity=qty, received_quantity=qty)
            result = client.post(BASE + "/receipts", json=request)
            assert result.status_code == 201, result.text
            return _orders(client)[0]
        def adjust(action, qty, **overrides):
            return client.post(url + "/" + action, json={"factory_id": "huaxing", "expected_revision": row["revision"],
                "line_quantities": [{"order_line_id": row["lines"][0]["id"], "required_quantity": qty}], **overrides})
        issue()
        row = receive(80)
        stocks = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"}).json()
        result = replenish(client, row, body(row, stocks, qty=10))
        assert result.status_code == 201, result.text
        row = result.json()["order"]
        assert D(row["lines"][0]["maximum_reducible_quantity"]) == 20
        # A net-zero demand change with a new date uses C01, independently of B01.
        result = adjust("append", 101, customer_due_date="2026-08-22", due_date="2026-08-14")
        assert result.status_code == 200, result.text
        row = result.json()
        result = adjust("reduce", 100)
        assert result.status_code == 200, result.text
        row = result.json()
        issue()
        context = client.get(url + "/purchase-order-context", params={"factory_id": "huaxing"}).json()
        assert context["issues"][0]["document_no"].endswith("-C01")
        assert adjust("reduce", 79).status_code == 409
        result = adjust("reduce", 80)
        assert result.status_code == 200, result.text
        row = result.json()
        assert row["status"] == "PARTIALLY_RECEIVED"
        assert D(row["lines"][0]["remaining_quantity"]) == 10
        row = receive(10)
        assert row["status"] == "COMPLETED"
        result = adjust("append", 100)
        assert result.status_code == 200, result.text
        row = result.json()
        result = adjust("reduce", 80)
        assert result.status_code == 200, result.text
        row = result.json()
        assert row["status"] == "COMPLETED"
        # Issue the ordinary reduction without changing the replacement history.
        issue()

        # Reversing the original receipt releases only its own protection evidence.
        from test_carton_receipt_correction_api import reverse
        receipts = client.get(BASE + "/receipts", params={"factory_id": "huaxing"}).json()["items"]
        original = next(doc for doc in receipts if D(doc["lines"][0]["effective_quantity"]) == 80)
        result = reverse(client, original)
        assert result.status_code == 200, result.text
        row = _orders(client)[0]
        assert D(row["lines"][0]["received_quantity"]) == 0
        assert D(row["lines"][0]["maximum_reducible_quantity"]) == 80
        result = adjust("reduce", 10)
        assert result.status_code == 200, result.text


def test_replenishment_requires_original_issue_and_available_physical_stock(monkeypatch):
    from test_carton_transaction_guards_api import outbound
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        result = client.post(BASE + "/receipts", json=receipt_payload(row))
        assert result.status_code == 201, result.text
        row = _orders(client)[0]
        stocks = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"}).json()
        before = ledger(client)
        # Submission now issues P00 automatically. Exercise the missing-document
        # guard using a legacy missing-issue fixture without deleting audit data.
        from app.services import carton_procurement as core
        with monkeypatch.context() as legacy:
            legacy.setattr(core, "_purchase_order_issues", lambda *_: [])
            assert replenish(client, row, body(row, stocks)).status_code == 409
        assert ledger(client) == before

        location = body(row, stocks)["lines"][0]["location_id"]
        result = client.post(BASE + "/inventory/movements", json=outbound(row, 9, location_id=location, issue_kind="USAGE"))
        assert result.status_code == 201, result.text
        before = ledger(client)
        assert replenish(client, row, body(row, stocks)).status_code == 409
        assert ledger(client) == before


def test_split_replacements_reserve_each_issue_and_separate_cost_from_payable(monkeypatch):
    from test_carton_transaction_guards_api import confirm
    from test_carton_receipt_correction_api import reverse
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        first = replenish(client, row, body(row, stocks, "SUPPLIER", 2)).json()
        row = first["order"]
        second = replenish(client, row, body(row, stocks, "OWN", 3)).json()
        row = second["order"]
        free_id, paid_id = first["issue"]["id"], second["issue"]["id"]
        def receive(qty, issue_id=None, *, post=True, price=9):
            request = receipt_payload(row)
            request.update(post_immediately=post, acceptance_date="2026-08-05")
            request["lines"] = request["lines"][:1]
            request["lines"][0].update(delivered_quantity=qty, received_quantity=qty, unit_price=price)
            if issue_id:
                request["lines"][0]["replenishment_issue_id"] = issue_id
            return client.post(BASE + "/receipts", json=request)
        assert receive(1).status_code == 409  # Mixed responsibility cannot be guessed.
        assert receive(1, "OTHER-FACTORY-ISSUE").status_code == 409
        pending = receive(1, free_id, post=False)
        assert pending.status_code == 201, pending.text
        assert receive(2, free_id).status_code == 409  # Pending receipt reserves only its B quota.
        posted = confirm(client, pending.json())
        assert posted.status_code == 200, posted.text
        assert D(posted.json()["lines"][0]["unit_price"]) == 2  # Submitted 9 cannot turn free replacement into a charge.
        assert D(posted.json()["lines"][0]["settlement_unit_price"]) == 0
        free = receive(1, free_id)
        assert free.status_code == 201, free.text
        paid = receive(3, paid_id, price=3)
        assert paid.status_code == 201, paid.text
        statement = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": "2026-08", "currency": "CNY"}).json()
        assert sum(D(s["amount"]) for s in statement["sources"]) == 229  # Original 220 plus OWN 3 × 3; SUPPLIER adds zero.
        positions = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"}).json()
        stock = next(s for s in positions if s["order_line_id"] == row["lines"][0]["id"])
        assert D(stock["balance"]) == 10 and D(stock["cost_amount"]) == 23
        login_as(client, "carton_supervisor")
        reversed_free = reverse(client, free.json())
        assert reversed_free.status_code == 200, reversed_free.text
        options = _orders(client)[0]["lines"][0]["replenishment_options"]
        assert len(options) == 1 and options[0]["replenishment_issue_id"] == free_id
        assert D(options[0]["remaining_quantity"]) == 1
        reentered = receive(1, free_id)
        assert reentered.status_code == 201, reentered.text
        again = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": "2026-08", "currency": "CNY"}).json()
        assert sum(D(s["amount"]) for s in again["sources"]) == 229


def test_concurrent_free_receipts_cannot_consume_one_replacement_twice(monkeypatch):
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        result = replenish(client, row, body(row, stocks, "SUPPLIER", 1)).json()
        row = result["order"]
        def submit(_):
            request = receipt_payload(row)
            request["lines"] = request["lines"][:1]
            request["lines"][0].update(delivered_quantity=1, received_quantity=1, replenishment_issue_id=result["issue"]["id"])
            request["lines"][0].pop("unit_price")
            return client.post(BASE + "/receipts", json=request)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]


def test_legacy_unlinked_replacement_is_flagged_instead_of_reused_as_free_quota(monkeypatch):
    from sqlalchemy import delete
    with make_client(monkeypatch) as client:
        from app.models.carton_procurement import CartonAuditEvent
        from app import db as app_db
        from app.services.carton_replenishment_receipts import EVENT
        row, stocks = setup(client, monkeypatch)
        result = replenish(client, row, body(row, stocks, "SUPPLIER", 2)).json()
        row = result["order"]
        request = receipt_payload(row); request["lines"] = request["lines"][:1]
        request["lines"][0].update(delivered_quantity=2, received_quantity=2)
        posted = client.post(BASE + "/receipts", json=request)
        assert posted.status_code == 201, posted.text
        # Isolated fixture: emulate a pre-link-version receipt without rewriting real data.
        with app_db.SessionLocal() as db:
            db.execute(delete(CartonAuditEvent).where(CartonAuditEvent.event_type == EVENT,
                       CartonAuditEvent.entity_id == posted.json()["lines"][0]["id"]))
            db.commit()
        current = _orders(client)[0]
        assert current["lines"][0]["replenishment_review_required"] is True
        assert current["lines"][0]["replenishment_options"] == []
        statement = client.get(BASE + "/supplier-settlements/workspace", params={"factory_id": "huaxing", "period": "2026-08", "currency": "CNY"}).json()
        assert any("未关联补单" in issue for source in statement["sources"] for issue in source["issues"])
        login_as(client, "carton_supervisor")
        appended = client.post(f"{BASE}/orders/{row['order_no']}/append", json={"factory_id": "huaxing",
            "expected_revision": current["revision"], "additional_quantity": 20})
        assert appended.status_code == 200, appended.text
        request.update(request_id=uuid4().hex, delivery_note_no=uuid4().hex)
        assert client.post(BASE + "/receipts", json=request).status_code == 409


def test_ordinary_receipts_after_replacement_do_not_consume_its_free_quota(monkeypatch):
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        login_as(client, "carton_supervisor")
        appended = client.post(f"{BASE}/orders/{row['order_no']}/append", json={"factory_id": "huaxing",
            "expected_revision": row["revision"], "additional_quantity": 100})
        assert appended.status_code == 200, appended.text
        row = appended.json()
        issued = client.post(f"{BASE}/orders/{row['order_no']}/purchase-order-issues.xlsx", json={"factory_id": "huaxing", "expected_revision": row["revision"]})
        assert issued.status_code == 200, issued.text
        result = replenish(client, row, body(row, stocks, "SUPPLIER", 2))
        assert result.status_code == 201, result.text
        row = result.json()["order"]
        request = receipt_payload(row); request["lines"] = request["lines"][:1]
        request["lines"][0].update(delivered_quantity=10, received_quantity=10)
        ordinary = client.post(BASE + "/receipts", json=request)
        assert ordinary.status_code == 201, ordinary.text
        assert ordinary.json()["lines"][0]["replenishment_issue_id"] is None
        current = _orders(client)[0]["lines"][0]
        assert not current["replenishment_review_required"]
        assert D(current["replenishment_options"][0]["remaining_quantity"]) == 2
        request.update(request_id=uuid4().hex, delivery_note_no=uuid4().hex)
        request["lines"][0].update(delivered_quantity=2, received_quantity=2)
        free = client.post(BASE + "/receipts", json=request)
        assert free.status_code == 201, free.text
        assert free.json()["lines"][0]["responsibility"] == "SUPPLIER"


@pytest.mark.parametrize("verified_zero", [False, True])
def test_free_replacement_distinguishes_unknown_cost_from_verified_zero(monkeypatch, verified_zero):
    with make_client(monkeypatch) as client:
        from app import db as app_db
        from app.models.carton_procurement import CartonInventoryMovement, CartonReceiptLine
        row, stocks = setup(client, monkeypatch)
        original = next(m for m in ledger(client) if m["order_line_id"] == row["lines"][0]["id"])
        # Isolated legacy fixture, not a production price edit.
        with app_db.SessionLocal() as db:
            movement = db.get(CartonInventoryMovement, original["id"])
            movement.unit_price = D(0)
            db.get(CartonReceiptLine, movement.source_line_id).unit_price = D(0)
            db.commit()
        login_as(client, "carton_supervisor")
        if verified_zero:
            result = client.post(f"{BASE}/inventory/movements/{original['id']}/price-confirmation", json={
                "factory_id": "huaxing", "unit_price": "0", "zero_price_confirmed": True, "reason": "已核对原货为免费物料"})
            assert result.status_code == 204, result.text
        result = replenish(client, row, body(row, stocks, "SUPPLIER", 1))
        assert result.status_code == 201, result.text
        request = receipt_payload(result.json()["order"])
        request["lines"] = request["lines"][:1]
        request["lines"][0].update(delivered_quantity=1, received_quantity=1, replenishment_issue_id=result.json()["issue"]["id"])
        request["lines"][0].pop("unit_price")
        posted = client.post(BASE + "/receipts", json=request)
        assert posted.status_code == (201 if verified_zero else 409), posted.text
        if verified_zero:
            assert D(posted.json()["lines"][0]["unit_price"]) == 0
            inbound = next(m for m in ledger(client) if m["source_line_id"] == posted.json()["lines"][0]["id"])
            assert D(inbound["cost_amount"]) == 0
            assert client.post(f"{BASE}/inventory/movements/{inbound['id']}/price-confirmation", json={
                "factory_id": "huaxing", "unit_price": "9", "reason": "不能覆盖免费补货成本"}).status_code == 409
