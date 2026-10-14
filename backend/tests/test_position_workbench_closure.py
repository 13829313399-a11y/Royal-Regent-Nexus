"""Remaining acceptance boundaries, using disposable SQLite/PostgreSQL data."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from test_position_reviews import client, employee, submit, plan, commit
from test_identity_changes import identity, draft, commit as identity_commit
from test_identity_postgres import postgres
from test_iam_api import login, create_user


def modules():
    return tuple(importlib.import_module(name) for name in (
        "app.db", "app.models.auth", "app.models.identity", "app.models.position_review"))


def columns(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def test_package_replacement_preserves_all_four_independent_sources(client):
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    dbm, models, _, _ = modules()
    sources = importlib.import_module("app.services.identity_sources")
    auth = importlib.import_module("app.services.auth")
    tracked = []
    with dbm.SessionLocal() as db:
        for source_type, code in (("system_administration", "system:audit_read"),
                                  ("external_collaboration", "carton_supplier:read")):
            role_id = "closure-" + source_type
            db.add(models.AuthRole(id=role_id, code=role_id, name=source_type))
            db.flush()
            permission = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == code))
            assert permission is not None
            db.add(models.AuthRolePermission(id=uuid4().hex, role_id=role_id, permission_id=permission.id))
            db.flush()
            version = sources.snapshot_role(db, role_id, "user-admin")
            binding = models.AuthUserRole(id=role_id, user_id=uid, role_id=role_id,
                                         factory_id="huakang-a", department="engineering")
            db.add(binding)
            db.flush()
            metadata = models.AuthRoleBindingMetadata(user_role_id=binding.id, source_type=source_type,
                source_id="independent-qa", role_version_id=version.id, employment_epoch=1,
                scope_ceiling_json='["huakang-a"]', state="active")
            db.add(metadata)
            tracked.extend(((models.AuthUserRole, binding.id), (models.AuthRoleBindingMetadata, binding.id)))
        for effect, code in (("allow", "three_d_printing:read"), ("deny", "molding_sample:create")):
            permission = db.scalar(select(models.AuthPermission).where(models.AuthPermission.code == code))
            override_id = "closure-" + effect
            db.add(models.AuthUserPermissionOverride(id=override_id, user_id=uid, permission_id=permission.id,
                factory_id="huakang-a", department="engineering", effect=effect, status="active",
                lifecycle_policy="independent", employment_epoch=1))
            tracked.append((models.AuthUserPermissionOverride, override_id))
        db.commit()
        before = [columns(db.get(model, key)) for model, key in tracked]
    key, body, preview = plan(client, review)
    assert body["independent_allow_decisions"] == [{"override_id": "closure-allow", "decision": "keep_original_scope"}]
    response, _ = commit(client, key, preview)
    assert response.status_code == 200, response.text
    with dbm.SessionLocal() as db:
        assert [columns(db.get(model, key)) for model, key in tracked] == before
        context = auth.build_auth_context(db, db.get(models.AuthUser, uid))
        for code in ("system:audit_read", "carton_supplier:read", "three_d_printing:read", "molding_sample:supervisor_review"):
            assert auth.can(context, code, "huakang-a", "engineering"), code
        assert not auth.can(context, "molding_sample:create", "huakang-a", "engineering")
        assert not auth.can(context, "three_d_printing:read", "huakang-b", "engineering")


def test_mixed_same_timestamp_queue_has_stable_pages_and_totals(client):
    dbm, models, _, reviews = modules()
    stamp = "2026-10-13T00:00:00Z"
    declaration = {"org_unit_id": "huakang-a", "department_code": "engineering", "position": "同秒验收", "note": ""}
    expected = []
    # Deliberately duplicate source IDs between tables, so the kind tie-breaker matters.
    for index in range(31):
        source_id = f"mixed-{index:03d}"
        for kind in ("position", "registration"):
            name = f"closure-{kind}-{index:03d}"
            uid = create_user(name, "position_engineering_engineer", "huakang-a", "engineering")
            with dbm.SessionLocal() as db:
                if kind == "position":
                    row = reviews.PositionReview(id=source_id, user_id=uid, employment_epoch=1, origin="employee",
                        initiator_user_id=uid, declared_snapshot_json=json.dumps(declaration),
                        created_at=stamp, updated_at=stamp, last_submitted_at=stamp)
                else:
                    db.get(models.AuthUser, uid).status = "pending"
                    row = models.AuthRegistrationRequest(id=source_id, user_id=uid, username=name,
                        factory_id="huakang-a", org_unit_id="huakang-a", department="engineering", position="同秒验收",
                        declared_profile_json=json.dumps(declaration), submitted_at=stamp, created_at=stamp, updated_at=stamp)
                db.add(row)
                db.commit()
            expected.append(kind + ":" + source_id)
    for page_size in (7, 20, 50):
        actual = []
        for page in range(1, (len(expected) + page_size - 1) // page_size + 1):
            response = client.get("/api/iam/position-workbench/queue", params={"page": page, "page_size": page_size})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["total"] == data["actionable_total"] == 62
            actual.extend(row["item_key"] for row in data["items"])
        assert actual == expected and len(set(actual)) == 62
    for kind in ("position", "registration"):
        data = client.get("/api/iam/position-workbench/queue", params={"kind": kind, "page_size": 50}).json()
        assert data["total"] == 31 and data["actionable_total"] == 62
        assert all(row["item_key"].startswith(kind + ":") for row in data["items"])


def test_leave_rehire_rejects_old_epoch_and_accepts_new_declaration(client):
    uid = employee(client)
    review = submit(client)
    old_cookie = client.cookies.get("rr_session")
    login(client, "admin")
    key, _, preview = plan(client, review)
    assert identity_commit(client, draft(client, uid, "leave")).status_code == 200
    response = identity_commit(client, draft(client, uid, "rehire", new_assignment={
        "org_unit_id": "huaxing", "department_code": "engineering", "official_position_title": "重新入职"}))
    assert response.status_code == 200, response.text
    current = identity(client, uid)
    assert current["employment_epoch"] > review["employment_epoch"]
    assert commit(client, key, preview)[0].status_code == 409
    assert identity(client, uid)["identity_version"] == current["identity_version"]
    client.cookies.clear()
    client.cookies.set("rr_session", old_cookie)
    assert client.get("/api/auth/me").status_code == 401
    login(client, "position-clerk")
    stale_edit = client.patch(f"/api/auth/me/position-reviews/{review['id']}", json={
        "expected_revision": review["revision"], "declaration": review["declaration"]})
    assert stale_edit.status_code == 404
    own = client.get("/api/auth/me/position-profile").json()
    assert own["open_review"] is None and own["official_position"]["position"] == "重新入职"
    new = submit(client, "复职后新声明")
    assert new["id"] != review["id"] and new["employment_epoch"] == current["employment_epoch"]
    dbm, _, _, reviews = modules()
    with dbm.SessionLocal() as db:
        assert db.get(reviews.PositionReview, review["id"]).status == "invalidated"


@pytest.mark.parametrize("contender", ["approve", "edit"])
def test_postgres_competing_writer_survives_failed_approval(postgres, monkeypatch, contender):
    client, dbm = postgres
    uid = employee(client)
    review = submit(client)
    login(client, "admin")
    key, _, preview = plan(client, review)
    before = identity(client, uid)
    service = importlib.import_module("app.services.position_workbench")
    reviews_service = importlib.import_module("app.services.position_reviews")
    schema = importlib.import_module("app.schemas.position_review")
    _, models, iam, reviews = modules()
    reached, release, contender_entered = Event(), Event(), Event()
    failed_command, successful_command = str(uuid4()), str(uuid4())
    original_receipt = service.save_receipt_tx

    def fault(*args):
        result = original_receipt(*args)  # Fail after actual identity/event/outbox/receipt writes have flushed.
        if str(args[4]) == failed_command:
            reached.set()
            assert release.wait(15)
            raise HTTPException(409, {"code": "INJECTED_AFTER_RECEIPT"})
        return result

    original_lock = (service if contender == "approve" else reviews_service).lock_mutation
    def observed_lock(db):
        if db.info.get("contender"):
            contender_entered.set()
        return original_lock(db)

    monkeypatch.setattr(service, "save_receipt_tx", fault)
    monkeypatch.setattr(service if contender == "approve" else reviews_service, "lock_mutation", observed_lock)

    def run(is_contender):
        with dbm.SessionLocal() as db:
            db.info["contender"] = is_contender
            try:
                if is_contender and contender == "edit":
                    result = reviews_service.mutate_self(db, uid, review["id"], schema.UpdateReview(
                        expected_revision=1, declaration={**review["declaration"], "position": "并发更正岗位"}))
                else:
                    result = service.commit(db, "user-admin", key, schema.CommitInput(
                        expected_source_revision=preview["source_revision"], preview_token=preview["preview_token"],
                        command_id=successful_command if is_contender else failed_command, risk_acknowledged=True))
                return 200, result
            except HTTPException as error:
                db.rollback()
                return error.status_code, error.detail

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, False)
        try:
            assert reached.wait(15)
            second = pool.submit(run, True)
            assert contender_entered.wait(15)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.25)  # The independent transaction is blocked on the database lock.
        finally:
            release.set()
        assert first.result(timeout=15) == (409, {"code": "INJECTED_AFTER_RECEIPT"})
        status, result = second.result(timeout=15)
        assert status == 200, result
    with dbm.SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(iam.IamMutationReceipt).where(
            iam.IamMutationReceipt.idempotency_key == failed_command)) == 0
        row = db.get(reviews.PositionReview, review["id"])
        assert row.revision == 2
        events = list(db.scalars(select(reviews.PositionReviewEvent).where(reviews.PositionReviewEvent.review_id == review["id"])))
        assert sorted(event.event_type for event in events) == (["applied", "submitted"] if contender == "approve" else ["edited", "submitted"])
        outboxes = list(db.scalars(select(iam.IamOutbox).where(iam.IamOutbox.aggregate_id == review["id"])))
        assert len(outboxes) == 2
        if contender == "approve":
            assert row.status == "applied" and row.receipt_command_id == successful_command
        else:
            assert row.status == "pending" and row.receipt_command_id == ""
            assert identity(client, uid)["identity_version"] == before["identity_version"]
    if contender == "approve":
        assert commit(client, key, preview, command=successful_command)[0].json() == result
    else:
        stale = commit(client, key, preview)[0]
        assert stale.status_code == 409 and stale.json()["code"] == "REVIEW_REVISION_CONFLICT"
        key, _, fresh = plan(client, result["review"])
        assert commit(client, key, fresh)[0].status_code == 200
