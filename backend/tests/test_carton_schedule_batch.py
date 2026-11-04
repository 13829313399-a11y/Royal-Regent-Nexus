"""Real schedule imports and atomic ordinary orders, with independent row quantities."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare
from test_carton_procurement_api import _order_payload
from test_carton_schedule_coverage_integrated import upload, row, source

BASE = "/api/carton-procurement"
URL = BASE + "/orders/from-schedule-batch"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    monkeypatch.setenv("ONLINE_DOCUMENTS_ENABLED", "false")
    monkeypatch.setenv("COLLABORATION_ENABLED", "false")


def setup(client, monkeypatch, *, second_packing=12, second_item="57520", due="2026-12-02"):
    prepare(client)
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 11, 4, 12))
    first = row("53607", quantity=4843, due="2026-12-01")
    second = row("53608", quantity=588, due=due)
    first[5] = "57520"; second[5] = second_item
    first[8] = 6; second[8] = second_packing
    batch = upload(client, "batch.xlsx", [first, second])
    body = dict(factory_id="huaxing", request_id=uuid4().hex,
        sources=[source(batch, "53607"), source(batch, "53608")], planned_due_date="2026-11-20",
        lines=[_order_payload()["lines"][0]])
    return batch, body


def orders(client):
    return client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"]


def test_creates_independent_calculated_orders_without_sending_and_replays(monkeypatch):
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch)
        result = client.post(URL, json=body)
        assert result.status_code == 201, result.text
        rows = result.json()
        assert len({r["id"] for r in rows}) == 2
        assert len({r["order_no"] for r in rows}) == 2
        assert [r["customer_po"] for r in rows] == ["PO-53607", "PO-53608"]
        assert [r["customer_due_date"] for r in rows] == ["2026-12-01", "2026-12-02"]
        assert [Decimal(r["lines"][0]["usage_quantity"]) for r in rows] == [6, 12]
        assert [Decimal(r["lines"][0]["required_quantity"]) for r in rows] == [808, 49]
        assert all(r["due_date"] == "2026-11-20" and r["plan_date_manual"] and r["status"] == "CONFIRMED" for r in rows)
        assert all("batch.xlsx" in r["note"] and "正单" in r["note"] for r in rows)
        assert client.post(URL, json=body).json() == rows
        assert len(orders(client)) == 2
        changed = deepcopy(body); changed["planned_due_date"] = "2026-11-21"
        assert client.post(URL, json=changed).status_code == 409
        changed = deepcopy(body); changed["request_id"] = uuid4().hex
        assert client.post(URL, json=changed).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent, CartonPurchaseOrderIssue, CartonInventoryMovement
        from sqlalchemy import select, func
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonPurchaseOrderIssue)) == 0
            assert db.scalar(select(func.count()).select_from(CartonInventoryMovement)) == 0
            assert db.scalar(select(func.count()).select_from(CartonAuditEvent).where(CartonAuditEvent.event_type == "SCHEDULE_ORDER_LINKED")) == 2


@pytest.mark.parametrize("failure", ["other_item", "bad_packing", "missing_due", "other_factory", "duplicate_source",
    "manual_quantity", "missing_spec", "missing_supplier", "stale_config"])
def test_invalid_batch_never_creates_partial_orders(monkeypatch, failure):
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch,
            second_item="OTHER" if failure == "other_item" else "57520",
            second_packing="待定" if failure == "bad_packing" else 12,
            due="" if failure == "missing_due" else "2026-12-02")
        if failure == "other_factory": body["factory_id"] = "huakang-a"
        elif failure == "duplicate_source": body["sources"][1] = body["sources"][0]
        elif failure == "manual_quantity": body["lines"][0]["required_quantity"] = 5
        elif failure == "missing_spec": body["lines"][0]["specification"] = ""
        elif failure == "stale_config": body.update(master_config_id="MISSING", master_config_revision=1)
        elif failure == "missing_supplier":
            from app.db import SessionLocal
            from app.models.carton_procurement import CartonSupplier
            from sqlalchemy import update
            with SessionLocal() as db:
                db.execute(update(CartonSupplier).where(CartonSupplier.factory_id == "huaxing").values(status="INACTIVE"))
                db.commit()
        response = client.post(URL, json=body)
        assert response.status_code in {404, 409, 422}, response.text
        assert orders(client) == []


def test_inner_outer_and_per_carton_each_use_their_own_row(monkeypatch):
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch, second_packing="2/12")
        # Both rows must explicitly have inner demand before using one shared config.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonImportBatch
        import json
        with SessionLocal() as db:
            source_batch = db.get(CartonImportBatch, batch["id"])
            data = json.loads(source_batch.parse_summary_json)
            data["rows"][0]["carton_rule"] = "3/6"
            source_batch.parse_summary_json = json.dumps(data)
            db.commit()
        outer = body["lines"][0]
        inner = {**outer, "packaging_type": "内箱"}
        divider = {**outer, "packaging_type": "配卡", "quantity_rule": {"mode": "PER_CARTON", "carton_line_no": 1, "per_carton_quantity": 2}}
        body["lines"] = [outer, inner, divider]
        response = client.post(URL, json=body)
        assert response.status_code == 201, response.text
        assert [[Decimal(line["required_quantity"]) for line in order["lines"]] for order in response.json()] == [[808, 1615, 1616], [49, 294, 98]]


def test_second_creation_failure_rolls_back_first_order_and_source_link(monkeypatch):
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch)
        from app.services import carton_procurement as core
        from fastapi import HTTPException
        original = core.create_order
        def reject_second(db, payload, user, **kwargs):
            if payload.contract_no == "53608":
                raise HTTPException(409, "订单规则已变更")
            return original(db, payload, user, **kwargs)
        monkeypatch.setattr(core, "create_order", reject_second)
        result = client.post(URL, json=body)
        assert result.status_code == 409, result.text
        assert orders(client) == []
        monkeypatch.setattr(core, "create_order", original)
        assert client.post(URL, json=body).status_code == 201


def test_permission_is_refreshed_inside_lock(monkeypatch):
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch)
        from app.api import carton_procurement as api
        from fastapi import HTTPException
        original = api._ensure_permission
        calls = 0
        def revoked(db, user, permission, factory):
            nonlocal calls
            if permission == "carton_procurement:order_write":
                calls += 1
                if calls > 1: raise HTTPException(403, "权限已撤回")
            return original(db, user, permission, factory)
        monkeypatch.setattr(api, "_ensure_permission", revoked)
        result = client.post(URL, json=body)
        assert result.status_code == 403, result.text
        assert orders(client) == []


@pytest.mark.parametrize("failure", ["marked", "replaced", "other_customer", "stale_revision", "customer_scope"])
def test_live_source_and_master_changes_block_whole_batch(monkeypatch, failure):
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch)
        if failure == "marked":
            from test_carton_schedule_coverage_integrated import mark
            mark(client, batch, "53608")
        elif failure == "replaced":
            first = row("53607", quantity=5000, due="2026-12-01"); first[5] = "57520"
            second = row("53608", quantity=588, due="2026-12-02"); second[5] = "57520"; second[8] = 12
            upload(client, "newer.xlsx", [first, second])
        elif failure == "customer_scope":
            from app.services import carton_schedule_batch as service
            from fastapi import HTTPException
            def denied(*args, **kwargs): raise HTTPException(403, "无此客户责任权限")
            monkeypatch.setattr(service, "ensure_customer_operation", denied)
        else:
            import json
            from app.db import SessionLocal
            from app.models.carton_procurement import CartonImportBatch
            from app.models.carton_master import CartonMasterRecord
            if failure == "other_customer":
                response = client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": "另一客户"})
                assert response.status_code == 201, response.text
                with SessionLocal() as db:
                    record = db.get(CartonImportBatch, batch["id"])
                    data = json.loads(record.parse_summary_json)
                    data["rows"][1]["schedule_customer_code"] = response.json()["customer_code"]
                    record.parse_summary_json = json.dumps(data)
                    db.commit()
            else:
                with SessionLocal() as db:
                    db.add(CartonMasterRecord(id="BATCH-CONFIG", factory_id="huaxing", kind="CONFIG", identity="batch-config",
                        customer_code="DICKIE", code="57520", status="ACTIVE", revision=2,
                        data_json=json.dumps({"lines": body["lines"]}), updated_at="2026-11-04"))
                    db.commit()
                body.update(master_config_id="BATCH-CONFIG", master_config_revision=1)
        response = client.post(URL, json=body)
        assert response.status_code in {403, 409, 422}, response.text
        assert orders(client) == []


def test_supplier_acceptance_and_receipt_stay_independent(monkeypatch):
    from test_carton_supplier_portal import setup_portal, supplier_login, ship_payload, receive_payload
    from test_carton_procurement_api import _submit_order
    supplier_base = "/api/carton-supplier"
    with make_client(monkeypatch) as client:
        batch, body = setup(client, monkeypatch)
        created = client.post(URL, json=body)
        assert created.status_code == 201, created.text
        first, second = created.json()
        setup_portal(client)
        login_as(client, "admin")
        _submit_order(client, first); _submit_order(client, second)
        supplier_login(client)
        def workspace():
            response = client.get(supplier_base + "/workspace", params={"factory_id": "huaxing"})
            assert response.status_code == 200, response.text
            return {o["order_no"]: o for o in response.json()["orders"]}
        before = workspace()
        first_live = before[first["order_no"]]
        for paper in first_live["lines"]:
            accepted = client.put(supplier_base + f"/papers/{paper['id']}/commitment", json=dict(
                factory_id="huaxing", issue_id=first_live["issue_id"], expected_revision=0, promised_date="2026-11-20"))
            assert accepted.status_code == 200, accepted.text
        after = workspace()
        assert after[second["order_no"]]["lines"] == before[second["order_no"]]["lines"]
        body = ship_payload(after[first["order_no"]]); body["delivery_date"] = "2026-11-04"
        sent = client.post(supplier_base + "/shipments", json=body)
        assert sent.status_code == 201, sent.text
        shipment = sent.json()
        login_as(client, "admin")
        receipt = receive_payload(client, shipment); receipt["acceptance_date"] = "2026-11-04"
        posted = client.post(supplier_base + f"/internal/shipments/{shipment['id']}/receive", json=receipt)
        assert posted.status_code == 200, posted.text
        actual = {o["id"]: o for o in orders(client)}
        assert actual[first["id"]]["status"] == "PARTIALLY_RECEIVED"
        assert actual[second["id"]]["status"] == "PENDING_SUPPLIER"
        assert all(Decimal(p["received_quantity"]) == 0 for p in actual[second["id"]]["lines"])
        receipts = client.get(BASE + "/receipts", params={"factory_id": "huaxing"}).json()["items"]
        posted_receipt = next(r for r in receipts if r["id"] == posted.json()["receipt_id"])
        assert {p["order_line_id"] for p in posted_receipt["lines"]} == {p["id"] for p in first["lines"]}


def test_duplicate_business_identity_requires_individual_review(monkeypatch):
    with make_client(monkeypatch) as client:
        _, body = setup(client, monkeypatch)
        original = row("DUPLICATE", quantity=60, due="2026-12-01"); original[5] = "57520"
        duplicated = upload(client, "duplicates.xlsx", [original, original])
        rows = duplicated["parse_summary"]["rows"]
        assert all(r.get("schedule_identity_duplicate") for r in rows)
        body["sources"] = [dict(batch_id=duplicated["id"], source_sheet=r["source_sheet"], source_row=r["source_row"]) for r in rows]
        response = client.post(URL, json=body)
        assert response.status_code == 409, response.text
        assert orders(client) == []


def override(body, index, lines):
    return {**body["sources"][index], "lines": lines}


def test_per_order_manual_quantities_weights_rush_and_note_follow_normal_rules(monkeypatch):
    with make_client(monkeypatch) as client:
        _, body = setup(client, monkeypatch)
        outer = body["lines"][0]
        outer.update(net_weight_kg="1.5", gross_weight_kg="2.5")
        card = {**outer, "packaging_type": "平卡", "quantity_rule": {"mode": "PER_CARTON", "carton_line_no": 1, "per_carton_quantity": 3}}
        other = {**outer, "packaging_type": "压线卡", "usage_quantity": "240", "quantity_rule": {"mode": "PACKING"}}
        body.update(lines=[outer, card, other], note="统一备注：请按各订单分别送货", rush=True, rush_reason="客户要求提前")
        body["order_overrides"] = [
            override(body, 0, [{"line_no": 1, "manual_quantity": "10", "net_weight_kg": "5.1", "gross_weight_kg": "6.2"}]),
            override(body, 1, [{"line_no": 1, "manual_quantity": None, "net_weight_kg": None},
                               {"line_no": 2, "manual_quantity": "7"}])]
        response = client.post(URL, json=body)
        assert response.status_code == 201, response.text
        first, second = response.json()
        assert [[Decimal(p["required_quantity"]) for p in o["lines"]] for o in (first, second)] == [[10, 30, 21], [49, 7, 3]]
        assert Decimal(first["lines"][0]["net_weight_kg"]) == Decimal("5.1")
        assert Decimal(first["lines"][0]["gross_weight_kg"]) == Decimal("6.2")
        assert second["lines"][0]["net_weight_kg"] is None
        assert Decimal(second["lines"][0]["gross_weight_kg"]) == Decimal("2.5")
        assert Decimal(first["lines"][1]["net_weight_kg"]) == Decimal("1.5")
        assert all(o["rush"] and o["rush_reason"] == "客户要求提前" for o in (first, second))
        assert all(o["note"].startswith("统一备注：请按各订单分别送货\n来源排期：") for o in (first, second))
        assert [Decimal(o["product_order_quantity"]) for o in (first, second)] == [4843, 588]
        assert client.post(URL, json=body).json() == response.json()
        # Omitting a clear operation inherits common weight: not the same request.
        changed = deepcopy(body)
        del changed["order_overrides"][1]["lines"][0]["net_weight_kg"]
        assert client.post(URL, json=changed).status_code == 409
        assert len(orders(client)) == 2


def test_explicit_null_clears_master_weights_while_omission_inherits(monkeypatch):
    with make_client(monkeypatch) as client:
        _, body = setup(client, monkeypatch, second_packing=6)
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        import json
        config_line = {**body["lines"][0], "usage_quantity": "6", "net_weight_kg": "9", "gross_weight_kg": "10"}
        with SessionLocal() as db:
            db.add(CartonMasterRecord(id="WEIGHT-CONFIG", factory_id="huaxing", kind="CONFIG", identity="weight-config",
                code="57520", status="ACTIVE", revision=1, data_json=json.dumps({"lines": [config_line]})))
            db.commit()
        body.update(master_config_id="WEIGHT-CONFIG", master_config_revision=1,
            order_overrides=[override(body, 0, [{"line_no": 1, "net_weight_kg": None, "gross_weight_kg": None}])])
        invalid = deepcopy(body); invalid["request_id"] = uuid4().hex
        invalid["order_overrides"] = [override(invalid, 0, [{"line_no": 1, "gross_weight_kg": "8"}])]
        rejected = client.post(URL, json=invalid)
        assert rejected.status_code == 422, rejected.text
        assert orders(client) == []
        response = client.post(URL, json=body)
        assert response.status_code == 201, response.text
        first, second = response.json()
        assert first["lines"][0]["net_weight_kg"] is None and first["lines"][0]["gross_weight_kg"] is None
        assert Decimal(second["lines"][0]["net_weight_kg"]) == 9
        assert Decimal(second["lines"][0]["gross_weight_kg"]) == 10
        changed = deepcopy(body)
        changed["lines"][0]["net_weight_kg"] = None
        assert client.post(URL, json=changed).status_code == 409
        assert client.post(URL, json=body).json() == response.json()


def test_invalid_overrides_and_rules_reject_whole_batch(monkeypatch):
    with make_client(monkeypatch) as client:
        _, base = setup(client, monkeypatch)
        cases = []
        unknown = override(base, 1, [{"line_no": 1, "manual_quantity": 2}]); unknown["source_row"] = 9999
        cases.append({"order_overrides": [unknown]})
        one = override(base, 1, [{"line_no": 1, "manual_quantity": 2}])
        cases.append({"order_overrides": [one, one]})
        cases.append({"order_overrides": [override(base, 1, [{"line_no": 1}, {"line_no": 1}])]})
        for line in ({"line_no": 2, "manual_quantity": 1}, {"line_no": 1, "manual_quantity": 0},
                     {"line_no": 1, "manual_quantity": -1}, {"line_no": 1, "gross_weight_kg": -1},
                     {"line_no": 1, "net_weight_kg": 8, "gross_weight_kg": 7}):
            cases.append({"order_overrides": [override(base, 1, [line])]})
        # A partial per-order override must be checked against the inherited common value.
        cases.append({"lines": [{**base["lines"][0], "net_weight_kg": 8, "gross_weight_kg": 10}],
            "order_overrides": [override(base, 1, [{"line_no": 1, "gross_weight_kg": 7}])]})
        card = {**base["lines"][0], "packaging_type": "平卡"}
        cases.append({"lines": [base["lines"][0], card]})  # no declared rule
        cases.append({"lines": [base["lines"][0], {**card, "quantity_rule": {"mode": "PER_CARTON", "carton_line_no": 2, "per_carton_quantity": 1}}]})
        for changes in cases:
            body = {**deepcopy(base), **changes, "request_id": uuid4().hex}
            response = client.post(URL, json=body)
            assert response.status_code == 422, (changes, response.text)
            assert orders(client) == []
        # Rejected writes do not claim either source or leave partial orders behind.
        response = client.post(URL, json=base)
        assert response.status_code == 201, response.text


def test_legacy_request_fingerprint_and_null_override_semantics():
    from app.schemas.carton_schedule_batch import ScheduleBatchCreate
    from app.services.carton_schedule_batch import request_content
    original = dict(factory_id="huaxing", request_id="legacy-request-1234",
        sources=[dict(batch_id="B", source_sheet="ITEM", source_row=2)], planned_due_date="2026-12-01",
        lines=[_order_payload()["lines"][0]])
    model = ScheduleBatchCreate.model_validate(original)
    old_keys = {"factory_id", "request_id", "sources", "planned_due_date", "lines", "master_config_id", "master_config_revision"}
    assert request_content(model) == model.model_dump(mode="json", include=old_keys)
    omitted = {**original, "order_overrides": [override(original, 0, [{"line_no": 1}])]}
    explicit = {**original, "order_overrides": [override(original, 0, [{"line_no": 1, "net_weight_kg": None}])]}
    assert request_content(ScheduleBatchCreate.model_validate(omitted)) != request_content(ScheduleBatchCreate.model_validate(explicit))
    common_clear = deepcopy(original); common_clear["lines"][0]["gross_weight_kg"] = None
    assert request_content(ScheduleBatchCreate.model_validate(original)) != request_content(ScheduleBatchCreate.model_validate(common_clear))
