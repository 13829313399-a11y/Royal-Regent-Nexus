from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _order_payload, _ensure_dickie_customer, _submit_order
from test_carton_transaction_guards_api import BASE, draft, confirm, outbound


def prepare(client):
    login_as(client, "admin")
    _ensure_dickie_customer(client)
    login_as(client, "admin")


def create(client, **changes):
    data = {**_order_payload(), **changes}
    response = client.post(BASE + "/orders", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def read(client):
    response = client.get(BASE + "/master-data", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return response.json()


def payload(row, **changes):
    return {"factory_id": "huaxing", "kind": row["kind"], "customer_code": row["customer_code"],
            "code": row["code"], "data": row["data"], "status": row["status"], "preferred": row["preferred"],
            "expected_revision": row["revision"], "reason": "主管核实资料", **changes}


def legacy_grant(user_id, warehouses):
    """Seed old evidence directly: the public ACCESS editor is retired."""
    import json
    from app.db import SessionLocal
    from app.models.carton_master import CartonMasterRecord
    with SessionLocal() as db:
        row=db.get(CartonMasterRecord, "LEGACY-ACCESS")
        if row is None:
            row=CartonMasterRecord(id="LEGACY-ACCESS",factory_id="huaxing",kind="ACCESS",identity="legacy-access",code=user_id)
            db.add(row)
        row.data_json=json.dumps({"warehouses":warehouses})
        db.commit()


def test_history_enrichment_privileged_edits_variants_and_concurrency(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        pending = create(client)
        assert read(client)["records"] == []  # persisted but not formally locked
        original = _submit_order(client, pending)
        config = next(r for r in read(client)["records"] if r["kind"] == "CONFIG")
        assert len(config["data"]["lines"]) == 2
        assert config["sources"][0]["order_no"] == original["order_no"]
        changed = deepcopy(config["data"])
        changed["product_name"] = "主管更正物品名"
        saved = client.patch(BASE + "/master-data/" + config["id"], json=payload(config, data=changed, preferred=True))
        assert saved.status_code == 200, saved.text
        assert client.post(BASE + "/master-data", json=payload(saved.json(), expected_revision=0)).status_code == 409
        login_as(client, "warehouse_keeper")
        assert read(client)["can_manage"]
        assert client.patch(BASE + "/master-data/" + config["id"], json=payload(saved.json(), factory_id="huadeng")).status_code == 403
        assert client.post(BASE + "/inventory/locations", json={"factory_id": "huaxing", "warehouse": "一仓", "bin_code": "A"}).status_code == 201
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: read(client), range(2)))
        for result in results:
            current = next(r for r in result["records"] if r["id"] == config["id"])
            assert current["data"]["product_name"] == changed["product_name"]
            assert current["preferred"]
            assert len(current["sources"]) == 1
        second = _order_payload()
        second["lines"] = deepcopy(second["lines"])
        second["lines"][0]["usage_quantity"] = "100"
        other = _submit_order(client, create(client, **second))
        assert len([r for r in read(client)["records"] if r["kind"] == "CONFIG"]) == 2
        login_as(client, "admin")
        inactive = client.patch(BASE + "/master-data/" + config["id"], json=payload(saved.json(), status="INACTIVE"))
        assert inactive.status_code == 200
        assert client.patch(BASE + "/master-data/" + config["id"], json=payload(saved.json())).status_code == 409
        final = read(client)
        assert len([r for r in final["records"] if r["kind"] == "CONFIG"]) == 2
        assert next(r for r in final["records"] if r["id"] == config["id"])["status"] == "INACTIVE"
        _submit_order(client, create(client, product_name=changed["product_name"]))
        configs = [r for r in read(client)["records"] if r["kind"] == "CONFIG"]
        assert len(configs) == 2  # corrected inactive configuration cannot be resurrected
        assert client.post(BASE + "/orders", json={**_order_payload(), "master_config_id": config["id"], "master_config_revision": inactive.json()["revision"]}).status_code == 409
        historical = client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"]
        assert next(r for r in historical if r["id"] == original["id"])["product_name"] == original["product_name"]
        assert other["lines"][0]["required_quantity"] == "36.0000"


def test_due_rules_keep_old_snapshots_and_enforce_number_rules(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        old = create(client, customer_due_date="2026-08-15")
        rule_payload = {"factory_id": "huaxing", "kind": "RULE", "customer_code": "DICKIE", "data": {"lead_days": 5, "customer_days": 10, "contract_rule": {"mode": "AUTO", "prefix": "LEGACY"}}, "reason": "客户规则调整"}
        result = client.post(BASE + "/master-data", json=rule_payload)
        assert result.status_code == 201, result.text
        assert result.json()["data"]["contract_rule"]["mode"] == "AUTO"
        assert result.json()["data"]["item_rule"]["mode"] == "AUTO"
        new = create(client, customer_due_date="2026-08-15")
        assert new["due_date"] == "2026-08-10" and new["safety_lead_days"] == 5
        update = {**_order_payload(), "customer_due_date": "2026-08-16", "expected_revision": old["revision"], "reason": "修改客户交期"}
        updated = client.patch(BASE + f"/orders/{old['order_no']}", json=update)
        assert updated.status_code == 200, updated.text
        assert updated.json()["safety_lead_days"] == 3 and updated.json()["due_date"] == "2026-08-13"
        appended = client.post(BASE + f"/orders/{old['order_no']}/append", json={"factory_id": "huaxing", "expected_revision": updated.json()["revision"], "additional_quantity": "10", "customer_due_date": "2026-08-17", "reason": "追加客户订单"})
        assert appended.status_code == 200, appended.text
        assert appended.json()["safety_lead_days"] == 3 and appended.json()["due_date"] == "2026-08-14"
        urgent = create(client, customer_due_date="2026-08-06")
        assert urgent["due_date"] == "2026-08-05"
        rule = result.json()
        data = {**rule["data"], "contract_rule": {"mode": "BLOCK", "prefix": "NEW", "characters": "ALNUM_DASH", "min_length": 3, "max_length": 20}}
        assert client.patch(BASE + "/master-data/" + rule["id"], json=payload(rule, data=data)).status_code == 200
        assert client.post(BASE + "/orders", json={**_order_payload(), "contract_no": "WRONG"}).status_code == 422
        # A new format rule must not block routine updates on an older valid order.
        old_update = {**_order_payload(), "customer_due_date": "2026-08-16", "note": "保留原单修改备注", "expected_revision": new["revision"], "reason": "核实交货说明"}
        assert client.patch(BASE + f"/orders/{new['order_no']}", json=old_update).status_code == 200


def test_location_permissions_deactivation_workshop_and_reversal(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        order = _submit_order(client, create(client))
        loc = client.post(BASE + "/inventory/locations", json={"factory_id": "huaxing", "warehouse": "一仓", "bin_code": "A", "reason": "新增纸箱分区仓位"}).json()
        events = client.get(BASE + "/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        assert next(e for e in events if e["entity_id"] == loc["id"])["detail"]["reason"] == "新增纸箱分区仓位"
        workshop = client.post(BASE + "/master-data", json={"factory_id": "huaxing", "kind": "WORKSHOP", "code": "装配车间", "data": {}, "reason": "新增领用车间"})
        assert workshop.status_code == 201, workshop.text
        receipt = draft(client, order, 10, lines=[{"order_line_id": order["lines"][0]["id"], "delivered_quantity": "10", "received_quantity": "10", "unit_price": "2", "location_allocations": [{"location_id": loc["id"], "quantity": "10"}]}])
        assert receipt.status_code == 201, receipt.text
        assert confirm(client, receipt.json()).status_code == 200
        change = {"factory_id": "huaxing", "warehouse": "一仓", "bin_code": "A-NEW", "status": "INACTIVE", "expected_revision": 1, "reason": "旧仓位停用"}
        stopped = client.patch(BASE + "/inventory/locations/" + loc["id"], json=change)
        assert stopped.status_code == 200, stopped.text
        assert draft(client, order, 1, lines=[{"order_line_id": order["lines"][0]["id"], "received_quantity": "1", "location_allocations": [{"location_id": loc["id"], "quantity": "1"}]}]).status_code == 422
        login_as(client, "warehouse_keeper")
        issue = client.post(BASE + "/inventory/movements", json=outbound(order, 2, location_id=loc["id"], workshop_id=workshop.json()["id"], issue_kind="USAGE"))
        assert issue.status_code == 201, issue.text
        assert issue.json()["workshop_name"] == "装配车间"
        profile = client.get('/api/auth/me').json()
        login_as(client, "admin")
        grant = client.post(BASE + "/master-data", json={"factory_id": "huaxing", "kind": "ACCESS", "code": profile["id"], "data": {"warehouses": ["一仓"]}, "reason": "授权仓库负责人"})
        assert grant.status_code == 422, grant.text
        login_as(client, "warehouse_keeper")
        assert client.patch(BASE + "/inventory/locations/" + loc["id"], json={**change, "expected_revision": 2, "factory_id": "huadeng", "warehouse": "二仓"}).status_code == 403
        allowed = client.patch(BASE + "/inventory/locations/" + loc["id"], json={**change, "expected_revision": 2, "bin_code": "A-LAST"})
        assert allowed.status_code == 200, allowed.text
        reversed_issue = client.post(BASE + f"/inventory/movements/{issue.json()['id']}/reverse", json={"factory_id": "huaxing", "reason": "纠正领用登记"})
        assert reversed_issue.status_code == 201, reversed_issue.text
        assert reversed_issue.json()["workshop_name"] == "装配车间"


def test_frozen_templates_persist_and_only_explicit_block_rejects(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        template = {"mode": "AUTO", "templates": ["SC{9}/{3,4}"], "frozen": True,
                    "source": "MANUAL", "sample_count": 2,
                    "sample_text": "SC700149169/600\nSC700143393/1600"}
        response = client.post(BASE + "/master-data", json={"factory_id": "huaxing", "kind": "RULE",
            "customer_code": "DICKIE", "data": {"contract_rule": template}, "reason": "确认客户编号格式"})
        assert response.status_code == 201, response.text
        rule = response.json()
        # A formally confirmed anomaly enriches history but cannot change the frozen rule.
        _submit_order(client, create(client, contract_no="SC700149169/60000"))
        current = next(r for r in read(client)["records"] if r["id"] == rule["id"])
        assert current["data"]["contract_rule"]["templates"] == ["SC{9}/{3,4}"]
        assert current["data"]["contract_rule"]["sample_text"] == template["sample_text"]
        data = {**current["data"], "contract_rule": {**template, "mode": "BLOCK"}}
        changed = client.patch(BASE + "/master-data/" + current["id"], json=payload(current, data=data))
        assert changed.status_code == 200, changed.text
        for contract in ["SC700149169/600", "SC700143393/1600"]:
            create(client, contract_no=contract)
        for contract in ["SC700149169/60", "SC700149169/60000", "SC70014916/600"]:
            rejected = client.post(BASE + "/orders", json={**_order_payload(), "contract_no": contract})
            assert rejected.status_code == 422, rejected.text
        # Editing the saved template explicitly expands it; a stale update cannot overwrite it.
        data["contract_rule"]["templates"] = ["SC{9}/{3,4,5}"]
        updated = client.patch(BASE + "/master-data/" + current["id"], json=payload(changed.json(), data=data))
        assert updated.status_code == 200, updated.text
        create(client, contract_no="SC700149169/60000")
        assert client.patch(BASE + "/master-data/" + current["id"], json=payload(changed.json(), data=data)).status_code == 409


def test_warehouse_creation_atomic_rename_and_grants_preserve_positions(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        new = {"factory_id": "huaxing", "warehouse": "WARE-A", "bin_code": "01", "reason": "新增仓库资料"}
        first = client.post(BASE + "/inventory/warehouses", json=new)
        assert first.status_code == 201, first.text
        first = first.json()[0]
        assert client.post(BASE + "/inventory/warehouses", json=new).status_code == 409
        order = _submit_order(client, create(client))
        receipt = draft(client, order, 10, lines=[{"order_line_id": order["lines"][0]["id"], "delivered_quantity": "10", "received_quantity": "10", "unit_price": "2", "location_allocations": [{"location_id": first["id"], "quantity": "10"}]}])
        posted = confirm(client, receipt.json())
        assert posted.status_code == 200, posted.text
        before = client.get(BASE + "/inventory/balances", params={"factory_id": "huaxing"}).json()
        rename = {"factory_id": "huaxing", "warehouse": "WARE-A", "new_name": "WARE-B", "expected_locations": {first["id"]: first["revision"]}, "reason": "统一仓库名称"}
        extra = client.post(BASE + "/inventory/locations", json={**new, "bin_code": "02"}).json()
        assert client.patch(BASE + "/inventory/warehouses", json=rename).status_code == 409
        rename["expected_locations"][extra["id"]] = extra["revision"]
        login_as(client, "warehouse_keeper")
        profile = client.get("/api/auth/me").json()
        assert read(client)["can_manage"]
        assert client.post(BASE + "/inventory/warehouses", json={**new, "warehouse": "WARE-C"}).status_code == 201
        legacy_grant(profile["id"], ["WARE-A"])
        response = client.patch(BASE + "/inventory/warehouses", json=rename)
        assert response.status_code == 200, response.text
        assert {r["id"] for r in response.json()} == {first["id"], extra["id"]}
        assert all(r["warehouse"] == "WARE-B" and r["revision"] == 2 for r in response.json())
        assert client.patch(BASE + "/inventory/warehouses", json=rename).status_code in (404, 409)
        current = client.get(BASE + "/inventory/balances", params={"factory_id": "huaxing"}).json()
        assert [(r["position_key"], r["balance"]) for r in current] == [(r["position_key"], r["balance"]) for r in before]
        saved_grant = next(r for r in read(client)["records"] if r["id"] == "LEGACY-ACCESS")
        assert saved_grant["data"]["warehouses"] == ["WARE-B"]
        # Obsolete grants no longer reserve names or block authorized maintenance.
        legacy_grant(profile["id"], ["WARE-B", "RESERVED"])
        fresh = {r["id"]: r["revision"] for r in response.json()}
        renamed = client.patch(BASE + "/inventory/warehouses", json={**rename, "warehouse": "WARE-B", "new_name": "RESERVED", "expected_locations": fresh})
        assert renamed.status_code == 200, renamed.text
        fresh = {r["id"]: r["revision"] for r in renamed.json()}
        assert client.post(BASE + "/inventory/warehouses", json={**new, "warehouse": "EXISTING"}).status_code == 201
        assert client.patch(BASE + "/inventory/warehouses", json={**rename, "warehouse": "RESERVED", "new_name": "EXISTING", "expected_locations": fresh}).status_code == 409
        # Fully allocated receipts do not create the legacy fallback location.
        from app.db import SessionLocal
        from app.services.carton_positions import unknown_location
        with SessionLocal() as db:
            unknown_location(db, "huaxing")
            db.commit()
        unknown = next(r for r in read(client)["locations"] if r["id"].startswith("CL-UNKNOWN-"))
        assert client.patch(BASE + "/inventory/locations/" + unknown["id"], json={"factory_id": "huaxing", "warehouse": "ORDINARY", "bin_code": "X", "expected_revision": unknown["revision"], "status": "ACTIVE", "reason": "试图修改系统仓位"}).status_code == 422

        # Original receipt keeps its original allocation labels.
        history = client.get(BASE + "/receipts", params={"factory_id": "huaxing"}).json()["items"]
        assert any("WARE-A" in str(r) for r in history)
        foreign = client.patch(BASE + "/inventory/warehouses", json={**rename, "factory_id": "huakang", "warehouse": "WARE-B"})
        assert foreign.status_code in (403, 404, 422)
        assert client.post(BASE + "/inventory/warehouses", json={**new, "warehouse": "待核仓位"}).status_code == 422
        login_as(client, "warehouse_keeper")
        assert read(client)["warehouses"] == []


def test_shared_item_packaging_names_and_customer_preservation(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        first = _submit_order(client, create(client))
        standard = next(r for r in read(client)["records"] if r["kind"] == "CONFIG")
        assert standard["data"]["packing_name"] == "标准装"
        other = client.post(BASE + "/customers", json={"factory_id": "huaxing", "customer_name": "共享配置客户", "status": "ACTIVE"})
        assert other.status_code == 201, other.text
        another = create(client, customer_code=other.json()["customer_code"], master_config_id=standard["id"], master_config_revision=standard["revision"])
        assert another["customer_code"] == other.json()["customer_code"]
        _submit_order(client, another)
        assert len([r for r in read(client)["records"] if r["kind"] == "CONFIG"]) == 1
        for count in [240, 60]:
            lines = deepcopy(_order_payload()["lines"])
            lines[0]["usage_quantity"] = str(count)
            _submit_order(client, create(client, lines=lines))
        records = [r for r in read(client)["records"] if r["kind"] == "CONFIG"]
        assert {r["data"]["packing_name"] for r in records} == {"标准装", "大包装（240个装）", "小包装（60个装）"}
        assert next(r for r in records if r["id"] == standard["id"])["data"]["packing_name"] == "标准装"
        assert len(next(r for r in records if r["id"] == standard["id"])["sources"]) == 2
        # Different paper composition cannot safely be called a larger or smaller pack.
        lines = deepcopy(_order_payload()["lines"])
        lines[0]["usage_quantity"] = "300"
        lines[1]["packaging_type"] = "内箱"
        _submit_order(client, create(client, lines=lines))
        records = [r for r in read(client)["records"] if r["kind"] == "CONFIG"]
        assert any(r["data"]["packing_name"] == "其他包装" for r in records)
        original = next(r for r in client.get(BASE + "/orders", params={"factory_id": "huaxing"}).json()["items"] if r["id"] == first["id"])
        assert original["lines"][0]["usage_quantity"] == first["lines"][0]["usage_quantity"]

        # Privileged maintenance recomputes labels, retaining the same standard identity.
        large = next(r for r in records if r["data"]["packing_name"].startswith("大包装"))
        changed = deepcopy(large["data"])
        next(l for l in changed["lines"] if l["packaging_type"] == "外箱")["usage_quantity"] = "80"
        renamed = client.patch(BASE + "/master-data/" + large["id"], json=payload(large, data=changed))
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["data"]["packing_name"] == "小包装（80个装）"
        standard = next(r for r in read(client)["records"] if r["id"] == standard["id"])
        changed = deepcopy(standard["data"])
        next(l for l in changed["lines"] if l["packaging_type"] == "外箱")["usage_quantity"] = "40"
        revised = client.patch(BASE + "/master-data/" + standard["id"], json=payload(standard, data=changed))
        assert revised.status_code == 200, revised.text
        assert revised.json()["data"]["packing_name"] == "标准装"
        records = [r for r in read(client)["records"] if r["kind"] == "CONFIG"]
        assert next(r for r in records if r["id"] == large["id"])["data"]["packing_name"] == "大包装（80个装）"
        # Legacy duplicate customer-scoped rows can still be deactivated without rewriting evidence.
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        import json
        legacy_data = deepcopy(revised.json()["data"])
        legacy_data["packing_name"] = "其他包装"
        with SessionLocal() as db:
            db.add(CartonMasterRecord(id="LEGACY-DUP", factory_id="huaxing", kind="CONFIG", identity="legacy-duplicate", customer_code=other.json()["customer_code"], code=standard["code"], data_json=json.dumps(legacy_data), updated_at="2099-01-01"))
            db.commit()
        legacy = next(r for r in read(client)["records"] if r["id"] == "LEGACY-DUP")
        stopped = client.patch(BASE + "/master-data/LEGACY-DUP", json=payload(legacy, status="INACTIVE"))
        assert stopped.status_code == 200, stopped.text
