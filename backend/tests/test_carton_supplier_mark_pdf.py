import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from test_molding_sample_api import make_client
from test_carton_supplier_mark_check import prepare, SCOPE
from test_carton_supplier_portal import revoke_supplier_permission, restore_supplier_permission
from test_carton_mark_api import _pdf_bytes

BASE = "/api/carton-supplier/carton-mark/generate-pdf"


def test_ai_generation_uses_builtin_template_and_revalidates_scope_before_saving(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare(client)
        from app.services import carton_supplier_mark_ai as ai
        from app.services import carton_supplier_mark_pdf as service
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select, func
        template = dict(id="zumiez-review-v1", name="Zumiez", reference_sha256="confirmed")
        monkeypatch.setattr(ai, "configuration", lambda: ({}, template, b"reference", "private-signature"))
        status_url = "/api/carton-supplier/carton-mark/pdf-ai-status"
        scope = dict(**SCOPE, order_id=order["id"], issue_id=payload["issue_id"])
        status = client.get(status_url, params=scope)
        assert status.status_code == 200 and status.json()["available"]
        assert "private-signature" not in status.text and "reference_sha256" not in status.text
        assert client.get(status_url, params={**scope, "factory_id": "huakang-b"}).status_code == 403
        assert client.get(status_url, params={**scope, "order_id": "foreign"}).status_code == 404
        calls = []
        def converted(original):
            calls.append(original)
            return _pdf_bytes(), 1, [], dict(consent_version=ai.CONSENT_VERSION, field_sources={})
        monkeypatch.setattr(service, "prepare_pdf", converted)
        body = dict(**payload, layout_id="zumiez-review-v1", engine="deepseek_zumiez", ai_consent=True)
        assert client.post(BASE, json={**body, "ai_consent": False}).status_code == 422
        assert client.post(BASE, json={**body, "layout_id": "old"}).status_code == 409
        assert not calls
        response = client.post(BASE, json=body)
        assert response.status_code == 201, response.text
        assert response.json()["asset"]["orders"][0]["id"] == order["id"]
        assert calls[0]["contract_no"] == order["contract_no"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == response.json()["asset"]["id"]))
            conversion = json.loads(event.detail_json)["conversion"]
            assert conversion["method"] == "deepseek_zumiez"
            assert conversion["ai"]["consent_version"] == ai.CONSENT_VERSION
            assert "private-signature" not in event.detail_json
        def revoked(original):
            revoke_supplier_permission("carton_supplier:edit")
            return converted(original)
        monkeypatch.setattr(service, "prepare_pdf", revoked)
        assert client.post(BASE, json=body).status_code == 403
        assert client.get(status_url, params=scope).status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        def changed(original):
            with SessionLocal() as db:
                db.get(CartonMarkAsset, "excel-source").revision += 1
                db.commit()
            return converted(original)
        monkeypatch.setattr(service, "prepare_pdf", changed)
        assert client.post(BASE, json=body).status_code == 409
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 2


def test_generation_saves_order_bound_original_and_provenance_without_qc_approval(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, excel = prepare_layout(client)
        from app.services import carton_supplier_mark_pdf as service
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select, func
        calls = []
        def convert(original):
            calls.append(original)
            return _pdf_bytes(), 1, ["检查分页"]
        monkeypatch.setattr(service, "prepare_pdf", convert)
        response = client.post(BASE, json=payload)
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["page_count"] == 1 and result["warnings"] == ["检查分页"]
        assert result["asset"]["orders"][0]["id"] == order["id"]
        assert result["asset"]["file_name"] == "customer_排版.pdf"
        assert calls[0]["excel_bytes"] == excel
        assert client.get(f"/api/carton-supplier/carton-mark/assets/{result['asset']['id']}/document", params=SCOPE).content == _pdf_bytes()
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
            assert bytes(db.get(CartonMarkAsset, "excel-source").content) == excel
            stored = db.get(CartonMarkAsset, result["asset"]["id"])
            assert stored.sha256 == hashlib.sha256(_pdf_bytes()).hexdigest()
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == stored.id))
            detail = json.loads(event.detail_json)
            assert detail["conversion"]["source_asset_id"] == "excel-source"
            assert detail["conversion"]["source_revision"] == 1
            assert detail["supplier_context"]["issue_id"] == payload["issue_id"]
        revoke_supplier_permission()
        assert client.get(f"/api/carton-supplier/carton-mark/assets/{result['asset']['id']}/document", params=SCOPE).status_code == 403


def test_generation_rejects_invalid_scopes_before_rendering_and_changed_permissions_or_source_afterwards(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare_layout(client)
        from app.services import carton_supplier_mark_pdf as service
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonOrder
        from sqlalchemy import select, func
        calls = []
        monkeypatch.setattr(service, "prepare_pdf", lambda original: calls.append(original))
        for changes, expected in (({"factory_id": "huakang-b"}, 403), ({"order_id": "foreign"}, 404),
                ({"excel_asset_id": "missing"}, 404), ({"expected_revision": 2}, 409), ({"issue_id": "old"}, 409)):
            assert client.post(BASE, json={**payload, **changes}).status_code == expected
        assert not calls
        revoke_supplier_permission("carton_supplier:edit")
        assert client.post(BASE, json=payload).status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        def revoked(original):
            revoke_supplier_permission("carton_supplier:edit")
            return _pdf_bytes(), 1, []
        monkeypatch.setattr(service, "prepare_pdf", revoked)
        assert client.post(BASE, json=payload).status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        def changed(original):
            with SessionLocal() as db:
                db.get(CartonMarkAsset, "excel-source").revision += 1
                db.commit()
            return _pdf_bytes(), 1, []
        monkeypatch.setattr(service, "prepare_pdf", changed)
        assert client.post(BASE, json=payload).status_code == 409
        def cancelled(original):
            with SessionLocal() as db:
                db.get(CartonOrder, order["id"]).status = "CANCELLED"
                db.commit()
            return _pdf_bytes(), 1, []
        monkeypatch.setattr(service, "prepare_pdf", cancelled)
        assert client.post(BASE, json={**payload, "expected_revision": 2}).status_code == 404
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 1


def test_generation_failed_render_is_not_persisted_and_corrupt_original_never_renders(monkeypatch):
    with make_client(monkeypatch) as client:
        _, payload, _ = prepare_layout(client)
        from app.services import carton_supplier_mark_pdf as service
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from fastapi import HTTPException
        from sqlalchemy import select, func
        from app.core.config import settings
        calls = []
        def unavailable(original):
            calls.append(original)
            raise HTTPException(503, "转换引擎未安装")
        monkeypatch.setattr(service, "prepare_pdf", unavailable)
        assert client.post(BASE, json=payload).status_code == 503
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 1
            db.get(CartonMarkAsset, "excel-source").content = b"corrupt"
            db.commit()
        assert client.post(BASE, json=payload).status_code == 409
        assert len(calls) == 1
        monkeypatch.setattr(settings, "document_tools_enabled", False)
        assert client.post(BASE, json=payload).status_code == 503
        assert len(calls) == 1


def prepare_layout(client):
    order, payload, excel = prepare(client)
    response = client.post("/api/carton-supplier/carton-mark/layouts", data=dict(
        factory_id=payload["factory_id"], order_id=payload["order_id"], issue_id=payload["issue_id"],
        name="Customer layout", config="{}", expected_version="0"), files={"reference_pdf": ("old.pdf", _pdf_bytes(), "application/pdf")})
    assert response.status_code == 201, response.text
    return order, {**payload, "layout_id": response.json()["id"]}, excel
