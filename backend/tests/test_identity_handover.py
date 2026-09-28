import importlib
from uuid import uuid4
from sqlalchemy import event, select
from test_identity_changes import client, engineer, confirm, identity, draft, commit
from test_iam_api import create_user


def test_quote_handover_checks_revision_holder_and_successor(client):
    source = create_user("source-sales", "position_sales_supervisor", "huakang-a", "sales-business")
    successor = create_user("next-sales", "position_sales_supervisor", "huakang-a", "sales-business")
    confirm(client, source)
    confirm(client, successor)
    dbm = importlib.import_module("app.db")
    quote_m = importlib.import_module("app.models.internal_quote")
    auth_m = importlib.import_module("app.models.auth")
    with dbm.SessionLocal() as db:
        db.add(quote_m.InternalQuote(id="handover-quote", factory_id="huakang-a", workshop_code="assembly", workshop_name="测试车间",
            quote_no="QA-HANDOVER", product_name="隔离样品", customer="隔离客户", qty=1, version_label="V1", status="drafting",
            business_owner_id=source, business_owner_name="原审核人", created_by=source, created_by_name="历史创建人", created_at="2026-01-01", updated_at="2026-01-01"))
        db.commit()
    row = draft(client, source, "leave")
    result = commit(client, row)
    assert result.status_code == 200, result.text
    response = client.get(f"/api/iam/identity-changes/{row['id']}/handover-items")
    item = response.json()["items"][0]
    assert any(c["status"] == "uncovered" for c in response.json()["coverage"])
    options = client.get(f"/api/iam/handover-items/{item['id']}/candidates").json()["items"]
    assert successor in {o["id"] for o in options} and source not in {o["id"] for o in options}
    with dbm.SessionLocal() as db:
        db.get(quote_m.InternalQuote, "handover-quote").header_revision += 1
        db.commit()
    assign = lambda revision: client.post(f"/api/iam/handover-items/{item['id']}/reassign", json={"successor_user_id": successor, "expected_resource_revision": revision})
    assert assign(item["expected_resource_revision"]).status_code == 409
    refreshed = client.post(f"/api/iam/identity-changes/{row['id']}/handover-refresh")
    assert refreshed.status_code == 200, refreshed.text
    revision = refreshed.json()["items"][0]["expected_resource_revision"]
    assert assign(revision).status_code == 200
    assert assign(revision).status_code == 200  # repeat does not write the business object twice
    with dbm.SessionLocal() as db:
        q = db.get(quote_m.InternalQuote, "handover-quote")
        assert (q.created_by, q.factory_id, q.created_by_name) == (source, "huakang-a", "历史创建人")
        assert q.business_owner_id == successor and q.header_revision == revision + 1
        assert len(list(db.scalars(select(quote_m.InternalQuoteAuditLog).where(quote_m.InternalQuoteAuditLog.action == "identity_handover")))) == 1
    assert commit(client, draft(client, successor, "leave")).status_code == 200
    outbox = importlib.import_module("app.services.identity_outbox")
    with dbm.SessionLocal() as db:
        outbox.reconcile_due(db)
    items = client.get(f"/api/iam/identity-changes/{row['id']}/handover-items").json()["items"]
    assert items[0]["status"] == "pending" and items[0]["last_error"] == "SUCCESSOR_UNAVAILABLE"


def test_notification_failure_keeps_identity_and_retry_is_idempotent(client):
    user_id = engineer(client)
    result = commit(client, draft(client, user_id, "freeze"))
    assert result.status_code == 200
    dbm = importlib.import_module("app.db")
    outbox = importlib.import_module("app.services.identity_outbox")
    models = importlib.import_module("app.models.auth")
    identitym = importlib.import_module("app.models.identity")
    def reject_notification(mapper, connection, target):
        if target.type == "identity_changed":
            raise RuntimeError("injected isolated notification failure")
    event.listen(models.SystemNotification, "before_insert", reject_notification)
    try:
        with dbm.SessionLocal() as db:
            failed = outbox.drain(db)
            assert failed["retry"] > 0
            assert db.get(models.AuthUser, user_id).status == "suspended"
    finally:
        event.remove(models.SystemNotification, "before_insert", reject_notification)
    with dbm.SessionLocal() as db:
        for row in db.scalars(select(identitym.IamOutbox)):
            row.next_attempt_at = ""
        db.commit()
        assert outbox.drain(db)["delivered"] > 0
        assert outbox.drain(db)["processed"] == 0
        count = len(list(db.scalars(select(models.SystemNotification).where(models.SystemNotification.type == "identity_changed"))))
        assert count == len(list(db.scalars(select(identitym.IamOutbox))))


def test_missing_profile_requires_explicit_organization_without_role_guess(client):
    user_id = create_user("missing-profile", "engineer", "huakang-a", "engineering")
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.auth")
    with dbm.SessionLocal() as db:
        db.delete(db.get(models.EmployeeProfile, user_id))
        db.commit()
    before = identity(client, user_id)
    assert before["primary_factory_id"] == "" and before["confirmation_status"] == "unconfirmed"
    row = draft(client, user_id, "confirm_identity", new_assignment={"org_unit_id": "huaxing", "department_code": "engineering", "official_position_title": "人工核实工程师"},
        binding_dispositions=[{"binding_id": b["id"], "source": "individual_exception"} for b in before["role_bindings"]])
    assert commit(client, row).status_code == 200
    assert identity(client, user_id)["primary_factory_id"] == "huaxing"
