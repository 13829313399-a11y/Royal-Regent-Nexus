"""File decoding precedes factory locks; matching uses fresh business state."""
import hashlib
import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from test_molding_sample_api import make_client
from test_carton_supplier_portal import BASE, setup_portal, accept_all, _dongkang_delivery_file


@pytest.mark.parametrize("invalid", ["warnings", "template", "coordinates", "row_limit"])
def test_invalid_delivery_structure_fails_before_any_factory_lock(monkeypatch, invalid):
    from app.services import carton_supplier_delivery_import as service
    row = {"source_sheet": "Delivery", "source_row": 2, "template": "dongkang-delivery"}
    parsed = {"rows": [row], "warnings": []}
    choices = []
    if invalid == "warnings":
        parsed["warnings"] = ["源行不完整"]
    elif invalid == "template":
        row["template"] = "generic-delivery"
    elif invalid == "coordinates":
        choices = [{"source_sheet": "Delivery", "source_row": 3, "order_line_id": "L1",
                    "issue_id": "I1", "order_revision": 1}]
    else:
        parsed["rows"] = [row] * 501
    monkeypatch.setattr(service.portal, "supplier_access", lambda *args: None)
    monkeypatch.setattr(service, "_parse_delivery_spreadsheet", lambda *args, **kwargs: parsed)

    def unexpected_lock(*args):
        pytest.fail("Invalid file structure must be rejected before taking a factory lock")

    monkeypatch.setattr(service.portal, "_lock_receipt_factory", unexpected_lock)
    content = b"private-test-file"
    with pytest.raises(HTTPException) as error:
        service.confirm(None, None, "delivery.xlsx", content, hashlib.sha256(content).hexdigest(),
                        [("huaxing", "DN-STRUCTURE")], choices)
    assert error.value.status_code == 422


@pytest.mark.parametrize("race", ["none", "revision", "reservation"])
def test_confirmation_parses_once_before_lock_and_rechecks_revision_and_demand(monkeypatch, race, tmp_path):
    monkeypatch.setattr("test_molding_sample_api.TEST_TMP_DIR", tmp_path)
    with make_client(monkeypatch) as client:
        setup_portal(client)
        order = accept_all(client)
        upload = {"file": ("delivery.xlsx", _dongkang_delivery_file(order))}
        preview = client.post(BASE + "/shipments/import-preview", files=upload)
        assert preview.status_code == 200, preview.text
        group = preview.json()["groups"][0]
        assert group["ready"]
        choices = [{key: row[key] for key in ("source_sheet", "source_row", "order_line_id",
                   "issue_id", "order_revision")} for row in group["rows"]]
        form = {"sha256": preview.json()["sha256"], "row_selections": json.dumps(choices),
                "selections": json.dumps([{"factory_id": group["factory_id"],
                                            "delivery_note_no": group["delivery_note_no"]}])}
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonReceipt, CartonInventoryMovement
        from app.models.carton_supplier_portal import SupplierShipment
        from app.schemas.carton_supplier_portal import ShipmentCreate
        from app.services.auth import build_auth_context
        from app.services import carton_supplier_delivery_import as service
        from sqlalchemy import select, func

        original_parse = service._parse_delivery_spreadsheet
        original_lock = service.portal._lock_receipt_factory
        events = []
        parse_calls = 0
        race_applied = False

        def parse_before_lock(*args, **kwargs):
            nonlocal parse_calls, race_applied
            assert "lock" not in events, "The incoming file was decoded while holding a factory lock"
            events.append("parse")
            parse_calls += 1
            rows = original_parse(*args, **kwargs)
            if race != "none" and not race_applied:
                race_applied = True
                # A separate transaction wins during decoding, before this
                # confirmation's business lock. Its result must survive rejection.
                with SessionLocal() as other:
                    if race == "revision":
                        current = other.get(CartonOrder, order["id"])
                        current.revision += 1
                        other.commit()
                    else:
                        paper = other.get(CartonOrderLine, choices[0]["order_line_id"])
                        actor = build_auth_context(other, other.get(AuthUser, "supplier-test"))
                        payload = ShipmentCreate(factory_id="huaxing", request_id=uuid4().hex,
                            delivery_note_no="DN-CONCURRENT", delivery_date=date(2026, 9, 24),
                            lines=[{"order_line_id": paper.id, "issue_id": choices[0]["issue_id"],
                                    "quantity": paper.required_quantity - Decimal(9)}])
                        with monkeypatch.context() as concurrent_patch:
                            concurrent_patch.setattr(service.portal, "_lock_receipt_factory", original_lock)
                            service.portal.create_shipment(other, actor, payload)
            return rows

        def observe_lock(db, factory):
            assert events and events[0] == "parse"
            events.append("lock")
            return original_lock(db, factory)

        monkeypatch.setattr(service, "_parse_delivery_spreadsheet", parse_before_lock)
        monkeypatch.setattr(service.portal, "_lock_receipt_factory", observe_lock)
        response = client.post(BASE + "/shipments/import-confirm", files=upload, data=form)
        assert parse_calls == 1  # No second Excel read inside the factory lock.
        assert events[0] == "parse" and "lock" in events
        if race == "none":
            assert response.status_code == 200, response.text
            shipment = response.json()["shipments"][0]
            assert {row["order_line_id"] for row in shipment["lines"]} == {row["order_line_id"] for row in choices}
            events.clear()
            replay = client.post(BASE + "/shipments/import-confirm", files=upload, data=form)
            assert replay.status_code == 200, replay.text
            assert replay.json()["shipments"][0]["id"] == shipment["id"]
            assert parse_calls == 2 and events[0] == "parse"
        else:
            assert response.status_code == 409, response.text
            assert ("所选订单不属于当前可匹配明细" if race == "revision" else "超过剩余未送") in response.text
        with SessionLocal() as db:
            notes = db.scalars(select(SupplierShipment)).all()
            assert len(notes) == (0 if race == "revision" else 1)
            if race == "revision":
                assert db.get(CartonOrder, order["id"]).revision == choices[0]["order_revision"] + 1
            elif race == "reservation":
                assert notes[0].delivery_note_no == "DN-CONCURRENT"
            assert db.scalar(select(func.count()).select_from(CartonReceipt)) == 0
            assert db.scalar(select(func.count()).select_from(CartonInventoryMovement)) == 0
