"""Supplier mark forms must retain all binding fields at the HTTP boundary."""
import hashlib
from test_molding_sample_api import make_client
from test_carton_supplier_mark_check import prepare, result_for
from test_carton_mark_api import _pdf_bytes
from test_carton_mark_asset_images import photo_bytes


def test_stored_pair_and_mixed_originals_parse_multipart_instead_of_json(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, excel = prepare(client)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from app.services.carton_mark_library import _now_text
        from app.api import carton_supplier_portal as api
        from sqlalchemy import select, func
        pdf = _pdf_bytes()
        with SessionLocal() as db:
            db.add(CartonMarkAsset(id="pdf-transport", factory_id="huaxing", file_name=order["contract_no"] + ".pdf",
                kind="pdf", content_type="application/pdf", size_bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest(),
                content=pdf, contract_number=order["contract_no"], bound_order_id=order["id"],
                recognition_source="manual_order", candidates_json="[]", warning="", created_by="supplier-test",
                created_by_name="供应商测试", created_at=_now_text(), updated_at=_now_text(), revision=1, is_archived=False))
            db.commit()
        data = {**payload, "pdf_asset_id": "pdf-transport", "expected_pdf_revision": 1}
        base = "/api/carton-supplier/carton-mark"
        invalid = client.post(base + "/checks", json=data)
        assert invalid.status_code == 422
        assert {item["loc"][-1] for item in invalid.json()["detail"]} >= {"factory_id", "order_id", "issue_id", "excel_asset_id", "expected_revision"}
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
        monkeypatch.setattr(api, "build_carton_mark_document_check", lambda **kwargs: result_for(kwargs))
        checked = client.post(base + "/checks", files=[(key, (None, str(value))) for key, value in data.items()])
        assert checked.request.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert checked.status_code == 201, checked.text
        assert checked.json()["order_id"] == order["id"] and checked.json()["excel_asset_id"] == payload["excel_asset_id"]
        assert checked.json()["qc_ready"]
        upload = client.post(base + "/assets/upload", files=[("factory_id", (None, "huaxing")),
            ("order_id", (None, order["id"])), ("issue_id", (None, payload["issue_id"])),
            ("files", (order["contract_no"] + ".xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", (order["contract_no"] + ".pdf", pdf, "application/pdf")),
            ("files", ("camera.png", photo_bytes(), "image/png"))])
        assert upload.request.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert upload.status_code == 201, upload.text
        assert [row["status"] for row in upload.json()] == ["duplicate", "duplicate", "created"]
        assert all(row["asset"]["orders"][0]["id"] == order["id"] for row in upload.json())
