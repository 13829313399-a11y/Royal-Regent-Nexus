"""Public workflow helpers for synthetic cancellation/deletion regression tests."""
from test_molding_sample_api import login_as
from test_carton_supplier_portal import grant_supplier_permissions


def cancel_and_acknowledge(client, order):
    actor = login_as(client, "admin")
    base = "/api/carton-procurement"
    if order["status"] != "CANCELLED":
        response = client.post(f"{base}/orders/{order['order_no']}/cancel", json={
            "factory_id": "huaxing", "expected_revision": order["revision"],
            "reason": "测试确认取消原采购需求"})
        assert response.status_code == 200, response.text
        order = response.json()
    from app.db import SessionLocal
    from app.models.auth import AuthUserPermissionOverride
    with SessionLocal() as db:
        granted = db.get(AuthUserPermissionOverride, f"supplier-allow-{actor['id']}-carton_supplier:read")
    if not granted:
        grant_supplier_permissions(user_id=actor["id"])
    login_as(client, "admin")
    response = client.get("/api/carton-supplier/workspace", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    current = next(item for item in response.json()["orders"] if item["id"] == order["id"])
    # Normal cancellation publishes automatically; only historical cancellations
    # need the missing immutable stop notice generated explicitly.
    if not (current.get("cancellation_notice") or {}).get("issued"):
        issued = client.post(f"{base}/orders/{order['order_no']}/purchase-order-issues.xlsx", json={
            "factory_id": "huaxing", "expected_revision": order["revision"]})
        assert issued.status_code == 200, issued.text
        response = client.get("/api/carton-supplier/workspace", params={"factory_id": "huaxing"})
        assert response.status_code == 200, response.text
        current = next(item for item in response.json()["orders"] if item["id"] == order["id"])
    response = client.post(f"/api/carton-supplier/orders/{order['id']}/cancellation-ack", json={
        "factory_id": "huaxing", "issue_id": current["issue_id"],
        "expected_order_revision": current["revision"]})
    assert response.status_code == 200, response.text
    response = client.get(base + "/orders", params={"factory_id": "huaxing"})
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["id"] == order["id"])
