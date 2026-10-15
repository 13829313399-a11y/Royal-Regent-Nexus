"""Complete late formal orders retain the original delivery and post stock only on receipt."""
import json
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook

from test_molding_sample_api import login_as, make_client
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import BASE, receive_payload, setup_portal, supplier_login


def _original_delivery(client, *, packaging_type="普通箱", specification="19.875*11.25*15.375 inch"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "送货明细"
    sheet.append(["送货单号", "日期", "客户", "客户单号", "客户料号", "名称", "纸质", "规格", "数量", "单价"])
    sheet.append(["DK-LATE-FORMAL", "2026-09-24", "华兴", "LATE-FORMAL", "LATE-ITEM",
                  packaging_type, "A=B", specification, 836, 3.22])
    output = BytesIO()
    workbook.save(output)
    upload = {"file": ("原送货单.xlsx", output.getvalue())}
    preview = client.post(BASE + "/shipments/import-preview", files=upload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"][0]["rows"][0]["status"] == "AD_HOC_REVIEW"
    response = client.post(BASE + "/shipments/import-confirm", files=upload, data={
        "sha256": preview.json()["sha256"],
        "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "DK-LATE-FORMAL"}]),
    })
    assert response.status_code == 200, response.text
    return response.json()["shipments"][0]


def _complete_order(client, *, packaging_type="外箱", paper_quality="A=B", specification="19.875*11.25*15.375",
                    dimension_unit="inch", quantity=1000, unit="个", submit=True):
    payload = _order_payload()
    payload.update(request_id=uuid4().hex, contract_no="LATE-FORMAL", item_no="LATE-ITEM",
                   quantity_basis="EXPLICIT", product_order_quantity=None,
                   lines=[{
                       "packaging_type": packaging_type, "paper_quality": paper_quality,
                       "specification": specification, "dimension_unit": dimension_unit,
                       "required_quantity": quantity, "unit": unit, "unit_price": "3.22",
                       "net_weight_kg": "1.25", "gross_weight_kg": "1.75",
                   }, {
                       "packaging_type": "内箱", "paper_quality": "A3", "specification": "10*8*5",
                       "dimension_unit": "cm", "required_quantity": 2000, "unit": "张", "unit_price": "0.9",
                   }])
    response = client.post("/api/carton-procurement/orders", json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "CONFIRMED"
    assert [Decimal(line["required_quantity"]) for line in created["lines"]] == [Decimal(quantity), Decimal(2000)]
    return _submit_order(client, created) if submit else created


def _association(shipment, order):
    source = shipment["lines"][0]
    return BASE + f"/internal/shipments/{shipment['id']}/lines/{source['id']}/link-order", {
        "factory_id": "huaxing", "customer_code": order["customer_code"],
        "order_line_id": order["lines"][0]["id"], "expected_revision": shipment["revision"],
        "expected_order_revision": order["revision"], "reason": "正单漏下补建完整需求",
    }


@pytest.mark.parametrize("source_type,target_type,target_unit", [
    ("普通箱", "外箱", "个"),
    ("滑板纸", "滑板纸", "张"),
])
def test_late_formal_order_associates_only_this_delivery_preserving_evidence_and_replay(
        monkeypatch, source_type, target_type, target_unit):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        shipment = _original_delivery(client, packaging_type=source_type)
        original_source_id = shipment["lines"][0]["id"]
        login_as(client, "warehouse_keeper")
        order = _complete_order(client, packaging_type=target_type, unit=target_unit, submit=False)
        url, pending_payload = _association(shipment, order)
        assert client.post(url, json=pending_payload).status_code == 409  # Requires normal confirmation/issuance.
        order = _submit_order(client, order)
        url, payload = _association(shipment, order)
        linked = client.post(url, json=payload)
        assert linked.status_code == 200, linked.text
        note = linked.json()
        assert note["status"] == "SENT" and not note["receipt_id"]
        assert len(note["lines"]) == 1
        paper = note["lines"][0]
        assert paper["order_line_id"] == order["lines"][0]["id"]
        assert paper["original_unmatched_line_id"] == original_source_id
        assert paper["packaging_type"] == target_type and Decimal(paper["quantity"]) == 836
        assert paper["unit"] == target_unit  # Dongkang has no counting-unit column; default 个 is not an assertion.
        assert paper["source_material"]["packaging_type"] == source_type
        replay = client.post(url, json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()["revision"] == note["revision"]
        assert client.post(url, json=dict(payload, reason="修改已关联的操作原因")).status_code == 409

        from sqlalchemy import func, select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement, CartonOrderLine, CartonReceipt
        from app.models.carton_supplier_portal import SupplierCommitment, SupplierShipmentLine, SupplierShipmentUnmatchedLine
        from app.services.carton_supplier_portal import fulfilled_by_line, outstanding
        with SessionLocal() as db:
            source = db.get(SupplierShipmentUnmatchedLine, original_source_id)
            assert source is not None and Decimal(source.quantity) == 836
            original = json.loads(source.snapshot_json)
            assert original["packaging_type"] == source_type and original["source_file"]["filename"] == "原送货单.xlsx"
            rows = db.scalars(select(SupplierShipmentLine).where(SupplierShipmentLine.shipment_id == shipment["id"])).all()
            assert len(rows) == 1
            frozen = json.loads(rows[0].snapshot_json)
            assert frozen["original_source_material"] == original
            assert frozen["dimension_unit"] == "inch"
            assert Decimal(frozen["net_weight_kg"]) == Decimal("1.25")
            assert Decimal(frozen["gross_weight_kg"]) == Decimal("1.75")
            assert db.scalar(select(func.count(CartonReceipt.id))) == 0
            assert db.scalar(select(func.count(CartonInventoryMovement.id))) == 0
            assert db.get(SupplierCommitment, order["lines"][0]["id"]) is None
            ids = [line["id"] for line in order["lines"]]
            assert outstanding(db, ids) == {ids[0]: Decimal(836)}
            assert fulfilled_by_line(db, ids) == {ids[0]: Decimal(0), ids[1]: Decimal(0)}
            assert [Decimal(db.get(CartonOrderLine, line_id).required_quantity) for line_id in ids] == [1000, 2000]

        supplier_login(client)
        supplier_notes = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["shipments"]
        external = next(row for row in supplier_notes if row["id"] == note["id"])
        assert "original_unmatched_line_id" not in external["lines"][0]
        login_as(client, "warehouse_keeper")
        receive = receive_payload(client, note)
        receive["lines"][0].update(received_quantity=836, difference_reason="",
                                  location_allocations=[dict(receive["lines"][0]["location_allocations"][0], quantity=836)])
        posted = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=receive)
        assert posted.status_code == 200, posted.text
        repeat = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=receive)
        assert repeat.status_code == 200 and repeat.json()["receipt_id"] == posted.json()["receipt_id"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count(CartonInventoryMovement.id))) == 1
            assert fulfilled_by_line(db, ids) == {ids[0]: Decimal(836), ids[1]: Decimal(0)}
            assert [Decimal(db.get(CartonOrderLine, line_id).required_quantity) for line_id in ids] == [1000, 2000]


@pytest.mark.parametrize("changes,expected_status", [
    ({"packaging_type": "内箱"}, 422),
    ({"paper_quality": "A3"}, 422),
    ({"dimension_unit": "cm"}, 422),
    ({"specification": "20*11.25*15.375"}, 422),
    ({"quantity": 835}, 409),
])
def test_late_formal_order_rejects_other_papers_units_or_insufficient_total(monkeypatch, changes, expected_status):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        shipment = _original_delivery(client)
        login_as(client, "warehouse_keeper")
        order = _complete_order(client, **changes)
        url, payload = _association(shipment, order)
        response = client.post(url, json=payload)
        assert response.status_code == expected_status, response.text
        from sqlalchemy import func, select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement, CartonReceipt
        from app.models.carton_supplier_portal import SupplierShipment, SupplierShipmentLine
        with SessionLocal() as db:
            assert db.get(SupplierShipment, shipment["id"]).revision == shipment["revision"]
            assert db.scalar(select(func.count(SupplierShipmentLine.id)).where(SupplierShipmentLine.shipment_id == shipment["id"])) == 0
            assert db.scalar(select(func.count(CartonReceipt.id))) == 0
            assert db.scalar(select(func.count(CartonInventoryMovement.id))) == 0


def test_late_formal_order_association_keeps_factory_actor_customer_and_revision_guards(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        shipment = _original_delivery(client)
        login_as(client, "warehouse_keeper")
        order = _complete_order(client)
        url, payload = _association(shipment, order)
        supplier_login(client)
        assert client.post(url, json=payload).status_code == 403
        login_as(client, "warehouse_keeper")
        assert client.post(url, json=dict(payload, factory_id="huakang-a")).status_code in {403, 404}
        assert client.post(url, json=dict(payload, expected_revision=shipment["revision"] + 1)).status_code == 409
        assert client.post(url, json=dict(payload, expected_order_revision=order["revision"] + 1)).status_code == 409
        assert client.post(url, json=dict(payload, customer_code="UNKNOWN")).status_code == 422
        assert client.post(url, json=dict(payload, order_line_id=order["lines"][1]["id"])).status_code == 422
        assert client.post(url, json=payload).status_code == 200
