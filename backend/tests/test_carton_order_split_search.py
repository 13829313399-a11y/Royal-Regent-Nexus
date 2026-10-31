"""Split search keeps one authorized procurement family and current audit state."""
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonOrder
from app.services import carton_order_split_search as search


def test_destination_search_keeps_factory_customer_identity_and_literal_characters(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    calls = []
    records = []
    for identifier, factory, customer, status in [
        ("active", "huadeng", "C1", "ACTIVE"), ("pending", "huadeng", "C1", "PENDING_WAREHOUSE"),
        ("cancelled", "huadeng", "C1", "CANCELLED"), ("foreign", "huaxing", "C1", "ACTIVE"),
        ("other-customer", "huadeng", "C2", "ACTIVE"), ("wrong-identity", "huadeng", "C2", "ACTIVE"),
    ]:
        records.append(dict(order_id=identifier, order_no="CT-" + identifier, factory_id=factory,
            customer_code=customer, item_no="ITEM", status=status,
            targets=[{"contract_no": "Child_%", "customer_po": "Child-PO"}]))
    def plans(db, factory):
        calls.append(factory)
        return records
    monkeypatch.setattr(search, "plans", plans)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE carton_orders (id TEXT, order_no TEXT, factory_id TEXT, customer_code TEXT, item_no TEXT, status TEXT)"))
        for record in records:
            connection.execute(text("INSERT INTO carton_orders VALUES (:order_id,:order_no,:factory_id,:customer_code,:item_no,'PENDING_SUPPLIER')"),
                {**record, "customer_code": "C1" if record["order_id"] == "wrong-identity" else record["customer_code"]})
    with Session(engine) as db:
        def matching(term):
            return set(db.scalars(select(CartonOrder.id).where(CartonOrder.factory_id == "huadeng",
                CartonOrder.customer_code == "C1", search.destination_predicate(db, "huadeng", term))))
        assert matching("child_%") == {"active", "pending"}
        assert matching("child-po") == {"active", "pending"}
        assert matching("ChildXYZ") == set()
    assert calls == ["huadeng"] * 3
    engine.dispose()


def test_split_destination_search_precedes_pagination_and_uses_live_plans(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)
    monkeypatch.setenv("SEED_DEFAULT_ACCOUNTS", "true")
    from test_molding_sample_api import make_client, login_as
    from test_carton_order_split import setup, save, split_body, action, context
    with make_client(monkeypatch) as client:
        order = setup(client, monkeypatch)
        plan = save(client, order, split_body(order, contract="CHILD_%_SEARCH"))
        body = split_body(order, pending="1", product="10", contract="CHILD_%_SEARCH-SECOND")
        body["expected_revision"] = context(client, order)["revision"]
        second = save(client, order, body)
        endpoint = "/api/carton-unified-orders"
        params = {"factory_id": "huaxing", "kind": "PURCHASE", "search": "CHILD_%_SEARCH", "limit": 1}
        response = client.get(endpoint, params=params)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["total"] == 1 and len(result["items"]) == 1
        assert result["items"][0]["order"]["id"] == order["id"]
        assert result["items"][0]["order"]["product_order_quantity"] == order["product_order_quantity"]
        assert result["statistics"]["pending"] == 1
        assert client.get(endpoint, params={**params, "offset": 1}).json()["items"] == []
        assert client.get(endpoint, params={**params, "search": "CHILD-PO-NOT-PRESENT"}).json()["total"] == 0
        by_po = client.get(endpoint, params={**params, "search": "NEW-PO"}).json()
        assert by_po["total"] == 1 and by_po["items"][0]["order"]["id"] == order["id"]
        direct = client.get("/api/carton-procurement/orders", params={**params, "search": "NEW-PO"}).json()
        assert direct["total"] == 1 and direct["items"][0]["id"] == order["id"]
        assert action(client, plan, "cancel").status_code == 200
        assert client.get(endpoint, params=params).json()["total"] == 1  # Other active destination still matches.
        assert action(client, second, "cancel").status_code == 200
        assert client.get(endpoint, params=params).json()["total"] == 0
        login_as(client, "admin")
        assert client.get(endpoint, params={**params, "factory_id": "huakang-a"}).json()["total"] == 0
