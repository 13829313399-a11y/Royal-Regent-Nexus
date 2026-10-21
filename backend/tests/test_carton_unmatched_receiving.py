"""Original supplier-note classification posts once without fabricated orders."""
import json
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import BASE, setup_portal, accept_all


@pytest.mark.parametrize("kind,price", [("SAMPLE", "2.5"), ("MISC", "2.5"), ("GIFT", "0"), ("SAMPLE", None), ("WRONG_DELIVERY", "2.5")])
def test_classified_original_delivery_posts_once(monkeypatch, kind, price):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        accept_all(client)
        book = Workbook(); sheet = book.active
        sheet.append(["送货单号", "日期", "客户", "客户单号", "客户料号", "名称", "纸质", "规格", "数量", "单价"])
        sheet.append(["CLASSIFIED-01", "2026-09-24", "华兴", "UNMATCHED-1", "BOX-1", "外箱", "A33+B", "18*12*17 cm", 4, price])
        stream = BytesIO(); book.save(stream)
        upload = {"file": ("送货明细.xlsx", stream.getvalue())}
        preview = client.post(BASE + "/shipments/import-preview", files=upload)
        assert preview.status_code == 200, preview.text
        sent = client.post(BASE + "/shipments/import-confirm", files=upload, data={
            "sha256": preview.json()["sha256"], "selections": json.dumps([{"factory_id": "huaxing", "delivery_note_no": "CLASSIFIED-01"}])})
        assert sent.status_code == 200, sent.text
        shipment = sent.json()["shipments"][0]; paper = shipment["lines"][0]
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        with SessionLocal() as db:
            db.add(CartonMasterRecord(id="MISC-WORKSHOP", factory_id="huaxing", kind="WORKSHOP", identity="CLASSIFY", code="注塑车间"))
            db.add(CartonMasterRecord(id="OTHER-WORKSHOP", factory_id="huakang-a", kind="WORKSHOP", identity="CLASSIFY", code="其他厂车间"))
            db.commit()
        login_as(client, "warehouse_keeper")
        bins = client.get("/api/carton-procurement/inventory/locations", params={"factory_id": "huaxing"}).json()
        location = next(row["id"] for row in bins if row["bin_code"] == "A-01")
        line = dict(shipment_line_id=paper["id"], received_quantity=4, unit_price=price or "0",
            price_action="FREE" if kind == "GIFT" else "MATCH" if price else "PENDING",
            price_reason="原单缺价待供应商补价" if price is None else "仓库核实免费赠送" if kind == "GIFT" else "",
            zero_price_kind="FREE" if kind == "GIFT" else "PENDING" if price is None else None,
            paper_quality=paper["paper_quality"], specification=paper["specification"], no_order_decision=kind,
            rejected_quantity=4 if kind == "WRONG_DELIVERY" else 0, difference_reason="送错货全数拒收" if kind == "WRONG_DELIVERY" else "",
            location_allocations=[] if kind == "WRONG_DELIVERY" else [dict(location_id=location, quantity=4)])
        payload = dict(factory_id="huaxing", request_id=str(uuid4()), expected_revision=shipment["revision"],
            acceptance_date="2026-09-24", remaining_action="WAIT", lines=[line])
        url = BASE + f"/internal/shipments/{shipment['id']}/receive"
        for invalid in ("", "UNORDERED"):
            denied = client.post(url, json={**payload, "lines": [{**line, "no_order_decision": invalid}]})
            assert denied.status_code == 422, denied.text
        if kind == "MISC":
            denied = client.post(url, json={**payload, "lines": [{**line, "workshop_id": "OTHER-WORKSHOP"}]})
            assert denied.status_code == 422, denied.text
        if price and kind not in {"GIFT", "WRONG_DELIVERY"}:
            denied = client.post(url, json={**payload, "lines": [{**line, "unit_price": "1"}]})
            assert denied.status_code == 422, denied.text
            denied = client.post(url, json={**payload, "lines": [{**line, "no_order_decision": "GIFT", "unit_price": "0", "price_action": "FREE", "zero_price_kind": "FREE"}]})
            assert denied.status_code == 422, denied.text
        posted = client.post(url, json=payload)
        assert posted.status_code == 200, posted.text
        replay = client.post(url, json=payload)
        assert replay.status_code == 200 and replay.json()["receipt_id"] == posted.json()["receipt_id"]
        assert posted.json()["lines"][0]["received_quantity"] == "4"
        if kind == "WRONG_DELIVERY":
            assert posted.json()["lines"][0]["rejected_quantity"] == "4"
            assert posted.json()["lines"][0]["effective_quantity"] == "0"
            assert not posted.json()["receipt_id"]
            unified = client.get("/api/carton-unified-deliveries", params={"factory_id": "huaxing"})
            assert unified.status_code == 200, unified.text
            projected = next(item for item in unified.json()["items"] if item["formal"] and item["formal"]["id"] == shipment["id"])
            assert projected["lines"][0]["effective_quantity"] == "0" and projected["lines"][0]["rejected_quantity"] == "4"
            return
        from sqlalchemy import select
        from app.models.carton_procurement import CartonReceiptLine, CartonInventoryMovement
        from app.models.carton_price_review import CartonPriceReview
        with SessionLocal() as db:
            lines = db.scalars(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == posted.json()["receipt_id"])).all()
            assert len(lines) == 1 and lines[0].order_line_id is None
            assert lines[0].effective_quantity == 4 and lines[0].unit_price == Decimal(price or "0")
            assert len(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.source_id == posted.json()["receipt_id"])).all()) == 1
            review = db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id == lines[0].id))
            assert review.status == ("PENDING" if price is None else "PROPOSED" if kind == "GIFT" else "CONFIRMED")
            assert lines[0].customer_code == {"SAMPLE": "__SAMPLE__", "MISC": "__WORKSHOP_MISC__", "GIFT": "__SUPPLIER_GIFT__"}[kind]
            from app.services.carton_source_links import receipt_sources
            from app.models.carton_procurement import CartonReceipt
            refs = receipt_sources(db, db.get(CartonReceipt, posted.json()["receipt_id"]))
            assert refs["business_kinds"] == [{"SAMPLE": "SAMPLE", "MISC": "WORKSHOP_MISC", "GIFT": "SUPPLIER_GIFT"}[kind]]
            if kind == "MISC":
                assert "无正式订单杂单" in lines[0].feedback_note
