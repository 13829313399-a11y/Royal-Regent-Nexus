import importlib

from sqlalchemy import select

from test_molding_sample_api import login_as, make_client
from test_carton_mark_api import _seed_carton_mark_customer, _workbook_bytes
from test_carton_mark_assets import seed_order, upload


def modules():
    return (importlib.import_module("app.db"), importlib.import_module("app.models.carton_procurement"),
            importlib.import_module("app.models.carton_mark"))


def recognize(client, **values):
    return client.post("/api/carton-mark/customer-recognition", params={"factory_id": "huaxing"},
        json={"contract_number": "4500222793", "item": "100369", **values})


def test_recognition_matches_exact_order_identity_and_existing_managed_name(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module, carton, mark = modules()
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "match-buzz", customer="BUZZ")
            seed_order(db, carton, "different-item", customer="Other", item="OTHER")
            seed_order(db, carton, "different-factory", customer="Foreign", factory="huakang-a")
            cancelled = seed_order(db, carton, "cancelled", customer="Cancelled")
            cancelled.status = "CANCELLED"
            removed = seed_order(db, carton, "removed", customer="Removed")
            removed.deleted_at = "2026-10-07"
            _seed_carton_mark_customer(db, mark, customer_id="managed-buzz", name="Buzz")
            db.commit()
        login_as(client, "carton_warehouse")
        response = recognize(client)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "MATCHED" and result["customer_name"] == "Buzz"
        assert result["managed_customer_id"] == "managed-buzz"
        assert [o["id"] for o in result["orders"]] == ["match-buzz"]
        assert recognize(client, contract_number="45002227930").json()["status"] == "NO_MATCH"
        assert recognize(client, item="10036").json()["status"] == "NO_MATCH"
        assert recognize(client, po="not-the-po").json()["status"] == "NO_MATCH"
        assert client.post("/api/carton-mark/customer-recognition", params={"factory_id": "huakang-a"},
            json={"contract_number": "4500222793"}).status_code == 403


def test_distinct_customer_codes_with_same_name_require_explicit_order_and_do_not_write(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module, carton, mark = modules()
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "same-name-a", customer="BUZZ")
            second = seed_order(db, carton, "same-name-b", customer="BUZZ")
            second.customer_code = "SECOND-BUZZ"
            db.commit()
        login_as(client, "carton_warehouse")
        result = recognize(client).json()
        assert result["status"] == "AMBIGUOUS" and len(result["orders"]) == 2
        selected = recognize(client, order_id="same-name-a").json()
        assert selected["status"] == "MATCHED" and selected["customer_name"] == "BUZZ"
        assert selected["managed_customer_id"] is None
        assert recognize(client, order_id="outside-order").json()["status"] == "NO_MATCH"
        with db_module.SessionLocal() as db:
            assert list(db.scalars(select(mark.CartonMarkCustomer))) == []


def test_source_boundaries_conflicts_and_deleted_bound_order_do_not_broaden(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module, carton, mark = modules()
        login_as(client, "admin")
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "bound-order", customer="BUZZ")
            seed_order(db, carton, "other-customer", customer="Other")
        source = upload(client, [("4500222793.xlsx", _workbook_bytes())])[0]["asset"]
        binding = client.put(f"/api/carton-mark/assets/{source['id']}/binding", params={"factory_id": "huaxing"},
            json={"order_id": "bound-order", "contract_number": "4500222793", "revision": source["revision"]})
        assert binding.status_code == 200, binding.text
        assert recognize(client, excel_asset_id=source["id"]).json()["customer_name"] == "BUZZ"
        assert recognize(client, excel_asset_id=source["id"], order_id="other-customer").json()["status"] == "NO_MATCH"
        assert recognize(client, excel_asset_id=source["id"], contract_number="different-contract").json()["status"] == "CONFLICT"
        assert recognize(client, pdf_asset_id=source["id"]).status_code == 404
        with db_module.SessionLocal() as db:
            db.delete(db.get(carton.CartonOrder, "bound-order"))
            db.commit()
        assert recognize(client, excel_asset_id=source["id"]).json()["status"] == "NO_MATCH"
        assert recognize(client, excel_asset_id="missing-source").status_code == 404


def test_initialization_requires_confirmation_permission_and_revalidates_order_names(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module, carton, mark = modules()
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "init-buzz", customer="BUZZ")
            seed_order(db, carton, "init-zuru", customer="ZURU", contract="OTHER")
            seed_order(db, carton, "init-foreign", customer="Foreign", factory="huakang-a")
            _seed_carton_mark_customer(db, mark, customer_id="init-managed-zuru", name="zuru")
            db.commit()
        params = {"factory_id": "huaxing"}
        login_as(client, "carton_warehouse")
        assert client.get("/api/carton-mark/customers/initialization-candidates", params=params).status_code == 403
        assert client.post("/api/carton-mark/customers/initialize", params=params, json={"names": ["BUZZ"]}).status_code == 403
        login_as(client, "admin")
        preview = client.get("/api/carton-mark/customers/initialization-candidates", params=params)
        assert preview.status_code == 200, preview.text
        assert {c["name"] for c in preview.json()} == {"BUZZ", "zuru"}
        assert client.post("/api/carton-mark/customers/initialize", params=params, json={"names": ["BUZZ", "Foreign"]}).status_code == 409
        with db_module.SessionLocal() as db:
            assert [c.name for c in db.scalars(select(mark.CartonMarkCustomer))] == ["zuru"]
        result = client.post("/api/carton-mark/customers/initialize", params={"factory_id": " huaxing "}, json={"names": ["BUZZ", " buzz ", "ZURU"]})
        assert result.status_code == 200, result.text
        assert result.json() == {"created_names": ["BUZZ"], "existing_names": ["zuru"]}
        with db_module.SessionLocal() as db:
            assert {c.factory_id for c in db.scalars(select(mark.CartonMarkCustomer))} == {"huaxing"}
        again = client.post("/api/carton-mark/customers/initialize", params=params, json={"names": ["BUZZ"]})
        assert again.json() == {"created_names": [], "existing_names": ["BUZZ"]}
        with db_module.SessionLocal() as db:
            db.get(carton.CartonOrder, "init-buzz").status = "CANCELLED"
            db.commit()
        assert client.post("/api/carton-mark/customers/initialize", params=params, json={"names": ["BUZZ"]}).status_code == 409


def test_conflicting_customer_names_are_not_implicitly_merged_and_qc_is_read_only(monkeypatch):
    with make_client(monkeypatch) as client:
        db_module, carton, _ = modules()
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "variant-a", customer="BUZZ")
            variant = seed_order(db, carton, "variant-b", customer="Buzz Bee")
            variant.customer_code = "BUZZ"
            db.commit()
        login_as(client, "admin")
        candidates = client.get("/api/carton-mark/customers/initialization-candidates", params={"factory_id": "huaxing"}).json()
        assert len(candidates) == 2 and all(c["warning"] for c in candidates)
        assert client.post("/api/carton-mark/customers/initialize", params={"factory_id": "huaxing"}, json={"names": ["BUZZ"]}).status_code == 409
        login_as(client, "qc_inspector")
        assert recognize(client).status_code == 403
        assert client.post("/api/carton-mark/customer-recognition", params={"factory_id": "huakang-a"}, json={"contract_number": "4500222793"}).status_code == 403
        assert client.get("/api/carton-mark/customers/initialization-candidates", params={"factory_id": "huaxing"}).status_code == 403
