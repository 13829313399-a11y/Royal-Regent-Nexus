"""Supplier document visibility, batch acceptance and Excel export boundaries."""
from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook
from pypdf import PdfWriter
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order, _order_payload
from test_carton_supplier_portal import BASE, setup_portal


def test_supplier_evidence_prevents_reassignment_after_attachment(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        order = _create_order(client, submit_supplier=False)
        assert order["status"] == "CONFIRMED"
        pdf = PdfWriter()
        pdf.add_blank_page(width=100, height=100)
        content = BytesIO()
        pdf.write(content)
        uploaded = client.post(BASE + f"/internal/orders/{order['id']}/attachments",
                               data={"factory_id": "huaxing"},
                               files={"file": ("supplier-a.pdf", content.getvalue())})
        assert uploaded.status_code == 201, uploaded.text
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id="new-supplier", factory_id="huaxing", supplier_code="OTHER",
                                  supplier_name="其他供应商", status="ACTIVE",
                                  created_at="2026-09-21", updated_at="2026-09-21"))
            db.commit()
        update = {**_order_payload(), "expected_revision": order["revision"],
                  "reason": "供应商改派安全回归", "supplier_id": "new-supplier"}
        response = client.patch(f"/api/carton-procurement/orders/{order['order_no']}", json=update)
        assert response.status_code == 409, response.text
        assert "不能改派供应商" in response.text


def test_batch_accept_is_atomic_per_factory_and_shipping_needs_acceptance(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        order = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        lines = [{
            "order_line_id": line["id"], "issue_id": order["issue_id"],
            "expected_revision": line["commitment_revision"], "promised_date": "2026-09-25",
        } for line in order["lines"]]
        assert len(lines) >= 2
        shipment = {
            "factory_id": "huaxing", "request_id": str(uuid4()),
            "delivery_note_no": "DN-BATCH-GATE", "delivery_date": "2026-09-25",
            "lines": [{"order_line_id": order["lines"][0]["id"], "issue_id": order["issue_id"], "quantity": 1}],
        }
        assert client.post(BASE + "/shipments", json=shipment).status_code == 409
        bad = [dict(line) for line in lines]
        bad[-1]["expected_revision"] += 1
        rejected = client.put(BASE + "/commitments/batch", json={"factory_id": "huaxing", "lines": bad})
        assert rejected.status_code == 409, rejected.text
        after_reject = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        assert all(not line["accepted"] for line in after_reject["lines"])
        first = client.put(BASE + f"/papers/{lines[0]['order_line_id']}/commitment", json={
            "factory_id": "huaxing", "issue_id": lines[0]["issue_id"],
            "expected_revision": 0, "promised_date": "2026-09-25"})
        assert first.status_code == 200, first.text
        partly_shipped = client.post(BASE + "/shipments", json=shipment)
        assert partly_shipped.status_code == 409
        assert "整单接单" in partly_shipped.text
        accepted = client.put(BASE + "/commitments/batch", json={"factory_id": "huaxing", "lines": lines[1:]})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["order_ids"] == [order["id"]]
        assert all(line["accepted"] for line in client.get(
            BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]["lines"])
        assert client.post(BASE + "/shipments", json=shipment).status_code == 201


def test_supplier_documents_export_and_audit_are_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        docs = client.get(BASE + "/documents", params={"factory_id": "huaxing"})
        assert docs.status_code == 200, docs.text
        purchase = next(row for row in docs.json() if row["kind"] == "PURCHASE")
        assert purchase["orders"][0]["contract_no"]
        assert purchase["lines"]
        assert "unit_price" not in docs.text and "supplier_id" not in docs.text
        assert client.get(BASE + "/documents", params={"factory_id": "huadeng"}).status_code in (403, 422)
        assert client.get(BASE + "/activity", params={"factory_id": "huadeng"}).status_code in (403, 422)

        order = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        lines = [{
            "order_line_id": line["id"], "issue_id": order["issue_id"],
            "expected_revision": line["commitment_revision"], "promised_date": "2026-09-25",
        } for line in order["lines"]]
        assert client.put(BASE + "/commitments/batch", json={"factory_id": "huaxing", "lines": lines}).status_code == 200
        sent = client.post(BASE + "/shipments", json={
            "factory_id": "huaxing", "request_id": str(uuid4()),
            "delivery_note_no": "DN-DOCS", "delivery_date": "2026-09-25",
            "lines": [{"order_line_id": order["lines"][0]["id"], "issue_id": order["issue_id"], "quantity": 3}],
        })
        assert sent.status_code == 201, sent.text
        delivery = next(row for row in client.get(
            BASE + "/documents", params={"factory_id": "huaxing"}).json() if row["kind"] == "DELIVERY")
        assert delivery["document_no"] == "DN-DOCS"
        assert {row["order_no"] for row in delivery["orders"]} == {order["order_no"]}
        selected = [
            {"factory_id": "huaxing", "kind": "PURCHASE", "id": purchase["id"]},
            {"factory_id": "huaxing", "kind": "DELIVERY", "id": delivery["id"]},
        ]
        exported = client.post(BASE + "/documents/export.xlsx", json={"documents": selected})
        assert exported.status_code == 200, exported.text
        book = load_workbook(BytesIO(exported.content), read_only=True)
        assert book.sheetnames == ["采购单", "送货单"]
        purchase_rows = list(book["采购单"].values)
        delivery_rows = list(book["送货单"].values)
        assert purchase["document_no"] in [row[1] for row in purchase_rows[1:]]
        assert "DN-DOCS" in [row[1] for row in delivery_rows[1:]]
        assert isinstance(delivery_rows[1][13], (int, float))
        book.close()
        activity = client.get(BASE + "/activity", params={"factory_id": "huaxing"})
        assert activity.status_code == 200
        actions = {row["action"] for row in activity.json()}
        assert {"采购单已发行", "纸品已确认接单", "送货单已登记"}.issubset(actions)
        assert "detail_json" not in activity.text and "unit_price" not in activity.text
        assert client.post(BASE + "/documents/export.xlsx", json={"documents": [
            *selected, {"factory_id": "huadeng", "kind": "PURCHASE", "id": purchase["id"]},
        ]}).status_code in (403, 422)
        assert client.post(BASE + "/documents/export.xlsx", json={"documents": [
            {"factory_id": "huaxing", "kind": "DELIVERY", "id": "forged-id"},
        ]}).status_code == 404
