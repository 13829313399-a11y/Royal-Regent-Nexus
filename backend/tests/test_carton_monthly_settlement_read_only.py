import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import event

from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare
from test_carton_partial_shipment_receiving import begin, payload, post
from test_carton_price_reviews import decision, rows as price_reviews
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import _dongkang_delivery_file, accept_all, receive_payload, setup_portal, ship_payload, supplier_login
from test_carton_transaction_guards_api import confirm, draft, outbound

BASE = "/api/carton-procurement"
SUPPLIER = "/api/carton-supplier"
MONTH = "/monthly-settlements/workspace"


def test_monthly_settlement_workspace_is_read_only(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        login_as(client, "admin")
        workspace = client.get(BASE + "/monthly-settlements/workspace",
                               params={"factory_id": "huaxing", "period": "2026-10", "currency": "CNY"})
        assert workspace.status_code == 200, workspace.text
        body = workspace.json()
        assert body["read_only"] is True
        assert body["can_submit"] is False and body["can_lock"] is False
        assert "totals" in body and "lines" in body

        for action in ("submit", "lock", "unlock"):
            response = client.post(BASE + f"/monthly-settlements/{action}",
                                   json={"factory_id": "huaxing", "period": "2026-10", "currency": "CNY", "reason": "只读验证"})
            assert response.status_code == 410, (action, response.text)


def test_monthly_customer_totals_and_original_documents_agree_between_portals(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    factory = {"factory_id": "huaxing"}
    query = {**factory, "period": "2026-09", "currency": "CNY"}

    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        shipment_data = ship_payload(accept_all(client))
        for line in shipment_data["lines"]:
            line["unit_price"] = "2"
        sent = client.post(SUPPLIER + "/shipments", json=shipment_data)
        assert sent.status_code == 201, sent.text
        shipment = sent.json()

        login_as(client, "admin")
        received = client.post(SUPPLIER + f"/internal/shipments/{shipment['id']}/receive",
                               json=receive_payload(client, shipment))
        assert received.status_code == 200, received.text
        receipt_id = received.json()["receipt_id"]
        returned = client.post(BASE + "/inventory/movements", json=outbound(
            order, 2, issue_kind="RETURN", document_no="MONTH-RETURN", return_date="2026-09-24"))
        assert returned.status_code == 201, returned.text

        customer = {"customer_code": "MONTH-B", "customer_name": "月结客户乙"}
        created = client.post(BASE + "/customers", json={**factory, **customer, "country_region": "德国"})
        assert created.status_code == 201, created.text
        other_order = client.post(BASE + "/orders", json={
            **_order_payload(), **customer, "contract_no": "MONTH-B-1",
        })
        assert other_order.status_code == 201, other_order.text
        other = _submit_order(client, other_order.json())
        manual = draft(client, other, 3, delivery_note_no="MONTH-MANUAL", acceptance_date="2026-09-22")
        assert manual.status_code == 201, manual.text
        posted = confirm(client, manual.json())
        assert posted.status_code == 200, posted.text

        internal = client.get(BASE + MONTH, params=query)
        assert internal.status_code == 200, internal.text
        warehouse = internal.json()
        accepted = [row for row in warehouse["lines"] if row["document_no"] == "DN-PORTAL"]
        assert len(accepted) == 2
        assert all(row["reference"] == {"kind": "RECEIPT", "id": receipt_id} for row in accepted)

        supplier_login(client)
        external = client.get(SUPPLIER + MONTH, params=query)
        assert external.status_code == 200, external.text
        east = external.json()
        assert east["totals"] == warehouse["totals"]
        assert east["customers"] == warehouse["customers"]
        assert east["global_issues"] == []
        groups = {group["key"]: group["totals"] for group in east["customers"]}
        assert set(groups) == {"code:DICKIE", "code:MONTH-B"}
        assert Decimal(groups["code:DICKIE"]["inbound"]) == 32
        assert groups["code:DICKIE"]["net"] is None
        assert Decimal(groups["code:MONTH-B"]["net"]) == 6
        assert Decimal(east["totals"]["inbound"]) == 38
        assert east["totals"]["net"] is None
        assert Decimal(east["totals"]["verified_net"]) == 38
        assert east["totals"]["pending_price_lines"] == 1
        assert Decimal(groups["code:DICKIE"]["verified_net"]) == 32
        documents = {row["document_no"]: row for row in east["lines"]}
        delivery = documents["DN-PORTAL"]["reference"]
        assert delivery["kind"] == "DELIVERY"
        original = client.get(SUPPLIER + f"/unified-deliveries/{delivery['id']}", params=factory)
        assert original.status_code == 200, original.text
        assert original.json()["delivery_note_no"] == "DN-PORTAL"
        assert "receipt_id" not in documents["DN-PORTAL"]
        assert documents["MONTH-MANUAL"]["reference"] is None
        difference = documents["MONTH-RETURN"]
        assert difference["issues"] and difference["customer_key"] == "code:DICKIE"
        assert difference["reference"] == {"kind": "RETURN", "id": returned.json()["id"]}
        assert client.get(SUPPLIER + f"/returns/{returned.json()['id']}", params=factory).status_code == 200
        assert client.get(BASE + f"/receipts/{receipt_id}", params=factory).status_code == 403
        for action in ("confirm", "dispute"):
            retired = client.post(SUPPLIER + f"/monthly-settlements/{action}", json={**query, "reason": "只读验证"})
            assert retired.status_code == 410, retired.text


def test_monthly_price_reference_and_cross_month_reversal_follow_the_original_note(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    factory = {"factory_id": "huaxing"}

    def month(client, endpoint, period="2026-09"):
        response = client.get(endpoint + MONTH, params={**factory, "period": period, "currency": "CNY"})
        assert response.status_code == 200, response.text
        return response.json()

    with make_client(monkeypatch) as client:
        setup_portal(client)
        order = accept_all(client)
        content = _dongkang_delivery_file(order, source_price=2)
        upload = {"file": ("送货明细表.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        preview = client.post(SUPPLIER + "/shipments/import-preview", files=upload)
        assert preview.status_code == 200 and preview.json()["groups"][0]["ready"], preview.text
        confirmed = client.post(SUPPLIER + "/shipments/import-confirm", files=upload, data={
            "sha256": preview.json()["sha256"],
            "selections": json.dumps([{**factory, "delivery_note_no": "DK-IMPORT-01"}]),
        })
        assert confirmed.status_code == 200, confirmed.text
        shipment = confirmed.json()["shipments"][0]

        login_as(client, "warehouse_keeper")
        first_data = payload(client, shipment, 6)
        for paper in first_data["lines"]:
            paper.update(unit_price=3, price_action="PROPOSE", price_reason="原单和实收价格待核对")
        first = post(client, shipment, first_data)
        warehouse = month(client, BASE)
        assert warehouse["totals"]["net"] is None and warehouse["totals"]["pending_price_lines"] == 2
        assert Decimal(warehouse["totals"]["verified_net"]) == 0
        assert all(row["unit_price"] is None and row["amount"] is None and row["issues"] for row in warehouse["lines"])

        supplier_login(client)
        pending = month(client, SUPPLIER)
        assert pending["totals"] == warehouse["totals"] and pending["customers"] == warehouse["customers"]
        assert len(pending["lines"]) == 2
        for row in pending["lines"]:
            assert row["amount"] is None and row["issues"] == ["送货单价待核实"]
            assert Decimal(row["supplier_original_unit_price"]) == 2
            assert Decimal(row["supplier_original_amount"]) == 12
            assert "receipt_id" not in row and "price_review" not in row
        for review in price_reviews(client, external=True):
            response = decision(client, review)
            assert response.status_code == 200, response.text
        agreed = month(client, SUPPLIER)
        assert Decimal(agreed["totals"]["net"]) == 36
        assert agreed["totals"]["pending_price_lines"] == 0

        login_as(client, "warehouse_keeper")
        assert month(client, BASE)["totals"] == agreed["totals"]
        second = post(client, first, payload(client, first, 4, "2026-10-01"))
        assert second["status"] == "RECEIVED"
        assert Decimal(month(client, BASE, "2026-10")["totals"]["net"]) == 16
        receipt_id = first["receipt_id"]
        receipt_path = BASE + f"/receipts/{receipt_id}"
        receipt = client.get(receipt_path, params=factory)
        assert receipt.status_code == 200, receipt.text
        reversed_receipt = client.post(receipt_path + "/reverse", json={
            **factory, "expected_revision": receipt.json()["revision"], "reason": "分批入库核对后冲销首批",
        })
        assert reversed_receipt.status_code == 200, reversed_receipt.text
        supplier_login(client)
        assert month(client, SUPPLIER)["lines"] == []
        october = month(client, SUPPLIER, "2026-10")
        assert Decimal(october["totals"]["net"]) == 16
        original_id = october["lines"][0]["reference"]["id"]
        original = client.get(SUPPLIER + f"/unified-deliveries/{original_id}", params=factory)
        assert original.status_code == 200, original.text
        assert original.json()["delivery_note_no"] == "DK-IMPORT-01"
        assert original.json()["requires_correction"] is True


def test_monthly_read_snapshot_allows_same_factory_receipt_and_refresh(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    query = {"factory_id": "huaxing", "period": "2026-09", "currency": "CNY"}
    with make_client(monkeypatch) as writer:
        _, shipment = begin(writer, monkeypatch)
        data = payload(writer, shipment, 6)
        from app.db import engine
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"

        started, posted = Event(), Event()
        statements = []
        reader_connection = None

        def observe(connection, _cursor, statement, _parameters, _context, _executemany):
            nonlocal reader_connection
            if statement == "BEGIN" and not started.is_set():
                reader_connection = connection
            if connection is reader_connection:
                statements.append(statement)
                if not started.is_set() and "FROM carton_suppliers" in statement:
                    started.set()
                    assert posted.wait(20), "Warehouse receipt did not commit while the month was open"

        reader = TestClient(writer.app)
        try:
            supplier_login(reader)
            event.listen(engine, "after_cursor_execute", observe)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending = pool.submit(reader.get, SUPPLIER + MONTH, params=query)
                    try:
                        assert started.wait(10), "Monthly GET did not start a read snapshot"
                        post(writer, shipment, data)
                    finally:
                        posted.set()
                    previous = pending.result(timeout=20)
            finally:
                event.remove(engine, "after_cursor_execute", observe)
            assert previous.status_code == 200 and previous.json()["lines"] == [], previous.text
            assert statements[0] == "BEGIN"
            assert all(statement.startswith("SELECT") for statement in statements[1:])
            latest = reader.get(SUPPLIER + MONTH, params=query)
            assert latest.status_code == 200, latest.text
            assert Decimal(latest.json()["totals"]["net"]) == 24
            assert len(latest.json()["lines"]) == 2
        finally:
            reader.close()
