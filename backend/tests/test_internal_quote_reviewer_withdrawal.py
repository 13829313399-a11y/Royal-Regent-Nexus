import importlib
import json

import pytest

from test_internal_quote_api import (
    create_payload, ensure_user, grant_user_permission, login, logout, make_client,
)
from test_internal_quote_whole_review import mark_whole_quote_ready


def set_department(username: str, department: str) -> None:
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.auth")
    with db_module.SessionLocal() as db:
        db.merge(models.EmployeeProfile(
            user_id=f"user-{username}", primary_factory_id="huaxing",
            primary_department=department, confirmation_status="confirmed",
        ))
        db.commit()


def set_override_effect(username: str, effect: str) -> None:
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.auth")
    with db_module.SessionLocal() as db:
        for row in db.query(models.AuthUserPermissionOverride).filter_by(user_id=f"user-{username}"):
            row.effect = effect
        db.commit()


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
def test_reviewer_selection_enforces_sales_membership_and_effective_access(monkeypatch, authz_mode):
    monkeypatch.setenv("AUTHZ_MODE", authz_mode)
    with make_client(monkeypatch) as client:
        login(client, "creator", "sales_customer_owner", "sales-business")
        ensure_user("sales", "position_sales_supervisor", "sales-business")
        ensure_user("sales_override", "position_sales_business", "sales-business")
        grant_user_permission("sales_override", "internal_quote:sales_review", "sales-business")
        ensure_user("engineer", "position_engineering_supervisor", "engineering")
        grant_user_permission("engineer", "internal_quote:sales_review", "sales-business")
        grant_user_permission("engineer", "internal_quote:self_review", "sales-business")
        ensure_user("manager", "position_general_manager", "management")
        ensure_user("transferred", "position_sales_supervisor", "sales-business")
        set_department("transferred", "engineering")
        ensure_user("foreign", "position_sales_supervisor", "sales-business", "huadeng")
        ensure_user("ordinary", "position_sales_business", "sales-business")
        ensure_user("inactive", "position_sales_supervisor", "sales-business")
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            db.get(models.AuthUser, "user-inactive").status = "disabled"
            db.commit()

        response = client.get("/api/internal-quotes/business-owners?factory_id=huaxing")
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()}
        assert {"user-sales", "user-sales_override"} <= ids
        assert not ids & {"user-engineer", "user-manager", "user-transferred", "user-foreign", "user-ordinary", "user-inactive", "user-admin"}

        payload = create_payload(suffix="REVIEWER-VALID")
        payload.update(business_owner_id="user-sales", business_owner_name="伪造显示名称")
        valid = client.post("/api/internal-quotes", json=payload)
        assert valid.status_code == 201, valid.text
        assert valid.json()["business_owner_name"] == "sales"
        quote_id = valid.json()["id"]
        for name in ["engineer", "manager", "transferred", "foreign", "ordinary", "inactive", "admin", "missing"]:
            invalid_id = f"user-{name}"
            rejected = client.post("/api/internal-quotes", json={
                **payload, "quote_no": f"INVALID-{name}", "business_owner_id": invalid_id,
            })
            assert rejected.status_code == 400, rejected.text
            header = client.patch(f"/api/internal-quotes/{quote_id}", json={
                "revision": 1, "business_owner_id": invalid_id, "business_owner_name": name,
            })
            assert header.status_code == 400, header.text
            clone = client.post(f"/api/internal-quotes/{quote_id}/clone", json={
                "quote_no": f"CLONE-{name}", "version_label": "V2",
                "business_owner_id": invalid_id, "business_owner_name": name,
            })
            assert clone.status_code == 400, clone.text
        assert client.get(f"/api/internal-quotes/{quote_id}").json()["header_revision"] == 1

        set_override_effect("sales_override", "deny")
        ids = {item["id"] for item in client.get("/api/internal-quotes/business-owners?factory_id=huaxing").json()}
        assert "user-sales_override" not in ids


@pytest.mark.parametrize("workflow", ["section_review", "whole_quote_review"])
def test_selected_reviewer_loses_review_access_after_leaving_sales(monkeypatch, workflow):
    with make_client(monkeypatch) as client:
        ensure_user("reviewer", "sales_customer_supervisor", "sales-business")
        login(client, "creator", "sales_customer_owner", "sales-business")
        payload = create_payload(suffix="TRANSFER")
        payload.update(business_owner_id="user-reviewer", workflow_mode=workflow)
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        if workflow == "whole_quote_review":
            mark_whole_quote_ready(quote_id)
            submit = client.post(f"/api/internal-quotes/{quote_id}/final-submit", json={"revision": 1})
            endpoint = f"/api/internal-quotes/{quote_id}/final-review"
        else:
            submit = client.post(f"/api/internal-quotes/{quote_id}/sections/engineering/request-na", json={"revision": 1, "reason": "无需工程核价"})
            endpoint = f"/api/internal-quotes/{quote_id}/sections/engineering/review"
        assert submit.status_code == 200, submit.text
        set_department("reviewer", "engineering")
        logout(client)
        login(client, "reviewer", "sales_customer_supervisor", "sales-business")
        for decision in ["approve", "reject"]:
            result = client.post(endpoint, json={"revision": 2, "decision": decision, "reason": "试图审核"})
            assert result.status_code == 403, result.text
            assert "只有业务部" in result.json()["detail"]


def create_pending_batch(client, *, count: int = 2, creator_department: str = "sales-business") -> list[str]:
    ensure_user("reviewer", "sales_customer_supervisor", "sales-business")
    role = "engineer" if creator_department == "engineering" else "sales_customer_owner"
    login(client, "creator", role, creator_department)
    payload = create_payload(suffix="WITHDRAW-BATCH", initiator_department=creator_department)
    payload.update(
        business_owner_id="user-reviewer", workflow_mode="whole_quote_review",
        quote_type="series" if count > 1 else "single",
        products=[{"product_name": f"产品{i}", "qty": 1000} for i in range(count)],
    )
    created = client.post("/api/internal-quotes", json=payload)
    assert created.status_code == 201, created.text
    root_id = created.json()["id"]
    ids = [row["quote_id"] for row in client.get(f"/api/internal-quotes/{root_id}/batch-products").json()]
    for quote_id in ids:
        mark_whole_quote_ready(quote_id)
    # A Sales colleague submits Engineering's quote, but only the creator may withdraw it.
    if creator_department == "engineering":
        logout(client)
        login(client, "submitter", "sales_customer_owner", "sales-business")
    response = client.post(f"/api/internal-quotes/{ids[-1]}/final-submit", json={"revision": 1})
    assert response.status_code == 200, response.text
    return ids


@pytest.mark.parametrize("count,creator_department", [(1, "sales-business"), (2, "sales-business"), (2, "engineering")])
def test_creator_can_withdraw_pending_batch_preserving_content_and_resubmit(monkeypatch, count, creator_department):
    with make_client(monkeypatch) as client:
        ids = create_pending_batch(client, count=count, creator_department=creator_department)
        endpoint = f"/api/internal-quotes/{ids[-1]}/final-withdraw"
        for username, role, department in [
            ("submitter", "sales_customer_owner", "sales-business"),
            ("reviewer", "sales_customer_supervisor", "sales-business"),
            ("manager", "position_general_manager", "management"),
        ]:
            logout(client)
            login(client, username, role, department)
            forbidden = client.post(endpoint, json={"revision": 2, "reason": "不是建单人"})
            assert forbidden.status_code == 403, forbidden.text
        logout(client)
        role = "engineer" if creator_department == "engineering" else "sales_customer_owner"
        login(client, "creator", role, creator_department)
        assert client.post(endpoint, json={"revision": 2, "reason": "   "}).status_code == 422
        assert client.post(endpoint, json={"revision": 1, "reason": "过期页面"}).status_code == 409
        before = [client.get(f"/api/internal-quotes/{qid}").json() for qid in ids]
        withdrawn = client.post(endpoint, json={"revision": 2, "reason": "客户数量需要修改"})
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["review"] is None
        assert client.post(endpoint, json={"revision": 3, "reason": "重复退回"}).status_code == 409
        for qid, previous in zip(ids, before, strict=True):
            after = client.get(f"/api/internal-quotes/{qid}").json()
            assert after["status"] == "rejected"
            assert after["header_revision"] == 3
            assert after["final_release_status"] == "invalidated"
            assert after["final_submitted_by"] == previous["final_submitted_by"]
            for old, new in zip(previous["sections"], after["sections"], strict=True):
                assert new["payload"] == old["payload"]
                assert new["calculation"] == old["calculation"]
                if old["is_required"]:
                    assert new["status"] == "rejected"
                    assert new["revision"] == old["revision"] + 1
                    assert new["reviewed_by"] == ""
                else:
                    assert new["revision"] == old["revision"]
            history = client.get(f"/api/internal-quotes/{qid}/timeline").json()
            assert any(event["action"] == "whole_review_withdraw" and event["reason"] == "客户数量需要修改" for event in history["business_events"])
            assert client.get(f"/api/internal-quotes/{qid}/final-reviews").json() == []

        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            notices = [row for row in db.query(models.SystemNotification).all()
                       if json.loads(row.payload_json).get("event") == "whole_quote_submitted"]
            assert notices and all(row.status == "handled" for row in notices)
        # Stale reviewer pages cannot approve the withdrawn submission.
        logout(client)
        login(client, "reviewer", "sales_customer_supervisor", "sales-business")
        assert client.post(f"/api/internal-quotes/{ids[0]}/final-review", json={"revision": 2, "decision": "approve"}).status_code == 409
        logout(client)
        login(client, "creator", role, creator_department)
        if creator_department == "engineering":
            edited = client.put(f"/api/internal-quotes/{ids[0]}/sections/engineering", json={
                "revision": 3, "payload": {"materials": [], "molds": []},
            })
        else:
            edited = client.patch(f"/api/internal-quotes/{ids[0]}", json={"revision": 3, "remark": "撤回后修改"})
        assert edited.status_code == 200, edited.text
        for qid in ids:
            mark_whole_quote_ready(qid)
        if creator_department == "engineering":
            logout(client)
            login(client, "submitter", "sales_customer_owner", "sales-business")
        revision = client.get(f"/api/internal-quotes/{ids[0]}").json()["header_revision"]
        submitted = client.post(f"/api/internal-quotes/{ids[0]}/final-submit", json={"revision": revision})
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["quote"]["final_submission_revision"] == 2
        logout(client)
        login(client, "reviewer", "sales_customer_supervisor", "sales-business")
        approved = client.post(f"/api/internal-quotes/{ids[0]}/final-review", json={"revision": revision + 1, "decision": "approve"})
        assert approved.status_code == 200, approved.text
        logout(client)
        login(client, "creator", role, creator_department)
        final_revision = client.get(f"/api/internal-quotes/{ids[-1]}").json()["header_revision"]
        assert client.post(endpoint, json={"revision": final_revision, "reason": "已经审核"}).status_code == 409
        assert all(client.get(f"/api/internal-quotes/{qid}").json()["status"] == "fully_approved" for qid in ids)


def test_withdrawal_rejects_inconsistent_batch_atomically_and_revoked_creator_access(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        ids = create_pending_batch(client)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            db.get(models.InternalQuote, ids[-1]).final_release_status = "approved"
            db.commit()
        endpoint = f"/api/internal-quotes/{ids[0]}/final-withdraw"
        rejected = client.post(endpoint, json={"revision": 2, "reason": "状态已变化"})
        assert rejected.status_code == 409
        root = client.get(f"/api/internal-quotes/{ids[0]}").json()
        assert root["header_revision"] == 2
        assert all(section["status"] == "pending_review" for section in root["sections"] if section["is_required"])
        grant_user_permission("creator", "internal_quote:create", "sales-business")
        set_override_effect("creator", "deny")
        assert client.post(endpoint, json={"revision": 2, "reason": "操作权限已收回"}).status_code == 403
