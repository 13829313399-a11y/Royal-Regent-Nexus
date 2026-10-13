import importlib
import json
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from test_molding_sample_api import make_client, login_as


BASE = "/api/carton-mark/qc-records"


def image_bytes(color="red"):
    output = BytesIO()
    Image.new("RGB", (30, 20), color).save(output, "PNG")
    return output.getvalue()


def result_data():
    return dict(summary=dict(overall_status="核对通过", pass_count=1, mismatch_count=0, missing_count=0, review_count=0),
        template_fields=[], front_template_fields=[], side_template_fields=[], front_photo_fields=[], side_photo_fields=[], comparisons=[], extraction=[])


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        dbm = importlib.import_module("app.db")
        model = importlib.import_module("app.models.carton_mark")
        qc = importlib.import_module("app.services.carton_mark_qc")
        schema = importlib.import_module("app.schemas.carton_mark")
        pdf = b"original-print-pdf"
        with dbm.SessionLocal() as db:
            for identifier, factory in (("T1", "huaxing"), ("T2", "huakang-c")):
                db.add(model.CartonMarkTemplate(id=identifier, factory_id=factory, customer_name="客户", po="PO1", item="ITEM1", contract_number="C1",
                    business_key_sha256="business", document_fingerprint=identifier, version=3, check_status="核对通过", check_result_json="{}",
                    excel_sha256="excel", pdf_sha256=qc.digest(pdf), created_by="seed", created_by_name="仓管", created_at="2026-10-10", updated_at="2026-10-10"))
                db.flush()
                db.add(model.CartonMarkDocument(id="DOC-" + identifier, factory_id=factory, template_id=identifier, kind="print_pdf",
                    file_name="original.pdf", content_type="application/pdf", size_bytes=len(pdf), sha256=qc.digest(pdf), content=pdf, created_at="2026-10-10"))
            db.commit()
        def batch(**kwargs):
            items = [schema.CartonMarkBatchCheckItem(side=side, file_name=name, file_index=index,
                result=schema.CartonMarkAutoCheckResponse(**result_data()))
                for side, files in (("front", kwargs["front_images"]), ("side", kwargs["side_images"])) for index, (name, _) in enumerate(files)]
            return schema.CartonMarkBatchCheckResponse(summary=items[0].result.summary, items=items)
        monkeypatch.setattr(qc, "build_carton_mark_batch_auto_check", batch)
        monkeypatch.setattr(qc, "build_carton_mark_auto_check", lambda **kw: schema.CartonMarkAutoCheckResponse(**result_data()))
        login_as(client, "qc_inspector")
        yield client, dbm, model, qc


def submit(client, request_id="upload-1", **data):
    return client.post(BASE, data={"factory_id": "huaxing", "template_id": "T1", "request_id": request_id, **data},
        files=[("front_photos", ("front.png", image_bytes(), "image/png"))])


def action(client, identifier, name, revision, request_id, note="人工检查已确认"):
    return client.post(f"{BASE}/{identifier}/actions", params={"factory_id": "huaxing"},
        json=dict(action=name, expected_revision=revision, request_id=request_id, note=note))


def test_originals_versions_idempotency_and_cross_device_read(setup):
    client, dbm, model, qc = setup
    saved = submit(client)
    assert saved.status_code == 200, saved.text
    value = saved.json()[0]
    assert value["status"] == "待复核"  # OCR pass cannot approve the product.
    assert value["template_version"] == 3
    assert value["events"][0]["result"]["summary"]["overall_status"] == "核对通过"
    assert submit(client).json()[0]["id"] == value["id"]
    assert submit(client, note="changed").status_code == 409
    photo_id = value["photos"][0]["id"]
    login_as(client, "qc_supervisor")  # A new authenticated session sees the original submission.
    page = client.get(BASE, params={"factory_id": "huaxing"}).json()
    assert page["total"] == 1 and page["items"][0]["id"] == value["id"]
    downloaded = client.get(f"{BASE}/{value['id']}/photos/{photo_id}", params={"factory_id": "huaxing"})
    assert downloaded.content == image_bytes() and downloaded.headers["cache-control"] == "private, no-store"
    with dbm.SessionLocal() as db:
        template = db.get(model.CartonMarkTemplate, "T1")
        template.is_archived = True
        db.commit()
    assert client.get(f"{BASE}/{value['id']}/template", params={"factory_id": "huaxing"}).content == b"original-print-pdf"
    assert submit(client, request_id="new-upload").status_code == 409
    for table in ("carton_mark_qc_records", "carton_mark_qc_photos", "carton_mark_qc_events"):
        with dbm.SessionLocal() as db:
            with pytest.raises(DBAPIError):
                db.execute(text(f"DELETE FROM {table}"))
            db.rollback()


def test_factory_permission_boundary_and_invalid_images(setup):
    client, _, _, _ = setup
    assert client.get(BASE, params={"factory_id": "huakang-c"}).status_code == 403
    assert submit(client, factory_id="huakang-c", template_id="T2").status_code == 403
    assert submit(client, template_id="T2").status_code == 404
    invalid = client.post(BASE, data={"factory_id": "huaxing", "template_id": "T1", "request_id": "invalid"},
        files={"front_photos": ("bad.png", b"broken", "image/png")})
    assert invalid.status_code == 422
    value = submit(client).json()[0]
    assert client.get(f"{BASE}/{value['id']}", params={"factory_id": "huakang-c"}).status_code == 403
    login_as(client, "carton_warehouse")
    assert client.get(BASE, params={"factory_id": "huaxing"}).status_code == 200
    assert submit(client, "warehouse-upload").status_code == 403
    assert action(client, value["id"], "核对通过", 1, "warehouse-review").status_code == 403


def test_reviews_corrections_void_and_optimistic_conflicts(setup):
    client, dbm, model, _ = setup
    original = submit(client).json()[0]
    identifier = original["id"]
    assert action(client, identifier, "发现异常", 1, "short-reason", "错").status_code == 422
    exception = action(client, identifier, "发现异常", 1, "review-1", "侧唛地址印刷错误")
    assert exception.status_code == 200, exception.text
    assert exception.json()["revision"] == 2
    assert action(client, identifier, "发现异常", 1, "review-1", "侧唛地址印刷错误").status_code == 200
    assert action(client, identifier, "核对通过", 1, "stale").status_code == 409
    correction = submit(client, "correction", corrects_record_id=identifier, note="已重新印刷侧唛")
    assert correction.status_code == 200, correction.text
    corrected = correction.json()[0]
    assert corrected["corrects_record_id"] == identifier
    passed = action(client, corrected["id"], "核对通过", 1, "passed")
    assert passed.json()["status"] == "核对通过"
    assert client.get(f"{BASE}/{identifier}", params={"factory_id": "huaxing"}).json()["status"] == "发现异常"
    void = action(client, corrected["id"], "作废", 2, "void", "本次记录选错照片")
    assert void.json()["status"] == "已作废" and len(void.json()["events"]) == 3
    assert action(client, corrected["id"], "核对通过", 3, "after-void").status_code == 409
    with dbm.SessionLocal() as db:
        assert len(list(db.scalars(select(model.CartonMarkQcPhoto)))) == 2


def test_ocr_failure_keeps_evidence_and_rerun_appends(setup, monkeypatch):
    client, _, _, qc = setup
    original_batch = qc.build_carton_mark_batch_auto_check
    def fail(**kwargs):
        raise RuntimeError("OCR unavailable")
    monkeypatch.setattr(qc, "build_carton_mark_batch_auto_check", fail)
    value = submit(client).json()[0]
    assert value["photos"] and value["events"][0]["error"] and value["status"] == "待复核"
    monkeypatch.setattr(qc, "build_carton_mark_batch_auto_check", original_batch)
    def reject_pair(**kwargs):
        raise AssertionError("A one-face record must use its original one-face comparison algorithm")
    monkeypatch.setattr(qc, "build_carton_mark_auto_check", reject_pair)
    rerun = action(client, value["id"], "重新自动核对", 1, "rerun")
    assert rerun.status_code == 200, rerun.text
    assert len(rerun.json()["events"]) == 2 and rerun.json()["events"][0]["error"]
    assert rerun.json()["events"][1]["result"]["summary"]["overall_status"] == "核对通过"


def test_batch_keeps_independent_faces_and_filters_by_contract_item(setup):
    client, _, _, _ = setup
    response = client.post(BASE, data={"factory_id": "huaxing", "template_id": "T1", "request_id": "batch"}, files=[
        ("front_photos", ("front.png", image_bytes(), "image/png")),
        ("side_photos", ("side.png", image_bytes("blue"), "image/png")),
    ])
    assert response.status_code == 200, response.text
    records = response.json()
    assert len(records) == 2
    assert [r["photos"][0]["side"] for r in records] == ["front", "side"]
    page = client.get(BASE, params={"factory_id": "huaxing", "contract_number": "C1", "item": "ITEM1", "limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get(BASE, params={"factory_id": "huaxing", "contract_number": "other"}).json()["total"] == 0


def test_template_revoked_during_ocr_does_not_save(setup, monkeypatch):
    client, dbm, model, qc = setup
    original = qc.compute
    def revoke(*args):
        with dbm.SessionLocal() as db:
            db.get(model.CartonMarkTemplate, "T1").is_archived = True
            db.commit()
        return original(*args)
    monkeypatch.setattr(qc, "compute", revoke)
    assert submit(client).status_code == 409
    assert client.get(BASE, params={"factory_id": "huaxing"}).json()["total"] == 0


def test_session_revoked_during_ocr_does_not_save(setup, monkeypatch):
    client, dbm, model, qc = setup
    auth_model = importlib.import_module("app.models.auth")
    original = qc.compute
    def revoke(*args):
        with dbm.SessionLocal() as db:
            for session in db.scalars(select(auth_model.AuthSession)):
                session.status = "revoked"
            db.commit()
        return original(*args)
    monkeypatch.setattr(qc, "compute", revoke)
    assert submit(client).status_code == 401
    with dbm.SessionLocal() as db:
        assert list(db.scalars(select(model.CartonMarkQcRecord))) == []
