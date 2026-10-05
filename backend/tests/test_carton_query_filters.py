"""Queries must filter the authorized full history before counting and paging."""
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order
from test_carton_supplier_portal import setup_portal, supplier_login, BASE
from test_carton_supplier_acceptance import accept_paper


def test_collaboration_state_filters_before_paging_and_uses_current_issue(monkeypatch):
    with make_client(monkeypatch) as client:
        first = setup_portal(client)
        supplier_order = client.get(BASE + "/workspace", params={"factory_id": "huaxing"}).json()["orders"][0]
        accept_paper(client, supplier_order, supplier_order["lines"][0])
        login_as(client, "admin")
        others = [_create_order(client) for _ in range(3)]
        params = {"factory_id": "huaxing", "limit": 1, "collaboration_filter": "PARTIAL", "sort": "ORDER_DESC"}
        result = client.get("/api/carton-procurement/orders", params=params)
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 1
        assert result.json()["items"][0]["id"] == first["id"]
        assert result.json()["statistics"]["pending"] == 1
        empty = client.get("/api/carton-procurement/orders", params={**params, "offset": 1}).json()
        assert empty["total"] == 1 and empty["items"] == []
        pending = client.get("/api/carton-procurement/orders", params={**params, "collaboration_filter": "PENDING", "offset": 2}).json()
        assert pending["total"] == 3 and pending["items"][0]["id"] in {row["id"] for row in others}
        changed = client.post(f"/api/carton-procurement/orders/{first['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": first["revision"], "additional_quantity": 120, "reason": "数量增加重新核对"})
        assert changed.status_code == 200, changed.text
        change = client.get("/api/carton-procurement/orders", params={**params, "collaboration_filter": "PENDING_CHANGE"}).json()
        assert change["total"] == 1 and change["items"][0]["id"] == first["id"]


def test_supplier_activity_queries_old_history_and_never_internal_or_wrong_entities(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        def event(key, **values):
            return CartonAuditEvent(id=key, factory_id="huaxing", event_type=values.pop("event_type", "SUPPLIER_PAPER_ACCEPTED"),
                entity_type=values.pop("entity_type", "carton_order"), entity_id=order["id"], detail_json='{"private":"secret"}',
                actor_user_id="admin", actor_name="管理员", created_at=values.pop("created_at", "2026-10-02T00:00:00"), **values)
        with SessionLocal() as db:
            db.add_all([event("OLD-1", created_at="2026-09-01T00:00:00"), event("OLD-2", created_at="2026-09-01T23:59:59.999999")])
            db.add_all([event(f"NEW-{i}") for i in range(505)])
            db.add(event("WRONG-ENTITY", entity_type="supplier_shipment", created_at="2026-09-01T12:00:00"))
            db.add(event("INTERNAL-ONLY", event_type="FEEDBACK_CREATED", created_at="2026-09-01T12:00:00"))
            db.add(event("COMBINED-PURCHASE", event_type="PURCHASE_ORDER_BATCH_ISSUED", entity_type="carton_purchase_order_batch", created_at="2026-09-01T12:00:00"))
            db.add(event("CLOSING", event_type="CLOSING_GENERATED", entity_type="carton_closing_period", created_at="2026-09-01T12:00:00"))
            db.commit()
        supplier_login(client)
        query = dict(date_from="2026-09-01", date_to="2026-09-01", search="纸品已确认", sort="ASC", limit=1, offset=1)
        result = client.get(BASE + "/activity-page", params=query)
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 2
        assert [row["id"] for row in result.json()["items"]] == ["OLD-2"]
        assert all("detail" not in row for row in result.json()["items"])
        assert client.get(BASE + "/activity-page", params={"search": "secret"}).json()["total"] == 0
        assert client.get(BASE + "/activity-page", params={"factory_id": "huadeng"}).status_code == 403
        login_as(client, "admin")
        audit = client.get("/api/carton-procurement/audit-events", params={"factory_id": "huaxing", "date_from": "2026-09-01", "date_to": "2026-09-01", "search": "员工问题", "limit": 1}).json()
        assert audit["total"] == 1 and audit["items"][0]["id"] == "INTERNAL-ONLY"
        assert "SUPPLIER_PAPER_ACCEPTED" in audit["event_types"]
        for label, key in [("合并采购单", "COMBINED-PURCHASE"), ("月结草稿", "CLOSING")]:
            result = client.get("/api/carton-procurement/audit-events", params={"factory_id": "huaxing", "search": label}).json()
            assert result["total"] == 1 and result["items"][0]["id"] == key


def test_feedback_and_updates_page_full_history_after_owner_factory_filters(monkeypatch):
    with make_client(monkeypatch) as client:
        viewer = login_as(client, "warehouse_keeper")
        from app.db import SessionLocal
        from app.models.carton_feedback import CartonFeedback, CartonFeatureUpdate
        from app.models.carton_stocktake import CartonStocktake
        with SessionLocal() as db:
            for index in range(115):
                key = f"OWN-{index:03}"
                db.add(CartonFeedback(id=key, factory_id="huaxing", author_id=viewer["id"], author_name="仓库",
                    title="数量核对", description="实收核实", context_path="/modules/pmc-warehouse/carton-procurement", status="FIXED", request_key=key,
                    payload_sha256="a" * 64, created_at="2026-09-01T23:59:59.123456", updated_at=f"2026-09-02T00:{index // 60:02}:{index % 60:02}"))
                db.add(CartonFeatureUpdate(id=key, factory_id="huaxing", author_id="admin", author_name="管理员", title="数量更新",
                    body="查询更新", request_key=key, created_at="2026-09-01T23:59:59.123456"))
            db.add(CartonFeedback(id="OTHER", factory_id="huaxing", author_id="admin", author_name="管理员", title="数量核对", description="private",
                context_path="/", status="FIXED", request_key="other", payload_sha256="a" * 64, created_at="2026-09-01T12:00:00", updated_at="2026-09-01T12:00:00"))
            db.add_all([CartonStocktake(id=f"ST-{i}", factory_id="huaxing", status="CANCELLED", created_by=viewer["id"], created_by_name="仓库", created_at=date)
                for i, date in enumerate(["2026-09-01T23:59:59.123456", "2026-10-01T00:00:00"])])
            db.commit()
        params = dict(factory_id="huaxing", search="数量", status="FIXED", date_from="2026-09-01", date_to="2026-09-01", limit=5, offset=110, updates_offset=110, sort="ASC")
        result = client.get("/api/carton-feedback", params=params)
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["total"] == 115 and len(data["feedbacks"]) == 5
        assert {row["id"] for row in data["feedbacks"]} == {f"OWN-{i}" for i in range(110, 115)}
        assert data["updates_total"] == 115 and len(data["updates"]) == 5
        assert client.get("/api/carton-feedback", params={**params, "all_feedback": True}).status_code == 403
        assert client.get("/api/carton-feedback", params={**params, "date_from": "2026-09-02"}).status_code == 422
        stock = client.get("/api/carton-procurement/stocktakes", params={"factory_id": "huaxing", "date_from": "2026-09-01", "date_to": "2026-09-01", "limit": 1}).json()
        assert [row["id"] for row in stock] == ["ST-0"]
        login_as(client, "admin")
        assert client.get("/api/carton-feedback", params={**params, "all_feedback": True}).json()["total"] == 116
