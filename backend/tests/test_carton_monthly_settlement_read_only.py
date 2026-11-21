from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import accept_all, receive_payload, setup_portal, ship_payload, supplier_login
from test_carton_transaction_guards_api import confirm, draft, outbound

BASE = "/api/carton-procurement"
SUPPLIER = "/api/carton-supplier"
MONTH = "/monthly-settlements/workspace"


def read_month(client, portal, query):
    from app.db import engine

    statements = []

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.upper().split()))

    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        response = client.get(portal + MONTH, params=query)
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)

    assert response.status_code == 200, response.text
    writes = [statement for statement in statements if statement.startswith(
        ("BEGIN IMMEDIATE", "UPDATE ", "INSERT ", "DELETE ")
    ) or "PG_ADVISORY_XACT_LOCK" in statement]
    assert not writes, writes
    assert "BEGIN" in statements
    return response.json()


def test_monthly_settlement_workspace_is_read_only(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        login_as(client, "admin")
        body = read_month(client, BASE, {"factory_id": "huaxing", "period": "2026-10", "currency": "CNY"})
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

        warehouse = read_month(client, BASE, query)
        accepted = [row for row in warehouse["lines"] if row["document_no"] == "DN-PORTAL"]
        assert len(accepted) == 2
        assert all(row["reference"] == {"kind": "RECEIPT", "id": receipt_id} for row in accepted)

        supplier_login(client)
        east = read_month(client, SUPPLIER, query)
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


def test_both_read_projections_follow_formal_prices_and_keep_original_quote_evidence(monkeypatch):
    from app.db import Base
    from app.models.carton_price_review import CartonPriceReview
    from app.models.carton_procurement import CartonInventoryMovement, CartonReceipt, CartonReceiptLine, CartonSupplier
    from app.services import carton_monthly_settlement as monthly
    from app.services import carton_settlement_collaboration as collaboration
    from app.services import carton_supplier_settlement as formal

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(monthly.database, "SessionLocal", sessions)
    now = "2026-09-10T08:00:00+08:00"
    day = "2026-09-10"

    with sessions.begin() as db:
        for factory in ("huaxing", "huakang-a"):
            db.add(CartonSupplier(id=f"dongkang-{factory}", factory_id=factory, supplier_code="HEYUAN-DONGKANG",
                                  supplier_name="东康", created_at=now, updated_at=now))
        db.add(CartonSupplier(id="other-huaxing", factory_id="huaxing", supplier_code="OTHER",
                              supplier_name="另一供应商", created_at=now, updated_at=now))

        def receipt(key, customer, quantity, *, posted_price=0, review=None, factory="huaxing", currency="CNY",
                    supplier=None, review_supplier=None):
            supplier = supplier or f"dongkang-{factory}"
            receipt_id = f"receipt-{key}"
            document = f"DN-{key}"
            db.add(CartonReceipt(id=receipt_id, factory_id=factory, receipt_no=receipt_id, delivery_note_no=document,
                                 delivery_date=day, acceptance_date=day, supplier_id=supplier, supplier_name_snapshot="东康",
                                 status="POSTED", created_by="warehouse", created_at=now, updated_at=now, confirmed_at=now))
            details = dict(factory_id=factory, customer_code=customer, customer_name=customer, contract_no="",
                           item_no=f"item-{key}", packaging_type="外箱", paper_quality="A33", specification="30*20*15",
                           unit="个", unit_price=posted_price, currency=currency)
            db.add(CartonReceiptLine(id=key, receipt_id=receipt_id, line_no=1, source_type="AD_HOC",
                                     delivered_quantity=quantity + 2, received_quantity=quantity + 2, rejected_quantity=2,
                                     effective_quantity=quantity, **details))
            db.add(CartonInventoryMovement(id=f"move-{key}", movement_type="INBOUND", quantity=quantity,
                                           document_no=document, source_type="RECEIPT", source_id=receipt_id,
                                           source_line_id=key, actor_user_id="warehouse", occurred_at=now, **details))
            if review is not None:
                status, original, proposed = review
                db.add(CartonPriceReview(id=f"review-{key}", factory_id=factory, supplier_id=review_supplier or supplier,
                                        receipt_line_id=key, source_kind="REGULAR", shipment_id=f"shipment-{key}",
                                        shipment_line_id=f"shipment-line-{key}", original_unit_price=original,
                                        proposed_unit_price=proposed, status=status, created_by="warehouse",
                                        updated_by="warehouse", updated_at=now))

        receipt("proposal", "ALPHA", 10, review=("PROPOSED", 2, 3))
        receipt("priced", "ALPHA", 4, posted_price=2, review=("CONFIRMED", 2, 2))
        receipt("zero-pending", "BETA", 3, review=("PENDING", 0, None))
        receipt("blank", "BETA", 3, review=("PENDING", None, None))
        receipt("free", "BETA", 2, review=("CONFIRMED", 0, 0))
        receipt("mislinked", "GAMMA", 2, posted_price=4, review=("CONFIRMED", 89, 99), review_supplier="other-huaxing")
        receipt("other-supplier", "GAMMA", 2, posted_price=5, review=("CONFIRMED", 5, 5), supplier="other-huaxing")
        receipt("hkd", "ALPHA", 5, posted_price=10, currency="HKD")
        receipt("other-factory", "ALPHA", 9, posted_price=10, factory="huakang-a")

    def month(factory="huaxing", currency="CNY"):
        return monthly.read_workspace(factory, "2026-09", currency)

    before = month()
    warehouse = {line["document_no"]: line for line in before["lines"]}
    assert set(warehouse) == {"DN-proposal", "DN-priced", "DN-zero-pending", "DN-blank", "DN-free", "DN-mislinked"}
    with sessions() as db:
        sources, fingerprint, *_ = formal.sources(db, "huaxing", "dongkang-huaxing", "2026-09", "CNY")
        other_sources, *_ = formal.sources(db, "huaxing", "other-huaxing", "2026-09", "CNY")
        suggested = collaboration.build(db, "huaxing", "dongkang-huaxing", "2026-09", "CNY", sources, fingerprint)
    assert before["source_fingerprint"] == fingerprint
    assert [(line["document_no"], line["amount"]) for line in other_sources] == [("DN-other-supplier", "10.00")]
    for source in sources:
        internal = warehouse[source["document_no"]]
        projected = monthly.supplier_line(internal)
        for key in ("unit_price", "amount"):
            assert projected[key] == internal[key] == source[key]
        assert projected.get("supplier_original_price") == internal.get("supplier_original_price")
        assert "receipt_id" not in projected and "price_review" not in projected and "supplier_delivery" not in projected

    mislinked = warehouse["DN-mislinked"]
    assert mislinked["unit_price"] is None and mislinked["amount"] is None
    assert any("供应商归属不一致" in issue for issue in mislinked["issues"])
    assert "price_review" not in mislinked and "supplier_original_price" not in mislinked
    assert monthly.supplier_line(mislinked)["issues"] == ["送货单价待核实"]
    mismatch_line = next(line for line in suggested["lines"] if line["document_no"] == "DN-mislinked")
    mismatch_source = next(line for line in suggested["sources"] if line["document_no"] == "DN-mislinked")
    assert mismatch_line["unit_price"] is None and mismatch_line["amount"] is None
    assert mismatch_source["supplier_delivery"] is None

    proposal = warehouse["DN-proposal"]
    assert proposal["amount"] is None and proposal["unit_price"] is None
    assert any("待双方核实" in issue for issue in proposal["issues"])
    assert Decimal(proposal["supplier_original_price"]["unit_price"]) == 2
    assert proposal["supplier_original_price"]["reference_amount"] == "20.00"
    assert warehouse["DN-zero-pending"]["amount"] is None
    assert warehouse["DN-zero-pending"]["supplier_original_price"]["reference_amount"] == "0.00"
    assert warehouse["DN-blank"]["supplier_original_price"] == {"unit_price": None, "reference_amount": None}
    assert warehouse["DN-free"]["amount"] == "0.00"
    totals = before["totals"]
    customers = {group["key"]: group["totals"] for group in before["customers"]}
    assert totals["net"] is None and totals["verified_net"] == "8.00" and totals["pending_price_lines"] == 4
    assert customers["code:ALPHA"]["net"] is None and customers["code:ALPHA"]["verified_net"] == "8.00"
    assert customers["code:ALPHA"]["pending_price_lines"] == 1
    assert customers["code:BETA"]["net"] is None and customers["code:BETA"]["verified_net"] == "0.00"
    assert customers["code:GAMMA"]["net"] is None and customers["code:GAMMA"]["verified_net"] is None
    assert customers["code:GAMMA"]["pending_price_lines"] == 1
    assert month(currency="HKD")["totals"]["net"] == "50.00"
    assert month(factory="huakang-a")["totals"]["net"] == "90.00"

    with sessions.begin() as db:
        review = db.get(CartonPriceReview, "review-proposal")
        review.status = "CONFIRMED"
        review.revision += 1

    after = month()
    confirmed = next(line for line in after["lines"] if line["document_no"] == "DN-proposal")
    assert confirmed["amount"] == "30.00" and Decimal(confirmed["unit_price"]) == 3
    assert confirmed["issues"] == []
    assert confirmed["supplier_original_price"] == proposal["supplier_original_price"]
    assert monthly.supplier_line(confirmed)["amount"] == "30.00"
    assert after["totals"]["verified_net"] == "38.00" and after["totals"]["pending_price_lines"] == 3
    alpha = next(group["totals"] for group in after["customers"] if group["key"] == "code:ALPHA")
    assert alpha["net"] == "38.00" and alpha["pending_price_lines"] == 0
    with sessions() as db:
        assert db.get(CartonReceiptLine, "proposal").unit_price == 0
        assert db.get(CartonInventoryMovement, "move-proposal").unit_price == 0
