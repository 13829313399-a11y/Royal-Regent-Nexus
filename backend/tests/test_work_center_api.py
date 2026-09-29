"""Isolated API regressions; never connects to the workstation business DB."""
import importlib
from urllib.parse import quote
from test_auth_api import make_client, ADMIN_TEST_PASSWORD
import json
from datetime import datetime, timezone
from sqlalchemy import select, func, text
import pytest


def actor(uid="user-admin", factory="huakang-a", department="engineering", permissions=()):
    auth = importlib.import_module("app.services.auth")
    grant = auth.AuthGrantContext(role_id="custom-duty", role_name="同名职位", role_code="custom-duty", factory_id=factory,
                                  department=department, permissions=frozenset(permissions), read_permissions=frozenset(permissions))
    return auth.AuthContext(id=uid, username=uid, display_name="测试成员", roles=("同名职位",), role_codes=("custom-duty",),
        permissions=frozenset(permissions), factory_scopes=(factory,), department_scopes=(department,), grants=(grant,),
        identity={"identity_mode": "v2", "employment_epoch": 1, "active_assignments_summary": [{"factory_id": factory, "department_code": department}]})


def services():
    return importlib.import_module("app.db"), importlib.import_module("app.services.work_center.service")


def new_quote(model, ident, **kw):
    values = dict(id=ident, factory_id="huakang-a", workshop_code="A", workshop_name="A车间", quote_no=ident,
        product_name="隔离测试产品", customer="测试", qty=100, version_label="V1", status="filling", created_by="user-admin",
        created_by_name="测试", created_at="2026-09-01 10:00:00", updated_at="2026-09-01 10:00:00")
    return model(**(values | kw))


def login(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_identity_is_info_and_personal_read_does_not_write_old_notification(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = login(client)
        dbm = importlib.import_module("app.db")
        auth = importlib.import_module("app.models.auth")
        with dbm.SessionLocal() as db:
            db.add(auth.SystemNotification(id="identity-test", type="identity_changed", target_user_id=user_id,
                                           title="任职更新", created_at="2026-09-28 10:00:00"))
            db.commit()
        response = client.get("/api/work-center/snapshot?view=info")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["summary"]["actionable_total"] == 0
        assert data["summary"]["info_unread_total"] == 1
        item = data["items"][0]
        assert item["actions"][0]["mode"] == "refresh_identity"
        response = client.patch(f'/api/work-center/entries/{quote(item["id"], safe="")}/user-state',
                                json={"observed_content_version": item["content_version"]})
        assert response.status_code == 200, response.text
        assert client.get("/api/work-center/snapshot?view=info").json()["summary"]["info_unread_total"] == 0
        with dbm.SessionLocal() as db:
            assert db.get(auth.SystemNotification, "identity-test").status == "unread"
            compatibility = importlib.import_module("app.services.work_center.compatibility")
            user = importlib.import_module("app.services.auth").build_auth_context(db, db.get(auth.AuthUser, user_id))
            assert compatibility.system_out(db, user, [db.get(auth.SystemNotification, "identity-test")])[0].status == "read"


def test_source_registration_survives_legacy_handled_and_snooze(monkeypatch):
    with make_client(monkeypatch) as client:
        user_id = login(client)
        dbm = importlib.import_module("app.db")
        auth = importlib.import_module("app.models.auth")
        with dbm.SessionLocal() as db:
            db.add(auth.AuthRegistrationRequest(id="old-request", user_id=user_id, username="pending-test", display_name="测试",
                   factory_id="huakang-a", department="engineering", status="pending", submitted_at="2025-01-01 08:00:00"))
            db.add(auth.SystemNotification(id="old-message", type="user_registration", status="handled"))
            db.commit()
        response = client.get("/api/work-center/snapshot")
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        url = f'/api/work-center/entries/{quote(item["id"], safe="")}/user-state'
        response = client.patch(url, json={"state_version": 0, "snoozed_until": "2099-01-01T00:00:00Z"})
        assert response.status_code == 200, response.text
        summary = client.get("/api/work-center/snapshot").json()["summary"]
        assert summary["actionable_total"] == 1
        assert summary["snoozed_total"] == 1
        assert summary["focus_total"] == 0
        assert client.patch(url, json={"state_version": 1, "archived": True}).status_code == 409
        assert client.patch(url, json={"lifecycle": "resolved"}).status_code == 422
        with dbm.SessionLocal() as db:
            db.get(auth.AuthRegistrationRequest, "old-request").status = "approved"
            db.commit()
        assert client.get("/api/work-center/snapshot").json()["summary"]["actionable_total"] == 0
        assert len(client.get("/api/work-center/snapshot?view=history").json()["items"]) == 1


def test_personal_versions_epoch_permission_and_batch(monkeypatch):
    from test_internal_quote_api import ensure_user
    with make_client(monkeypatch) as client:
        uid = login(client)
        ensure_user("peer", "admin", "engineering", "huakang-a")
        dbm, svc = services()
        auth = importlib.import_module("app.models.auth")
        schema = importlib.import_module("app.schemas.work_center")
        with dbm.SessionLocal() as db:
            db.add(auth.AuthRegistrationRequest(id="r", user_id=uid, username="pending", factory_id="huakang-a", department="engineering", submitted_at="2024-01-01 00:00:00"))
            db.commit()
            a = actor(uid, permissions=("system:user_manage",))
            b = actor("user-peer", permissions=("system:user_manage",))
            item = svc.snapshot(db, a)["items"][0]
            svc.patch_state(db, a, item["id"], schema.UserStatePatch(observed_content_version=1)); db.commit()
            assert svc.detail(db, a, item["id"])["personal"]["read_state"] == "read"
            assert svc.detail(db, b, item["id"])["personal"]["read_state"] == "unread"
            assert svc.snapshot(db, actor(uid))["summary"]["actionable_total"] == 0
            with pytest.raises(Exception) as error: svc.detail(db, actor(uid), item["id"])
            assert error.value.status_code == 404
            svc.patch_state(db, a, item["id"], schema.UserStatePatch(observed_content_version=0)); db.commit()
            assert svc.detail(db, a, item["id"])["personal"]["read_state"] == "read"
            with pytest.raises(Exception) as error:
                svc.patch_state(db, a, item["id"], schema.UserStatePatch(pinned=True, state_version=0))
            assert error.value.status_code == 409
            db.rollback()
            wc = importlib.import_module("app.models.work_center")
            projected = db.get(wc.WorkCenterEntry, item["id"])
            projected.content_version = 4; projected.attention_version = 2; db.commit()
            svc.patch_state(db, a, item["id"], schema.UserStatePatch(observed_content_version=3)); db.commit()
            assert svc.detail(db, a, item["id"])["personal"]["read_state"] == "unread"
            profile = db.get(auth.EmployeeProfile, uid); profile.employment_epoch += 1; db.commit()
            assert svc.detail(db, a, item["id"])["personal"]["read_state"] == "unread"
        response = client.post("/api/work-center/user-state/batch", json={"items": [{"id": item["id"], "observed_content_version": 1}, {"id": "missing", "observed_content_version": 1}]})
        assert response.status_code == 200, response.text
        assert [r["status"] for r in response.json()["results"]] == ["ok", "error"]
        response = client.post("/api/work-center/user-state/batch", json={"items": [
            {"id": item["id"], "observed_content_version": 999},
            {"id": item["id"], "observed_content_version": 4}]})
        assert [r["status"] for r in response.json()["results"]] == ["error", "ok"]
        assert response.json()["results"][1]["entry"]["personal"]["read_state"] == "read"
        initial = client.get("/api/work-center/preferences").json()
        assert client.patch("/api/work-center/preferences", json={"sound_enabled": True, "version": initial["version"]}).status_code == 200
        assert client.patch("/api/work-center/preferences", json={"sound_enabled": False, "version": initial["version"]}).status_code == 409


def test_molding_dispatch_and_cycle_withdrawal(monkeypatch):
    with make_client(monkeypatch):
        dbm, svc = services()
        models = importlib.import_module("app.models.molding_sample")
        permissions = ("molding_sample:production_read", "molding_sample:production_start", "molding_sample:production_fillback")
        a = actor(factory="huakang-a", department="production", permissions=permissions)
        b = actor(factory="huakang-b", department="production", permissions=permissions)
        with dbm.SessionLocal() as db:
            order = models.MoldingSampleOrder(id="C-to-A", factory_id="huakang-c", production_factory_id="huakang-a",
                product_name="跨厂测试", date="2026-09-01", status="待生产", created_at="2026-09-01 12:00:00")
            db.add(order); db.commit()
            old = svc.snapshot(db, a)["items"][0]
            assert old["source_factory"]["id"] == "huakang-c"
            assert old["execution_factory"]["id"] == "huakang-a"
            assert svc.snapshot(db, b)["summary"]["actionable_total"] == 0
            order.production_factory_id = "huakang-b"; order.production_assignment_version += 1; db.commit()
            assert svc.snapshot(db, a)["summary"]["actionable_total"] == 0
            assert svc.snapshot(db, b)["summary"]["actionable_total"] == 1
            with pytest.raises(Exception) as error: svc.detail(db, a, old["id"])
            assert error.value.status_code == 404
            first = svc.snapshot(db, b)["items"][0]["id"]
            db.add(models.MoldingSampleNotification(id="legacy-completion", order_id=order.id, factory_id="huakang-b",
                target_module="production_molding_sample_task", target_role="production", event_type="生产完成回传"))
            for n, (before, after) in enumerate((("待生产", "生产中"), ("生产中", "已完成"), ("已完成", "生产中"))):
                order.status = after
                db.add(models.MoldingSampleAuditLog(id=f"m-audit-{n}", order_id=order.id, action="正式流转", from_status=before,
                    to_status=after, actor_user_id="user-admin", actor_name="测试", created_at=f"2026-09-28 10:0{n}:00"))
                db.commit()
            current = svc.snapshot(db, b)["items"][0]
            assert current["id"] != first and current["stage_label"] == "填写啤办结果"
            assert svc.snapshot(db, b)["summary"]["actionable_total"] == 1
            history = svc.snapshot(db, b, view="history")["items"]
            assert next(item for item in history if ":legacy_history:" in item["id"])["lifecycle"] == "superseded"


def test_quote_batch_reviewer_version_and_v2_nonroot(monkeypatch):
    with make_client(monkeypatch):
        dbm, svc = services()
        model = importlib.import_module("app.models.internal_quote")
        formula = importlib.import_module("app.services.internal_quote_calculator").FORMULA_VERSION
        reviewer = actor(department="sales-business", permissions=("internal_quote:read", "internal_quote:sales_review", "internal_quote:final_submit"))
        # The actual business identity rule must be satisfied in addition to a display name.
        from dataclasses import replace
        reviewer = replace(reviewer, grants=(replace(reviewer.grants[0], role_id="position_sales_quote_reviewer", role_code="position_sales_quote_reviewer"),))
        with dbm.SessionLocal() as db:
            for pos in (1, 2):
                q = new_quote(model.InternalQuote, f"v3-{pos}", module_version="v3", batch_id="B", batch_position=pos,
                    business_owner_id=reviewer.id, created_by="other", status="final_reviewing", final_release_status="pending",
                    final_submission_revision=1, formula_version=formula, final_submission_manifest_json=json.dumps({"header_revision": 1, "section_revisions": {"engineering": 1}}))
                db.add(q)
                db.add(model.InternalQuoteSection(id=f"s{pos}", quote_id=q.id, department="engineering", department_name="工程",
                    status="pending_review", is_required=True, revision=1, calculation_status="valid", dependency_status="current", calculation_formula_version=formula))
            db.add(new_quote(model.InternalQuote, "v2-nonroot", batch_position=2, status="ready_for_final_review"))
            db.add(new_quote(model.InternalQuote, "v4", module_version="v4", status="final_reviewing", final_release_status="pending"))
            db.commit()
            data = svc.snapshot(db, reviewer)
            assert {i["reference_label"] for i in data["items"]} == {"v3-1", "v2-nonroot"}
            assert svc.snapshot(db, actor("other", department="sales-business", permissions=("internal_quote:read", "internal_quote:sales_review")))["summary"]["actionable_total"] == 0
            db.get(model.InternalQuoteSection, "s2").revision = 2; db.commit()
            data = svc.snapshot(db, reviewer)
            assert data["summary"]["actionable_total"] == 1
            assert data["health"]["status"] == "partial"
            for pos in (1, 2):
                q = db.get(model.InternalQuote, f"v3-{pos}"); q.status = "rejected"; q.final_release_status = "rejected"
                section = db.get(model.InternalQuoteSection, f"s{pos}")
                section.status = "rejected"; section.filled_at = "2026-09-01 10:00:00"; section.payload_json = '{"valid":true}'
            db.commit()
            editor = actor(permissions=("internal_quote:read", "internal_quote:engineering_edit"))
            assert svc.snapshot(db, editor)["summary"]["actionable_total"] == 2


def test_reconcile_twice_snapshot_read_only_savepoint_events_cursor(monkeypatch):
    with make_client(monkeypatch) as client:
        uid = login(client)
        dbm, svc = services()
        auth = importlib.import_module("app.models.auth")
        wc = importlib.import_module("app.models.work_center")
        rec = importlib.import_module("app.services.work_center.reconciliation")
        with dbm.SessionLocal() as db:
            # Bulk SQL represents historical data written before hooks existed.
            for i in range(7):
                db.execute(auth.AuthRegistrationRequest.__table__.insert().values(id=f"historical-{i}", user_id=uid, username=f"u{i}",
                    factory_id="huakang-a", department="engineering", status="pending", submitted_at="2025-01-01 12:00:00"))
            db.commit()
            dry = rec.reconcile(db)
            assert dry["current_by_module"]["account_requests"] == 7
            assert db.scalar(select(func.count()).select_from(wc.WorkCenterEntry)) == 0
            first = rec.reconcile(db, apply=True); db.commit()
            second = rec.reconcile(db, apply=True); db.commit()
            assert first["projection"]["created"] == 7
            assert second["projection"] == {"created": 0, "updated": 0, "unchanged": 7}
            assert db.scalar(select(func.count()).select_from(wc.WorkCenterEvent)) == 7
            projection = importlib.import_module("app.services.work_center.projection")
            registry = importlib.import_module("app.services.work_center.registry")
            source = registry.current_query(db, None)
            repeated = db.execute(select(source).where(source.c.entity_id == "historical-0")).mappings().all()
            for _ in range(100): projection.materialize(db, repeated, legacy=True)
            db.commit()
            assert db.scalar(select(func.count()).select_from(wc.WorkCenterEvent)) == 7
            db.add(auth.AuthRegistrationRequest(id="outer", user_id=uid, username="outer", factory_id="huakang-a", department="engineering"))
            db.flush()
            with db.begin_nested() as nested: nested.rollback()
            db.commit()
            assert db.get(wc.WorkCenterEntry, "account_requests:outer:registration:1")
            user = actor(uid, permissions=("system:user_manage",))
            ids, cursor = [], None
            while True:
                page = svc.snapshot(db, user, limit=3, cursor=cursor)
                ids.extend(i["id"] for i in page["items"])
                cursor = page["next_cursor"]
                if not cursor: break
            assert len(ids) == len(set(ids)) == 8
            entry_id = "account_requests:historical-0:registration:1"
            for i in range(8): db.add(wc.WorkCenterEvent(id=f"event-{i}", entry_id=entry_id, source_event_key=f"test-{i}",
                occurred_at=datetime(2090, 1, 1, tzinfo=timezone.utc), event_kind="test", safe_summary="相同时间事件"))
            db.commit()
            events1 = svc.events(db, user, entry_id, limit=5)
            events2 = svc.events(db, user, entry_id, events1["next_cursor"], limit=5)
            assert len({i["id"] for i in events1["items"] + events2["items"]}) == 9
            assert not db.new and not db.dirty
        assert client.get("/api/work-center/snapshot?cursor=not-json").status_code == 409
        page = client.get("/api/work-center/snapshot?limit=3").json()
        assert client.get("/api/work-center/snapshot", params={"cursor": page["next_cursor"], "q": "changed"}).status_code == 409


def test_password_reset_approved_waiting_not_actionable(monkeypatch):
    with make_client(monkeypatch) as client:
        uid = login(client)
        dbm, svc = services()
        auth = importlib.import_module("app.models.auth")
        with dbm.SessionLocal() as db:
            db.add(auth.AuthPasswordResetRequest(id="reset", user_id=uid, username="test", factory_id="huakang-a", department="engineering",
                reviewer_user_id=uid, status="approved", approved_at="2026-09-28 10:00:00", expires_at="2099-01-01 00:00:00", issue_count=1))
            db.commit()
        data = client.get("/api/work-center/snapshot?view=waiting").json()
        assert data["summary"]["actionable_total"] == 0
        assert data["summary"]["waiting_total"] == 1
        assert data["items"][0]["can_act_now"] is False
        entry = data["items"][0]
        assert client.patch(f'/api/work-center/entries/{quote(entry["id"], safe="")}/user-state', json={"following": False, "state_version": 0}).status_code == 200
        assert client.get("/api/work-center/snapshot?view=waiting").json()["summary"]["waiting_total"] == 0
        with dbm.SessionLocal() as db:
            db.get(auth.AuthPasswordResetRequest, "reset").expires_at = "2020-01-01 00:00:00"; db.commit()
        assert client.get("/api/work-center/snapshot?view=waiting").json()["summary"]["waiting_total"] == 0


def test_snapshot_is_one_read_transaction_during_concurrent_completion(monkeypatch):
    from sqlalchemy import event
    with make_client(monkeypatch) as client:
        uid = login(client)
        dbm, svc = services()
        auth = importlib.import_module("app.models.auth")
        with dbm.engine.connect() as conn: conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        with dbm.SessionLocal() as db:
            db.add(auth.AuthRegistrationRequest(id="concurrent", user_id=uid, username="test", factory_id="huakang-a", department="engineering"))
            db.commit()
        completed = False
        def complete_after_summary(conn, cursor, statement, params, context, many):
            nonlocal completed
            if not completed and " AS actionable_total" in statement:
                completed = True
                with dbm.engine.begin() as writer:
                    writer.execute(auth.AuthRegistrationRequest.__table__.update().where(auth.AuthRegistrationRequest.id == "concurrent").values(status="approved"))
        event.listen(dbm.engine, "after_cursor_execute", complete_after_summary)
        try:
            data = client.get("/api/work-center/snapshot").json()
            assert completed and data["summary"]["actionable_total"] == data["query"]["filtered_total"] == len(data["items"]) == 1
        finally:
            event.remove(dbm.engine, "after_cursor_execute", complete_after_summary)
        assert client.get("/api/work-center/snapshot").json()["summary"]["actionable_total"] == 0
        # A late old notification cannot reopen the completed source obligation.
        with dbm.SessionLocal() as db:
            db.add(auth.SystemNotification(id="late-old", type="user_registration", target_factory_id="huakang-a",
                payload_json=json.dumps({"registration_request_id": "concurrent"}), created_at="2025-01-01 12:00:00"))
            db.commit()
        assert client.get("/api/work-center/snapshot").json()["summary"]["actionable_total"] == 0


def test_reset_scope_includes_functional_organization_and_full_target_scope(monkeypatch):
    with make_client(monkeypatch):
        dbm, svc = services()
        auth = importlib.import_module("app.models.auth")
        system = importlib.import_module("app.services.system")
        manager = actor(factory="group-management", department="engineering", permissions=("system:user_manage",))
        with dbm.SessionLocal() as db:
            db.add(auth.AuthPasswordResetRequest(id="group-reset", user_id="user-admin", username="admin",
                factory_id="group-management", department="engineering", status="pending", claim_token_hash="qa"))
            db.commit()
            monkeypatch.setattr(system, "target_users_scopes", lambda db, targets: {"user-admin": {("group-management", "engineering")}})
            assert svc.snapshot(db, manager)["summary"]["actionable_total"] == 1
            db.get(auth.AuthPasswordResetRequest, "group-reset").status = "completed"; db.commit()
            assert len(svc.snapshot(db, manager, view="history")["items"]) == 1
            monkeypatch.setattr(system, "target_users_scopes", lambda db, targets: {"user-admin": {("group-management", "engineering"), ("huakang-a", "engineering")}})
            assert svc.snapshot(db, manager, view="history")["items"] == []


def test_partial_adapter_failure_and_invalid_old_source_are_not_clean_zero(monkeypatch):
    with make_client(monkeypatch) as client:
        uid = login(client)
        dbm, svc = services()
        auth = importlib.import_module("app.models.auth")
        with dbm.SessionLocal() as db:
            db.add(auth.SystemNotification(id="bad-quote", type="internal_quote", target_factory_id="huakang-a", payload_json='{"quote_id":"missing"}'))
            db.add(auth.AuthRegistrationRequest(id="still-pending", user_id=uid, username="test", factory_id="huakang-a", department="engineering"))
            db.commit()
        data = client.get("/api/work-center/snapshot").json()
        assert data["health"]["status"] == "partial"
        assert data["summary"]["verification_required_total"] == 1
        assert data["summary"]["actionable_total"] == 1
        # Simulate an unavailable adapter table in this disposable DB only.
        with dbm.engine.begin() as conn: conn.execute(text("DROP TABLE carton_supplier_shipments"))
        response = client.get("/api/work-center/snapshot")
        assert response.status_code == 200, response.text
        assert response.json()["health"]["status"] == "partial"
        assert "carton_supplier" in response.json()["health"]["unavailable_sources"]
        assert response.json()["summary"]["actionable_total"] == 1
