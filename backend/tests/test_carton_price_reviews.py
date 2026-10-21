from decimal import Decimal
from uuid import uuid4
import json
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_partial_shipment_receiving import begin, payload, post
from test_carton_supplier_portal import BASE, supplier_login, revoke_supplier_permission
from test_carton_settlement_collaboration import workspace, save, review
from test_carton_supplier_settlement_api import action

PRICES = "/api/carton-price-reviews"


def rows(client, external=False):
    response = client.get(PRICES + ("/supplier" if external else "/internal"), params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def decision(client, row, **changes):
    data = dict(factory_id="huaxing", expected_revision=row["revision"], request_id=str(uuid4()), decision="CONFIRM") | changes
    return client.post(PRICES + f"/supplier/{row['id']}/decide", json=data)


def test_pending_price_receives_stock_then_supplier_agrees_without_mutating_original(monkeypatch):
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        data = payload(client, shipment, 6)
        for line in data["lines"]:
            line.update(unit_price=3, price_action="PROPOSE", price_reason="供应商送货价格有误")
        received = post(client, shipment, data)
        pending = rows(client)
        assert len(pending) == 2
        assert {row["status"] for row in pending} == {"PROPOSED"}
        assert {Decimal(row["original_unit_price"]) for row in pending} == {2}
        assert {Decimal(row["quantity"]) for row in pending} == {6}
        # Idempotent physical receipt does not duplicate a review or stock.
        assert post(client, shipment, data)["receipt_id"] == received["receipt_id"]
        assert len(rows(client)) == 2
        login_as(client, "carton_supervisor")
        before = workspace(client)
        assert all(row["amount"] is None for row in before["sources"])
        assert all("送货价格待双方核实" in " ".join(row["issues"]) for row in before["sources"])
        supplier_login(client)
        for row in rows(client, True):
            confirmed = decision(client, row)
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["status"] == "CONFIRMED"
            assert decision(client, row).status_code == 409
        login_as(client, "carton_supervisor")
        after = workspace(client)
        assert all(Decimal(row["unit_price"]) == 3 and Decimal(row["amount"]) == 18 for row in after["sources"])
        assert all(Decimal(row["amount"]) == 18 for row in after["collaboration"]["lines"])
        # Vendor source price is preserved; agreement is a distinct evidence record.
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipmentLine
        from sqlalchemy import select
        with SessionLocal() as db:
            assert all(json.loads(line.snapshot_json)["delivery_unit_price"] == "2" for line in db.scalars(select(SupplierShipmentLine)))


def test_explicit_free_needs_supplier_confirmation_and_closed_month_is_immutable(monkeypatch):
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        data = payload(client, shipment, 6)
        for line in data["lines"]:
            line.update(unit_price=0, zero_price_kind="FREE", price_action="FREE", price_reason="核实为免费补送")
        post(client, shipment, data)
        supplier_login(client)
        for row in rows(client, True):
            result = decision(client, row)
            assert result.status_code == 200, result.text
        login_as(client, "carton_supervisor")
        current = workspace(client)
        assert all(Decimal(row["amount"]) == 0 and not row["issues"] for row in current["sources"])
        saved = save(client, current)
        supplier_login(client)
        approved = review(client, saved)
        assert approved.status_code == 200, approved.text
        login_as(client, "carton_supervisor")
        confirmed = action(client, approved.json())
        assert confirmed.status_code == 200, confirmed.text
        row = rows(client)[0]
        assert row["locked"] and not row["actionable"]
        response = client.post(PRICES + f"/internal/{row['id']}/propose", json=dict(factory_id="huaxing",
            expected_revision=row["revision"], request_id=str(uuid4()), proposed_unit_price=2, reason="事后核对价格变化"))
        assert response.status_code == 409


def test_supplier_permission_factory_revision_and_rejection(monkeypatch):
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        data = payload(client, shipment, 6)
        for line in data["lines"]:
            line.update(unit_price=0, zero_price_kind="PENDING", price_action="PENDING")
        post(client, shipment, data)
        row = rows(client)[0]
        supplier_login(client)
        assert decision(client, row).status_code == 409
        assert decision(client, row, factory_id="huakang-a").status_code in {403, 404, 409}
        login_as(client, "warehouse_keeper")
        proposal = dict(factory_id="huaxing", expected_revision=row["revision"], request_id=str(uuid4()), proposed_unit_price=0, reason="核实为赠品免费")
        url = PRICES + f"/internal/{row['id']}/propose"
        assert client.post(url, json=proposal).status_code == 422
        proposal["free_confirmed"] = True
        proposed = client.post(url, json=proposal)
        assert proposed.status_code == 200, proposed.text
        assert client.post(url, json=proposal).status_code == 200
        assert client.post(url, json=proposal | {"proposed_unit_price": 1, "free_confirmed": False}).status_code == 409
        supplier_login(client)
        rejected = decision(client, proposed.json(), decision="REJECT", reason="供应商核实不是赠品")
        assert rejected.status_code == 200 and rejected.json()["status"] == "PENDING"
        revoke_supplier_permission("carton_supplier:approve")
        supplier_login(client)
        assert decision(client, rejected.json()).status_code == 403


def test_blank_price_is_not_free():
    from app.schemas.carton_price_review import Propose
    from pydantic import ValidationError
    base = dict(factory_id="huaxing", expected_revision=1, request_id="blank-price", reason="等待核实送货价格")
    assert Propose(**base).proposed_unit_price is None
    with pytest.raises(ValidationError):
        Propose(**base, proposed_unit_price=0)


@pytest.mark.parametrize("action,value", [("FREE", Decimal("2")), ("PROPOSE", None)])
def test_special_acceptance_cannot_mislabel_or_infer_a_price_proposal(action, value):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.services.carton_price_review import record_line
    source = SimpleNamespace(snapshot_json=json.dumps({"unit_price": "2", "pricing_kind": "CHARGED"}))
    receipt_line = SimpleNamespace(unit_price=Decimal("2"), effective_quantity=Decimal("1"))
    acceptance = SimpleNamespace(unit_price=value, price_action=action, price_reason="现场核对送货价格")
    with pytest.raises(HTTPException) as error:
        record_line(None, None, receipt_line, source, None, acceptance, source_kind="SPECIAL")
    assert error.value.status_code == 422


def test_declared_free_delivery_requires_no_second_price_approval(monkeypatch):
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipmentLine
        from sqlalchemy import select
        with SessionLocal() as db:
            for source in db.scalars(select(SupplierShipmentLine)):
                source.snapshot_json = json.dumps(json.loads(source.snapshot_json) | {"delivery_unit_price": "0", "free_confirmed": True})
            db.commit()
        data = payload(client, shipment, 6)
        for line in data["lines"]:
            line.update(unit_price=0, price_action="FREE", zero_price_kind="FREE", difference_reason="")
        post(client, shipment, data)
        assert all(row["status"] == "CONFIRMED" for row in rows(client))
        login_as(client, "carton_supervisor")
        result = workspace(client)
        assert all(row["amount"] == "0.00" and not row["issues"] for row in result["sources"])
