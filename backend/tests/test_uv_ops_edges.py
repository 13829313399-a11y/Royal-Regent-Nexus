from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from secrets import token_urlsafe
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from test_uv_ops import client, post, read, payload, setup_task, confirm, user_with
from app.models import uv_operations as m
from app.services.uv_operations import common as c, exports


def test_uv_ops_concurrent_same_operation_commits_once(client):
    body = payload(code="RACE", name="合成并发机台")
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: client.post("/api/uv-operations/machines", json=body), range(2)))
    assert [x.status_code for x in results] == [200,200]
    assert results[0].json()["data"]["id"] == results[1].json()["data"]["id"]
    assert len(read(client,"machines")) == 1


def test_uv_ops_payroll_freezes_subsequent_output(client):
    data = setup_task(client, quantity=20)
    result = confirm(client, data, good=10, rework=0)
    post(client,"participations", shift_id=data["shift"]["id"], task_id=data["task"]["id"], employee_id="worker-a", employee_name="合成员工", start_at="2026-09-23T08:00:00+08:00", end_at="2026-09-23T09:00:00+08:00")
    accrued = post(client,"wages/confirm", shift_id=data["shift"]["id"], task_id=data["task"]["id"])
    assert Decimal(accrued["accrual"]["payroll_amount"]) == Decimal("0.15")
    response = client.post("/api/uv-operations/production/confirm", json=payload(expected_version=result["batch"]["version"], task_id=data["task"]["id"], batch_id=data["batch"]["id"], shift_id=data["shift"]["id"], pass_index=1, processed=10,good=10,rework=0,scrap=0,pending=0,evidence="合成重复核数"))
    assert response.status_code == 409 and response.json()["code"] == "payroll_frozen"


def test_uv_ops_cross_date_quality_has_opening_balance_and_missing_payroll(client):
    data = setup_task(client, quantity=5)
    result = confirm(client,data,good=0,rework=0,pending=5)
    shift = post(client,"shifts", name="次日合成班", business_date="2026-09-24",start_at="2026-09-24T08:00:00+08:00",end_at="2026-09-24T16:00:00+08:00")
    post(client,"quality/resolve",batch_id=data["batch"]["id"],shift_id=shift["id"],expected_version=result["batch"]["version"],quantity=5,disposition="good",evidence="合成次日转良")
    result = client.get("/api/uv-operations/reports",params=dict(factory_id="huakang-a",start_date="2026-09-24",end_date="2026-09-24")).json()["data"]
    assert result["totals"]["pending"] == 0
    assert result["coverage"]["state"] == "partial"
    assert {x["code"] for x in result["cost_missing"]} == {"missing_payroll","missing_cost_evidence"}
    assert read(client,"tasks/"+data["task"]["id"])["status"] == "completed"


def test_uv_ops_concurrent_ink_and_transfer_not_consumption(client):
    sku = post(client,"ink/skus",code="INK-X",supplier="合成供应商",model="X",ink_family="hard",color="cyan",capacity_ml="100")
    stock = post(client,"ink/movements",sku_id=sku["id"],location="store",kind="receipt",quantity_ml="100",cost_value="20",currency="CNY",business_date="2026-09-23",evidence="合成入库")
    def consume(_):
        return client.post("/api/uv-operations/ink/movements",json=payload(sku_id=sku["id"],location="store",expected_version=stock["balance"]["version"],kind="consume",quantity_ml="100",currency="CNY",business_date="2026-09-23",evidence="合成抢占最后库存"))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(consume, range(2)))
    assert sorted(x.status_code for x in results) == [200,409]
    assert Decimal(read(client,"ink/balances")[0]["quantity_ml"]) == 0


def setup_agent(client):
    machine = post(client,"machines",code="SYN-M",name="合成采集机台")
    created = post(client,"agents",name="合成代理")
    body = dict(pairing_code=created["pairing_code"], enrollment_id=uuid4().hex, token=token_urlsafe(48))
    response = client.post("/api/internal/uv-agent/enroll",json=body)
    assert response.status_code == 200, response.text
    assert client.post("/api/internal/uv-agent/enroll",json=body).json() == response.json()
    assert client.post("/api/internal/uv-agent/enroll",json=body|dict(token=token_urlsafe(48),enrollment_id=uuid4().hex)).status_code == 401
    source = post(client,"sources",agent_id=created["agent"]["id"],machine_id=machine["id"],source_id="synthetic-source",adapter_type="simulator")
    return machine,created,source,{"Authorization":"Bearer "+body["token"]}


def event(machine, source, sequence=1, native="synthetic-job-1",count="0",kind="job_start"):
    return dict(event_id=uuid4().hex,stream_id="synthetic-stream",sequence=sequence,machine_id=machine["id"],source_id=source["source_id"],binding_version=source["binding_version"],kind=kind,observed_at=f"2026-09-23T08:00:{sequence:02d}+08:00",adapter_type="simulator",adapter_version="1.0.0",source_identity=dict(generation="gen-1"),evidence=dict(synthetic=True),payload=dict(native_job_id=native,count=count,count_unit="board",counter_mode="cumulative",ink_total_ml=None,work_state="running"))


def test_uv_ops_agent_partial_batch_retransmit_payload_conflict_and_counts(client):
    machine,created,source,headers = setup_agent(client)
    one = event(machine,source)
    two = event(machine,source,2,count="1")
    three = event(machine,source,3,count="3",kind="job_complete")
    body = dict(schema_version=1,batch_id=uuid4().hex,events=[one,dict(bad=True),two,three])
    response = client.post("/api/internal/uv-agent/events/batch",headers=headers,json=body)
    assert response.status_code == 200,response.text
    assert [x["status"] for x in response.json()["results"]] == ["persisted","rejected","persisted","persisted"]
    response = client.post("/api/internal/uv-agent/events/batch",headers=headers,json=body)
    assert [x["status"] for x in response.json()["results"]] == ["duplicate","rejected","duplicate","duplicate"]
    run = read(client,"runs")[0]
    assert Decimal(run["raw_count"]) == 3 and run["state"] == "completed"
    assert not read(client,"production")
    altered = one|dict(payload=one["payload"]|dict(count="9"))
    response=client.post("/api/internal/uv-agent/events/batch",headers=headers,json=body|dict(events=[altered]))
    assert response.json()["results"][0]["code"] == "event_payload_conflict"
    other=event(machine,source,4,native="synthetic-job-2")
    client.post("/api/internal/uv-agent/events/batch",headers=headers,json=body|dict(events=[other]))
    assert len(read(client,"runs")) == 2


def test_uv_ops_import_duplicate_and_export_formula_safety(client):
    content = b'code,name,customer\n0017,=1+1,synthetic\n'
    def preview():
        response=client.post("/api/uv-operations/imports/preview",data=dict(factory_id="huakang-a",template="products-v1",units_confirmed="true"),files={"file":("products.csv",content,"text/csv")})
        assert response.status_code == 200,response.text
        return response.json()["data"]
    job=preview()
    post(client,"imports/"+job["id"]+"/commit",expected_version=job["version"])
    job=preview()
    result=post(client,"imports/"+job["id"]+"/commit",expected_version=job["version"])
    assert result["duplicates"] == 1 and result["imported"] == 0
    assert read(client,"products")[0]["code"] == "0017"


def test_uv_ops_quote_theoretical_and_discrete_capacity(client):
    response=client.post("/api/uv-operations/quotes/calculate",json=dict(factory_id="huakang-a",available_seconds="100",cycle_seconds="30",pieces_per_board=12,cost_amount="120",currency="CNY",pricing_mode="markup",ratio="0.4"))
    assert response.status_code == 200,response.text
    result=response.json()["data"]
    assert Decimal(result["theoretical_quantity"]) == 40 and result["quantity"] == 36
    assert Decimal(result["cost_unit"]) == 3 and Decimal(result["quoted_unit_rate"]) == Decimal("4.2")
