import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login
from test_carton_master_api import prepare
from test_carton_procurement_api import _order_payload

BASE = "/api/carton-procurement"
PORTAL = "/api/carton-supplier"


def test_manual_plan_date_and_supplier_rush_acknowledgement(monkeypatch):
    with make_client(monkeypatch) as client:
        portal_order = setup_portal(client)
        login_as(client, "admin")
        prepare(client)

        payload = {**_order_payload(), "customer_po": "RUSH-MANUAL-1", "customer_due_date": "2026-10-30",
                   "due_date": "2026-10-28", "plan_date_manual": True, "rush": True, "rush_reason": "客户临时确认"}
        created = client.post(BASE + "/orders", json=payload)
        assert created.status_code == 201, created.text
        manual = created.json()
        assert manual["due_date"] == "2026-10-28"
        assert manual["plan_date_manual"] is True
        assert manual["rush"] is True and manual["rush_acknowledged"] is False
        assert manual["rush_reason"] == "客户临时确认"

        marked = client.post(BASE + f"/orders/{portal_order['order_no']}/rush",
                             json={"factory_id": "huaxing", "rush": True, "reason": "客户临时确认"})
        assert marked.status_code == 200, marked.text
        assert marked.json()["rush"] is True and marked.json()["rush_acknowledged"] is False

        supplier_login(client)
        acknowledged = client.post(PORTAL + f"/orders/{portal_order['id']}/rush-ack", json={"factory_id": "huaxing"})
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["rush_acknowledged"] is True
        workspace = client.get(PORTAL + "/workspace", params={"factory_id": "huaxing"}).json()
        visible = next(row for row in workspace["orders"] if row["id"] == portal_order["id"])
        assert visible["rush"] is True and visible["rush_acknowledged"] is True

        login_as(client, "admin")
        cleared = client.post(BASE + f"/orders/{portal_order['order_no']}/rush",
                              json={"factory_id": "huaxing", "rush": False})
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["rush"] is False and cleared.json()["rush_acknowledged"] is False
