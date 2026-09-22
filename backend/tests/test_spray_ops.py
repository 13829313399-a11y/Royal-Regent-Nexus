"""Synthetic acceptance only. These tests never use the configured business DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.api import spray_operations as api
from app.models import spray_ops as m
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
from app.services.permission_codes import SPRAY_OPS_PERMISSION_CODES
from app.services.spray_ops.common import seed_factories


def user_with(*actions, factory="*"):
    codes = frozenset("spray_ops:" + action for action in actions)
    grant = AuthGrantContext(role_id="test", role_name="Synthetic", factory_id=factory, department="production", permissions=codes)
    return AuthContext(id="spray-test", username="test", display_name="测试用户", roles=("test",), role_codes=("test",), permissions=codes, factory_scopes=(factory,), department_scopes=("production",), grants=(grant,), active_permission_codes=frozenset(SPRAY_OPS_PERMISSION_CODES))


@pytest.fixture
def client(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'spray-acceptance.db'}", connect_args={"timeout": 20, "check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    tables = [table for table in m.Base.metadata.sorted_tables if table.name.startswith("spray_ops_")]
    m.Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        seed_factories(db)
        db.commit()
    monkeypatch.setattr(api.settings, "spray_ops_enabled", True)
    app = FastAPI()
    app.include_router(api.router)
    auth = {"user": user_with(*(code.split(":")[1] for code in SPRAY_OPS_PERMISSION_CODES))}
    def db_dependency():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[api.get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: auth["user"]
    with TestClient(app) as test_client:
        test_client.spray_engine, test_client.spray_auth = engine, auth
        yield test_client
    engine.dispose()


def payload(**values):
    return dict(factory_id="huaxing", operation_id=uuid4().hex, expected_version=0) | values


def post(client, path, **values):
    response = client.post("/api/spray-operations/" + path, json=payload(**values))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def read(client, path, factory="huaxing"):
    response = client.get("/api/spray-operations/" + path, params={"factory_id": factory, "page_size": 200})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def setup_order(client, *, factory="huaxing", quantity="1000", second_batch=False):
    resource = post(client, "resources", factory_id=factory, code="MAN-01", name="手喷 01", kind="manual", capabilities=[dict(capability="coat", hourly_capacity="1000", evidence="合成测试确认")], calendar=[dict(start_at="2026-09-01T00:00:00Z", end_at="2026-10-01T00:00:00Z")])
    route = post(client, "routes", factory_id=factory, code="R-01", label="合成单工序", revision=1, confirmed=True, evidence="合成测试依据", steps=[dict(code="S1", name="喷底色", capability="coat", prep_required=True)])
    demand = post(client, "demands", factory_id=factory, document_no="ORDER-01", counterparty="测试委托方", business_date="2026-09-01", lines=[dict(item_no="00017", part="左件", color="灰色 V1", quantity=quantity, due_date="2026-10-01", route_id=route["id"], commercial_price="2.07", price_evidence="合成合同")])
    line = demand["lines"][0]
    amount = "5000" if second_batch else quantity
    batch = post(client, "batches", factory_id=factory, document_no="ARR-01", business_date="2026-09-01", line_id=line["id"], item_no="00017", part="左件", quantity=amount, accepted=amount)
    prep = post(client, "preparations", factory_id=factory, batch_id=batch["id"], step_id=route["steps"][0]["id"], ready_at="2026-09-01T01:00:00Z", evidence="合成备料完成")
    return dict(resource=resource, route=route, demand=demand, line=line, batch=batch, stock=batch["stock"][0], prep=prep)


def manual_scenario(client, setup, *, qty="1000", start="2026-09-02T00:00:00Z", end="2026-09-02T01:00:00Z", **extra):
    return post(client, "scenarios/preview", start_at=start, end_at=end, tasks=[dict(step_id=setup["route"]["steps"][0]["id"], resource_id=setup["resource"]["id"], start_at=start, end_at=end, allocations=[dict(stock_id=setup["stock"]["id"], quantity=qty)])], **extra)


def publish(client, scenario):
    return post(client, f"scenarios/{scenario['id']}/publish", expected_version=scenario["version"], base_revision=scenario["base_revision"])["tasks"][0]


def start(client, task):
    return post(client, f"tasks/{task['id']}/start", expected_version=task["version"], business_date="2026-09-02", actual_start=task["start_at"])


def report(client, task, *, qty="1000", good="900", hold="50", scrap="50", **extra):
    quantities = dict(processed=qty, good=good, hold=hold, scrap=scrap, normal=qty, overtime="0")
    return post(client, "reports", document_no="DAILY-01", business_date="2026-09-02", shift="合成白班", rows=[dict(task_id=task["id"], **quantities, reason="合成质量检查", allocations=[dict(task_allocation_id=task["allocations"][0]["id"], **quantities)])], **extra)


def test_order_two_arrivals_and_real_stock_lifecycle(client):
    setup = setup_order(client)
    scenario = manual_scenario(client, setup)
    assert read(client, "stock")[0]["reserved"] == "0.000000"
    task = start(client, publish(client, scenario))
    result = report(client, task)
    assert result["status"] == "confirmed"
    stock = read(client, "stock")
    assert sum(Decimal(row["quantity"]) for row in stock) == 950
    assert sum(Decimal(row["quantity"]) for row in stock if row["state"] == "finished") == 900
    hold = next(row for row in stock if row["state"] == "hold")
    result = post(client, f"stock/{hold['id']}/quality", expected_version=hold["version"], business_date="2026-09-02", good="30", rework="20", scrap="0", reason="复检")
    assert Decimal(result["quantity"]) == 0
    assert {row["state"] for row in result["outputs"]} == {"finished", "white"}
    assert read(client, "demands")[0]["lines"][0]["item_no"] == "00017"


def test_partial_arrival_only_schedules_available_5000(client):
    setup_order(client, quantity="50000", second_batch=True)
    scenario = post(client, "scenarios/preview", start_at="2026-09-02T00:00:00Z", end_at="2026-09-03T00:00:00Z")
    assert sum(Decimal(a["quantity"]) for t in scenario["snapshot"]["tasks"] for a in t["allocations"]) == 5000


def test_idempotency_before_version_and_different_payload_rejected(client):
    body = payload(code="E01", name="合成员工")
    first = client.post("/api/spray-operations/employees", json=body)
    second = client.post("/api/spray-operations/employees", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    conflict = client.post("/api/spray-operations/employees", json=body | {"name": "不同员工"})
    assert conflict.status_code == 409
    assert len(read(client, "employees")) == 1


@pytest.mark.parametrize("factory", ["", "group", "huakang-c", "huakang-d", "unknown"])
def test_no_factory_fallback(client, factory):
    response = client.get("/api/spray-operations/demands", params={"factory_id": factory})
    assert response.status_code == 422


def test_all_twelve_directed_cross_factory_references(client):
    setups = {factory: setup_order(client, factory=factory) for factory in m.FACTORIES}
    for source in m.FACTORIES:
        for target in m.FACTORIES:
            if source == target:
                continue
            body = payload(factory_id=target, document_no=uuid4().hex, line_id=setups[source]["line"]["id"], business_date="2026-09-01", item_no="00017", part="左件", quantity="1", accepted="1")
            response = client.post("/api/spray-operations/batches", json=body)
            assert response.status_code == 404


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_strict_permissions_in_all_auth_modes(client, monkeypatch, mode):
    monkeypatch.setattr(api.settings, "authz_mode", mode)
    setup_order(client)
    client.spray_auth["user"] = user_with("read")
    data = read(client, "demands")
    assert "commercial_price" not in data[0]["lines"][0]
    response = client.post("/api/spray-operations/employees", json=payload(code="x", name="x"))
    assert response.status_code == 403
    client.spray_auth["user"] = replace(user_with("read"), overrides=(AuthOverrideContext(id="deny", permission_code="spray_ops:read", factory_id="huaxing", department="production", effect="deny", valid_from="", valid_until=""),))
    assert client.get("/api/spray-operations/demands", params={"factory_id": "huaxing"}).status_code == 403


def test_concurrent_publish_cannot_double_reserve(client):
    setup = setup_order(client)
    one = manual_scenario(client, setup, qty="700")
    two = manual_scenario(client, setup, qty="700", start="2026-09-02T02:00:00Z", end="2026-09-02T03:00:00Z")
    def commit(scenario):
        return client.post(f"/api/spray-operations/scenarios/{scenario['id']}/publish", json=payload(expected_version=1, base_revision=scenario["base_revision"]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, [one, two]))
    assert sorted(response.status_code for response in outcomes) == [200, 409]
    assert Decimal(read(client, "stock")[0]["reserved"]) == 700


def test_resource_conflict_and_unconfirmed_route(client):
    setup = setup_order(client)
    one = manual_scenario(client, setup, qty="700")
    publish(client, one)
    body = payload(start_at="2026-09-02T00:00:00Z", end_at="2026-09-02T01:00:00Z", tasks=[dict(step_id=setup["route"]["steps"][0]["id"], resource_id=setup["resource"]["id"], start_at="2026-09-02T00:00:00Z", end_at="2026-09-02T01:00:00Z", allocations=[dict(stock_id=setup["stock"]["id"], quantity="300")])])
    response = client.post("/api/spray-operations/scenarios/preview", json=body)
    assert response.status_code == 409 and response.json()["code"] == "resource_conflict"


def test_dag_cycle_and_numeric_guards(client):
    body = payload(code="cycle", label="cycle", revision=1, steps=[dict(code="a", name="a", capability="a", predecessors=["b"]), dict(code="b", name="b", capability="b", predecessors=["a"])])
    response = client.post("/api/spray-operations/routes", json=body)
    assert response.status_code == 422 and response.json()["code"] == "route_cycle"
    for bad in ["NaN", "Infinity", "-1", 1.2]:
        response = client.post("/api/spray-operations/batches", json=payload(document_no="X", business_date="2026-09-01", item_no="01", part="左", quantity=bad, accepted=bad))
        assert response.status_code == 422


def test_report_correction_blocks_downstream_quality(client):
    setup = setup_order(client)
    task = start(client, publish(client, manual_scenario(client, setup)))
    result = report(client, task)
    stock = next(row for row in read(client, "stock") if row["state"] == "hold")
    post(client, f"stock/{stock['id']}/quality", expected_version=1, business_date="2026-09-02", good="1", reason="复检")
    response = client.post(f"/api/spray-operations/reports/{result['id']}/reverse", json=payload(expected_version=result["version"], business_date="2026-09-02", reason="纠错"))
    assert response.status_code == 409 and response.json()["code"] == "downstream_impact"


def approved_rule(client, kind, parameters, **extra):
    rule = post(client, "rules", code=uuid4().hex, label="合成确认规则", kind=kind, revision=1, effective_from="2026-09-01", parameters=parameters, evidence="仅隔离测试使用", **extra)
    return post(client, f"rules/{rule['id']}/confirm", expected_version=1, business_date="2026-09-01", reason="合成测试明确确认")


def accepted_delivery(client):
    setup = setup_order(client)
    task = start(client, publish(client, manual_scenario(client, setup)))
    report(client, task, good="1000", hold="0", scrap="0")
    stock = next(row for row in read(client, "stock") if row["state"] == "finished")
    delivery = post(client, "deliveries", document_no="DEL-01", business_date="2026-09-02", counterparty="测试委托方", lines=[dict(stock_id=stock["id"], quantity="1000")])
    return post(client, f"deliveries/{delivery['id']}/accept", expected_version=delivery["version"], business_date="2026-09-03", lines=[dict(delivery_line_id=delivery["lines"][0]["id"], accepted="1000")])


def test_partial_settlement_concurrent_and_separate_return_credit(client):
    delivery = accepted_delivery(client)
    line = delivery["lines"][0]
    def settle(_):
        return client.post("/api/spray-operations/settlements", json=payload(document_no=uuid4().hex, counterparty="测试委托方", month="2026-09", business_date="2026-09-03", currency="CNY", lines=[dict(delivery_line_id=line["id"], quantity="600")]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(settle, range(2)))
    assert sorted(r.status_code for r in outcomes) == [200, 409]
    settled = next(r.json()["data"] for r in outcomes if r.status_code == 200)
    line = read(client, "delivery-lines")[0]
    assert Decimal(line["accepted"]) - Decimal(line["settled"]) == 400
    returned = post(client, "returns", expected_version=line["version"], business_date="2026-09-04", delivery_line_id=line["id"], quantity="700", reason="测试退货")
    assert returned["credit_required"] is True
    credit = post(client, "credits", business_date="2026-09-04", return_id=returned["id"], settlement_line_id=settled["lines"][0]["id"], quantity="300", reason="退货结算调整")
    assert Decimal(credit["amount"]) == Decimal("621")
    assert Decimal(read(client, "settlements")[0]["total_amount"]) == Decimal("1242")


def test_material_cost_uses_original_lot_and_savings_not_second_cost(client):
    material = post(client, "materials", code="TEST-628", name="合成开油水", unit="KG")
    conversion = approved_rule(client, "unit", dict(from_unit="桶", to_unit="KG", factor="160"), material_id=material["id"])
    purchase = post(client, "purchases", document_no="FBD-TEST", business_date="2026-09-01", supplier="合成供应商", currency="CNY", tax_basis="合成含税", lines=[dict(material_id=material["id"], quantity="2", unit="桶", price="1472", due_date="2026-09-03")])
    receipt = post(client, "material-receipts", document_no="MR-TEST", business_date="2026-09-02", supplier="合成供应商", lines=[dict(purchase_line_id=purchase["lines"][0]["id"], quantity="2", unit="桶", conversion_rule_id=conversion["id"])])
    lot = receipt["lots"][0]
    issued = post(client, f"material-lots/{lot['id']}/move", expected_version=lot["version"], business_date="2026-09-02", kind="issue", quantity="160", reason="领料")
    consumed = post(client, f"material-lots/{lot['id']}/move", expected_version=issued["lot"]["version"], business_date="2026-09-02", kind="consume", quantity="80", issue_id=issued["id"], reason="实际耗用")
    assert Decimal(consumed["cost"]) == 736
    returned = post(client, f"material-lots/{lot['id']}/move", expected_version=consumed["lot"]["version"], business_date="2026-09-02", kind="return", quantity="80", issue_id=issued["id"], reason="原批次余料退回")
    assert Decimal(returned["lot"]["warehouse"]) * Decimal(returned["lot"]["unit_cost"]) == 2208
    saving = post(client, "savings", business_date="2026-09-02", purchase_line_id=purchase["lines"][0]["id"], quantity="2", old_price="1586", new_price="1472", currency="CNY", source_ref="S12 合成验证")
    assert Decimal(saving["saving"]) == 228
    assert Decimal(saving["signed_difference"]) == -228
    assert sum(Decimal(row["cost"] or "0") for row in read(client, "material-movements")) == 736


def test_seven_people_560_team_output_wage_trial_and_official_gate(client):
    setup = setup_order(client, quantity="560")
    task = start(client, publish(client, manual_scenario(client, setup, qty="560")))
    employees = [post(client, "employees", code=f"E-{i}", name=f"合成员工 {i}") for i in range(7)]
    quantities = dict(processed="560", good="560", normal="560")
    daily = post(client, "reports", document_no="TEAM-DAILY", business_date="2026-09-02", shift="测试白班", rows=[dict(task_id=task["id"], **quantities, allocations=[dict(task_allocation_id=task["allocations"][0]["id"], **quantities)], labor=[dict(employee_id=employee["id"], hours="8") for employee in employees])])
    rule = post(client, "rules", code="TEAM-RATE", label="测试班组规则", kind="wage", revision=1, effective_from="2026-09-01", parameters=dict(method="team_piece", basis="processed", rate="0.82", currency="CNY"), evidence="待确认测试规则")
    trial = post(client, "payroll/trial", document_no="WAGE-TRIAL", business_date="2026-09-02", rule_id=rule["id"])
    assert sum(Decimal(line["payroll_amount"]) for line in trial["lines"]) == Decimal("459.20")
    assert Decimal(daily["rows"][0]["processed"]) == 560
    blocked = client.post(f"/api/spray-operations/payroll/{trial['id']}/confirm", json=payload(expected_version=trial["version"]))
    assert blocked.status_code == 409 and blocked.json()["code"] == "rule_unconfirmed"
    post(client, f"rules/{rule['id']}/confirm", expected_version=1, business_date="2026-09-01", reason="合成测试确认")
    stale = client.post(f"/api/spray-operations/payroll/{trial['id']}/confirm", json=payload(expected_version=trial["version"]))
    assert stale.status_code == 409 and stale.json()["code"] == "stale_payroll"
    fresh = post(client, "payroll/trial", document_no="WAGE-FRESH", business_date="2026-09-02", rule_id=rule["id"])
    official = post(client, f"payroll/{fresh['id']}/confirm", expected_version=fresh["version"])
    assert official["status"] == "confirmed"


def test_close_period_previews_and_blocks_late_writes(client):
    preview = client.get("/api/spray-operations/periods/preview", params={"factory_id": "huaxing", "month": "2026-08"}).json()["data"]
    assert preview["blockers"] == []
    period = post(client, "periods/close", business_date="2026-09-01", month="2026-08", reason="空期间测试锁月", fingerprint=preview["fingerprint"])
    blocked = client.post("/api/spray-operations/expenses", json=payload(document_no="late", business_date="2026-08-31", category="测试", kind="expense", amount="1", currency="CNY", included=True, evidence="测试"))
    assert blocked.status_code == 409 and blocked.json()["code"] == "period_closed"
    reopened = post(client, f"periods/{period['id']}/reopen", expected_version=period["version"], business_date="2026-09-01", reason="合成重开验证")
    assert reopened["status"] == "open"


def test_financial_permissions_hide_rules_and_block_payroll(client):
    approved_rule(client, "wage", dict(method="team_piece", basis="processed", rate="9.99", currency="CNY"))
    client.spray_auth["user"] = user_with("read")
    assert "parameters" not in read(client, "rules")[0]
    assert client.get("/api/spray-operations/payroll", params={"factory_id": "huaxing"}).status_code == 403


def test_rounding_and_source_formula_fixtures():
    from app.services.spray_ops.finance import split_money
    assert sum(split_money(Decimal("1"), {str(i): Decimal(1) for i in range(7)}).values()) == 1
    rate, qty, workers = Decimal(".82"), Decimal(560), Decimal(7)
    n = rate * Decimal("1.27") * Decimal("1.2") * Decimal("1.13") / Decimal(".88")
    per_person = rate * qty / workers / Decimal(11) * Decimal("12.5")
    total = per_person * workers / Decimal(".88")
    assert abs(n - Decimal("1.60470272727272727")) < Decimal(".0000001")
    assert abs(total - Decimal("592.97520661157024")) < Decimal(".0000001")
    assert qty * Decimal("2.07") == Decimal("1159.20")
    assert Decimal("624") - Decimal("1270") * Decimal(".26") == Decimal("293.80")
