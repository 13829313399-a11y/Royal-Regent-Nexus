"""Name intake is independent of display names and scoped to the source factory."""
import json

import pytest
from sqlalchemy import select

from test_molding_sample_api import make_client, login_as
from test_carton_item_schedule import workbook, source_row

BASE = "/api/carton-procurement"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    monkeypatch.setenv("ONLINE_DOCUMENTS_ENABLED", "false")


def sync(client, factory="huaxing"):
    return client.post(BASE + "/customers/business-sync", params={"factory_id": factory})


def customers(client, factory="huaxing"):
    response = client.get(BASE + "/customers", params={"factory_id": factory, "include_inactive": True})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def upload(client, code="dickie", factory="huaxing"):
    return client.post(f"/api/customer-orders/{code}/warehouse-schedule",
        data={"factory_id": factory, "source_kind": "UPLOADED"},
        files={"schedule_file": ("source.xlsx", workbook([source_row()]))})


def fast_parser(monkeypatch):
    from app.services import customer_order_carton_schedule as handoff
    async def run(fn, *args, **kwargs):
        return fn(*args)
    monkeypatch.setattr(handoff, "run_order_job", run)


def test_name_only_exact_reuse_rename_delete_tombstone_and_factory(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        original = client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": "Dickie", "contact_name": "仓库原联系人"}).json()
        other = client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": "Dick"}).json()
        first = sync(client)
        assert first.status_code == 200 and first.json()["added"] > 0, first.text
        assert sync(client).json()["added"] == 0
        rows = customers(client)
        imported = next(r for r in rows if r["business_customer_code"] == "dickie")
        assert len([r for r in rows if r["customer_name"] == "Dickie"]) == 1
        assert imported["id"] == original["id"]
        assert imported["contact_name"] == "仓库原联系人"
        fresh = next(r for r in rows if r["business_customer_code"] == "buzzbee")
        assert all(fresh[field] == "" for field in ("contact_name", "contact_phone", "country_region", "note"))
        saved = client.patch(BASE + f"/customers/{imported['id']}", json={"factory_id": "huaxing",
            "expected_revision": imported["revision"], "customer_name": "Dickie", "note": "仓库自填"})
        assert saved.status_code == 200, saved.text
        renamed = client.patch(BASE + f"/customers/{imported['id']}", json={"factory_id": "huaxing",
            "expected_revision": saved.json()["revision"], "customer_name": "仓库迪奇"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["business_customer_name"] == "Dickie"
        changed_code = client.patch(BASE + f"/customers/{imported['id']}", json={"factory_id": "huaxing",
            "expected_revision": renamed.json()["revision"], "customer_code": "NEW"})
        assert changed_code.status_code == 409
        fast_parser(monkeypatch)
        handed = upload(client)
        assert handed.status_code == 200, handed.text
        batch = client.get(BASE + f"/imports/{handed.json()['batch_id']}", params={"factory_id": "huaxing"}).json()
        assert batch["parse_summary"]["schedule_customer"] == {"customer_code": imported["customer_code"], "customer_name": "仓库迪奇"}
        assert sync(client).json()["added"] == 0
        assert next(r for r in customers(client) if r["id"] == imported["id"])["customer_name"] == "仓库迪奇"
        assert client.delete(BASE + f"/customers/{imported['id']}", params={"factory_id": "huadeng"}).status_code == 404
        assert client.delete(BASE + f"/customers/{imported['id']}", params={"factory_id": "huaxing"}).status_code == 204
        assert sync(client).json()["added"] == 0
        assert not any(r["id"] == imported["id"] for r in customers(client))
        assert any(r["id"] == other["id"] for r in customers(client))
        assert upload(client).status_code == 422
        assert sync(client, "huadeng").status_code == 200
        assert not any(r["business_customer_code"] == "dickie" for r in customers(client, "huadeng"))
        from app.db import SessionLocal
        from app.services.carton_master import workspace
        from app.services.auth import build_auth_context
        from app.models.auth import AuthUser
        with SessionLocal() as db:
            actor = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == "admin")))
            assert all(r["kind"] != "BUSINESS_CUSTOMER" for r in workspace(db, "huaxing", actor)["records"])


def test_sales_handoff_creates_names_but_does_not_grant_warehouse_write(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        login_as(client, "huaxing_molding_a_sales")
        fast_parser(monkeypatch)
        assert sync(client).status_code == 403
        response = upload(client)
        assert response.status_code == 200, response.text
        assert upload(client, factory="huakang-a").status_code in (400, 403)
        login_as(client, "admin")
        rows = customers(client)
        assert len(rows) == 1 and rows[0]["business_customer_code"] == "dickie"
        assert client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["total"] == 0
        row = rows[0]
        assert client.patch(BASE + f"/customers/{row['id']}", json={"factory_id": "huaxing",
            "expected_revision": row["revision"], "status": "INACTIVE"}).status_code == 200
        assert upload(client).status_code == 422
        assert sync(client).status_code == 200
        assert next(r for r in customers(client) if r["id"] == row["id"])["status"] == "INACTIVE"


def test_exact_name_intake_preserves_inactive_ambiguous_and_other_factory_customers(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        inactive = client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": "dIcKiE"}).json()
        assert client.patch(BASE + f"/customers/{inactive['id']}", json={"factory_id": "huaxing",
            "expected_revision": inactive["revision"], "status": "INACTIVE"}).status_code == 200
        foreign = client.post(BASE + "/customers", json={"factory_id": "huadeng", "customer_name": "Dickie"}).json()
        duplicates = [client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": name}).json()
                      for name in ("旧客户一", "旧客户二")]
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonCustomer
        from app.services.carton_business_customers import catalog
        with SessionLocal() as db:
            # Rehearse pre-existing duplicate names without weakening freeform creation checks.
            for row in duplicates:
                db.get(CartonCustomer, row["id"]).customer_name = catalog("huaxing")["buzzbee"]
            db.commit()
        assert sync(client).status_code == 200
        rows = customers(client)
        reused = next(r for r in rows if r["business_customer_code"] == "dickie")
        assert reused["id"] == inactive["id"] and reused["status"] == "INACTIVE"
        assert reused["customer_name"] == "dIcKiE"
        separate = next(r for r in rows if r["business_customer_code"] == "buzzbee")
        assert separate["id"] not in {r["id"] for r in duplicates}
        assert all(any(r["id"] == old["id"] and not r["business_customer_code"] for r in rows) for old in duplicates)
        other_factory = customers(client, "huadeng")
        assert len(other_factory) == 1 and other_factory[0]["id"] == foreign["id"]
        assert not other_factory[0]["business_customer_code"]
        fast_parser(monkeypatch)
        assert upload(client).status_code == 422


@pytest.mark.parametrize("mode", ["catalog_new_first", "catalog_old_first", "single_handoff"])
def test_proven_old_handoff_reuses_original_customer_without_renaming(monkeypatch, mode):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        fast_parser(monkeypatch)
        response = upload(client, "buzzbee")
        assert response.status_code == 200, response.text
        old = next(r for r in customers(client) if r["business_customer_code"] == "buzzbee")
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        from app.models.carton_procurement import CartonCustomer
        with SessionLocal() as db:
            # Rehearse an old pre-binding database with successful source evidence.
            db.delete(db.scalar(select(CartonMasterRecord).where(CartonMasterRecord.kind == "BUSINESS_CUSTOMER")))
            db.get(CartonCustomer, old["id"]).customer_name = "Dickie"
            db.commit()
        from app.services import carton_business_customers as intake
        names = intake.catalog("huaxing")
        order = ("buzzbee", "dickie") if mode == "catalog_old_first" else ("dickie", "buzzbee")
        monkeypatch.setattr(intake, "catalog", lambda factory: {code: names[code] for code in order})
        if mode == "single_handoff":
            assert upload(client, "dickie").status_code == 200
        assert sync(client).status_code == 200
        rows = {r["business_customer_code"]: r for r in customers(client)}
        assert len(rows) == 2 and rows["buzzbee"]["id"] == old["id"]
        assert rows["buzzbee"]["customer_name"] == "Dickie"
        assert rows["dickie"]["id"] != old["id"]
        replay = upload(client, "buzzbee")
        assert replay.status_code == 200 and replay.json()["duplicate"], replay.text
        assert replay.json()["batch_id"] == response.json()["batch_id"]


def test_360_identity_survives_rename_for_manual_schedule_import(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        assert sync(client).status_code == 200
        for code, name, expected in [("360", "仓库自定义", "SHIP"), ("dickie", "360", "PRODUCT")]:
            row = next(r for r in customers(client) if r["business_customer_code"] == code)
            saved = client.patch(BASE + f"/customers/{row['id']}", json={"factory_id": "huaxing",
                "expected_revision": row["revision"], "customer_name": name})
            assert saved.status_code == 200, saved.text
            from app.db import SessionLocal
            from app.services import carton_procurement as carton
            from app.services.auth import build_auth_context
            from app.models.auth import AuthUser
            from fastapi import UploadFile
            from io import BytesIO
            with SessionLocal() as db:
                actor = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == "admin")))
                parsed = {"rows": [{"source_row": 2, "source_sheet": "ITEM", "template": "unified-item",
                    "contract_no": "TEST", "item_no": "PRODUCT", "shipping_item_no": "SHIP"}], "warnings": []}
                batch = carton.create_import_batch(db, "huaxing", "WEEKLY_SCHEDULE", UploadFile(filename=code + ".xlsx", file=BytesIO(b"test")),
                    b"test", actor, {"customer_code": row["customer_code"], "business_customer_code": "forged"}, parsed_source=parsed)
                assert batch.parse_summary["rows"][0]["item_no"] == expected
                from app.models.carton_procurement import CartonImportBatch
                profile = json.loads(db.get(CartonImportBatch, batch.id).import_profile)
                assert "business_customer_code" not in profile  # old manual-import identity
                replay = carton.create_import_batch(db, "huaxing", "WEEKLY_SCHEDULE", UploadFile(filename=code + ".xlsx", file=BytesIO(b"test")),
                    b"test", actor, {"customer_code": row["customer_code"]}, parsed_source=parsed)
                assert replay.duplicate and replay.id == batch.id


def test_legacy_manual_import_replay_and_revoked_catalog_session(monkeypatch):
    from uuid import uuid4
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        original = client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": "自建客户"}).json()
        content = workbook([source_row()])
        def manual():
            return client.post(BASE + "/weekly-imports", params={"factory_id": "huaxing"},
                data={"customer_code": original["customer_code"]}, files={"file": ("legacy.xlsx", content)})
        first = manual()
        assert first.status_code == 201, first.text
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        from app.models.carton_procurement import CartonImportBatch
        from app.models.auth import AuthSession
        from sqlalchemy import update
        with SessionLocal() as db:
            profile = json.loads(db.get(CartonImportBatch, first.json()["id"]).import_profile)
            assert "business_customer_code" not in profile
            # Upgrade: explicit historical binding is added, display name is retained.
            db.add(CartonMasterRecord(id="CMD-" + uuid4().hex, factory_id="huaxing", kind="BUSINESS_CUSTOMER",
                identity="legacy-link", code="dickie", customer_code=original["customer_code"],
                data_json=json.dumps({"customer_id": original["id"], "source_name": "Dickie"}),
                status="ACTIVE", maintained=1))
            db.commit()
        second = manual()
        assert second.status_code == 201 and second.json()["duplicate"], second.text
        assert second.json()["id"] == first.json()["id"]
        from app.services import carton_special_requests
        real_lock = carton_special_requests.locked_actor
        def revoke(db, actor, factory):
            result = real_lock(db, actor, factory)
            db.execute(update(AuthSession).values(status="revoked"))
            db.commit()
            return result
        monkeypatch.setattr(carton_special_requests, "locked_actor", revoke)
        assert sync(client).status_code == 401
        login_as(client, "admin")
        assert len(customers(client)) == 1
