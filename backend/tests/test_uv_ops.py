"""Only disposable databases and explicitly synthetic files; no app lifespan."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.api import uv_operations as api, uv_agent
from app.models import uv_operations as m
from app.services.auth import AuthContext, AuthGrantContext, get_current_user
from app.services.permission_codes import UV_OPS_PERMISSION_CODES


def user_with(*actions, factory="huakang-a"):
    codes = frozenset("uv_ops:"+x for x in actions)
    grant = AuthGrantContext(role_id="synthetic", role_name="Synthetic", factory_id=factory, department="production", permissions=codes)
    return AuthContext(id="uv-test", username="test", display_name="合成验收", roles=("test",), role_codes=("test",), permissions=codes, factory_scopes=(factory,), department_scopes=("production",), grants=(grant,), active_permission_codes=frozenset(UV_OPS_PERMISSION_CODES))


@pytest.fixture(params=["sqlite", "postgres"])
def client(tmp_path, monkeypatch, request):
    admin = None
    if request.param == "postgres":
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        value = os.environ.get("UV_OPS_TEST_POSTGRES_URL")
        if not value:
            pytest.skip("UV_OPS_TEST_POSTGRES_URL not configured; no PostgreSQL claim")
        url = make_url(value)
        assert url.host in {"localhost", "127.0.0.1"} and url.database == "uv_ops_test"
        schema = "uvqa_"+uuid4().hex
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options":f"-csearch_path={schema}"})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'uv-acceptance.db'}", connect_args={"check_same_thread": False, "timeout": 20})
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    m.Base.metadata.create_all(engine, tables=[t for t in m.Base.metadata.sorted_tables if t.name.startswith("uv_ops_")])
    with Session(engine) as db:
        db.add(m.UvOpsSettings(id="huakang-a", factory_id="huakang-a", data_mode="synthetic"))
        db.commit()
    monkeypatch.setattr(api.settings, "uv_ops_enabled", True)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(uv_agent.router)
    auth = {"user": user_with(*(x.split(":")[1] for x in UV_OPS_PERMISSION_CODES))}
    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[api.get_db] = database
    app.dependency_overrides[get_current_user] = lambda: auth["user"]
    with TestClient(app) as value:
        value.uv_engine, value.uv_auth = engine, auth
        yield value
    engine.dispose()
    if admin:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def payload(**values):
    return dict(factory_id="huakang-a", operation_id=uuid4().hex, expected_version=0) | values


def post(client, path, **values):
    response = client.post("/api/uv-operations/"+path, json=payload(**values))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def read(client, path):
    response = client.get("/api/uv-operations/"+path, params={"factory_id": "huakang-a"})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def setup_task(client, *, quantity=120, passes=1, piece_rate="0.12"):
    suffix = uuid4().hex[:6]
    machine = post(client, "machines", code="M-"+suffix, name="合成机台", width_mm="1000", height_mm="800", ink_family="synthetic-hard", capability_evidence="合成尺寸与墨材")
    product = post(client, "products", code="P-"+suffix, name="合成产品")
    fixture = post(client, "fixtures", code="F-"+suffix, revision=1, slots=12, width_mm="100", height_mm="80")
    process = post(client, "process-versions", product_id=product["id"], fixture_id=fixture["id"], revision=1, name="合成工艺", ink_family="synthetic-hard", pieces_per_board=12, cycle_seconds="30", width_mm="100", height_mm="80", passes=passes)
    response = client.post("/api/uv-operations/files", data=dict(factory_id="huakang-a", operation_id=uuid4().hex, process_version_id=process["id"], role="production"), files={"file": ("synthetic.prn", b"SYNTHETIC NON EXECUTABLE PRN FIXTURE v1", "application/octet-stream")})
    assert response.status_code == 200, response.text
    file = response.json()["data"]
    file = post(client, "file-versions/"+file["id"]+"/confirm", expected_version=file["version"], first_article_evidence="合成首件人工验收证据")
    price = post(client, "pricing-policies", product_id=product["id"], basis="piece", rate=piece_rate, currency="CNY", evidence="合成价格协议")
    wage = post(client, "wage-policies", name="合成计件", basis="piece", rate="0.015", currency="CNY", evidence="合成工资制度")
    demand = post(client, "demands", code="D-"+suffix, product_id=product["id"], quantity=quantity, due_at="2026-09-24T08:00:00+08:00")
    task = post(client, "tasks", code="T-"+suffix, demand_id=demand["id"], process_version_id=process["id"], file_version_id=file["id"], price_policy_id=price["id"], wage_policy_id=wage["id"], quantity=quantity)
    shift = post(client, "shifts", name="合成白班", business_date="2026-09-23", start_at="2026-09-23T08:00:00+08:00", end_at="2026-09-23T16:00:00+08:00")
    return dict(machine=machine, product=product, fixture=fixture, process=process, file=file, price=price, wage=wage, demand=demand, task=task, batch=task["batches"][0], shift=shift)


def confirm(client, data, *, good=114, rework=6, scrap=0, pending=0, source_bucket="remaining"):
    return post(client, "production/confirm", expected_version=data["batch"]["version"], task_id=data["task"]["id"], batch_id=data["batch"]["id"], shift_id=data["shift"]["id"], pass_index=data["batch"]["pass_index"], processed=good+rework+scrap+pending, good=good, rework=rework, scrap=scrap, pending=pending, source_bucket=source_bucket, evidence="合成人工核数")


@pytest.mark.parametrize("factory", ["", "group", "huakang-b", "huaxing"])
def test_uv_ops_factory_is_always_explicit(client, factory):
    assert client.get("/api/uv-operations/access", params={"factory_id": factory}).status_code == 422


def test_uv_ops_manual_conservation_rework_handover(client):
    data = setup_task(client)
    result = confirm(client, data)
    data["batch"] = result["batch"]
    rework = post(client, "rework-tasks", batch_id=data["batch"]["id"], expected_version=data["batch"]["version"], code="REWORK-1", quantity=6)
    data["task"] = rework
    result = confirm(client, data, good=5, rework=0, scrap=1, source_bucket="rework")
    batch = result["batch"]
    assert (batch["good"], batch["scrap"], batch["rework"], batch["quantity"]) == (119, 1, 0, 120)
    report = client.get("/api/uv-operations/reports", params=dict(factory_id="huakang-a", start_date="2026-09-23", end_date="2026-09-23")).json()["data"]
    assert report["totals"]["processed"] == 126
    assert report["totals"]["good"] == 119
    handover = post(client, "handovers", batch_id=batch["id"], expected_version=batch["version"], target="合成下工序", quantity=119, business_date="2026-09-23")
    result = post(client, "handovers/"+handover["id"]+"/receive", expected_version=handover["version"], quantity=100, business_date="2026-09-23", evidence="合成签收")
    assert result["batch"]["received"] == 100 and result["batch"]["reserved"] == 19
    result = post(client, "handovers/"+handover["id"]+"/reject", expected_version=result["handover"]["version"], quantity=19, business_date="2026-09-23", evidence="合成拒收")
    assert result["batch"]["good"] == 119 and result["batch"]["reserved"] == 0


def test_uv_ops_idempotent_replay_and_conflict(client):
    body = payload(code="M-RETRY", name="合成机台")
    first = client.post("/api/uv-operations/machines", json=body)
    second = client.post("/api/uv-operations/machines", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    assert client.post("/api/uv-operations/machines", json=body | {"name": "更改"}).status_code == 409
    assert len(read(client, "machines")) == 1


def test_uv_ops_task_prices_are_frozen_and_projected(client):
    data = setup_task(client)
    post(client, "pricing-policies", product_id=data["product"]["id"], basis="piece", rate="0.15", currency="CNY", evidence="合成新版本价格")
    task = read(client, "tasks/"+data["task"]["id"])
    assert Decimal(task["cost_price_snapshot"]["rate"]) == Decimal("0.12")
    client.uv_auth["user"] = user_with("read")
    task = read(client, "tasks/"+data["task"]["id"])
    assert "cost_price_snapshot" not in task and "payroll_policy_snapshot" not in task
    assert client.get("/api/uv-operations/pricing-policies", params={"factory_id":"huakang-a"}).status_code == 403


def test_uv_ops_rounding_and_piece_rate():
    from app.services.uv_operations.payroll import split_money
    from app.services.uv_operations.common import money
    assert split_money(Decimal(100), {"a": Decimal(1), "b": Decimal(1), "c": Decimal(1)}) == {"a": Decimal("33.34"), "b": Decimal("33.33"), "c": Decimal("33.33")}
    assert money(Decimal("0.015")*1000) == Decimal("15.00")


def test_uv_ops_multiple_passes_do_not_duplicate_output(client):
    data = setup_task(client, quantity=101, passes=2)
    result = confirm(client, data, good=101, rework=0)
    assert result["batch"]["intermediate"] == 101 and result["batch"]["good"] == 0
    data["batch"] = post(client, "batches/"+data["batch"]["id"]+"/advance-pass", expected_version=result["batch"]["version"])
    result = confirm(client, data, good=101, rework=0)
    assert result["batch"]["good"] == result["batch"]["quantity"] == 101
