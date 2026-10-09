import importlib.util
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.module_feedback import router
from app.core.config import settings
from app.db import get_db
from app.models.auth import AuthPermission
from app.models.customer_order_ledger import OrderLedgerLine
from app.models.module_feedback import FeedbackAttachment, FeedbackMessage, FeedbackReadReceipt, FeedbackTicket
from app.schemas.module_feedback import FeedbackCreate, FeedbackReply
from app.services import module_feedback as service
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, AuthProfileContext, get_current_user
from app.services.permission_codes import APPLICATION_PERMISSION_CODES, BUSINESS_PERMISSION_CODES
from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS


MODELS = (FeedbackTicket, FeedbackMessage, FeedbackAttachment, FeedbackReadReceipt)
BASE = "/api/module-feedback"
SCOPE = "?factory_id=huaxing"


def user(identity="owner", factory="huaxing", department="sales-business", permissions=None):
    permissions = frozenset(permissions if permissions is not None else {"customer_order:read"})
    return AuthContext(id=identity, username=identity, display_name=identity, roles=("test",), role_codes=("test",),
        permissions=permissions, factory_scopes=(factory,), department_scopes=(department,),
        profile=AuthProfileContext(primary_factory_id=factory, primary_department=department, confirmation_status="confirmed"),
        grants=(AuthGrantContext("test", "test", factory, department, permissions),))


def developer(factory="huaxing"):
    return user("dev", factory, "system", {service.MANAGE})


def png():
    stream = BytesIO()
    Image.new("RGB", (20, 10), "red").save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (AuthPermission, OrderLedgerLine, *MODELS):
        model.__table__.create(engine)
    app = FastAPI()
    app.include_router(router)
    context = {"user": user()}

    def db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: context["user"]
    with TestClient(app) as client:
        yield client, context, engine
    engine.dispose()


def create_payload(**kwargs):
    return {"factory_id": "huaxing", "module": service.MODULE, "title": "导入问题", "body": "操作后出现错误 😕",
            "category": "bug", "emoji": "😕", "client_request_id": str(uuid4()), **kwargs}


def multipart(client, url, payload, files=()):
    return client.post(url, data={"payload": json.dumps(payload)}, files=[("files", item) for item in files])


def created(api, files=()):
    result = multipart(api[0], BASE, create_payload(), files)
    assert result.status_code == 200, result.text
    return result.json()


def action(client, ticket, name="reply", **kwargs):
    payload = {"expected_revision": ticket["revision"], "client_request_id": str(uuid4()), "action": name, **kwargs}
    return multipart(client, BASE + "/" + ticket["id"] + "/messages" + SCOPE, payload)


def test_lifecycle_owner_verifies_and_reopens_preserving_history(api):
    client, context, engine = api
    ticket = created(api)
    assert ticket["status"] == "submitted" and not ticket["unread"]
    assert ticket["messages"][0]["actor_kind"] == "user"
    assert action(client, ticket, "start").status_code == 403
    assert action(client, ticket, "resolve").status_code == 409
    context["user"] = developer()
    assert client.get(BASE + SCOPE + "&view=manage").json()["unread_count"] == 1
    ticket = action(client, ticket, "start").json()
    assert ticket["status"] == "in_progress"
    assert action(client, ticket, "resolve").status_code == 403
    assert action(client, ticket, "ready").status_code == 422
    ticket = action(client, ticket, "ready", body="修复已经发布", release_note="2026.10.05-v2：修复导入空行").json()
    assert ticket["status"] == "awaiting_verification"
    assert ticket["messages"][-1]["actor_kind"] == "developer"
    context["user"] = user()
    assert client.get(BASE + SCOPE).json()["unread_count"] == 1
    ticket = action(client, ticket, "resolve", body="已验证正常").json()
    assert ticket["status"] == "resolved"
    assert action(client, ticket, body="还想补充").status_code == 409
    context["user"] = developer()
    assert action(client, ticket, body="请补充").status_code == 409
    context["user"] = user()
    ticket = action(client, ticket, "reopen", body="另一个文件仍有问题").json()
    assert ticket["status"] == "submitted"
    assert len(ticket["messages"]) == 5
    assert ticket["release_note"].startswith("2026.10.05")


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_scope_ownership_revocation_and_explicit_denies_all_modes(api, monkeypatch, mode):
    client, context, _ = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    ticket = created(api, [("screen.png", png(), "image/png")])
    url = BASE + "/" + ticket["id"]
    attachment_url = ticket["messages"][0]["attachments"][0]["url"]
    for forbidden in (user("other"), user(factory="huadeng"), replace(user(), profile=None), replace(user(), profile=AuthProfileContext(primary_factory_id="huaxing"))):
        context["user"] = forbidden
        assert client.get(url + SCOPE).status_code in {403, 404}
        assert client.get(attachment_url).status_code in {403, 404}
        assert action(client, ticket, body="guess").status_code in {403, 404}
        assert client.post(url + "/read" + SCOPE, json={"through_revision": 1}).status_code in {403, 404}
    context["user"] = user("other")
    assert client.get(BASE + SCOPE).json()["total"] == 0
    assert client.get(BASE + SCOPE + "&view=manage").status_code == 403
    for original, permission, department in ((user(), service.SUBMIT, "sales-business"), (developer("huadeng"), service.MANAGE, "system")):
        context["user"] = replace(original, overrides=(AuthOverrideContext("deny", permission, "deny", "huaxing", department),))
        assert client.get(url + SCOPE).status_code == 403
    context["user"] = developer("huadeng")
    assert client.get(url + SCOPE).status_code == 403
    context["user"] = developer()
    assert client.get(url + SCOPE).status_code == 200
    assert client.get(url + "?factory_id=huadeng").status_code == 403


def test_wildcard_admin_denies_and_explicit_scope_only(api):
    client, context, _ = api
    ticket = created(api)
    admin = replace(user("admin"), grants=(AuthGrantContext("admin", "admin", "*", "*", frozenset(), role_code="admin"),))
    context["user"] = admin
    assert client.get(BASE + SCOPE + "&view=manage").status_code == 200
    context["user"] = replace(admin, overrides=(AuthOverrideContext("deny", service.MANAGE, "deny", "huaxing", "system"),))
    assert client.get(BASE + SCOPE + "&view=manage").status_code == 403
    assert client.get(BASE + "/" + ticket["id"] + SCOPE).status_code == 404
    expanded = user(factory="huadeng")
    context["user"] = replace(expanded, grants=(replace(expanded.grants[0], unrestricted_department=True,
        scope_mode="cross_factory_read", read_permissions=frozenset({"customer_order:read"})),))
    assert client.get(BASE + "/capabilities" + SCOPE).json()["can_submit"] is False
    context["user"] = replace(developer("huadeng"), overrides=(AuthOverrideContext("allow", service.MANAGE, "allow", "huaxing", "system"),))
    assert client.get(BASE + SCOPE + "&view=manage").status_code == 200
    assert service.MANAGE in APPLICATION_PERMISSION_CODES
    assert service.MANAGE not in BUSINESS_PERMISSION_CODES
    assert all(service.MANAGE not in position.permission_codes for position in SYSTEM_POSITION_DEFINITIONS)


def test_create_and_reply_idempotency_revision_and_actor_forgery(api):
    client, context, engine = api
    payload = create_payload()
    first = multipart(client, BASE, payload).json()
    assert multipart(client, BASE, payload).json()["id"] == first["id"]
    assert multipart(client, BASE, payload | {"body": "changed"}).status_code == 409
    assert multipart(client, BASE, payload | {"author_id": "admin"}).status_code == 422
    request = {"expected_revision": 1, "client_request_id": "retry-123456", "body": "补充说明"}
    url = BASE + "/" + first["id"] + "/messages" + SCOPE
    assert multipart(client, url, request).json()["revision"] == 2
    assert multipart(client, url, request).json()["revision"] == 2
    assert multipart(client, url, request | {"body": "different"}).status_code == 409
    assert multipart(client, url, request | {"client_request_id": "another-request"}).status_code == 409
    context["user"] = replace(user(), profile=None)
    assert multipart(client, BASE, payload).status_code == 403
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(FeedbackTicket)) == 1
        assert db.scalar(select(func.count()).select_from(FeedbackMessage)) == 2


def test_read_receipts_do_not_hide_new_reply_or_regress_and_filters_do_not_hide_unread(api):
    client, context, engine = api
    ticket = created(api)
    context["user"] = developer()
    ticket = action(client, ticket, body="正在检查").json()
    viewed_revision = ticket["revision"]
    ticket = action(client, ticket, body="已找到原因").json()
    context["user"] = user()
    read_url = BASE + "/" + ticket["id"] + "/read" + SCOPE
    assert client.post(read_url, json={"through_revision": viewed_revision}).status_code == 200
    result = client.get(BASE + SCOPE + "&status=resolved&q=nomatch").json()
    assert result["total"] == 0 and result["unread_count"] == 1
    assert client.get(BASE + "/" + ticket["id"] + SCOPE).json()["unread"] is True
    assert client.post(read_url, json={"through_revision": 999}).status_code == 422
    assert client.post(read_url, json={"through_revision": ticket["revision"]}).json()["through_revision"] == 3
    assert client.post(read_url, json={"through_revision": 1}).json()["through_revision"] == 3
    assert client.get(BASE + SCOPE).json()["unread_count"] == 0
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(FeedbackReadReceipt).where(FeedbackReadReceipt.user_id == "owner")) == 3


def test_requested_materials_are_developer_controlled_and_evidence_required(api):
    client, context, _ = api
    ticket = created(api)
    assert action(client, ticket, "request_info", body="hey", requested_materials=["steps"]).status_code == 403
    assert action(client, ticket, body="hey", requested_materials=["steps"]).status_code == 422
    context["user"] = developer()
    assert action(client, ticket, "request_info", requested_materials=["steps"]).status_code == 422
    ticket = action(client, ticket, "request_info", body="请提供操作和截图", requested_materials=["steps", "screenshot"]).json()
    context["user"] = user()
    assert action(client, ticket, body="有步骤", provided_materials=["original_file"]).status_code == 422
    assert action(client, ticket, body="有截图", provided_materials=["screenshot"]).status_code == 422
    ticket = action(client, ticket, body="先导入再保存", provided_materials=["steps"]).json()
    assert ticket["provided_materials"] == ["steps"]
    request = {"expected_revision": ticket["revision"], "client_request_id": str(uuid4()), "body": "截图在此",
               "provided_materials": ["screenshot"]}
    ticket = multipart(client, BASE + "/" + ticket["id"] + "/messages" + SCOPE, request,
                       [("annotated.png", png(), "image/png")]).json()
    assert set(ticket["provided_materials"]) == {"steps", "screenshot"}
    assert ticket["status"] == "in_progress"
    context["user"] = developer()
    ticket = action(client, ticket, "request_info", body="另外需要原始文件", requested_materials=["original_file"]).json()
    assert ticket["provided_materials"] == []
    assert ticket["messages"][1]["requested_materials"] == ["steps", "screenshot"]


def test_attachment_scope_validation_and_atomicity(api, monkeypatch):
    client, context, engine = api
    ticket = created(api, [("../screen.png", png(), "application/octet-stream")])
    attachment = ticket["messages"][0]["attachments"][0]
    assert attachment["file_name"] == "screen.png"
    response = client.get(attachment["url"])
    assert response.content == png()
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "private, no-store"
    other = created(api)
    assert client.get(attachment["url"].replace(ticket["id"], other["id"])).status_code == 404
    for filename, data in (("bad.svg", b"<svg/>"), ("bad.png", b"bogus"), ("fake.jpg", png()), ("bad.xlsx", b"PK"), ("bad.pdf", b"%PDF-bad"), ("bad.xls", b"xls")):
        assert multipart(client, BASE, create_payload(), [(filename, data, "image/png")]).status_code == 422
    assert multipart(client, BASE, create_payload(), [("x.png", png(), "image/png")] * 6).status_code == 400
    monkeypatch.setattr(service, "MAX_FILE_BYTES", 20)
    assert multipart(client, BASE, create_payload(), [("screen.png", png(), "image/png")]).status_code == 413
    monkeypatch.setattr(service, "MAX_REQUEST_BYTES", 20)
    assert multipart(client, BASE, create_payload()).status_code == 413
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(FeedbackTicket)) == 2
        assert db.scalar(select(func.count()).select_from(FeedbackAttachment)) == 1


def test_context_is_whitelisted_and_linked_order_verified(api):
    client, context, engine = api
    with Session(engine) as db:
        db.add(OrderLedgerLine(id="order-hx", factory_id="huaxing", customer_code="buzzbee", customer_name="BuzzBee",
            identity_key="key", reference_no="PO123", product_no="P1", data={}, created_at="now", updated_at="now"))
        db.add(OrderLedgerLine(id="order-hd", factory_id="huadeng", customer_code="casdon", customer_name="Casdon",
            identity_key="key", reference_no="private", product_no="secret", data={}, created_at="now", updated_at="now"))
        db.commit()
    for extra in ({"cookie": "secret"}, {"file_names": ["C:\\secrets.txt"]}, {"order_id": "order-hd"}):
        response = multipart(client, BASE, create_payload(context=extra))
        assert response.status_code in {404, 422}
    response = multipart(client, BASE, create_payload(context={"order_id": "order-hx", "order_reference": "forged",
        "product_no": "forged", "customer_code": "forged", "error_message": "错误", "file_names": ["test.xlsx"]}))
    assert response.status_code == 200
    linked = response.json()["context"]
    assert linked["order_reference"] == "PO123" and linked["product_no"] == "P1" and linked["customer_code"] == "buzzbee"
    assert client.get(BASE + "/capabilities?factory_id=group").status_code == 422
    assert client.get(BASE + "/capabilities" + SCOPE + "&module=internal-quote").status_code == 422


def migration():
    path = Path(__file__).parents[1] / "alembic/versions/20261005_0120_module_feedback.py"
    spec = importlib.util.spec_from_file_location("feedback_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_append_only_constraints_and_nondestructive_downgrade(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    AuthPermission.__table__.create(engine)
    revision = migration()
    assert revision.down_revision == "20260924_0119"
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
    with Session(engine) as db:
        assert db.scalar(select(AuthPermission).where(AuthPermission.code == service.MANAGE))
        ticket = service.create_ticket(db, user(), FeedbackCreate(**create_payload()), service.validate_uploads([("a.png", png())]))
    for table, column, value in (("module_feedback_messages", "body", "'overwrite'"),
                                  ("module_feedback_reads", "through_revision", "99"),
                                  ("module_feedback_attachments", "file_name", "'replace'")):
        for command in (f"UPDATE {table} SET {column}={value}", f"DELETE FROM {table}"):
            with engine.begin() as connection:
                with pytest.raises(DatabaseError, match="append-only"):
                    connection.execute(text(command))
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="Cannot discard"):
                revision.downgrade()
    import app.db as db_module
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.ensure_module_feedback_schema_ready()
    engine.dispose()


def test_empty_migration_roundtrip_and_startup_guard(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "guard.db"))
    AuthPermission.__table__.create(engine)
    import app.db as db_module
    monkeypatch.setattr(db_module, "engine", engine)
    with pytest.raises(RuntimeError, match="20261005_0120"):
        db_module.ensure_module_feedback_schema_ready()
    assert "module_feedback_tickets" not in inspect(engine).get_table_names()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
            migration().downgrade()
    assert inspect(engine).get_table_names() == ["auth_permissions"]
    engine.dispose()


def test_image_only_submission_and_developer_mine(api):
    client, context, _ = api
    assert multipart(client, BASE, create_payload(body="")).status_code == 422
    result = multipart(client, BASE, create_payload(body=""), [("screen.png", png(), "image/png")])
    assert result.status_code == 200
    context["user"] = developer()
    assert client.get(BASE + SCOPE).json()["total"] == 0
    assert client.get(BASE + SCOPE + "&view=manage").json()["total"] == 1


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_reply_cas_and_retry_are_atomic(tmp_path, monkeypatch, same_request):
    engine = create_engine("sqlite:///" + str(tmp_path / "concurrent.db"), connect_args={"check_same_thread": False})
    for model in MODELS:
        model.__table__.create(engine)
    with Session(engine) as db:
        ticket = service.create_ticket(db, user(), FeedbackCreate(**create_payload()), [])
    barrier = Barrier(2)
    original_hash = service._request_hash

    def both_have_read(payload, files):
        result = original_hash(payload, files)
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(service, "_request_hash", both_have_read)

    def worker(index):
        payload = FeedbackReply(expected_revision=1, client_request_id="same-request" if same_request else f"request-{index}", body="reply")
        with Session(engine) as db:
            try:
                result = service.reply(db, developer(), ticket["id"], "huaxing", payload,
                                       service.validate_uploads([("screen.png", png())]))
                return 200, result["revision"]
            except HTTPException as exc:
                return exc.status_code, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, [1, 2]))
    assert sorted(status for status, _ in results) == ([200, 200] if same_request else [200, 409])
    with Session(engine) as db:
        assert db.get(FeedbackTicket, ticket["id"]).revision == 2
        assert db.scalar(select(func.count()).select_from(FeedbackMessage)) == 2
        assert db.scalar(select(func.count()).select_from(FeedbackAttachment)) == 1
    engine.dispose()


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
@pytest.mark.parametrize("has_role", [True, False])
def test_confirmed_legacy_sales_supervisor_and_roleless_employee_can_feedback_without_business_access(api, monkeypatch, mode, has_role):
    client, context, _ = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    # Reproduce the reported account's permission shape without changing it.
    employee = user("zhang", permissions={"customer_order:duplicate_confirm", "customer_order:audit_read"})
    employee = replace(employee, grants=(replace(employee.grants[0], role_id="sales_customer_supervisor",
        role_code="sales_customer_supervisor"),) if has_role else (),
        permissions=employee.permissions if has_role else frozenset())
    context["user"] = employee
    before = employee
    caps = client.get(BASE + "/capabilities" + SCOPE).json()
    assert caps["can_submit"] is True and caps["can_manage"] is False and caps["can_link_order"] is False
    ticket = created(api, [("screenshot.png", png(), "image/png")])
    assert action(client, ticket, body="没有权限，请协助").status_code == 200
    assert client.get(ticket["messages"][0]["attachments"][0]["url"]).status_code == 200
    assert client.get(BASE + SCOPE).json()["total"] == 1
    assert client.get(BASE + SCOPE + "&view=manage").status_code == 403
    assert context["user"] == before
    assert "customer_order:read" not in context["user"].permissions
    context["user"] = replace(employee, id="coworker", username="coworker")
    assert client.get(BASE + SCOPE).json()["total"] == 0
    assert client.get(BASE + "/" + ticket["id"] + SCOPE).status_code == 404
    assert client.get(ticket["messages"][0]["attachments"][0]["url"]).status_code == 404


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_home_factory_and_confirmation_required_even_with_read_allow_or_admin(api, monkeypatch, mode):
    client, context, _ = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    for profile in (None, AuthProfileContext(primary_factory_id="huaxing", confirmation_status="needs_review"),
                    AuthProfileContext(primary_factory_id="huaxing", confirmation_status="pending"),
                    AuthProfileContext(primary_factory_id="group", confirmation_status="confirmed")):
        context["user"] = replace(user(), profile=profile)
        assert client.get(BASE + "/capabilities" + SCOPE).json()["can_submit"] is False
        assert multipart(client, BASE, create_payload()).status_code == 403
    original = user(factory="huadeng")
    for grant in (replace(original.grants[0], factory_id="huaxing"),
                  replace(original.grants[0], unrestricted_department=True, scope_mode="cross_factory_operate"),
                  AuthGrantContext("admin", "admin", "*", "*", frozenset(), role_code="admin")):
        context["user"] = replace(original, grants=(grant,), overrides=(
            AuthOverrideContext("allow", service.SUBMIT, "allow", "huaxing", "*"),))
        assert client.get(BASE + "/capabilities" + SCOPE).json()["can_submit"] is False
        assert multipart(client, BASE, create_payload()).status_code == 403
    context["user"] = replace(developer(), profile=None)
    caps = client.get(BASE + "/capabilities" + SCOPE).json()
    assert caps["can_submit"] is False and caps["can_manage"] is True
    assert client.get(BASE + SCOPE + "&view=manage").status_code == 200


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_feedback_deny_disabled_and_business_deny_are_independent(api, monkeypatch, mode):
    client, context, _ = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    original = replace(user(), active_permission_codes=frozenset(APPLICATION_PERMISSION_CODES))
    context["user"] = replace(original, overrides=(AuthOverrideContext("no-orders", "customer_order:read", "deny", "huaxing", "sales-business"),))
    caps = client.get(BASE + "/capabilities" + SCOPE).json()
    assert caps["can_submit"] is True and caps["can_link_order"] is False
    ticket = created(api)
    denied = replace(original, overrides=(AuthOverrideContext("no-feedback", service.SUBMIT, "deny", "huaxing", "sales-business"),))
    disabled = replace(original, active_permission_codes=original.active_permission_codes - {service.SUBMIT})
    for blocked in (denied, disabled):
        context["user"] = blocked
        caps = client.get(BASE + "/capabilities" + SCOPE).json()
        assert caps["can_submit"] is False and caps["can_link_order"] is True
        assert multipart(client, BASE, create_payload()).status_code == 403
        assert client.get(BASE + "/" + ticket["id"] + SCOPE).status_code == 403
        assert action(client, ticket, body="reply").status_code == 403
    # A deny in a different factory does not affect the employee's own channel.
    context["user"] = replace(original, overrides=(AuthOverrideContext("other", service.SUBMIT, "deny", "huadeng", "*"),))
    assert client.get(BASE + "/capabilities" + SCOPE).json()["can_submit"] is True
    # Nor can a developer manage denial revoke an ordinary employee's own data.
    context["user"] = replace(original, overrides=(AuthOverrideContext("no-manage", service.MANAGE, "deny", "huaxing", "*"),))
    assert client.get(BASE + "/" + ticket["id"] + SCOPE).status_code == 200


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_feedback_without_order_read_never_queries_or_derives_orders(api, monkeypatch, mode):
    client, context, engine = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    context["user"] = user(permissions=set())
    statements = []

    def collect(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", collect)
    try:
        for order_id in ("valid-looking-id", "guess-in-other-factory", "does-not-exist"):
            result = multipart(client, BASE, create_payload(context={"order_id": order_id}))
            assert result.status_code == 403
        assert not any("order_ledger_lines" in statement.lower() for statement in statements)
        result = multipart(client, BASE, create_payload(context={"order_reference": "用户主动填写PO123", "product_no": "手填P1"}))
        assert result.status_code == 200
        assert result.json()["context"]["order_reference"] == "用户主动填写PO123"
        assert not any("order_ledger_lines" in statement.lower() for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", collect)


def test_revoking_order_access_hides_derived_context_but_preserves_private_thread(api):
    client, context, engine = api
    with Session(engine) as db:
        db.add(OrderLedgerLine(id="linked-order", factory_id="huaxing", customer_code="buzzbee", customer_name="BuzzBee",
            identity_key="key", reference_no="private-PO", product_no="private-item", data={}, created_at="now", updated_at="now"))
        db.commit()
    ticket = multipart(client, BASE, create_payload(context={"order_id": "linked-order"})).json()
    assert ticket["context"]["order_reference"] == "private-PO"
    context["user"] = replace(user(permissions=set()), grants=())
    detail = client.get(BASE + "/" + ticket["id"] + SCOPE).json()
    summary = client.get(BASE + SCOPE).json()["items"][0]
    for item in (detail, summary):
        assert all(item["context"][field] == "" for field in ("order_id", "order_reference", "product_no", "customer_code"))
    assert detail["messages"][0]["body"] == ticket["messages"][0]["body"]
    assert action(client, ticket, body="现在没有订单权限，也需要协助").status_code == 200
    context["user"] = developer()
    assert client.get(BASE + "/" + ticket["id"] + SCOPE).json()["context"]["order_reference"] == "private-PO"
    with Session(engine) as db:
        assert db.get(FeedbackTicket, ticket["id"]).context["order_reference"] == "private-PO"


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_order_link_preserves_local_canonical_position_access_without_cross_factory_expansion(api, monkeypatch, mode):
    client, context, _ = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    definition = next(item for item in SYSTEM_POSITION_DEFINITIONS if item.role_id == "position_general_manager")
    manager = user("gm", department="management", permissions=definition.permission_codes)
    manager = replace(manager, grants=(replace(manager.grants[0], role_id=definition.role_id,
        unrestricted_department=True, scope_mode="cross_factory_operate", read_permissions=frozenset({"customer_order:read"})),))
    context["user"] = manager
    caps = client.get(BASE + "/capabilities" + SCOPE).json()
    assert caps["can_submit"] is True and caps["can_link_order"] is True and caps["can_manage"] is False
    caps = client.get(BASE + "/capabilities?factory_id=huadeng").json()
    assert caps["can_submit"] is False and caps["can_link_order"] is False and caps["can_manage"] is False
    context["user"] = replace(manager, overrides=(AuthOverrideContext("no-read", "customer_order:read", "deny", "huaxing", "sales-business"),))
    caps = client.get(BASE + "/capabilities" + SCOPE).json()
    assert caps["can_submit"] is True and caps["can_link_order"] is False


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
def test_linked_create_retry_recovers_after_order_permission_revocation_without_querying_orders(api, monkeypatch, mode):
    client, context, engine = api
    monkeypatch.setattr(settings, "authz_mode", mode)
    with Session(engine) as db:
        db.add(OrderLedgerLine(id="retry-linked-order", factory_id="huaxing", customer_code="buzzbee", customer_name="BuzzBee",
            identity_key="key", reference_no="private-PO", product_no="private-item", data={}, created_at="now", updated_at="now"))
        db.commit()
    payload = create_payload(context={"order_id": "retry-linked-order"})
    original = multipart(client, BASE, payload)
    assert original.status_code == 200
    ticket = original.json()
    assert ticket["context"]["order_reference"] == "private-PO"
    context["user"] = replace(user(), overrides=(AuthOverrideContext(
        "revoke-read", "customer_order:read", "deny", "huaxing", "sales-business"),))
    statements = []

    def collect(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", collect)
    try:
        retried = multipart(client, BASE, payload)
        assert retried.status_code == 200
        restored = retried.json()
        assert restored["id"] == ticket["id"] and restored["revision"] == 1
        assert all(restored["context"][field] == "" for field in ("order_id", "order_reference", "product_no", "customer_code"))
        assert multipart(client, BASE, payload | {"body": "changed content"}).status_code == 409
        assert multipart(client, BASE, payload | {"client_request_id": str(uuid4())}).status_code == 403
        assert not any("order_ledger_lines" in statement.lower() for statement in statements)
        # Recovering an old request must still honor feedback-level revocation.
        context["user"] = replace(context["user"], overrides=context["user"].overrides + (
            AuthOverrideContext("revoke-feedback", service.SUBMIT, "deny", "huaxing", "sales-business"),))
        assert multipart(client, BASE, payload).status_code == 403
    finally:
        event.remove(engine, "before_cursor_execute", collect)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(FeedbackTicket)) == 1
        assert db.scalar(select(func.count()).select_from(FeedbackMessage)) == 1
        assert db.get(FeedbackTicket, ticket["id"]).context["order_reference"] == "private-PO"
