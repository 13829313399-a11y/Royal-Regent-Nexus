"""Supplier checks retain original documents and enforce current issued-order ownership."""
import hashlib
import json
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import (setup_portal, revoke_supplier_permission,
    restore_supplier_permission, supplier_login)
from test_carton_supplier_mark_assets import add_asset
from test_carton_mark_api import _workbook_bytes, _pdf_bytes

BASE = "/api/carton-supplier/carton-mark/checks"
SCOPE = {"factory_id": "huaxing"}


def prepare(client):
    order = setup_portal(client)
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset
    excel = _workbook_bytes()
    with SessionLocal() as db:
        add_asset(db, "excel-source", order["contract_no"], kind="excel", order_id=order["id"])
        db.flush()
        source = db.get(CartonMarkAsset, "excel-source")
        source.file_name = "customer.xlsx"
        source.content = excel
        source.sha256 = hashlib.sha256(excel).hexdigest()
        source.size_bytes = len(excel)
        db.commit()
    asset = client.get("/api/carton-supplier/carton-mark/assets", params=SCOPE).json()[0]
    return order, dict(**SCOPE, order_id=order["id"], issue_id=asset["orders"][0]["issue_id"],
        excel_asset_id=asset["id"], expected_revision=asset["revision"]), excel


def result_for(kwargs, status="核对通过"):
    from app.schemas.carton_mark import CartonMarkDocumentCheckResponse
    return CartonMarkDocumentCheckResponse(excel_file_name=kwargs["excel_file_name"],
        pdf_file_name=kwargs["pdf_file_name"], summary=dict(overall_status=status,
            pass_count=int(status == "核对通过"), changed_count=int(status == "发现差异"),
            missing_count=0, unexpected_count=0, review_count=int(status == "需复核")),
        excel_items=[], pdf_items=[], comparisons=[], extraction=[])


def post(client, payload, content=None, **extra):
    return client.post(BASE, data={**payload, **extra}, files={"print_pdf": (
        "print.pdf", _pdf_bytes() if content is None else content, "application/pdf")})


def test_supplier_check_persists_pair_without_customer_master_and_links_internal_qc(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, excel = prepare(client)
        from app.api import carton_supplier_portal as api
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkCustomer, CartonMarkTemplate, CartonMarkDocument
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select, func
        calls = []
        def checked(**kwargs):
            calls.append(kwargs)
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", checked)
        created = post(client, payload, customer_name="FORGED", contract_number="OTHER", item="OTHER")
        assert created.status_code == 201, created.text
        record = created.json()
        assert (record["customer_name"], record["contract_number"], record["item"]) == (
            order["customer_name"], order["contract_no"], order["item_no"])
        assert record["qc_ready"] and record["version"] == 1
        assert calls[0]["excel_bytes"] == excel and calls[0]["pdf_bytes"] == _pdf_bytes()
        for private in ("created_by_name", "manual_release_reason", "manual_released_by_name"):
            assert private not in created.text
        assert client.get(BASE, params=SCOPE).json() == [record]
        for kind, expected in (("source_excel", excel), ("print_pdf", _pdf_bytes())):
            downloaded = client.get(f"{BASE}/{record['id']}/documents/{kind}", params={**SCOPE, "preview": True})
            assert downloaded.status_code == 200 and downloaded.content == expected
            assert downloaded.headers["cache-control"] == "private, no-store"
            assert downloaded.headers["content-disposition"].startswith("inline" if kind == "print_pdf" else "attachment")
        assert post(client, payload).status_code == 409
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 1
            assert db.scalar(select(func.count()).select_from(CartonMarkDocument)) == 2
            assert db.scalar(select(func.count()).select_from(CartonMarkCustomer)) == 0
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == record["id"]))
            assert json.loads(event.detail_json)["supplier_context"]["issue_id"] == payload["issue_id"]
        assert client.get("/api/carton-mark/templates", params=SCOPE).status_code == 403
        assert client.post(f"/api/carton-mark/templates/{record['id']}/manual-release",
            params=SCOPE, json={"reason": "供应商不应该能够自行放行"}).status_code == 403
        login_as(client, "qc_inspector")
        internal = client.get("/api/carton-mark/templates", params=SCOPE)
        assert internal.status_code == 200, internal.text
        assert internal.json()[0]["id"] == record["id"] and internal.json()[0]["qc_ready"]
        supplier_login(client)
        revoke_supplier_permission()
        assert client.get(BASE, params=SCOPE).status_code == 403
        assert client.get(f"{BASE}/{record['id']}/documents/print_pdf", params=SCOPE).status_code == 403


def test_supplier_check_rejects_read_only_wrong_scope_source_and_stale_versions_before_parsing(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare(client)
        from app.api import carton_supplier_portal as api
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonSupplier
        from app.models.carton_mark import CartonMarkTemplate
        from sqlalchemy import select, func
        calls = []
        monkeypatch.setattr(api, "build_carton_mark_document_check", lambda **kwargs: calls.append(kwargs) or result_for(kwargs))
        with SessionLocal() as db:
            add_asset(db, "pdf-source", order["contract_no"])
            add_asset(db, "unbound", "", kind="excel")
            add_asset(db, "other-factory", order["contract_no"], factory="huakang-a", kind="excel")
            db.commit()
        for changes, status in (({"factory_id": "huakang-a"}, 403), ({"order_id": "foreign-order"}, 404),
                ({"excel_asset_id": "other-factory"}, 404), ({"excel_asset_id": "unbound"}, 404),
                ({"excel_asset_id": "pdf-source"}, 422), ({"expected_revision": 2}, 409),
                ({"issue_id": "old-issue"}, 409)):
            response = post(client, {**payload, **changes})
            assert response.status_code == status, response.text
        revoke_supplier_permission("carton_supplier:edit")
        assert post(client, payload).status_code == 403
        assert client.get(BASE, params=SCOPE).status_code == 200
        restore_supplier_permission("carton_supplier:edit")
        with SessionLocal() as db:
            db.get(CartonOrder, order["id"]).deleted_at = "2026-10-07"
            db.commit()
        assert post(client, payload).status_code == 404
        assert calls == []
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0


def test_supplier_check_revalidates_permissions_and_source_after_comparison(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare(client)
        from app.api import carton_supplier_portal as api
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from app.models.carton_procurement import CartonOrder
        from sqlalchemy import select, func
        def revoked(**kwargs):
            revoke_supplier_permission("carton_supplier:edit")
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", revoked)
        assert post(client, payload).status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        def changed_source(**kwargs):
            with SessionLocal() as db:
                db.get(CartonMarkAsset, "excel-source").revision += 1
                db.commit()
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", changed_source)
        assert post(client, payload).status_code == 409
        payload["expected_revision"] = 2
        def cancelled(**kwargs):
            with SessionLocal() as db:
                db.get(CartonOrder, order["id"]).status = "CANCELLED"
                db.commit()
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", cancelled)
        assert post(client, payload).status_code == 404
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0


def test_failed_supplier_checks_remain_visible_and_only_internal_release_enables_qc(monkeypatch):
    with make_client(monkeypatch) as client:
        order, payload, _ = prepare(client)
        from app.api import carton_supplier_portal as api
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonSupplier
        monkeypatch.setattr(api, "build_carton_mark_document_check", lambda **kwargs: result_for(kwargs, "发现差异"))
        first = post(client, payload).json()
        assert first["check_status"] == "发现差异" and not first["qc_ready"]
        monkeypatch.setattr(api, "build_carton_mark_document_check", lambda **kwargs: result_for(kwargs, "需复核"))
        second_response = post(client, payload, _pdf_bytes() + b"\n% version2")
        assert second_response.status_code == 201, second_response.text
        second = second_response.json()
        assert second["version"] == 2 and not second["qc_ready"]
        assert {row["id"] for row in client.get(BASE, params=SCOPE).json()} == {first["id"], second["id"]}
        login_as(client, "admin")
        released = client.post(f"/api/carton-mark/templates/{second['id']}/manual-release",
            params=SCOPE, json={"reason": "内部主管已人工逐项核对并同意使用"})
        assert released.status_code == 200, released.text
        supplier_login(client)
        records = client.get(BASE, params=SCOPE).json()
        latest = next(row for row in records if row["id"] == second["id"])
        assert latest["manual_released"] and latest["qc_ready"] and latest["check_status"] == "需复核"
        with SessionLocal() as db:
            owned = db.get(CartonOrder, order["id"])
            original = db.get(CartonSupplier, owned.supplier_id)
            foreign = CartonSupplier(**{column.name: getattr(original, column.name)
                for column in CartonSupplier.__table__.columns})
            foreign.id = "FOREIGN-SUPPLIER"
            foreign.supplier_code = "FOREIGN-SUPPLIER"
            db.add(foreign)
            db.flush()
            owned.supplier_id = foreign.id
            db.commit()
        hidden = client.get(BASE, params=SCOPE)
        assert hidden.status_code == 403 or hidden.json() == []
        assert client.get(f"{BASE}/{second['id']}/documents/print_pdf", params=SCOPE).status_code in {403, 404}


def test_supplier_parser_errors_and_invalid_uploads_never_create_records(monkeypatch):
    with make_client(monkeypatch) as client:
        _, payload, _ = prepare(client)
        from app.api import carton_supplier_portal as api
        from app.services.carton_mark import CartonMarkDocumentError, CartonMarkDocumentConfigurationError
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkTemplate
        from sqlalchemy import select, func
        assert post(client, payload, b"").status_code == 400
        assert post(client, payload, b"x" * (20 * 1024 * 1024 + 1)).status_code == 413
        assert post(client, payload, b"not a PDF").status_code == 422
        for exception, status in ((CartonMarkDocumentError("文档无效"), 422),
                (CartonMarkDocumentConfigurationError("解析服务不可用"), 503)):
            def failed(**kwargs):
                raise exception
            monkeypatch.setattr(api, "build_carton_mark_document_check", failed)
            assert post(client, payload).status_code == status
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
