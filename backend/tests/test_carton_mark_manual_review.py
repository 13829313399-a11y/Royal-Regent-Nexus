"""Original-only review must remain pending until explicit internal approval."""
import hashlib
import json
from io import BytesIO

from PIL import Image
from pypdf import PdfReader

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login, revoke_supplier_permission
from test_carton_supplier_mark_assets import add_asset
from test_carton_mark_api import _pdf_bytes
from test_carton_mark_qc_api import image_bytes, result_data

SCOPE = {"factory_id": "huaxing"}
SUPPLIER = "/api/carton-supplier/carton-mark/manual-reviews"
INTERNAL = "/api/carton-mark/manual-reviews"


def prepare(client, image=False):
    order = setup_portal(client)
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset
    with SessionLocal() as db:
        content = add_asset(db, "original", order["contract_no"], order_id=order["id"], kind="image" if image else "pdf")
        db.flush()
        if not image:
            content = _pdf_bytes()
            asset = db.get(CartonMarkAsset, "original")
            asset.content, asset.sha256, asset.size_bytes = content, hashlib.sha256(content).hexdigest(), len(content)
        db.commit()
    asset = client.get("/api/carton-supplier/carton-mark/assets", params=SCOPE).json()[0]
    return order, dict(**SCOPE, order_id=order["id"], issue_id=asset["orders"][0]["issue_id"],
        assets=[dict(id=asset["id"], revision=asset["revision"])], note="客户确认的原稿，仅提供 PDF 或图片"), content


def test_pdf_pending_approval_qc_and_archived_originals(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        order, payload, original = prepare(client)
        payload.pop("note")  # Source explanations and checkbox confirmations are no longer required.
        assert client.post(SUPPLIER, json={**payload, "approve": True}).status_code == 403
        created = client.post(SUPPLIER, json=payload)
        assert created.status_code == 201, created.text
        value = created.json()
        identifier = value["id"]
        assert not value["qc_ready"] and not value["manual_released"]
        assert value["check_result"]["review_method"] == "manual_sources"
        assert value["check_result"]["summary"]["pass_count"] == 0
        assert value["excel_file_name"] == ""
        assert client.post(SUPPLIER, json=payload).status_code == 409
        history = client.get("/api/carton-supplier/carton-mark/checks", params=SCOPE)
        assert history.json()[0]["id"] == identifier
        assert "manual_released_by_name" not in history.text
        release = f"/api/carton-mark/templates/{identifier}/manual-release"
        assert client.post(release, params=SCOPE, json={}).status_code == 403
        login_as(client, "qc_inspector")
        photo_data = dict(**SCOPE, template_id=identifier, request_id="pending-test")
        assert client.post("/api/carton-mark/qc-records", data=photo_data, files={"front_photos": ("front.png", image_bytes(), "image/png")}).status_code == 409
        login_as(client, "admin")
        approved = client.post(release, params=SCOPE, json={})
        assert approved.status_code == 200, approved.text
        assert approved.json()["qc_ready"] and approved.json()["excel_file_size"] == 0
        assert approved.json()["check_status"] == "需复核"
        assert approved.json()["check_result"]["confirmed_checks"] == []
        assert approved.json()["manual_released_by_name"] and approved.json()["manual_released_at"]
        assert client.get(f"/api/carton-mark/templates/{identifier}/sources/original", params=SCOPE).content == original
        assert client.post(release, params=SCOPE, json={}).status_code == 409
        from app.services import carton_mark_qc as qc
        from app.schemas.carton_mark import CartonMarkBatchCheckResponse, CartonMarkBatchCheckItem, CartonMarkAutoCheckResponse
        monkeypatch.setattr(qc, "build_carton_mark_batch_auto_check", lambda **kw: CartonMarkBatchCheckResponse(
            summary=result_data()["summary"], items=[CartonMarkBatchCheckItem(side="front", file_name="front.png", file_index=0,
                result=CartonMarkAutoCheckResponse(**result_data()))]))
        login_as(client, "qc_inspector")
        photo_data["request_id"] = "approved-test"
        submitted = client.post("/api/carton-mark/qc-records", data=photo_data, files={"front_photos": ("front.png", image_bytes(), "image/png")})
        assert submitted.status_code == 200, submitted.text
        record = submitted.json()[0]
        assert record["status"] == "待复核"
        assert record["events"][0]["kind"] == "AUTO_CHECK" and record["events"][0]["result"]
        assert record["template_snapshot"]["review_method"] == "manual_sources"
        assert record["template_snapshot"]["source_assets"][0]["sha256"] == hashlib.sha256(original).hexdigest()
        assert record["template_snapshot"]["manual_release_reason"] == "订单资料审核通过"
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        with SessionLocal() as db:
            db.get(CartonMarkAsset, "original").is_archived = True
            db.get(CartonMarkTemplate, identifier).is_archived = True
            db.commit()
        assert client.get(f"/api/carton-mark/qc-records/{record['id']}/sources/original", params=SCOPE).content == original
        assert client.get(f"/api/carton-mark/qc-records/{record['id']}/template", params=SCOPE).content == original
        assert client.get(f"/api/carton-mark/qc-records/{record['id']}/sources/unknown", params=SCOPE).status_code == 404
        assert client.get(f"/api/carton-mark/qc-records/{record['id']}/sources/original", params={"factory_id": "huakang-c"}).status_code == 403


def test_image_reference_keeps_pixels_order_and_original_bytes(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        order, payload, original = prepare(client, image=True)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkDocument
        from app.models.carton_procurement import CartonOrder
        transparent = BytesIO()
        Image.new("RGBA", (37, 19), (0, 0, 255, 128)).save(transparent, "PNG")
        with SessionLocal() as db:
            add_asset(db, "side", order["contract_no"], order_id=order["id"], kind="image")
            db.flush()
            asset = db.get(CartonMarkAsset, "side")
            asset.content = transparent.getvalue()
            asset.sha256 = hashlib.sha256(asset.content).hexdigest()
            asset.size_bytes = len(asset.content)
            db.get(CartonOrder, order["id"]).customer_po = ""  # Never manufacture a PO from a contract.
            db.commit()
        payload["assets"].append(dict(id="side", revision=1))
        login_as(client, "admin")
        created = client.post(INTERNAL, json={**payload, "approve": True, "note": ""})
        assert created.status_code == 201, created.text
        value = created.json()
        assert value["po"] == "" and value["qc_ready"] and value["manual_released"]
        assert [row["id"] for row in value["check_result"]["source_assets"]] == ["original", "side"]
        pdf = client.get(f"/api/carton-mark/templates/{value['id']}/documents/print_pdf", params=SCOPE).content
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 2
        assert reader.pages[1].mediabox.width == 37 and reader.pages[1].mediabox.height == 19
        # pypdf decodes the Flate image bytes: alpha is placed on white, with no JPEG loss.
        xobject = reader.pages[1]["/Resources"]["/XObject"]["/Im0"]
        assert xobject.get_data()[:3] == bytes([127, 127, 255])
        assert client.get(f"/api/carton-mark/templates/{value['id']}/sources/original", params=SCOPE).content == original
        assert client.get(f"/api/carton-mark/templates/{value['id']}/sources/side", params=SCOPE).content == transparent.getvalue()
        with SessionLocal() as db:
            assert list(db.query(CartonMarkDocument).filter_by(template_id=value["id"]).all())[0].kind == "print_pdf"
        from app.services import carton_mark_qc as qc
        def never_compare(**kwargs):
            raise AssertionError("Image references must not enter automated PDF comparison")
        monkeypatch.setattr(qc, "build_carton_mark_batch_auto_check", never_compare)
        monkeypatch.setattr(qc, "build_carton_mark_auto_check", never_compare)
        login_as(client, "qc_inspector")
        response = client.post("/api/carton-mark/qc-records", data=dict(**SCOPE, template_id=value["id"], request_id="image-manual"),
            files=[("front_photos", ("front.png", image_bytes(), "image/png")), ("side_photos", ("side.png", image_bytes(), "image/png"))])
        assert response.status_code == 200, response.text
        records = response.json()
        assert len(records) == 2
        for record in records:
            assert record["status"] == "待复核" and record["events"][0]["kind"] == "REVIEW"
            assert record["events"][0]["result"] is None and record["events"][0]["error"] == ""
            assert record["photos"]
        action = dict(action="重新自动核对", expected_revision=1, request_id="image-rerun")
        assert client.post(f"/api/carton-mark/qc-records/{records[0]['id']}/actions", params=SCOPE, json=action).status_code == 422
        action.update(action="核对通过", request_id="image-accept")
        reviewed = client.post(f"/api/carton-mark/qc-records/{records[0]['id']}/actions", params=SCOPE, json=action)
        assert reviewed.status_code == 200 and reviewed.json()["status"] == "核对通过"


def test_manual_sources_reject_stale_wrong_order_scope_and_permissions_changed_during_conversion(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare(client)
        from app.services import carton_mark_manual_review as service
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkTemplate
        calls = []
        converter = service.reference_pdf
        monkeypatch.setattr(service, "reference_pdf", lambda rows: calls.append(rows) or converter(rows))
        for changed, code in (({"factory_id": "huakang-c"}, 403), ({"order_id": "foreign"}, 422),
                ({"assets": [dict(id="original", revision=2)]}, 409),
                ({"assets": [dict(id="unknown", revision=1)]}, 404),
                ({"assets": payload["assets"] * 2}, 422)):
            response = client.post(SUPPLIER, json={**payload, **changed})
            assert response.status_code == code, response.text
        assert not calls
        login_as(client, "carton_warehouse")
        assert client.post(INTERNAL, json={**payload, "approve": True}).status_code == 403
        assert not calls
        supplier_login(client)
        def revoke(rows):
            revoke_supplier_permission()
            return converter(rows)
        monkeypatch.setattr(service, "reference_pdf", revoke)
        assert client.post(SUPPLIER, json=payload).status_code == 403
        with SessionLocal() as db:
            assert db.query(CartonMarkTemplate).count() == 0


def test_direct_approval_rolls_back_creation_if_final_order_validation_fails(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        _, payload, _ = prepare(client)
        login_as(client, "admin")
        from fastapi import HTTPException
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkTemplate, CartonMarkDocument
        from app.services import carton_mark_manual_review as service
        validate = service.validate_release
        def changed_order(*args):
            raise HTTPException(409, "订单归属已变化")
        monkeypatch.setattr(service, "validate_release", changed_order)
        response = client.post(INTERNAL, json={**payload, "approve": True})
        assert response.status_code == 409, response.text
        with SessionLocal() as db:
            assert db.query(CartonMarkTemplate).count() == 0
            assert db.query(CartonMarkDocument).count() == 0
        monkeypatch.setattr(service, "validate_release", validate)
        response = client.post(INTERNAL, json={**payload, "approve": True})
        assert response.status_code == 201 and response.json()["qc_ready"], response.text
