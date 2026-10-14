from decimal import Decimal

from test_molding_sample_api import login_as, make_client


def test_history_route_filters_business_dates_and_enforces_read_scope(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement
        from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user

        def row(identifier, factory, at):
            return CartonInventoryMovement(
                id=identifier, factory_id=factory, order_line_id=None,
                customer_code="C1", customer_name="客户甲", contract_no="CONTRACT", item_no="ITEM",
                packaging_type="外箱", paper_quality="A33", specification="1x1x1",
                movement_type="INBOUND", quantity=Decimal(1), unit="个", unit_price=Decimal(2),
                currency="CNY", location="A01", document_no=identifier,
                source_type="MANUAL", source_id=identifier, source_line_id=identifier,
                reversal_of_movement_id=None, reason="", actor_user_id="user-admin", actor_name="仓管",
                occurred_at=at,
            )

        with SessionLocal() as db:
            db.add_all([row("before", "huaxing", "2026-09-30T15:59:59Z"),
                        row("old-document", "huaxing", "2026-09-30T16:00:00Z"),
                        row("foreign", "huadeng", "2026-09-30T16:00:00Z")])
            db.commit()
        endpoint = "/api/carton-procurement/inventory/movement-history"
        unfiltered = client.get(endpoint, params={"factory_id": "huaxing"})
        assert unfiltered.status_code == 200 and unfiltered.json()["total"] == 2
        one_sided = client.get(endpoint, params={"factory_id": "huaxing", "date_from": "2026-10-01"})
        assert one_sided.status_code == 200 and one_sided.json()["total"] == 1
        named = client.get(endpoint, params={"factory_id": "huaxing", "customer_name": "客户甲"})
        assert named.status_code == 200 and named.json()["total"] == 2
        excluded = client.get(endpoint, params={"factory_id": "huaxing", "customer_name": "其他客户"})
        assert excluded.status_code == 200 and excluded.json()["total"] == 0
        query = dict(factory_id="huaxing", customer_code="C1", search="old-document",
                     movement_type="INBOUND", date_from="2026-10-01", date_to="2026-10-01", limit=1)
        result = client.get(endpoint, params=query)
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 1
        assert result.json()["items"][0]["id"] == "old-document"
        assert Decimal(result.json()["items"][0]["balance"]) == 2
        assert result.json()["items"][0]["is_reversed"] is False
        assert client.get(endpoint, params={**query, "offset": 1}).json()["items"] == []
        assert client.get(endpoint, params={**query, "date_to": "2026-09-30"}).status_code == 422
        assert client.get(endpoint, params={**query, "date_from": "invalid"}).status_code == 422
        assert client.get(endpoint, params={**query, "movement_type": "INVALID"}).status_code == 422
        legacy = client.get("/api/carton-procurement/inventory/movements", params={"factory_id": "huaxing"})
        assert legacy.status_code == 200 and legacy.json()["total"] == 2

        grant = AuthGrantContext("reader", "Reader", "huaxing", "pmc-warehouse",
                                 frozenset({"carton_procurement:read"}))
        actor = AuthContext("user-warehouse", "scoped_reader", "Scoped reader", (), (), grant.permissions,
                            ("huaxing",), ("pmc-warehouse",), grants=(grant,))
        client.app.dependency_overrides[get_current_user] = lambda: actor
        assert client.get(endpoint, params=query).status_code == 200
        assert client.get(endpoint, params={"factory_id": "huadeng"}).status_code == 403
        denied_actor = AuthContext("user-warehouse", "denied_reader", "Denied reader", (), (), grant.permissions,
                                   ("huaxing",), ("pmc-warehouse",), grants=(grant,), overrides=(
                                       AuthOverrideContext("deny", "carton_procurement:read", "deny", "huaxing", "pmc-warehouse"),))
        client.app.dependency_overrides[get_current_user] = lambda: denied_actor
        assert client.get(endpoint, params=query).status_code == 403
        client.app.dependency_overrides.clear()
