"""Repeated unpublished-to-supplier changes must not invent an agreed baseline."""
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login
from test_carton_special_requests import created, create_body, command, ok, BASE
import pytest
from uuid import uuid4


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def test_two_unaccepted_regular_and_special_changes_keep_truthful_readonly_history(monkeypatch):
    with make_client(monkeypatch) as client:
        regular = setup_portal(client)
        login_as(client, "admin")
        for _ in range(2):
            regular = ok(client.post(f"/api/carton-procurement/orders/{regular['order_no']}/append", json={
                "factory_id": "huaxing", "expected_revision": regular["revision"], "additional_quantity": 120,
                "reason": "连续追加尚未取得供应商同意", "issue_to_supplier": True}))
        special = created(client, accept_order=False)
        for quantity in (110, 120):
            payload = {**create_body(), "expected_revision": special["revision"], "reason": "连续样板调整尚未接单"}
            payload["lines"][0].update(id=special["lines"][0]["id"], quantity=str(quantity))
            special = ok(client.post(BASE + f"/{special['id']}/adjust", json=payload))
        supplier_login(client)
        tasks = ok(client.get("/api/carton-supplier/changes", params={"factory_id": "huaxing"}))["items"]
        for kind, identifier in (("REGULAR", regular["id"]), ("SPECIAL", special["id"])):
            task = next(row for row in tasks if row["source_kind"] == kind and row["order_id"] == identifier)
            assert task["status"] == "PENDING"
            history = task["publication_history"]
            assert len(history) == 3
            assert [row["superseded"] for row in history] == [True, True, False]
            assert all(row["status"] == "PENDING" for row in history)
            assert len({str(row["lines"][0]["quantity"]) for row in history}) == 3
            rejected = client.post("/api/carton-supplier/changes/respond", json={
                "factory_id": "huaxing", "source_kind": kind, "source_id": history[0]["source_id"],
                "expected_revision": task["expected_revision"], "action": "ACCEPT", "promised_date": "2026-10-25",
                "request_id": uuid4().hex})
            assert rejected.status_code == 409, rejected.text
