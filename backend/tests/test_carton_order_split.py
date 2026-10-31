from decimal import Decimal
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload, _submit_order, _freeze_carton_time

BASE = "/api/carton-procurement"


def setup(client, monkeypatch, *, explicit=False):
    login_as(client, "warehouse_keeper")
    _freeze_carton_time(monkeypatch)
    _ensure_dickie_customer(client)
    body = _order_payload()
    body.update(product_order_quantity="100", customer_po="ORIGINAL")
    body["lines"] = [body["lines"][0]]
    body["lines"][0].update(usage_quantity="10", unit_price="1")
    if explicit:
        body.update(quantity_basis="EXPLICIT", product_order_quantity=None)
        body["lines"][0].update(usage_quantity=None, required_quantity="10")
    result = client.post(BASE + "/orders", json=body)
    assert result.status_code == 201, result.text
    return _submit_order(client, result.json())


def latest(client):
    return client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"][0]


def context(client, order):
    response = client.get(BASE + f"/orders/{order['order_no']}/splits", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def split_body(order, *, pending="4", stock=(), product="40", contract="NEW-CONTRACT"):
    return {"factory_id": "huaxing", "request_id": uuid4().hex, "expected_revision": order["revision"],
        "reason": "按客户要求拆分合同", "targets": [{"contract_no": contract, "customer_po": "NEW-PO", "product_quantity": product,
        "lines": [{"order_line_id": order["lines"][0]["id"], "pending_quantity": pending, "stock": list(stock)}]}]}


def save(client, order, body):
    """Seed a pre-upgrade allocation; the public endpoint is now retired."""
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services.carton_order_split import create
    from app.schemas.carton_order_split import SplitCreate
    from sqlalchemy import select
    from unittest.mock import patch
    with SessionLocal() as db:
        user=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
        # Pre-upgrade data may contain several allocation plans. Bypass only
        # the new legacy-write hold while constructing that historical fixture.
        # Public creation/confirmation retirement is tested separately below.
        with patch('app.services.carton_print_split.guard_legacy'):
            return create(db,order['order_no'],SplitCreate(**body),user)


def action(client, plan, name, **changes):
    if name == 'confirm':
        # Fixture-only replay of a historical warehouse confirmation. Current
        # HTTP confirmation is separately asserted to reject new allocations.
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from app.services.carton_order_split import act
        from app.schemas.carton_order_split import SplitAction
        from sqlalchemy import select
        from httpx import Response
        from fastapi import HTTPException
        with SessionLocal() as db:
            user=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
            try:
                result=act(db,plan['id'],SplitAction(factory_id='huaxing',expected_revision=plan['revision'],reason='重建历史库存确认'),user)
                return Response(200,json=result)
            except HTTPException as error:
                return Response(error.status_code,json={'detail':error.detail})
    return client.post(BASE + f"/order-splits/{plan['id']}/{name}", json={
        "factory_id": "huaxing", "expected_revision": plan["revision"], "reason": "仓库已核对拆分归属", **changes})


def preview(client, order, qty):
    result = client.post(BASE + "/order-splits/receipt-preview", json={"factory_id": "huaxing", "lines": [
        {"order_line_id": order["lines"][0]["id"], "effective_quantity": qty}]})
    assert result.status_code == 200, result.text
    return result.json()


def receive(client, order, qty, *, price="1", token="", post=True, rejected="0"):
    result = client.post(BASE + "/receipts", json={"factory_id": "huaxing", "delivery_note_no": "DN-" + uuid4().hex,
        "delivery_date": "2026-08-05", "acceptance_date": "2026-08-05", "post_immediately": post,
        "request_id": uuid4().hex, "split_confirmation": token, "lines": [{"order_line_id": order["lines"][0]["id"],
        "delivered_quantity": qty, "received_quantity": qty, "rejected_quantity": rejected, "unit_price": price}]})
    return result


def balances(client):
    response = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def valuation():
    from app.db import SessionLocal
    from app.services.carton_inventory_valuation import load_valuation
    with SessionLocal() as db:
        return load_valuation(db, "huaxing")


def test_retired_allocation_writes_do_not_create_virtual_demand(monkeypatch):
    with make_client(monkeypatch) as client:
        order=setup(client,monkeypatch)
        result=client.post(BASE+f"/orders/{order['order_no']}/splits",json=split_body(order))
        assert result.status_code==409 and '停用' in result.text
        assert context(client,order)['plans']==[]
        historical=save(client,order,split_body(order))
        rejected=client.post(BASE+f"/order-splits/{historical['id']}/confirm",json={'factory_id':'huaxing','expected_revision':historical['revision'],'reason':'不能新增库存分配'})
        assert rejected.status_code==409


def test_legacy_receipts_are_blocked_without_allocation_token(monkeypatch):
    with make_client(monkeypatch) as client:
        order=setup(client,monkeypatch)
        plan=save(client,order,split_body(order))
        data=preview(client,order,'3')
        assert data=={'allocations':[],'confirmation':'','blocked_plans':[plan['id']]}
        for post in [True,False]:
            response=receive(client,order,'3',post=post,token='old-token')
            assert response.status_code==409 and '独立订单' in response.text
        assert balances(client)==[]
        assert action(client,plan,'cancel').status_code==200
        assert receive(client,order,'3').status_code==201


def test_historical_stock_pairs_keep_cost_and_can_be_reversed_together(monkeypatch):
    with make_client(monkeypatch) as client:
        order=setup(client,monkeypatch)
        assert receive(client,order,'3',price='1').status_code==201
        assert receive(client,order,'6',price='2').status_code==201
        order=latest(client)
        position=context(client,order)['lines'][0]['positions'][0]
        stock=[{'location_id':position['location_id'],'expected_position_revision':position['position_revision'],'quantity':'4'}]
        plan=save(client,order,split_body(order,pending='0',stock=stock))
        moved=action(client,plan,'confirm'); assert moved.status_code==200,moved.text
        plan=moved.json()
        assert valuation().errors==[]
        assert abs(sum(pool.amount for pool in valuation().balances.values())-15)<Decimal('1e-24')
        cancelled=action(client,plan,'cancel'); assert cancelled.status_code==200,cancelled.text
        assert valuation().errors==[]
        assert abs(sum(pool.amount for pool in valuation().balances.values())-15)<Decimal('1e-24')
