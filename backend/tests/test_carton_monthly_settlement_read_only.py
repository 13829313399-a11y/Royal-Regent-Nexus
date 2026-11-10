from decimal import Decimal
from types import SimpleNamespace

from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import accept_all, receive_payload, setup_portal, ship_payload, supplier_login
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


def test_original_price_fallback_does_not_turn_unconfirmed_zero_into_free():
    from app.services import carton_monthly_settlement as monthly

    pending = "送货价格待双方核实，不能完成月结确认"
    rows = [
        {"kind": "RECEIPT", "source_key": "RECEIPT:pending", "quantity": "3", "amount": None, "issues": [pending]},
        {"kind": "RECEIPT", "source_key": "RECEIPT:free", "quantity": "3", "amount": "0.00", "issues": []},
        {"kind": "RECEIPT", "source_key": "RECEIPT:priced", "quantity": "3", "amount": None, "issues": [pending]},
    ]
    reviews = [
        SimpleNamespace(receipt_line_id=identifier, original_unit_price=Decimal(price))
        for identifier, price in (("pending", "0"), ("free", "0"), ("priced", "2.5"))
    ]
    monthly.adopt_supplier_original_prices(SimpleNamespace(scalars=lambda query: reviews), "huaxing", rows)
    assert rows[0]["amount"] is None and rows[0]["issues"] == [pending]
    assert rows[1]["amount"] == "0.00" and rows[1]["issues"] == []
    assert rows[2]["amount"] == "7.50" and rows[2]["issues"] == []
    assert monthly._totals(rows)["net"] is None
