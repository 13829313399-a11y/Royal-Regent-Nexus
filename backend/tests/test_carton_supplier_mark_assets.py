"""Raw carton-mark sharing follows issued contracts and supplier ownership."""
import hashlib
from test_molding_sample_api import make_client
from test_carton_supplier_portal import setup_portal, revoke_supplier_permission

BASE = "/api/carton-supplier/carton-mark/assets"
SCOPE = {"factory_id": "huaxing"}


def test_multi_contract_source_hides_unowned_links_and_revokes_document_access(monkeypatch):
    from test_molding_sample_api import login_as
    from test_carton_supplier_portal import supplier_login
    from test_carton_procurement_api import _order_payload
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, "admin")
        other = client.post("/api/carton-procurement/orders", json={**_order_payload(), "contract_no": "PRIVATE-CONTRACT"})
        assert other.status_code == 201, other.text
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        with SessionLocal() as db:
            content = add_asset(db, "shared-original", "")
            db.commit()
        binding_url = "/api/carton-mark/assets/shared-original/binding"
        bound = client.put(binding_url, params=SCOPE, json={"order_ids": [order["id"], other.json()["id"]], "revision": 1})
        assert bound.status_code == 200, bound.text
        supplier_login(client)
        result = client.get(BASE, params=SCOPE)
        assert result.status_code == 200, result.text
        assert result.json()[0]["contract_number"] == order["contract_no"]
        assert [row["id"] for row in result.json()[0]["orders"]] == [order["id"]]
        assert "PRIVATE-CONTRACT" not in result.text and other.json()["id"] not in result.text
        assert "bound_order_ids" not in result.text
        assert client.get(BASE + "/shared-original/document", params=SCOPE).content == content
        login_as(client, "admin")
        narrowed = client.put(binding_url, params=SCOPE, json={"order_ids": [other.json()["id"]], "revision": 2})
        assert narrowed.status_code == 200, narrowed.text
        supplier_login(client)
        assert client.get(BASE, params=SCOPE).json() == []
        assert client.get(BASE + "/shared-original/document", params=SCOPE).status_code == 404
        with SessionLocal() as db:
            assert db.get(CartonMarkAsset, "shared-original").content == content


def add_asset(db, key, contract, *, factory="huaxing", order_id=None, kind="pdf"):
    from app.models.carton_mark import CartonMarkAsset
    content = b"%PDF-1.4 " + key.encode() if kind == "pdf" else key.encode()
    if kind == "image":
        from test_carton_mark_asset_images import photo_bytes
        content = photo_bytes()
    asset = CartonMarkAsset(id=key, factory_id=factory, file_name=f"{key}.png" if kind == "image" else f"{key}.{kind}",
        kind=kind, content_type="image/png" if kind == "image" else "application/pdf" if kind == "pdf" else "application/vnd.ms-excel",
        size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), content=content,
        contract_number=contract, bound_order_id=order_id,
        recognition_source="manual_order" if order_id else "filename", candidates_json='[]',
        warning="private warning", created_by="admin", created_by_name="private actor",
        created_at="2026-10-05", updated_at="2026-10-05")
    db.add(asset)
    return content


def test_supplier_can_read_single_original_files_but_not_unbound_or_other_factory(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            pdf = add_asset(db, "source-pdf", order["contract_no"])
            excel = add_asset(db, "source-excel", order["contract_no"], kind="excel")
            photo = add_asset(db, "source-photo", order["contract_no"], kind="image")
            db.flush()
            db.get(CartonMarkAsset, "source-photo").photo_group_id = "CMP-scoped-photos"
            add_asset(db, "unbound", "")
            add_asset(db, "different-contract", order["contract_no"] + "-OTHER")
            add_asset(db, "other-factory", order["contract_no"], factory="huakang-a")
            db.commit()
        response = client.get(BASE, params=SCOPE)
        assert response.status_code == 200, response.text
        assert {row["id"] for row in response.json()} == {"source-pdf", "source-excel", "source-photo"}
        assert next(row for row in response.json() if row["id"] == "source-photo")["photo_group_id"] == "CMP-scoped-photos"
        for private in ("private actor", "private warning", "created_by", "warning", "candidates", "order_no", "customer_code"):
            assert private not in response.text
        assert response.json()[0]["orders"][0]["contract_no"] == order["contract_no"]
        assert client.get(BASE + "/source-excel/document", params=SCOPE).content == excel
        preview = client.get(BASE + "/source-pdf/document", params={**SCOPE, "preview": True})
        assert preview.content == pdf and preview.headers["content-disposition"].startswith("inline;")
        assert preview.headers["cache-control"] == "private, no-store"
        photo_preview = client.get(BASE + "/source-photo/document", params={**SCOPE, "preview": True})
        assert photo_preview.content == photo and photo_preview.headers["content-type"] == "image/png"
        assert photo_preview.headers["content-disposition"].startswith("inline;")
        assert photo_preview.headers["cache-control"] == "private, no-store"
        assert photo_preview.headers["x-content-type-options"] == "nosniff"
        assert client.get(BASE + "/source-photo/document", params=SCOPE).headers["content-disposition"].startswith("attachment;")
        for key in ("unbound", "different-contract", "other-factory", "unknown"):
            assert client.get(BASE + f"/{key}/document", params=SCOPE).status_code == 404
        assert client.get(BASE, params={"factory_id": "huakang-a"}).status_code == 403
        assert client.get("/api/carton-mark/assets", params=SCOPE).status_code == 403
        with SessionLocal() as db:
            db.get(CartonMarkAsset, "source-pdf").is_archived = True
            db.commit()
        assert client.get(BASE + "/source-pdf/document", params=SCOPE).status_code == 404
        with SessionLocal() as db:
            db.get(CartonOrder, order["id"]).status = "CANCELLED"
            db.commit()
        assert client.get(BASE, params=SCOPE).json() == []
        assert client.get(BASE + "/source-excel/document", params=SCOPE).status_code == 404
        assert client.get(BASE + "/source-photo/document", params=SCOPE).status_code == 404
        revoke_supplier_permission()
        assert client.get(BASE, params=SCOPE).status_code == 403
        assert client.get(BASE + "/source-excel/document", params=SCOPE).status_code == 403


def test_sharing_uses_issued_contract_and_never_expands_an_explicit_binding(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonOrder, CartonSupplier
        with SessionLocal() as db:
            add_asset(db, "issued", order["contract_no"])
            add_asset(db, "unissued", "UNISSUED-CONTRACT")
            original = db.get(CartonOrder, order["id"])
            original.contract_no = "UNISSUED-CONTRACT"
            original.item_no = "UNISSUED-ITEM"
            db.commit()
        rows = client.get(BASE, params=SCOPE).json()
        assert [row["id"] for row in rows] == ["issued"]
        assert rows[0]["orders"][0]["item_no"] == order["item_no"]
        assert client.get(BASE + "/unissued/document", params=SCOPE).status_code == 404
        with SessionLocal() as db:
            original = db.get(CartonOrder, order["id"])
            collision = CartonOrder(**{column.name: getattr(original, column.name)
                for column in CartonOrder.__table__.columns})
            collision.id = "OTHER-CUSTOMER-ORDER"
            collision.order_no = "OTHER-CUSTOMER-ORDER"
            collision.contract_no = order["contract_no"]
            collision.customer_code = "OTHER-CUSTOMER"
            collision.customer_name = "Other customer"
            collision.status = "CONFIRMED"
            db.add(collision)
            db.commit()
        assert client.get(BASE, params=SCOPE).json() == []
        assert client.get(BASE + "/issued/document", params=SCOPE).status_code == 404
        with SessionLocal() as db:
            asset = db.get(CartonMarkAsset, "issued")
            asset.bound_order_id = order["id"]
            asset.recognition_source = "manual_order"
            db.commit()
        rows = client.get(BASE, params=SCOPE).json()
        assert [row["id"] for row in rows] == ["issued"]
        assert [entry["id"] for entry in rows[0]["orders"]] == [order["id"]]
        with SessionLocal() as db:
            original = db.get(CartonOrder, order["id"])
            original.deleted_at = "2026-10-05"
            db.commit()
        assert client.get(BASE, params=SCOPE).json() == []
        assert client.get(BASE + "/issued/document", params=SCOPE).status_code == 404
        # A later order with the same contract cannot inherit a deleted explicit target.
        with SessionLocal() as db:
            original = db.get(CartonOrder, order["id"])
            original.deleted_at = None
            supplier = db.get(CartonSupplier, original.supplier_id)
            other = CartonSupplier(**{column.name: getattr(supplier, column.name)
                for column in CartonSupplier.__table__.columns})
            other.id = "OTHER-SUPPLIER"
            other.supplier_code = "OTHER-SUPPLIER"
            db.add(other)
            db.flush()
            original.supplier_id = other.id
            db.commit()
        assert client.get(BASE + "/issued/document", params=SCOPE).status_code in (403, 404)
