"""Automatic handoff preserves warehouse demand and the source permission boundary."""
import asyncio
from io import BytesIO

import pytest
from openpyxl import Workbook

from test_molding_sample_api import make_client, login_as
from test_carton_item_schedule import workbook, source_row, _prepare_schedule_customer

URL = "/api/customer-orders/dickie/warehouse-schedule"
BASE = "/api/carton-procurement"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def upload(client, content, factory="huaxing", kind="UPLOADED"):
    return client.post(URL, data=dict(factory_id=factory, source_kind=kind),
        files={"schedule_file": ("business.xlsx", content)})


def test_real_upload_retry_change_and_existing_purchase_are_preserved(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        login_as(client, "admin")
        from test_carton_procurement_api import _order_payload, _submit_order
        created = client.post(BASE + "/orders", json=_order_payload())
        assert created.status_code == 201, created.text
        purchase = _submit_order(client, created.json())
        first = upload(client, workbook([source_row()]))
        assert first.status_code == 200, first.text
        assert not first.json()["duplicate"]
        # Reuse the exact uploaded bytes; Excel ZIP timestamps can differ.
        content = workbook([source_row(qty=400)])
        changed = upload(client, content, kind="GENERATED")
        assert changed.status_code == 200, changed.text
        retry = upload(client, content, kind="GENERATED")
        assert retry.status_code == 200 and retry.json()["duplicate"], retry.text
        assert retry.json()["batch_id"] == changed.json()["batch_id"]
        from app.services import carton_procurement as carton
        monkeypatch.setattr(carton, "business_today", lambda: "2026-10-29")
        next_day = upload(client, content, kind="GENERATED")
        assert next_day.status_code == 200 and next_day.json()["batch_id"] == changed.json()["batch_id"]
        stale = upload(client, workbook([source_row()]))
        assert stale.status_code == 409, stale.text
        batch = client.get(BASE + f"/imports/{changed.json()['batch_id']}", params={"factory_id": "huaxing"}).json()
        assert batch["parse_summary"]["business_source"]["source_kind"] == "GENERATED"
        assert batch["parse_summary"]["schedule_customer"]["customer_code"] == "DICKIE"
        assert batch["parse_summary"]["rows"][0]["schedule_change"] not in {"NEW", "UNCHANGED"}
        orders = client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()
        assert orders["total"] == 1
        assert orders["items"][0]["id"] == purchase["id"]
        from app.services import customer_order_carton_schedule as handoff
        monkeypatch.setattr(handoff, "order_request_started_at", lambda: "2099-01-02T00:00:00.000000+00:00")
        later_duplicate = upload(client, content, kind="GENERATED")
        assert later_duplicate.status_code == 200 and later_duplicate.json()["duplicate"]
        monkeypatch.setattr(handoff, "order_request_started_at", lambda: "2099-01-01T00:00:00.000000+00:00")
        older_slow_request = upload(client, workbook([source_row(qty=500)]), kind="GENERATED")
        assert older_slow_request.status_code == 409, older_slow_request.text


def test_sales_only_permission_can_sync_without_procurement_write(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        login_as(client, "admin")
        profile = login_as(client, "huaxing_molding_a_sales")
        assert "carton_procurement:import" not in profile["permissions"]
        assert "customer_order:export" in profile["permissions"]
        response = upload(client, workbook([source_row()]))
        assert response.status_code == 200, response.text
        assert client.post(BASE + "/weekly-imports", params={"factory_id": "huaxing"},
            data={"customer_code": "DICKIE"}, files={"file": ("warehouse.xlsx", workbook([source_row()]))}).status_code == 403
        assert upload(client, workbook([source_row()]), factory="huakang-a").status_code in {400, 403}
        login_as(client, "warehouse_keeper")
        assert upload(client, workbook([source_row()])).status_code == 403


def test_missing_conflicting_and_foreign_customer_never_guessed(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        assert upload(client, workbook([source_row()])).status_code == 422
        _prepare_schedule_customer(client)
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonCustomer
        from sqlalchemy import select
        with SessionLocal() as db:
            db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id == "huaxing", CartonCustomer.customer_code == "DICKIE")).customer_name = "Code owner"
            db.commit()
        other = client.post(BASE + "/customers", json=dict(factory_id="huaxing", customer_code="OTHER", customer_name="Dickie"))
        assert other.status_code == 201, other.text
        assert upload(client, workbook([source_row()])).status_code == 422
        assert client.get(BASE + "/imports", params={"factory_id": "huaxing"}).json()["total"] == 0


def test_revoked_original_session_after_parsing_writes_nothing(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        login_as(client, "admin")
        from app.services import customer_order_carton_schedule as handoff
        real = handoff.run_order_job
        async def revoke(*args, **kwargs):
            parsed = await real(*args, **kwargs)
            from app.db import SessionLocal
            from app.models.auth import AuthSession
            from sqlalchemy import update
            with SessionLocal() as db:
                db.execute(update(AuthSession).values(status="revoked")); db.commit()
            return parsed
        monkeypatch.setattr(handoff, "run_order_job", revoke)
        assert upload(client, workbook([source_row()])).status_code == 401
        login_as(client, "admin")
        assert client.get(BASE + "/imports", params={"factory_id": "huaxing"}).json()["total"] == 0


def test_declared_coverage_remains_incremental_and_absence_does_not_cancel(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        login_as(client, "admin")
        baseline = client.post(BASE + "/weekly-imports", params={"factory_id": "huaxing"},
            data=dict(customer_code="DICKIE", scope_mode="FULL", as_of_date="2026-07-01",
                coverage_start="2026-09-01", coverage_end="2026-09-30", full_scope_confirmed="true"),
            files={"file": ("full.xlsx", workbook([source_row(contract="A"), source_row(contract="B")]))})
        assert baseline.status_code == 201, baseline.text
        result = upload(client, workbook([source_row(contract="A")]))
        assert result.status_code == 200, result.text
        batch = client.get(BASE + f"/imports/{result.json()['batch_id']}", params={"factory_id": "huaxing"}).json()
        scope = batch["parse_summary"]["schedule_coverage"]
        assert scope["scope_mode"] == "INCREMENTAL" and not scope["missing_rows"]


def test_isolated_parser_supports_encrypted_output_and_rejects_invalid_sources():
    from app.services.customer_order_carton_schedule import parse_business_schedule
    from app.services.customer_order_buzzbee import _encrypt_schedule
    from app.services.customer_order_jobs import run_order_job
    parsed = asyncio.run(run_order_job(parse_business_schedule, "encrypted.xlsx", _encrypt_schedule(workbook([source_row()]))))
    assert parsed["rows"][0]["contract_no"] == "53135"
    stream = BytesIO(); book = Workbook(); book.save(stream)
    with pytest.raises(Exception):
        asyncio.run(run_order_job(parse_business_schedule, "empty.xlsx", stream.getvalue()))


def test_normal_preview_and_export_await_warehouse_handoff(monkeypatch):
    from urllib.parse import unquote
    import json
    from test_customer_order_goliath import po, template
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        source = template()
        files = [("po_files", ("order.pdf", po())), ("schedule_file", ("schedule.xlsx", source))]
        data = dict(factory_id="huadeng", received_date="2026-09-07")
        missing = client.post("/api/customer-orders/goliath/preview-batch", data=data, files=files)
        assert missing.status_code == 200, missing.text
        assert missing.json()["warehouse_sync"]["status"] == "ERROR"
        customer = client.post(BASE + "/customers", json=dict(factory_id="huadeng", customer_code="GOLIATH", customer_name="Goliath"))
        assert customer.status_code == 201, customer.text
        preview = client.post("/api/customer-orders/goliath/preview-batch", data=data, files=files)
        assert preview.status_code == 200, preview.text
        result = preview.json()
        assert result["warehouse_sync"]["status"] == "SUCCESS", result["warehouse_sync"]
        # The success response is evidence the handoff has finished already.
        existing = client.get(BASE + f"/imports/{result['warehouse_sync']['batch_id']}", params={"factory_id": "huadeng"})
        assert existing.status_code == 200
        output = client.post("/api/customer-orders/goliath/export-batch", data={**data, "confirmed": "true",
            "preview_fingerprint": result["preview_fingerprint"]}, files=files)
        assert output.status_code == 200, output.text[:300] if output.status_code != 200 else ""
        sync = json.loads(unquote(output.headers["x-warehouse-sync"]))
        assert sync["status"] == "SUCCESS", sync
        latest = client.get(BASE + f"/imports/{sync['batch_id']}", params={"factory_id": "huadeng"}).json()
        assert any(row["contract_no"] == "T_10130-PHK26_00694" for row in latest["parse_summary"]["rows"])
        from app.services.customer_order_carton_schedule import parse_business_schedule
        assert all(row["contract_no"] != "T_10130-PHK26_00694" for row in parse_business_schedule("source.xlsx", source)["rows"])
        assert client.get(BASE + "/orders", params={"factory_id": "huadeng"}).json()["total"] == 0
        from app.db import Base, engine
        # Rehearse against isolated ledger tables, never upgrade the local business DB.
        Base.metadata.create_all(bind=engine, tables=[table for name, table in Base.metadata.tables.items() if name.startswith("order_ledger_")])
        saved = client.post("/api/customer-order-ledger/imports/goliath", data={**data, "confirmed": "true",
            "preview_fingerprint": result["preview_fingerprint"]}, files=files)
        assert saved.status_code == 200, saved.text
        assert saved.json()["warehouse_sync"]["status"] == "SUCCESS", saved.json()["warehouse_sync"]
        assert saved.json()["warehouse_sync"]["duplicate"]
