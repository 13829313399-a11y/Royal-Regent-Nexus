"""Mixed supplier originals retain factory/order isolation and the QC check gate."""
import hashlib
import json
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, revoke_supplier_permission, restore_supplier_permission
from test_carton_mark_api import _workbook_bytes, _pdf_bytes
from test_carton_mark_asset_images import photo_bytes
from test_carton_supplier_mark_check import result_for

BASE = "/api/carton-supplier/carton-mark"
SCOPE = {"factory_id": "huaxing"}


def upload(client, files, **data):
    return client.post(BASE + "/assets/upload", data={**SCOPE, **data},
        files=[("files", (name, content, "application/octet-stream")) for name, content in files])


def test_mixed_upload_auto_binds_own_issue_retains_success_and_never_approves_qc(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        contract = order["contract_no"]
        files = [(contract + ".xlsx", _workbook_bytes()), (contract + ".pdf", _pdf_bytes()),
            (contract + "_正唛.png", photo_bytes()), ("invalid.pdf", b"not PDF"), ("photo.png", photo_bytes() + b"\n")]
        response = upload(client, files, customer_name="FORGED", contract_number="FOREIGN", supplier_id="FOREIGN")
        assert response.status_code == 201, response.text
        results = response.json()
        assert [row["status"] for row in results] == ["created", "created", "created", "failed", "failed"]
        assets = client.get(BASE + "/assets", params=SCOPE).json()
        assert len(assets) == 3 and {row["kind"] for row in assets} == {"excel", "pdf", "image"}
        for row in assets:
            assert row["orders"][0]["id"] == order["id"] and row["orders"][0]["contract_no"] == contract
            assert not {"created_by", "created_by_name", "sha256", "supplier_id", "candidates", "warning"} & row.keys()
            original = next(content for name, content in files if name == row["file_name"])
            assert client.get(f"{BASE}/assets/{row['id']}/document", params=SCOPE).content == original
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate, CartonMarkCustomer
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select, func
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
            assert db.scalar(select(func.count()).select_from(CartonMarkCustomer)) == 0
            assert all(row.bound_order_id == order["id"] for row in db.scalars(select(CartonMarkAsset)))
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == "CARTON_MARK_ASSET_CREATED")))
            assert len(events) == 3 and all(json.loads(event.detail_json)["supplier_context"]["order_id"] == order["id"] for event in events)
        repeated = upload(client, files[:3])
        assert [row["status"] for row in repeated.json()] == ["duplicate"] * 3
        login_as(client, "admin")
        assert len(client.get("/api/carton-mark/assets", params=SCOPE).json()) == 3


def test_explicit_order_fallback_rejects_wrong_contract_scope_and_hidden_duplicates(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        orders = client.get(BASE + "/upload-orders", params=SCOPE).json()
        selected = {"order_id": order["id"], "issue_id": orders[0]["issue_id"]}
        assert upload(client, [("camera.png", photo_bytes())], **selected).json()[0]["status"] == "created"
        assert upload(client, [("FOREIGN123.pdf", _pdf_bytes())], **selected).json()[0]["status"] == "failed"
        assert upload(client, [("print.pdf", _pdf_bytes())], order_id="foreign", issue_id="foreign").status_code == 404
        assert upload(client, [("print.pdf", _pdf_bytes())], factory_id="huakang-b").status_code == 403
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonOrder
        from sqlalchemy import select
        with SessionLocal() as db:
            asset = db.scalar(select(CartonMarkAsset))
            asset.is_archived = True
            db.commit()
            identifier = asset.id
        blocked = upload(client, [("camera.png", photo_bytes())], **selected)
        assert blocked.json()[0]["status"] == "failed" and blocked.json()[0]["asset"] is None
        with SessionLocal() as db:
            assert db.get(CartonMarkAsset, identifier).is_archived
            db.get(CartonOrder, order["id"]).status = "CANCELLED"
            db.commit()
        assert client.get(BASE + "/assets", params=SCOPE).json() == []
        assert upload(client, [("print.pdf", _pdf_bytes())], **selected).status_code == 404


def test_multiple_identical_warehouse_copies_reuse_only_an_authorized_active_copy(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from test_carton_mark_assets import upload as warehouse_upload
        from test_carton_supplier_portal import supplier_login
        login_as(client, "admin")
        first, second = [row["asset"] for row in warehouse_upload(client, [
            (order["contract_no"] + ".pdf", _pdf_bytes()),
            (order["contract_no"] + ".pdf", _pdf_bytes()),
        ])]
        assert first["id"] != second["id"]
        assert client.delete(f"/api/carton-mark/assets/{first['id']}", params={**SCOPE, "revision": first["revision"]}).status_code == 204
        supplier_login(client)
        selected = client.get(BASE + "/upload-orders", params=SCOPE).json()[0]
        response = upload(client, [("print.pdf", _pdf_bytes())], order_id=order["id"], issue_id=selected["issue_id"])
        assert response.status_code == 201, response.text
        outcome = response.json()[0]
        assert outcome["status"] == "duplicate" and outcome["asset"]["id"] == second["id"]
        assert client.get(f"{BASE}/assets/{first['id']}/document", params=SCOPE).status_code == 404


def test_permissions_limits_and_changes_during_recognition_cannot_write(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        from app.services import carton_supplier_mark_upload as service
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from sqlalchemy import select, func
        files = [("print.pdf", _pdf_bytes())]
        revoke_supplier_permission("carton_supplier:edit")
        assert upload(client, files).status_code == 403
        assert client.get(BASE + "/upload-orders", params=SCOPE).status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        assert upload(client, files * 51).status_code == 413
        assert upload(client, [("large.pdf", b"x" * (20 * 1024 * 1024 + 1))]).status_code == 413
        original = service.recognize_batch
        def revoked(*args):
            result = original(*args)
            revoke_supplier_permission("carton_supplier:edit")
            return result
        monkeypatch.setattr(service, "recognize_batch", revoked)
        assert upload(client, files).status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        def changed(*args):
            result = original(*args)
            from app.models.carton_procurement import CartonOrder
            with SessionLocal() as db:
                db.scalar(select(CartonOrder).where(CartonOrder.factory_id == "huaxing")).status = "CANCELLED"
                db.commit()
            return result
        monkeypatch.setattr(service, "recognize_batch", changed)
        assert upload(client, files).status_code == 409
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 0


def test_uploaded_excel_pdf_pair_reuses_bytes_revalidates_both_and_retains_provenance(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        contract = order["contract_no"]
        response = upload(client, [(contract + ".xlsx", _workbook_bytes()), (contract + ".pdf", _pdf_bytes())])
        assert response.status_code == 201, response.text
        excel, pdf = [row["asset"] for row in response.json()]
        data = dict(**SCOPE, order_id=order["id"], issue_id=excel["orders"][0]["issue_id"],
            excel_asset_id=excel["id"], expected_revision=excel["revision"], pdf_asset_id=pdf["id"], expected_pdf_revision=pdf["revision"])
        from app.api import carton_supplier_portal as api
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select, func
        calls = []
        def compared(**kwargs):
            calls.append(kwargs)
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", compared)
        for changes, status in (({"pdf_asset_id": "foreign"}, 404), ({"pdf_asset_id": excel["id"]}, 422), ({"expected_pdf_revision": 10}, 409)):
            assert client.post(BASE + "/checks", data={**data, **changes}).status_code == status
        assert calls == []
        def changed_pdf(**kwargs):
            with SessionLocal() as db:
                db.get(CartonMarkAsset, pdf["id"]).revision += 1
                db.commit()
            return result_for(kwargs)
        monkeypatch.setattr(api, "build_carton_mark_document_check", changed_pdf)
        assert client.post(BASE + "/checks", data=data).status_code == 409
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0
        data["expected_pdf_revision"] = 2
        monkeypatch.setattr(api, "build_carton_mark_document_check", compared)
        checked = client.post(BASE + "/checks", data=data)
        assert checked.status_code == 201, checked.text
        assert checked.json()["qc_ready"]
        assert calls[0]["pdf_bytes"] == _pdf_bytes()
        assert client.get(f"{BASE}/checks/{checked.json()['id']}/documents/print_pdf", params=SCOPE).content == _pdf_bytes()
        with SessionLocal() as db:
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.event_type == "CARTON_MARK_TEMPLATE_CREATED"))
            context = json.loads(event.detail_json)["supplier_context"]
            assert context["pdf_asset_id"] == pdf["id"] and context["pdf_asset_revision"] == 2
            assert context["pdf_sha256"] == hashlib.sha256(_pdf_bytes()).hexdigest()


def test_same_contract_orders_require_explicit_selection_and_do_not_share_a_new_binding(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonPurchaseOrderIssue
        from app.models.carton_mark import CartonMarkAsset
        from sqlalchemy import select, func
        with SessionLocal() as db:
            original = db.get(CartonOrder, order["id"])
            second = CartonOrder(**{column.name: getattr(original, column.name) for column in CartonOrder.__table__.columns})
            second.id = "OWN-SECOND-ORDER"
            second.order_no = "OWN-SECOND-ORDER"
            db.add(second)
            db.flush()
            original_issue = db.scalar(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id == order["id"]).order_by(CartonPurchaseOrderIssue.issue_sequence.desc()))
            second_issue = CartonPurchaseOrderIssue(**{column.name: getattr(original_issue, column.name) for column in CartonPurchaseOrderIssue.__table__.columns})
            second_issue.id = "SECOND-ISSUE"
            second_issue.order_id = second.id
            second_issue.order_no = second.order_no
            second_issue.document_no = "SECOND-PURCHASE-P00"
            snapshot = json.loads(second_issue.snapshot_json)
            snapshot["order"].update(id=second.id, order_no=second.order_no, order_date="2026-10-07")
            second_issue.snapshot_json = json.dumps(snapshot)
            db.add(second_issue)
            db.commit()
        options = client.get(BASE + "/upload-orders", params=SCOPE).json()
        assert len(options) == 2 and len({row["document_no"] for row in options}) == 2
        selected = next(row for row in options if row["id"] == "OWN-SECOND-ORDER")
        assert selected["document_no"] == "SECOND-PURCHASE-P00" and selected["order_date"] == "2026-10-07"
        file = [(order["contract_no"] + ".pdf", _pdf_bytes())]
        ambiguous = upload(client, file).json()[0]
        assert ambiguous["status"] == "failed" and ambiguous["asset"] is None
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 0
        linked = upload(client, file, order_id=selected["id"], issue_id=selected["issue_id"]).json()[0]
        assert linked["status"] == "created"
        assert [row["id"] for row in linked["asset"]["orders"]] == [selected["id"]]
