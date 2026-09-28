"""Regression coverage for the procurement/supplier audit's material and correction gaps."""
import json
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import setup_portal, accept_all, supplier_login, ship_payload, receive_payload, BASE


def delivery_file(contract, item, paper, note="FIX-NOTE", **changes):
    row = {"packaging_type": paper["packaging_type"], "paper_quality": paper["paper_quality"],
        "specification": paper["specification"], "quantity": 4, **changes}
    book = Workbook(); sheet = book.active
    sheet.append(["送货单号", "日期", "客户", "客户单号", "客户料号", "名称", "纸质", "规格", "数量", "单价"])
    sheet.append([note, "2026-09-24", "华兴", contract, item, row["packaging_type"], row["paper_quality"], row["specification"], row["quantity"], 2])
    output = BytesIO(); book.save(output)
    return {"file": ("送货明细.xlsx", output.getvalue())}


@pytest.mark.parametrize("changes", [
    {"packaging_type": "隔板"}, {"packaging_type": "普通箱"}, {"paper_quality": "H99"},
    {"specification": "99*88*77 cm"}, {"specification": "31.5*11.125*11.25 in"},
])
def test_shared_material_identity_rejects_explicit_conflicts(changes):
    from app.services.carton_material_identity import material_conflicts
    material = {"packaging_type": "外箱", "paper_quality": "A33+B", "specification": "31.5*11.125*11.25", "dimension_unit": "cm"}
    assert material_conflicts(material | changes, material)
    assert not material_conflicts(material | {"specification": "31.500 × 11.125 × 11.250 厘米"}, material)
    assert not material_conflicts({"packaging_type": "待复核", "paper_quality": "", "specification": ""}, material)
    assert not material_conflicts({"packaging_type": "普通箱", "packaging_type_explicit": False}, material)


def test_both_importers_keep_conflicts_visible_and_block_dispatch(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client); paper = order["lines"][0]
        for changes in ({"packaging_type": "隔板"}, {"packaging_type": "普通箱"}, {"paper_quality": "H99"}, {"specification": "99*88*77 in"}):
            supplier_login(client)
            upload = delivery_file(order["contract_no"], order["item_no"], paper, **changes)
            preview = client.post(BASE + "/shipments/import-preview", files=upload)
            assert preview.status_code == 200, preview.text
            group = preview.json()["groups"][0]
            assert not group["ready"] and group["rows"][0]["status"] == "BLOCKED"
            blocked = client.post(BASE + "/shipments/import-confirm", files=upload, data={
                "sha256": preview.json()["sha256"], "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "FIX-NOTE"}])})
            assert blocked.status_code == 409, blocked.text
            login_as(client, "warehouse_keeper")
            preview = client.post("/api/carton-procurement/receipt-imports", params={"factory_id": "huaxing"}, files=upload)
            assert preview.status_code == 201, preview.text
            row = preview.json()["parse_summary"]["rows"][0]
            assert row["match_status"] == "REVIEW_REQUIRED" and not row.get("order_line_id")
            for key, value in changes.items():
                assert row[key] == value and row["source_material"][key] == value
            assert row["material_candidates"] and row["material_candidates"][0]["conflicts"]
        supplier_login(client)
        valid = delivery_file(order["contract_no"], order["item_no"], paper)
        assert client.post(BASE + "/shipments/import-preview", files=valid).json()["groups"][0]["ready"]
        login_as(client, "warehouse_keeper")
        valid_batch = client.post("/api/carton-procurement/receipt-imports", params={"factory_id": "huaxing"}, files=valid).json()
        valid_row = valid_batch["parse_summary"]["rows"][0]
        assert valid_row["match_status"] == "MATCHED" and valid_row["source_material"]["packaging_type"] == paper["packaging_type"]
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonImportBatch
        from app.services.carton_procurement import import_batch_out
        bins = client.get("/api/carton-procurement/inventory/locations", params={"factory_id": "huaxing"}).json()
        bin_id = next(row["id"] for row in bins if row["bin_code"] == "A-01")
        draft = client.post("/api/carton-procurement/receipts", json={"factory_id": "huaxing",
            "delivery_note_no": "FIX-NOTE", "delivery_date": "2026-09-24", "acceptance_date": "2026-09-24",
            "import_batch_id": valid_batch["id"], "lines": [{"order_line_id": paper["id"],
                "delivered_quantity": 1, "received_quantity": 1, "unit_price": 2,
                "location_allocations": [{"location_id": bin_id, "quantity": 1}]}]})
        assert draft.status_code == 201, draft.text
        with SessionLocal() as db:
            batch = db.get(CartonImportBatch, valid_batch["id"])
            parsed = json.loads(batch.parse_summary_json); parsed["parser_version"] = "delivery-note-local-v7-dongkang"
            batch.parse_summary_json = json.dumps(parsed); db.commit()
            summary = import_batch_out(batch).parse_summary
            assert summary["material_review_required"] and summary["rows"][0]["match_status"] == "REVIEW_REQUIRED"
        blocked_draft = client.post(f"/api/carton-procurement/receipts/{draft.json()['id']}/confirm", json={
            "factory_id": "huaxing", "expected_revision": draft.json()["revision"]})
        assert blocked_draft.status_code == 409 and "重新导入" in blocked_draft.json()["detail"]
        denied = client.post("/api/carton-procurement/receipts", json={"factory_id": "huaxing",
            "delivery_note_no": "OLD-PREVIEW", "delivery_date": "2026-09-24", "acceptance_date": "2026-09-24",
            "import_batch_id": valid_batch["id"], "post_immediately": True, "request_id": str(uuid4()),
            "lines": [{"order_line_id": paper["id"], "delivered_quantity": 1, "received_quantity": 1, "unit_price": 2}]})
        assert denied.status_code == 409 and "重新导入" in denied.json()["detail"]


def test_reversed_supplier_receipt_has_history_linked_correction_and_replay_protection(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        shipment = client.post(BASE + "/shipments", json=ship_payload(order)).json()
        login_as(client, "warehouse_keeper")
        original = receive_payload(client, shipment)
        received = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=original)
        assert received.status_code == 200, received.text
        receipt_id = received.json()["receipt_id"]
        receipts = client.get("/api/carton-procurement/receipts", params={"factory_id": "huaxing"}).json()["items"]
        receipt = next(row for row in receipts if row["id"] == receipt_id)
        response = client.post(f"/api/carton-procurement/receipts/{receipt_id}/reverse", json={"factory_id": "huaxing",
            "expected_revision": receipt["revision"], "reason": "原数量登记错误"})
        assert response.status_code == 200, response.text
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.auth import SystemNotification
        from app.models.carton_supplier_portal import SupplierShipment
        from app.models.carton_procurement import CartonAuditEvent
        from app.services.carton_supplier_notifications import notification_id
        notice_id = notification_id(shipment["id"])
        notices = client.get("/api/system/notifications").json()
        assert any(notice["id"] == notice_id and notice["status"] == "unread" for notice in notices)
        # Simulate preserved evidence produced by the previous version of the reversal flow.
        with SessionLocal() as db:
            db.get(SupplierShipment, shipment["id"]).status = "RECEIVED"
            db.get(SystemNotification, notice_id).status = "handled"
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == shipment["id"],
                CartonAuditEvent.event_type == "SUPPLIER_SHIPMENT_RECEIVED"))
            detail = json.loads(event.detail_json); detail.pop("request_fingerprint")
            event.detail_json = json.dumps(detail)
            db.commit()
        notice = next(notice for notice in client.get("/api/system/notifications").json() if notice["id"] == notice_id)
        assert notice["status"] == "unread" and "冲销" in notice["title"]
        assert client.patch(f"/api/system/notifications/{notice_id}", json={"status": "read"}).status_code == 200
        assert client.patch(f"/api/system/notifications/{notice_id}", json={"status": "handled"}).status_code == 409
        supplier_login(client)
        workspace = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()
        visible = workspace["shipments"][0]
        assert visible["status"] == "RECEIPT_REVERSED" and not visible["acceptance_lines"]
        assert visible["acceptance_history"][0]["status"] == "REVERSED"
        assert Decimal(str(visible["acceptance_history"][0]["lines"][0]["received_quantity"])) == 8
        assert all(Decimal(line["received_quantity"]) == 0 and Decimal(line["in_transit_quantity"]) == 8 for line in workspace["orders"][0]["lines"])
        assert "customer_code" not in json.dumps(workspace)
        docs = client.get(BASE + "/documents", params={"factory_id": "huaxing"}).json()
        delivery = next(row for row in docs if row["kind"] == "DELIVERY")
        assert delivery["status"] == "RECEIPT_REVERSED" and all(Decimal(line["received_quantity"]) == 0 for line in delivery["lines"])
        assert any("冲销" in event["action"] for event in client.get(BASE + "/activity", params={"factory_id": "huaxing"}).json())
        # Another real dispatch may occupy only the capacity not reserved for this correction.
        remainder = ship_payload(order) | {"request_id": str(uuid4()), "delivery_note_no": "NEXT-NOTE",
            "lines": [{"order_line_id": line["id"], "issue_id": order["issue_id"], "quantity": line["remaining_to_ship"]}
                for line in workspace["orders"][0]["lines"]]}
        assert client.post(BASE + "/shipments", json=remainder).status_code == 201
        login_as(client, "warehouse_keeper")
        replay = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=original)
        assert replay.status_code == 200 and replay.json()["requires_correction"]
        correction = dict(original, expected_revision=visible["revision"], request_id=str(uuid4()))
        assert client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=correction).status_code == 422
        correction["correction_reason"] = "重核原单实际收到"
        wrong = dict(correction, lines=[dict(line, received_quantity=10,
            location_allocations=[dict(line["location_allocations"][0], quantity=10)]) for line in correction["lines"]])
        assert client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=wrong).status_code == 409
        corrected = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=correction)
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["receipt_id"] != receipt_id and not corrected.json()["requires_correction"]
        assert len(corrected.json()["acceptance_history"]) == 2
        again = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=correction)
        assert again.status_code == 200 and again.json()["receipt_id"] == corrected.json()["receipt_id"]
        altered = dict(correction, correction_reason="复用请求伪造修改")
        assert client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=altered).status_code == 409
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonAuditEvent
        from app.services.carton_supplier_settlement import sources
        with SessionLocal() as db:
            current = db.get(CartonReceipt, corrected.json()["receipt_id"])
            rows, _, issues, undated = sources(db, "huaxing", current.supplier_id, "2026-09", "CNY")
            assert not issues and not undated and len(rows) == 2
            assert all(Decimal(str(row["quantity"])) == 8 for row in rows)
            audits = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == shipment["id"],
                CartonAuditEvent.event_type == "SUPPLIER_SHIPMENT_RECEIVED")).all()
            assert len(audits) == 2
            assert json.loads(audits[-1].detail_json)["supersedes_receipt_id"] == receipt_id


def test_unmatched_shipment_can_link_later_order_before_receiving_without_duplicates(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        paper = {"packaging_type": "外箱", "paper_quality": "A33+B", "specification": "18*12*10 cm"}
        upload = delivery_file("LATE-FIX", "LATE-ITEM", paper)
        preview = client.post(BASE + "/shipments/import-preview", files=upload).json()
        sent = client.post(BASE + "/shipments/import-confirm", files=upload, data={"sha256": preview["sha256"],
            "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "FIX-NOTE"}])})
        assert sent.status_code == 200, sent.text
        shipment = sent.json()["shipments"][0]; source = shipment["lines"][0]
        excessive = delivery_file("LATE-FIX", "LATE-ITEM", paper, note="TOO-MUCH", quantity=31)
        excessive_preview = client.post(BASE + "/shipments/import-preview", files=excessive).json()
        excessive_sent = client.post(BASE + "/shipments/import-confirm", files=excessive, data={"sha256": excessive_preview["sha256"],
            "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "TOO-MUCH"}])})
        assert excessive_sent.status_code == 200, excessive_sent.text
        excessive_shipment = excessive_sent.json()["shipments"][0]
        login_as(client, "warehouse_keeper")
        payload = _order_payload()
        payload.update(contract_no="LATE-FIX", item_no="LATE-ITEM", lines=[dict(payload["lines"][0], **paper, dimension_unit="cm"), payload["lines"][1]])
        created = client.post("/api/carton-procurement/orders", json=payload)
        assert created.status_code == 201, created.text
        order = _submit_order(client, created.json()); target = order["lines"][0]
        link = {"factory_id": "huaxing", "customer_code": order["customer_code"], "order_line_id": target["id"],
            "expected_revision": shipment["revision"], "expected_order_revision": order["revision"], "reason": "已补正式订单核对"}
        url = BASE + f"/internal/shipments/{shipment['id']}/lines/{source['id']}/link-order"
        supplier_login(client)
        assert client.post(url, json=link).status_code == 403
        login_as(client, "warehouse_keeper")
        assert client.post(url, json=dict(link, factory_id="huakang-a")).status_code in {403, 404}
        assert client.post(url, json=dict(link, expected_order_revision=order["revision"] + 1)).status_code == 409
        assert client.post(url, json=dict(link, customer_code="UNKNOWN")).status_code == 422
        assert client.post(url, json=dict(link, order_line_id=order["lines"][1]["id"])).status_code == 422
        excessive_url = BASE + f"/internal/shipments/{excessive_shipment['id']}/lines/{excessive_shipment['lines'][0]['id']}/link-order"
        assert client.post(excessive_url, json=link).status_code == 409
        linked = client.post(url, json=link)
        assert linked.status_code == 200, linked.text
        formal = linked.json()
        assert len(formal["lines"]) == 1 and formal["lines"][0]["source_type"] == "FORMAL_ORDER"
        assert formal["lines"][0]["order_line_id"] == target["id"]
        replay = client.post(url, json=link)
        assert replay.status_code == 200, replay.text
        assert replay.json()["revision"] == formal["revision"]
        assert client.post(url, json=dict(link, reason="企图再次更换关联")).status_code == 409
        # Linking reserves delivery demand but never creates a receipt or inventory.
        from sqlalchemy import select, func
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt, CartonInventoryMovement
        from app.models.carton_supplier_portal import SupplierShipmentUnmatchedLine, SupplierShipmentLine
        with SessionLocal() as db:
            assert db.scalar(select(func.count(CartonReceipt.id))) == 0
            assert db.scalar(select(func.count(CartonInventoryMovement.id))) == 0
            assert db.get(SupplierShipmentUnmatchedLine, source["id"]) is not None
            assert db.scalar(select(func.count(SupplierShipmentLine.id)).where(SupplierShipmentLine.shipment_id == shipment["id"])) == 1
        receive = receive_payload(client, formal)
        receive["lines"][0].update(received_quantity=4, difference_reason="", location_allocations=[dict(receive["lines"][0]["location_allocations"][0], quantity=4)])
        posted = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=receive)
        assert posted.status_code == 200, posted.text
        assert client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=receive).json()["receipt_id"] == posted.json()["receipt_id"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count(CartonInventoryMovement.id))) == 1
