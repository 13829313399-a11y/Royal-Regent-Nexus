"""Synthetic UV API acceptance; optional UV_TEST_DATABASE_URL is isolated PG only."""
import os
import importlib.util
import sys
import types
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite://")
from app.api import uv_printing as api
from app.api import uv_handover as handover_api
from app.models import uv_printing as m
from app.models import uv_finance, uv_ingest  # noqa: F401: complete UV FK graph
from app.services import uv_printing as s
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
from app.services.permission_codes import UV_PRINTING_PERMISSION_CODES


def user_with(*permissions, factory="huakang-a", department="production"):
    codes = frozenset("uv_printing:" + p for p in permissions)
    grant = AuthGrantContext(role_id="test", role_name="Synthetic", factory_id=factory, department=department, permissions=codes)
    return AuthContext(id="uv-test-user", username="uv-test", display_name="Synthetic UV", roles=("test",), role_codes=("test",), permissions=codes, factory_scopes=(factory,), department_scopes=(department,), grants=(grant,), active_permission_codes=frozenset(UV_PRINTING_PERMISSION_CODES))


@pytest.fixture
def client(monkeypatch, tmp_path):
    url = os.environ.get("UV_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'uv-test.db'}")
    if not url.startswith("sqlite:"):
        assert "127.0.0.1:55432/rr_uv_core" in url, "Only the explicitly isolated UV test database is allowed"
    engine = create_engine(url)
    tables = [t for t in m.Base.metadata.sorted_tables if t.name.startswith("uv_")]
    m.Base.metadata.drop_all(engine, tables=tables)
    m.Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(api.settings, "uv_printing_enabled", True)
    monkeypatch.setattr(api.settings, "authz_mode", "enforce")
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(handover_api.router)
    auth = {"user": user_with(*(p.split(":")[1] for p in UV_PRINTING_PERMISSION_CODES))}
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[api.get_db] = db
    app.dependency_overrides[get_current_user] = lambda: auth["user"]
    with TestClient(app) as c:
        c.uv_engine, c.uv_auth = engine, auth
        yield c
    engine.dispose()


def post(c, path, payload, expected=200, operation=None):
    body = {"factory_id": "huakang-a", "operation_id": operation or uuid4().hex, "expected_version": 0, **payload}
    response = c.post("/api/uv-printing/" + path, json=body)
    assert response.status_code == expected, response.text
    return response.json().get("data", response.json())


def get(c, path, **scope):
    response = c.get("/api/uv-printing/" + path, params=dict(factory_id="huakang-a", **scope))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def masters(c, workers=3):
    machine = post(c, "machines", dict(code="0001", name="Synthetic UV"))["entity"]
    product = post(c, "products", dict(product_no="0000123", name="Synthetic product"))["entity"]
    process = post(c, f"products/{product['id']}/process-versions", dict(product_id=product["id"], version_label="v1", effective_from="2026-01-01", width_cm="2", length_cm="3", pieces_per_board=20))["entity"]
    template = post(c, "shift-templates", dict(label="Day", shift="day", start_local="07:40", end_local="21:00", effective_from="2026-01-01"))["entity"]
    team = [post(c, "workers", dict(employee_no=f"00{i}", display_name=f"Worker {i}"))["entity"] for i in range(workers)]
    return dict(machine_id=machine["id"], product_id=product["id"], process_version_id=process["id"], shift_template_version_id=template["id"], worker_ids=[w["id"] for w in team])


def rate(c, refs, kind, price, **more):
    return post(c, "rate-versions", {"rate_kind": kind, "product_id": refs["product_id"], "currency": "HKD", "unit_price": price, "effective_from": "2026-01-01", **more})["entity"]


def report(c, refs, good=100, defective=0, pending=0, day="2026-09-13", **more):
    payload = {**refs, "business_date": day, "shift": "day", "reported_qty": good+defective+pending, "good_qty": good, "defective_qty": defective, "pending_qty": pending, "semi_finished_qty": 0, "notes": "Synthetic", "source_allocations": [], "evidence_job_ids": [], **more}
    result = post(c, "production-reports", payload)["entity"]
    return post(c, f"production-reports/{result['id']}/confirm", dict(report_id=result["id"], expected_version=result["version"]))["entity"]


def test_real_vertical_chain_and_exact_wage_remainder(client):
    refs = masters(client)
    rate(client, refs, "commercial", "1")
    rate(client, refs, "piece_wage", "0.01")
    row = report(client, refs)
    assert row["commercial"]["output_value"] == {"currency": "HKD", "amount": "100.00"}
    assert row["payroll"]["amount"]["amount"] == "1.00"
    assert [v["amount"]["amount"] for v in row["worker_shares"]] == ["0.34", "0.33", "0.33"]
    assert get(client, "payroll/preview")["batch_total"]["amount"] == "1.00"
    assert get(client, "summary")["counts"]["good_qty"] == 100
    assert get(client, "reports/daily-projection")["items"][0]["good_qty"] == 100
    assert get(client, "reports/monthly")["months"][0]["good_qty"] == 100
    assert row["product_no"] == "0000123"


def test_zero_distinct_missing_and_immutable_price_snapshot(client):
    refs = masters(client)
    initial = rate(client, refs, "commercial", "0")
    row = report(client, refs)
    assert row["commercial"]["pricing_state"] == "priced"
    assert row["commercial"]["output_value"]["amount"] == "0.00"
    assert row["payroll"]["amount"] is None
    updated = post(client, "rate-versions/"+initial["id"], dict(id=initial["id"], expected_version=initial["version"], rate_kind="commercial", product_id=refs["product_id"], unit_price="2", currency="HKD", effective_from="2026-09-14"))["entity"]
    assert updated["id"] != initial["id"]
    assert get(client, "production-reports/"+row["id"])["commercial"]["output_value"]["amount"] == "0.00"
    assert report(client, refs, day="2026-09-14")["commercial"]["output_value"]["amount"] == "200.00"


def test_operation_replay_conflict_and_stale_version(client):
    payload = dict(product_no="0005", name="Original")
    first = post(client, "products", payload, operation="repeat-1")
    assert post(client, "products", payload, operation="repeat-1")["replayed"] is True
    post(client, "products", {**payload, "name": "Changed"}, operation="repeat-1", expected=409)
    assert get(client, "products")["total"] == 1
    post(client, "products/"+first["entity"]["id"], {**payload, "id": first["entity"]["id"], "expected_version": 0}, expected=409)


def test_concurrent_identical_command_creates_once(client):
    def send(_):
        return post(client, "products", dict(product_no="concurrent",name="One effect"),operation="same-command")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(send, range(10)))
    assert len({r["entity"]["id"] for r in results}) == 1
    assert sum(not r["replayed"] for r in results) == 1
    assert get(client,"products")["total"] == 1


def test_quality_revision_and_void_count_only_effective(client):
    refs = masters(client)
    rate(client, refs, "commercial", "1")
    rate(client, refs, "piece_wage", "0.2")
    old = report(client, refs, good=90, pending=10)
    revised = post(client, f"production-reports/{old['id']}/quality", dict(report_id=old["id"], expected_version=old["version"], quality=dict(reported_qty=100, good_qty=95, defective_qty=5, pending_qty=0, semi_finished_qty=0), reason="Quality recheck"))["entity"]
    assert revised["status"] == "corrected" and revised["replaces_report_id"] == old["id"]
    assert get(client, "summary")["counts"]["good_qty"] == 95
    assert get(client, "payroll/preview")["batch_total"]["amount"] == "19.00"
    assert get(client, "production-reports/"+old["id"])["good_qty"] == 90
    post(client, f"production-reports/{revised['id']}/void", dict(report_id=revised["id"], expected_version=revised["version"], reason="Cancelled"))
    assert get(client, "summary")["counts"]["good_qty"] == 0
    assert get(client, "production-reports")["total"] == 2


def test_permissions_factory_department_sensitive_fields_and_disabled(client, monkeypatch):
    refs = masters(client)
    rate(client, refs, "commercial", "1")
    rate(client, refs, "piece_wage", "0.2")
    row = report(client, refs)
    assert client.get("/api/uv-printing/summary").status_code == 422
    for factory in ("group", "huaxing", "huakang-b"):
        assert client.get("/api/uv-printing/summary", params={"factory_id": factory}).status_code == 403
    client.uv_auth["user"] = user_with("read")
    redacted = get(client, "production-reports")["items"][0]
    assert not {"commercial", "payroll", "worker_shares"} & redacted.keys()
    assert "commercial" not in get(client, "summary")
    assert "payroll_amount" not in get(client, "reports/daily-projection")["items"][0]
    assert client.get("/api/uv-printing/payroll/preview", params={"factory_id":"huakang-a"}).status_code == 403
    post(client, "products", dict(product_no="deny", name="No"), expected=403)
    client.uv_auth["user"] = user_with("read", department="sales")
    assert client.get("/api/uv-printing/summary", params={"factory_id":"huakang-a"}).status_code == 403
    denied = replace(user_with("read"), overrides=(AuthOverrideContext(id="deny", permission_code="uv_printing:read", effect="deny", factory_id="huakang-a", department="production"),))
    client.uv_auth["user"] = denied
    monkeypatch.setattr(api.settings, "authz_mode", "legacy")
    assert client.get("/api/uv-printing/summary", params={"factory_id":"huakang-a"}).status_code == 403
    client.uv_auth["user"] = user_with("read")
    monkeypatch.setattr(api.settings, "uv_printing_enabled", False)
    assert client.get("/api/uv-printing/summary", params={"factory_id":"huakang-a"}).status_code == 503


def test_validation_no_partial_records_and_rates_do_not_cross_kind(client):
    refs = masters(client)
    rate(client, refs, "commercial", "1")
    rate(client, refs, "commercial", "3", machine_id=refs["machine_id"])
    row = report(client, refs)
    assert row["commercial"]["output_value"]["amount"] == "300.00" and row["payroll"]["amount"] is None
    invalid = dict(**refs, business_date="2026-09-13", shift="day", reported_qty=10, good_qty=11, defective_qty=0, pending_qty=0, semi_finished_qty=0)
    post(client, "production-reports", invalid, expected=422)
    post(client, "production-reports", {**invalid,"reported_qty":11.5}, expected=422)
    assert get(client, "production-reports")["total"] == 1
    post(client, "rate-versions", dict(rate_kind="commercial", product_id=refs["product_id"], currency="HKD", unit_price="NaN", effective_from="2026-01-01"), expected=422)


def test_full_filtered_monthly_ratio_not_page_or_average(client):
    refs = masters(client, workers=0)
    report(client, refs, good=90, defective=10, day="2026-09-01")
    report(client, refs, good=1, defective=9, day="2026-09-02")
    assert get(client, "production-reports",page_size=1)["total"] == 2
    assert get(client, "summary",page_size=1)["counts"]["good_qty"] == 91
    assert Decimal(get(client, "reports/monthly",page_size=1)["months"][0]["yield_rate"]) == Decimal(91)/110
    assert get(client, "summary", business_date="2026-09-01")["counts"]["good_qty"] == 90


def test_cross_factory_object_reference_rejected(client):
    refs = masters(client)
    with Session(client.uv_engine) as db:
        other = m.UvProduct(factory_id="huaxing", product_no="different",name="Foreign")
        db.add(other)
        db.commit()
        other_id = other.id
    post(client, f"products/{other_id}/process-versions", dict(product_id=other_id, version_label="x", effective_from="2026-01-01"), expected=404)


def test_source_allocation_conservation_and_atomic_replay(client):
    refs = masters(client)
    with Session(client.uv_engine) as db:
        job = m.UvJob(factory_id="huakang-a", machine_id=refs["machine_id"], product_id=refs["product_id"], process_version_id=refs["process_version_id"],source_job_id="j1", source_event_id="e1", connector_id="test", generation="1", raw_task_name="Job", state="completed", raw_count=100, raw_unit="piece", suggested_piece_qty=100)
        db.add(job); db.commit(); job_id = job.id
    first = report(client, refs, good=60,source_allocations=[dict(job_id=job_id,piece_qty=60,job_version=1)])
    jobs = get(client,"jobs")["items"]
    assert jobs[0]["available_piece_qty"] == 40
    payload = dict(**refs,business_date="2026-09-13",shift="day",reported_qty=50,good_qty=50,defective_qty=0,pending_qty=0,semi_finished_qty=0,source_allocations=[dict(job_id=job_id,piece_qty=50,job_version=jobs[0]["version"])])
    post(client,"production-reports",payload,expected=422)
    assert get(client,"production-reports")["total"] == 1
    assert get(client,"jobs")["items"][0]["available_piece_qty"] == 40
    correction = {**payload, "factory_id": "huakang-a", "operation_id": uuid4().hex, "expected_version": 0, "reported_qty": 55,"good_qty":55,"source_allocations":[dict(job_id=job_id,piece_qty=55,job_version=jobs[0]["version"])]}
    revised = post(client,f"production-reports/{first['id']}/corrections",dict(report_id=first["id"],expected_version=first["version"],reason="Correct source quantity",correction=correction))["entity"]
    assert revised["good_qty"] == 55 and get(client,"jobs")["items"][0]["available_piece_qty"] == 45
    first = revised
    post(client,f"production-reports/{first['id']}/void",dict(report_id=first["id"],expected_version=first["version"],reason="Cancel"))
    assert get(client,"jobs")["items"][0]["available_piece_qty"] == 100


def test_rate_currency_ambiguity_and_replay_does_not_leak(client):
    refs = masters(client)
    rate(client, refs, "commercial", "1")
    rate(client, refs, "commercial", "2",currency="CNY")
    assert report(client, refs)["commercial"]["output_value"] is None
    payload = dict(product_no="safe", name="Safe")
    post(client,"products",payload,operation="master-write")
    client.uv_auth["user"] = user_with("read", "cost_write")
    result = post(client,"rate-versions",dict(rate_kind="commercial",unit_price="12.3",currency="HKD",effective_from="2026-01-01"),operation="sensitive-rate")
    assert "unit_price" not in result["entity"] and "currency" not in result["entity"]
    result = post(client,"rate-versions",dict(rate_kind="commercial",unit_price="12.3",currency="HKD",effective_from="2026-01-01"),operation="sensitive-rate")
    assert result["replayed"] and "unit_price" not in result["entity"]


def test_assignments_versions_and_worker_identity_snapshot(client):
    refs=masters(client)
    assignment=post(client,"shift-assignments",dict(business_date="2026-09-13",shift="day",machine_id=refs["machine_id"],worker_ids=refs["worker_ids"]))["entity"]
    assert len(assignment)==3
    post(client,"shift-assignments",dict(business_date="2026-09-13",shift="day",machine_id=refs["machine_id"],worker_ids=[],expected_version=0),expected=409)
    rate(client,refs,"piece_wage","1")
    row=report(client,refs,good=1,pending=1)
    worker=get(client,"workers")["items"][0]
    post(client,"workers/"+worker["id"],dict(id=worker["id"],expected_version=worker["version"],employee_no=worker["employee_no"],display_name="Renamed"))
    new=post(client,f"production-reports/{row['id']}/quality",dict(report_id=row["id"],expected_version=row["version"],reason="Quality",quality=dict(reported_qty=2,good_qty=2,defective_qty=0,pending_qty=0,semi_finished_qty=0)))["entity"]
    assert new["worker_names"]==row["worker_names"]


def test_drafts_do_not_reserve_sources_and_confirm_rechecks_atomically(client):
    refs = masters(client)
    with Session(client.uv_engine) as db:
        source = m.UvJob(factory_id="huakang-a", machine_id=refs["machine_id"], product_id=refs["product_id"],process_version_id=refs["process_version_id"],source_job_id="draft-source",source_event_id="e",connector_id="test",generation="1",raw_task_name="100 pieces",state="completed",raw_unit="piece",suggested_piece_qty=100)
        db.add(source); db.commit(); ident=source.id
    payload=dict(**refs,business_date="2026-09-13",shift="day",reported_qty=80,good_qty=80,defective_qty=0,pending_qty=0,semi_finished_qty=0,source_allocations=[dict(job_id=ident,piece_qty=80,job_version=1)])
    drafts=[post(client,"production-reports",payload)["entity"] for _ in range(2)]
    assert get(client,"jobs")["items"][0]["available_piece_qty"]==100
    assert get(client,"jobs")["items"][0]["version"]==1
    assert get(client,"summary")["counts"]["good_qty"]==0
    first=post(client,f"production-reports/{drafts[0]['id']}/confirm",dict(report_id=drafts[0]["id"],expected_version=1))["entity"]
    post(client,f"production-reports/{drafts[1]['id']}/confirm",dict(report_id=drafts[1]["id"],expected_version=1),operation="blocked-confirm",expected=422)
    assert get(client,"jobs")["items"][0]["available_piece_qty"]==20
    assert get(client,"operations/blocked-confirm") is None
    post(client,f"production-reports/{first['id']}/void",dict(report_id=first["id"],expected_version=first["version"],reason="Release source"))
    post(client,f"production-reports/{drafts[1]['id']}/confirm",dict(report_id=drafts[1]["id"],expected_version=1),operation="blocked-confirm")
    assert get(client,"summary")["counts"]["good_qty"]==80


def test_correction_omitted_sources_cannot_detach_and_double_count(client):
    refs=masters(client)
    with Session(client.uv_engine) as db:
        source=m.UvJob(factory_id="huakang-a",machine_id=refs["machine_id"],product_id=refs["product_id"],process_version_id=refs["process_version_id"],source_job_id="keep-source",source_event_id="e",connector_id="test",generation="1",raw_task_name="100 pieces",state="completed",raw_unit="piece",suggested_piece_qty=100)
        db.add(source);db.commit();ident=source.id
    original=report(client,refs,source_allocations=[dict(job_id=ident,piece_qty=100,job_version=1)],evidence_job_ids=[ident])
    assert original["source_allocations"][0]["piece_qty"]==100
    correction={**refs,"factory_id":"huakang-a","operation_id":uuid4().hex,"expected_version":0,"business_date":"2026-09-13","shift":"day","reported_qty":100,"good_qty":90,"defective_qty":10,"pending_qty":0,"semi_finished_qty":0,"source_allocations":[],"evidence_job_ids":[]}
    revised=post(client,f"production-reports/{original['id']}/corrections",dict(report_id=original["id"],expected_version=original["version"],reason="Quality correction",correction=correction))["entity"]
    assert revised["allocation_total"]==100 and revised["evidence_job_ids"]==[ident]
    assert get(client,"jobs")["items"][0]["available_piece_qty"]==0
    smaller={**correction,"reported_qty":90,"good_qty":80}
    post(client,f"production-reports/{revised['id']}/corrections",dict(report_id=revised["id"],expected_version=revised["version"],reason="Reduce quantity",correction=smaller),expected=422)
    assert get(client,"jobs")["items"][0]["available_piece_qty"]==0


def test_trace_preserves_revisions_audit_and_redacts_sensitive_history(client):
    refs=masters(client)
    rate(client,refs,"commercial","1")
    rate(client,refs,"piece_wage","0.2")
    old=report(client,refs,good=90,pending=10)
    new=post(client,f"production-reports/{old['id']}/quality",dict(report_id=old["id"],expected_version=old["version"],reason="Rechecked",quality=dict(reported_qty=100,good_qty=95,defective_qty=5,pending_qty=0,semi_finished_qty=0)))["entity"]
    trace=get(client,f"production-reports/{new['id']}/trace")
    assert trace["root_report_id"]==old["id"]
    assert trace["effective_report_ids"]==[new["id"]]
    assert trace["changes"][0]["changes"]["good_qty"]=={"before":90,"after":95}
    assert len(trace["audit"])==3
    client.uv_auth["user"]=user_with("read")
    restricted=get(client,f"production-reports/{old['id']}/trace")
    def assert_scrubbed(value):
        if isinstance(value,dict):
            assert not {"commercial","payroll","worker_shares","fingerprint","result","unit_price","piece_wage"}&value.keys()
            for item in value.values(): assert_scrubbed(item)
        elif isinstance(value,list):
            for item in value: assert_scrubbed(item)
    assert_scrubbed(restricted)
    assert restricted["audit"][1]["quality"]["good_qty"]==90


def test_quality_clearing_and_void_require_quality_permission(client):
    refs=masters(client)
    old=report(client,refs,good=90,defective=10)
    client.uv_auth["user"]=user_with("read","report")
    correction={**refs,"factory_id":"huakang-a","operation_id":uuid4().hex,"expected_version":0,"business_date":"2026-09-13","shift":"day","reported_qty":100,"good_qty":0,"defective_qty":0,"pending_qty":100,"semi_finished_qty":0}
    post(client,f"production-reports/{old['id']}/corrections",dict(report_id=old["id"],expected_version=old["version"],reason="Clear quality",correction=correction),expected=403)
    post(client,f"production-reports/{old['id']}/void",dict(report_id=old["id"],expected_version=old["version"],reason="Void"),expected=403)
    assert get(client,"summary")["counts"]["good_qty"]==90


def test_handover_versions_scope_difference_and_stale_report(client):
    refs=masters(client)
    reported=report(client,refs)
    payload=dict(business_date="2026-09-13",report_id=reported["id"],product_id=refs["product_id"],received_qty=97,receiver="Synthetic receiver",note="Counted")
    original=post(client,"handovers",payload,operation="handover-once")
    assert original["entity"]["difference_qty"]==-3 and original["entity"]["state"]=="difference"
    assert post(client,"handovers",payload,operation="handover-once")["replayed"]
    post(client,"handovers",payload,expected=409)
    post(client,"handovers",{**payload,"business_date":"2026-09-14"},expected=422)
    row=original["entity"]
    post(client,"handovers/"+row["id"],{**payload,"id":row["id"],"expected_version":0},expected=409)
    updated=post(client,"handovers/"+row["id"],{**payload,"id":row["id"],"expected_version":row["version"],"received_qty":100})["entity"]
    assert updated["state"]=="reconciled"
    assert get(client,"summary")["counts"]["handover_differences"]==0
    post(client,f"production-reports/{reported['id']}/void",dict(report_id=reported["id"],expected_version=reported["version"],reason="Source voided"))
    stale=get(client,"handovers")["items"][0]
    assert stale["source_stale"] and stale["state"]=="pending" and stale["reported_qty"]==100
    assert get(client,"summary")["counts"]["handover_differences"]==1
    client.uv_auth["user"]=user_with("read")
    post(client,"handovers",{**payload,"report_id":None},expected=403)


def test_frozen_handover_migration_matches_model(client):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    from app.models.uv_handover import UvHandover
    path=Path(__file__).resolve().parents[1]/"alembic"/"versions"/"20260914_0115_uv_handover.py"
    spec=importlib.util.spec_from_file_location("uv_handover_frozen_migration",path)
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision=="20260913_0114"
    with client.uv_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
        actual={column["name"] for column in inspect(connection).get_columns("uv_handovers")}
        assert actual==set(UvHandover.__table__.columns.keys())
        assert {row["name"] for row in inspect(connection).get_unique_constraints("uv_handovers")}=={"uq_uv_handover_report"}


def test_runtime_splits_cross_month_evidence_without_duplicate_output(client):
    refs=masters(client)
    post(client,"shift-templates",dict(label="Night",shift="night",start_local="21:00",end_local="07:40",effective_from="2026-01-01"))
    with Session(client.uv_engine) as db:
        job=m.UvJob(factory_id="huakang-a",machine_id=refs["machine_id"],source_job_id="cross-night",source_event_id="e",connector_id="test",generation="1",raw_task_name="Night print",state="completed",raw_unit="piece",suggested_piece_qty=10,started_at="2026-08-31T22:00:00+08:00",completed_at="2026-09-01T09:00:00+08:00",time_evidence="observed")
        db.add(job);db.commit()
    # Quantity-facing jobs use the completed business date only.
    assert get(client,"jobs",business_date="2026-08-31",shift="night")["total"]==0
    assert get(client,"jobs",business_date="2026-09-01",shift="day")["total"]==1
    night=get(client,"machines/"+refs["machine_id"],business_date="2026-08-31",shift="night")
    day=get(client,"machines/"+refs["machine_id"],business_date="2026-09-01",shift="day")
    assert sum(w["duration_minutes"] for w in night["runtime_windows"] if w["kind"]=="run")==580
    assert sum(w["duration_minutes"] for w in day["runtime_windows"] if w["kind"]=="run")==80
    assert all(w["kind"] in {"run","gap"} for w in night["runtime_windows"])
    assert any(w["kind"]=="gap" for w in night["runtime_windows"])
    client.uv_auth["user"]=user_with("read")
    assert "expenses" not in get(client,"machines/"+refs["machine_id"],business_date="2026-08-31",shift="night")


def test_jobs_without_business_time_are_explicitly_pending_not_hidden_zero(client):
    refs=masters(client)
    with Session(client.uv_engine) as db:
        db.add(m.UvJob(factory_id="huakang-a",machine_id=refs["machine_id"],source_job_id="missing-time",source_event_id="e",connector_id="test",generation="1",raw_task_name="Unknown time",state="uncertain",raw_unit="unknown"))
        db.commit()
    assert get(client,"jobs")["total"]==1
    result=client.get("/api/uv-printing/jobs",params={"factory_id":"huakang-a","business_date":"2026-09-13"}).json()
    assert result["data"]["total"]==0 and result["meta"]["coverage"]=="partial"
    assert result["meta"]["warnings"][0]["code"]=="jobs_business_date_unknown"
    assert get(client,"jobs",status="needs_unit")["total"]==1
    assert get(client,"jobs",status="completed")["total"]==0


def test_meta_matches_payroll_data_and_explicit_pending_status(client):
    refs=masters(client)
    report(client,refs)
    response=client.get("/api/uv-printing/payroll/preview",params={"factory_id":"huakang-a"}).json()
    assert response["meta"]["coverage"]==response["data"]["coverage"]=="partial"
    assert response["meta"]["warnings"]
    response=client.get("/api/uv-printing/payroll/preview",params={"factory_id":"huakang-a","business_date":"2025-01-01"}).json()
    assert response["meta"]["coverage"]==response["data"]["coverage"]=="no_data"


def finance_hook(monkeypatch, cost_days, costs, adjustments=None):
    """Exercise the bounded finance/core hook contract with synthetic inputs."""
    import app.services
    module=types.ModuleType("app.services.uv_finance")
    module.__spec__=importlib.util.spec_from_loader(module.__name__,loader=None)
    module.ensure_open=lambda *args:None
    module.ensure_report_mutable=lambda *args:None
    module.cost_dates=lambda db,factory,scope:[d for d in cost_days if (not scope.get("business_date") or d==scope["business_date"]) and (not scope.get("date_from") or d>=scope["date_from"]) and (not scope.get("date_to") or d<=scope["date_to"])]
    module.day_costs=lambda db,factory,day,machine=None:costs[day]
    module.payroll_adjustments=lambda db,factory,scope:[r for r in (adjustments or []) if not scope.get("business_date") or r["business_date"]==scope["business_date"]]
    module.summary_counts=lambda db,factory,scope:{"low_stock_skus":2}
    module.latest_policy=lambda db,factory,month:None
    monkeypatch.setitem(sys.modules,module.__name__,module)
    monkeypatch.setattr(app.services,"uv_finance",module,raising=False)
    return module


def test_cost_missing_reason_blocks_result_and_cost_only_days_have_known_zero(client,monkeypatch):
    refs=masters(client)
    rate(client,refs,"commercial","1")
    rate(client,refs,"piece_wage","0.2")
    report(client,refs)
    finance_hook(monkeypatch,["2026-09-13","2026-09-14"],{
        "2026-09-13":dict(ink_cost={"currency":"HKD","amount":"1.00"},expense_amount={"currency":"HKD","amount":"2.00"},provisional_reasons=["月固定费用有未填写项"]),
        "2026-09-14":dict(ink_cost={"currency":"HKD","amount":"0.00"},expense_amount={"currency":"HKD","amount":"3.00"},provisional_reasons=[]),
    })
    rows=get(client,"reports/daily-projection")["items"]
    assert rows[0]["operating_result"] is None and rows[0]["provisional_reasons"]==["月固定费用有未填写项"]
    assert rows[1]["output_value"]=={"currency":"HKD","amount":"0.00"}
    assert rows[1]["payroll_amount"]=={"currency":"HKD","amount":"0.00"}
    assert rows[1]["operating_result"]=={"currency":"HKD","amount":"-3.00"}
    monthly=get(client,"reports/monthly")["months"][0]
    assert monthly["output_value"]["amount"]=="100.00" and monthly["payroll_amount"]["amount"]=="20.00"
    assert monthly["operating_result"] is None
    assert get(client,"summary")["counts"]["low_stock_skus"]==2


def test_payroll_adjustment_enters_preview_and_day_cost_once(client,monkeypatch):
    refs=masters(client)
    rate(client,refs,"piece_wage","0.2")
    report(client,refs)
    adjustment=dict(worker_id=refs["worker_ids"][0],worker_name="Worker adjustment",currency="HKD",amount="-1.25",business_date="2026-09-14",batch_id="adjustment-1",reason="Verified correction")
    finance_hook(monkeypatch,["2026-09-14"],{"2026-09-13":dict(ink_cost=None,expense_amount=None,provisional_reasons=["Unknown costs"]),"2026-09-14":dict(ink_cost={"currency":"HKD","amount":"0.00"},expense_amount={"currency":"HKD","amount":"0.00"},provisional_reasons=[])},[adjustment])
    preview=get(client,"payroll/preview")
    assert preview["batch_total"]["amount"]=="18.75"
    line=next(v for v in preview["lines"] if v["worker_id"]==adjustment["worker_id"])
    assert line["state"]=="adjusted" and "Verified correction" in line["reason"]
    rows=get(client,"reports/daily-projection")["items"]
    day=next(v for v in rows if v["business_date"]=="2026-09-14")
    assert day["good_qty"]==0 and day["payroll_amount"]["amount"]=="-1.25"
    assert day["operating_result"]["amount"]=="1.25"
    with Session(client.uv_engine) as db:
        assert s.payroll_preview(db,"huakang-a",{"include_adjustments":False})["batch_total"]["amount"]=="20.00"


@pytest.mark.parametrize("instant, expected", [("2026-09-13T07:39:59+08:00",("2026-09-12","night")),("2026-09-13T07:40:00+08:00",("2026-09-13","day")),("2026-09-13T21:00:00+08:00",("2026-09-13","night")),("2026-10-01T01:00:00+08:00",("2026-09-30","night"))])
def test_business_slot_boundaries(instant,expected):
    templates = [m.UvShiftTemplate(id="d",factory_id="huakang-a",shift="day",start_local="07:40",end_local="21:00",effective_from="2026-01-01"),m.UvShiftTemplate(id="n",factory_id="huakang-a",shift="night",start_local="21:00",end_local="07:40",effective_from="2026-01-01")]
    assert s.business_slot(instant,templates)[:2] == expected
