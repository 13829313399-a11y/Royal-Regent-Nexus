import importlib

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_molding_sample_api import login_as, make_client
from test_carton_mark_api import _workbook_bytes, _pdf_bytes, _seed_carton_mark_customer
from test_carton_mark_library_service import _check_result


def seed_order(db, model, order_id, contract="4500222793", factory="huaxing", customer="ZURU", item="100369"):
    order = model.CartonOrder(id=order_id, factory_id=factory, order_no=order_id,
        customer_code=customer, customer_name=customer, supplier_id="test-supplier",
        supplier_name_snapshot="测试供应商", contract_no=contract, item_no=item,
        quantity_basis="EXPLICIT", product_order_quantity=None, order_date="2026-10-05",
        due_date="2026-10-10", status="DRAFT", created_by="seed", created_by_name="seed",
        updated_by="seed", updated_by_name="seed", created_at="2026-10-05", updated_at="2026-10-05")
    db.add(order)
    db.commit()
    return order


def upload(client, files):
    response = client.post("/api/carton-mark/assets/batch", data={"factory_id": "huaxing"},
        files=[("files", file) for file in files])
    assert response.status_code == 200, response.text
    return response.json()


def test_batch_partial_failure_dedup_contract_reuse_future_order_and_factory_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        db_module = importlib.import_module("app.db")
        carton = importlib.import_module("app.models.carton_procurement")
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "asset-order-a")
            seed_order(db, carton, "asset-order-b", item="100370")
            seed_order(db, carton, "asset-order-other-factory", factory="huakang-a")
        files = [("4500222793_Shipping Mark.xlsx", _workbook_bytes("GTIN: 10193052021172")),
                 ("notes.xlsx", _workbook_bytes("No contract")), ("broken.pdf", b"invalid")]
        result = upload(client, files)
        assert [r["status"] for r in result] == ["created", "created", "failed"]
        asset = result[0]["asset"]
        assert asset["contract_number"] == "4500222793"
        assert {o["id"] for o in asset["orders"]} == {"asset-order-a", "asset-order-b"}
        assert result[1]["asset"]["binding_status"] == "UNBOUND"
        repeat = upload(client, files[:1])[0]
        assert repeat["status"] == "created" and repeat["asset"]["id"] != asset["id"]
        assert client.get(f"/api/carton-mark/assets/{asset['id']}/document", params={"factory_id": "huakang-a"}).status_code == 404
        assert client.get("/api/carton-mark/assets", params={"factory_id": "huaxing", "order_id": "asset-order-other-factory"}).status_code == 404
        # Files uploaded before an order exist start linking when that contract arrives.
        future = upload(client, [("SC-NEW123.pdf", _pdf_bytes())])[0]["asset"]
        assert future["binding_status"] == "NO_ORDER"
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "asset-future", contract="SC-NEW123")
        linked = client.get("/api/carton-mark/assets", params={"factory_id": "huaxing", "order_id": "asset-future"}).json()
        assert [r["id"] for r in linked] == [future["id"]]


def test_conflicts_manual_binding_cas_archive_and_order_delete_preserve_original(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        db_module = importlib.import_module("app.db")
        carton = importlib.import_module("app.models.carton_procurement")
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "asset-zuru")
            seed_order(db, carton, "asset-dick", customer="Dick")
            seed_order(db, carton, "asset-foreign", factory="huakang-a")
        content = _workbook_bytes("Item: 100369")
        asset = upload(client, [("4500222793.xlsx", content)])[0]["asset"]
        assert asset["binding_status"] == "AMBIGUOUS"
        assert client.get("/api/carton-mark/assets", params={"factory_id": "huaxing", "order_id": "asset-zuru"}).json() == []
        url = f"/api/carton-mark/assets/{asset['id']}/binding?factory_id=huaxing"
        payload = {"contract_number": "4500222793", "order_id": "asset-foreign", "revision": 1}
        assert client.put(url, json=payload).status_code == 404
        payload["order_id"] = "asset-zuru"
        response = client.put(url, json=payload)
        assert response.status_code == 200, response.text
        assert [o["id"] for o in response.json()["orders"]] == ["asset-zuru"]
        assert client.put(url, json=payload).status_code == 409
        # DB-enforced delete action empties only the order reference. It never
        # broadens the previous explicit selection to the other customer's order.
        with db_module.SessionLocal() as db:
            db.delete(db.get(carton.CartonOrder, "asset-zuru"))
            db.commit()
        updated = next(a for a in client.get("/api/carton-mark/assets?factory_id=huaxing").json() if a["id"] == asset["id"])
        assert updated["bound_order_id"] is None and updated["binding_status"] == "NO_ORDER"
        document_url = f"/api/carton-mark/assets/{asset['id']}/document?factory_id=huaxing"
        assert client.get(document_url).content == content
        assert client.delete(f"/api/carton-mark/assets/{asset['id']}?factory_id=huaxing&revision=1").status_code == 409
        assert client.delete(f"/api/carton-mark/assets/{asset['id']}?factory_id=huaxing&revision=2").status_code == 204
        assert client.get(document_url).status_code == 404
        restored = upload(client, [("4500222793.xlsx", content)])[0]
        assert restored["status"] == "created" and restored["asset"]["id"] != asset["id"]


def test_recognition_does_not_use_partial_identifiers_or_choose_conflicting_contracts(monkeypatch):
    with make_client(monkeypatch):
        service = importlib.import_module("app.services.carton_mark_assets")
        evidence = service.recognize_asset("notes.xlsx", _workbook_bytes("45002227930"), ["4500222793"])
        assert evidence["contract_number"] == "" and not evidence["candidates"]
        evidence = service.recognize_asset("4500222793_Shipping Mark.xlsx", _workbook_bytes("CONTRACT NO: SC-OTHER123"), [])
        assert evidence["contract_number"] == ""
        assert set(evidence["candidates"]) == {"4500222793", "SC-OTHER123"}


def test_reuse_stored_pair_runs_original_check_and_keeps_qc_gate(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        db_module = importlib.import_module("app.db")
        model = importlib.import_module("app.models.carton_mark")
        schema = importlib.import_module("app.schemas.carton_mark")
        api = importlib.import_module("app.api.carton_mark")
        with db_module.SessionLocal() as db:
            _seed_carton_mark_customer(db, model, customer_id="asset-customer")
            db.commit()
        excel, pdf = _workbook_bytes(), _pdf_bytes()
        result = upload(client, [("4500222793.xlsx", excel), ("4500222793.pdf", pdf)])
        called = []
        def check(**values):
            called.append(values)
            result = _check_result(schema, "需复核")
            return result.model_copy(update={"excel_file_name": values["excel_file_name"], "pdf_file_name": values["pdf_file_name"]})
        monkeypatch.setattr(api, "build_carton_mark_document_check", check)
        payload = {"factory_id": "huaxing", "customer_name": "客人 A", "item": "100369", "contract_number": "4500222793",
                   "excel_asset_id": result[0]["asset"]["id"], "pdf_asset_id": result[1]["asset"]["id"]}
        response = client.post("/api/carton-mark/templates", data=payload)
        assert response.status_code == 201, response.text
        assert not response.json()["qc_ready"] and response.json()["check_status"] == "需复核"
        assert called[0]["excel_bytes"] == excel and called[0]["pdf_bytes"] == pdf
        payload["factory_id"] = "huakang-a"
        assert client.post("/api/carton-mark/templates", data=payload).status_code == 404
        auth = importlib.import_module("app.services.auth")
        write_only = auth.AuthContext(id="asset-write-only", username="asset-write-only", display_name="仅上传",
            roles=("纸箱仓管",), role_codes=("carton_warehouse_keeper",),
            permissions=frozenset({"carton_mark:template_upload"}), factory_scopes=("huaxing",), department_scopes=("pmc-warehouse",))
        client.app.dependency_overrides[auth.get_current_user] = lambda: write_only
        library = importlib.import_module("app.services.carton_mark_library")
        monkeypatch.setattr(library, "has_permission_in_scope",
            lambda _user, permission, *_args: permission == "carton_mark:template_upload")
        payload["factory_id"] = "huaxing"
        assert client.post("/api/carton-mark/templates", data=payload).status_code == 403
        assert client.get(f"/api/carton-mark/assets/{result[0]['asset']['id']}/document?factory_id=huaxing").status_code == 403
        local_payload = {key: value for key, value in payload.items() if not key.endswith("asset_id")}
        local = client.post("/api/carton-mark/templates", data=local_payload,
            files={"excel_contract": ("new.xlsx", _workbook_bytes("Changed source")), "print_pdf": ("new.pdf", pdf)})
        assert local.status_code == 201, local.text


def test_raw_repository_permissions_and_stale_copy_never_restore_original(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        content = _workbook_bytes()
        asset = upload(client, [("4500222793.xlsx", content)])[0]["asset"]
        service = importlib.import_module("app.services.carton_mark_assets")
        model = importlib.import_module("app.models.carton_mark")
        db_module = importlib.import_module("app.db")
        auth = importlib.import_module("app.services.auth")
        user = auth.AuthContext(id="asset-test", username="asset-test", display_name="仓管",
            roles=("纸箱仓管",), role_codes=("carton_warehouse_keeper",),
            permissions=frozenset({"carton_mark:read"}), factory_scopes=("huaxing",), department_scopes=("pmc-warehouse",))
        client.app.dependency_overrides[auth.get_current_user] = lambda: user
        assert client.get("/api/carton-mark/assets?factory_id=huakang-a").status_code == 403
        assert client.post("/api/carton-mark/assets/batch", data={"factory_id": "huaxing"}, files=[("files", ("a.xlsx", content))]).status_code == 403
        client.app.dependency_overrides.clear()
        with db_module.SessionLocal() as first, db_module.SessionLocal() as stale:
            service.archive_asset(first, user, "huaxing", asset["id"], 1)
            cached = stale.scalar(select(model.CartonMarkAsset).where(model.CartonMarkAsset.id == asset["id"]))
            stale.commit()  # Retain the stale identity map, release the read transaction.
            recognition = service.recognize_asset("4500222793.xlsx", content, [])
            first_copy, first_status = service.save_asset(first, user, "huaxing", content, recognition)
            assert first_status == "created" and first_copy.id != asset["id"]
            assert cached.revision == 2
            stale_copy, stale_status = service.save_asset(stale, user, "huaxing", content, recognition)
            assert stale_status == "created" and stale_copy.id not in {asset["id"], first_copy.id}
            first.expire_all()
            original = first.get(model.CartonMarkAsset, asset["id"])
            assert original.revision == 2 and original.is_archived
