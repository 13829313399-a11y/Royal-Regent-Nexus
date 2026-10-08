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


def test_session_revoked_during_recognition_cannot_persist_supplier_originals(monkeypatch):
    from test_carton_supplier_portal import setup_portal
    from test_carton_supplier_mark_upload import upload
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.services import carton_supplier_mark_upload as service
        from app.db import SessionLocal
        from app.models.auth import AuthSession
        from app.models.carton_mark import CartonMarkAsset
        from sqlalchemy import select, func
        recognize = service.recognize_batch
        def revoke_after_recognition(*args):
            result = recognize(*args)
            with SessionLocal() as db:
                for session in db.scalars(select(AuthSession).where(AuthSession.user_id == "supplier-test")):
                    session.status = "revoked"
                db.commit()
            return result
        monkeypatch.setattr(service, "recognize_batch", revoke_after_recognition)
        response = upload(client, [(order["contract_no"] + ".pdf", _pdf_bytes())])
        assert response.status_code == 401, response.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 0


def test_stored_pdf_archived_during_comparison_cannot_create_a_qc_template(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare(client)
        from app.api import carton_supplier_portal as api
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from app.services.carton_mark_library import _now_text
        from sqlalchemy import select, func
        pdf = _pdf_bytes()
        with SessionLocal() as db:
            db.add(CartonMarkAsset(id="pdf-archive-race", factory_id="huaxing", file_name="print.pdf",
                kind="pdf", content_type="application/pdf", size_bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest(),
                content=pdf, contract_number=order["contract_no"], bound_order_id=order["id"],
                recognition_source="manual_order", candidates_json="[]", warning="", created_by="supplier-test",
                created_by_name="供应商测试", created_at=_now_text(), updated_at=_now_text(), revision=1, is_archived=False))
            db.commit()
        data = {**payload, "pdf_asset_id": "pdf-archive-race", "expected_pdf_revision": 1}
        comparisons = []
        def archive_after_comparison(**kwargs):
            comparisons.append(kwargs)
            with SessionLocal() as db:
                asset = db.get(CartonMarkAsset, "pdf-archive-race")
                asset.is_archived = True
                asset.revision += 1
                db.commit()
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", archive_after_comparison)
        fields = [(key, (None, str(value))) for key, value in data.items()]
        invalid = client.post("/api/carton-supplier/carton-mark/checks", files=fields + [("print_pdf", ("another.pdf", pdf, "application/pdf"))])
        assert invalid.status_code == 422 and comparisons == []
        response = client.post("/api/carton-supplier/carton-mark/checks", files=fields)
        assert response.status_code == 404 and len(comparisons) == 1, response.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
