"""Real Cookie sessions and an isolated store exercise private collaboration."""
import importlib
import pytest
from test_user_directory import make_client, add_member, login, ADMIN_TEST_PASSWORD, avatar_png


@pytest.fixture
def collab(monkeypatch, tmp_path):
    monkeypatch.setenv("COLLABORATION_ENABLED", "true")
    monkeypatch.setenv("COLLABORATION_STORAGE_DIR", str(tmp_path / "assets"))
    with make_client(monkeypatch) as client:
        cookies = {}
        for name in ["alice", "bob", "carol"]:
            add_member(user_id=name, username=name, display_name=name)
            login(client, name)
            cookies[name] = dict(client.cookies)
        login(client, "admin", ADMIN_TEST_PASSWORD)
        cookies["admin"] = dict(client.cookies)
        def as_user(name):
            client.cookies.clear()
            client.cookies.update(cookies[name])
            return client
        yield as_user


def direct(client, peer="bob"):
    response = client.post("/api/collaboration/conversations/direct", json={"peer_user_id": peer})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_summary_queries_are_bounded_and_pinned_thanks_survive_pagination(collab):
    from sqlalchemy import event
    a = collab("alice")
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.collaboration")
    authmodels = importlib.import_module("app.models.auth")
    auth = importlib.import_module("app.services.auth")
    core = importlib.import_module("app.services.collaboration.core")
    with dbm.SessionLocal() as db:
        for i in range(31):
            uid, cid = f"synthetic-{i:02}", f"summary-{i:02}"
            db.add(authmodels.AuthUser(id=uid, username=uid, display_name=uid, password_salt="test", password_hash="test"))
            db.flush()
            db.add(models.DirectConversation(id=cid, low_user_id="alice", low_epoch=1, high_user_id=uid, high_epoch=1,
                created_at=core.stamp(), updated_at=core.stamp(), last_message_seq=1))
            db.flush()
            db.add_all([models.ConversationMember(conversation_id=cid, user_id=p, epoch=1) for p in ["alice", uid]])
            db.add(models.Message(id=f"message-{i}", conversation_id=cid, message_seq=1, sender_user_id=uid, sender_epoch=1,
                client_message_id=f"seed-message-{i}", request_hash="test", kind="text", body="summary", created_at=core.stamp()))
            db.add(models.Appreciation(id=f"thanks-{i:02}", sender_id="bob", sender_epoch=1, receiver_id="alice", receiver_epoch=1,
                client_request_id=f"seed-thanks-{i}", request_hash="test", category="help", text="谢谢",
                created_at=f"2026-10-01T00:00:{i:02}+00:00", private_pin_order=1 if i == 0 else 0))
        db.commit()
    counts = []
    for limit in [1, 10, 30]:
        with dbm.SessionLocal() as db:
            user = auth.build_auth_context(db, db.get(authmodels.AuthUser, "alice"))
            statements = []
            def record(_conn, _cursor, statement, *_):
                if statement.lstrip().upper().startswith("SELECT"):
                    statements.append(statement)
            event.listen(dbm.engine, "before_cursor_execute", record)
            try:
                result = core.conversations(db, user, limit=limit)
            finally:
                event.remove(dbm.engine, "before_cursor_execute", record)
            counts.append(len(statements))
            assert len(result["items"]) == limit
            assert all(c["unread"] == 1 and c["last_message"]["body"] == "summary" and c["peer_read_seq"] is None for c in result["items"])
    assert max(counts) <= 9 and max(counts) - min(counts) <= 1, counts
    page = a.get("/api/collaboration/me/appreciations").json()
    assert page["items"][0]["id"] == "thanks-00"
    second = a.get("/api/collaboration/me/appreciations", params={"cursor": page["next_cursor"]}).json()
    assert len({r["id"] for r in page["items"] + second["items"]}) == 31
    sent = collab("bob").get("/api/collaboration/me/appreciations", params={"sent": True}).json()
    assert sent["items"][0]["id"] == "thanks-30"
    assert all(r["private_pin_order"] == 0 and r["version"] is None for r in sent["items"])


def send(client, cid, text="你好", key="message-0001", **extra):
    response = client.post(f"/api/collaboration/conversations/{cid}/messages", json={"client_message_id": key, "body": text, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_pair_idempotency_read_retract_epoch_and_admin_boundary(collab):
    a = collab("alice")
    cid = direct(a)
    base = a.get("/api/collaboration/bootstrap").json()
    first = send(a, cid)
    assert send(a, cid)["id"] == first["id"]
    conflict = a.post(f"/api/collaboration/conversations/{cid}/messages", json={"client_message_id": "message-0001", "body": "不同正文"})
    assert conflict.status_code == 409
    assert a.get("/api/collaboration/sync", params={"cursor": base["cursor"]}).json()["events"][0]["message"]["id"] == first["id"]
    b = collab("bob")
    assert direct(b, "alice") == cid
    assert b.get("/api/collaboration/bootstrap").json()["unread"] == 1
    assert b.post(f"/api/collaboration/conversations/{cid}/read", json={"through_message_seq": 99}).status_code == 422
    read = b.post(f"/api/collaboration/conversations/{cid}/read", json={"through_message_seq": 1})
    assert read.json()["unread"] == 0
    assert collab("alice").get("/api/collaboration/conversations").json()["items"][0]["peer_read_seq"] is None
    for user in ["carol", "admin"]:
        assert collab(user).get(f"/api/collaboration/conversations/{cid}/messages").status_code == 404
        assert collab(user).get(f"/api/collaboration/conversations/{cid}/search?q=你好").status_code == 404
    b = collab("bob")
    reply = send(b, cid, text="收到", key="reply-0001", reply_to_id=first["id"])
    a = collab("alice")
    assert a.post(f"/api/collaboration/messages/{first['id']}/retract").status_code == 200
    assert send(a, cid)["retracted_at"]
    replay = a.get("/api/collaboration/sync", params={"cursor": base["cursor"]}).json()
    assert all(not e["message"]["body"] for e in replay["events"] if e.get("message", {}).get("id") == first["id"])
    history = collab("bob").get(f"/api/collaboration/conversations/{cid}/messages").json()["items"]
    assert next(m for m in history if m["id"] == reply["id"])["reply"]["retracted"]
    dbm, models = importlib.import_module("app.db"), importlib.import_module("app.models.auth")
    with dbm.SessionLocal() as db:
        db.get(models.EmployeeProfile, "bob").employment_epoch += 2
        db.commit()
    assert collab("bob").get(f"/api/collaboration/conversations/{cid}/messages").status_code == 404
    a = collab("alice")
    assert a.get(f"/api/collaboration/conversations/{cid}/messages").status_code == 200
    assert send(a, cid)["id"] == first["id"]
    assert direct(a) != cid


def test_draft_cas_and_identity_bound_cursor(collab):
    a = collab("alice")
    cid = direct(a)
    path = f"/api/collaboration/conversations/{cid}/draft"
    draft = a.patch(path, json={"expected_version": 0, "text": "A"})
    assert draft.status_code == 200, draft.text
    send(a, cid, text="A", draft_version=1)
    assert a.get(path).json() == {"text": "", "reply_to_id": None, "attachment_ids": [], "version": 2}
    assert a.patch(path, json={"expected_version": 1, "text": "A"}).status_code == 409
    assert a.patch(path, json={"expected_version": 2, "text": "B"}).status_code == 200
    send(a, cid, text="A", draft_version=1)
    assert a.get(path).json()["text"] == "B"
    initial = a.get("/api/collaboration/bootstrap").json()["cursor"]
    assert collab("bob").get("/api/collaboration/sync", params={"cursor": initial}).status_code == 422
    assert collab("bob").get(path).json()["text"] == ""


def test_assets_upload_retry_participant_scope_and_retraction(collab):
    a = collab("alice")
    cid = direct(a)
    path = f"/api/collaboration/conversations/{cid}/attachments"
    def upload(data):
        return a.post(path, data={"client_upload_id": "upload-0001"}, files={"file": ("photo.png", data, "image/png")})
    first = upload(avatar_png())
    assert first.status_code == 200, first.text
    asset = first.json()
    assert upload(avatar_png()).json()["id"] == asset["id"]
    assert collab("bob").get(asset["url"]).status_code == 404
    a = collab("alice")
    message = send(a, cid, text="图片", kind="attachment", attachment_ids=[asset["id"]])
    assert collab("bob").get(asset["url"]).status_code == 200
    assert collab("admin").get(asset["url"]).status_code == 404
    assert collab("alice").post(f"/api/collaboration/messages/{message['id']}/retract").status_code == 200
    assert collab("bob").get(asset["url"]).status_code == 404


def test_profiles_contacts_private_appreciation_and_validation(collab):
    a = collab("alice")
    assert a.patch("/api/collaboration/me/profile", json={"expected_version": 0, "help_topics": "试模协调", "skill_tags": ["试模"], "theme": "jade"}).status_code == 200
    assert a.patch("/api/collaboration/me/profile", json={"expected_version": 0, "bio": "旧版本"}).status_code == 409
    assert a.patch("/api/collaboration/me/profile", json={"expected_version": 1, "primary_factory_id": "huaxing"}).status_code == 422
    assert collab("bob").get("/api/directory/members?q=试模").json()["items"][0]["self_profile"]["theme"] == "jade"
    assert collab("alice").put("/api/collaboration/me/contacts/bob").status_code == 200
    assert collab("alice").get("/api/collaboration/me/contacts").json()["items"][0]["id"] == "bob"
    assert collab("bob").get("/api/collaboration/me/contacts").json()["items"] == []
    a = collab("alice")
    body = {"client_request_id": "thanks-0001", "receiver_id": "bob", "category": "careful_check", "text": "谢谢核对模具资料"}
    thanks = a.post("/api/collaboration/appreciations", json=body)
    assert thanks.status_code == 200, thanks.text
    assert a.post("/api/collaboration/appreciations", json=body).json()["id"] == thanks.json()["id"]
    b = collab("bob")
    assert b.get("/api/collaboration/bootstrap").json()["unread"] == 0
    assert b.get("/api/collaboration/me/appreciations").json()["unseen"] == 1
    aid = thanks.json()["id"]
    assert b.patch(f"/api/collaboration/appreciations/{aid}", json={"expected_version": 1, "seen": True, "private_pin_order": 1}).status_code == 200
    assert b.get("/api/collaboration/me/appreciations").json()["unseen"] == 0
    assert collab("carol").get("/api/collaboration/me/appreciations").json()["items"] == []
    assert "谢谢核对" not in collab("carol").get("/api/directory/members/bob").text


def test_bulk_eligibility_matches_runtime_for_supplier_mixed_v2_and_functional_unit(collab):
    from sqlalchemy import select
    dbm, authm = importlib.import_module("app.db"), importlib.import_module("app.models.auth")
    auth = importlib.import_module("app.services.auth")
    iam = importlib.import_module("app.models.identity")
    rule = importlib.import_module("app.services.internal_members")
    for name in ["supplier", "mixed", "v2-empty", "group-staff"]:
        add_member(user_id=name, username=name, display_name=name)
    with dbm.SessionLocal() as db:
        supplier_permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "carton_supplier:read"))
        internal_permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == "molding_sample:read"))
        for uid in ["supplier", "mixed"]:
            db.add(authm.AuthUserPermissionOverride(id=f"{uid}-supplier", user_id=uid, permission_id=supplier_permission.id, effect="allow", factory_id="*", department="*", source_type="manual"))
        db.add(authm.AuthUserPermissionOverride(id="mixed-internal", user_id="mixed", permission_id=internal_permission.id, effect="allow", factory_id="huakang-a", department="engineering", source_type="manual"))
        db.get(authm.EmployeeProfile, "v2-empty").identity_mode = "v2"
        db.get(authm.EmployeeProfile, "group-staff").identity_mode = "v2"
        db.add(iam.EmployeeAssignment(id="group-assignment", user_id="group-staff", org_unit_id="group-management", department_code="management", official_position_title="总务协调", is_primary=True, valid_from="2026-01-01T00:00:00Z", employment_epoch=1, created_by="test", confirmed_by="test", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z"))
        db.commit()
        expected = {u.id for u in db.scalars(select(authm.AuthUser)) if rule.is_internal(auth.build_auth_context(db, u))}
        actual = set(rule.eligible_member_ids(db))
        assert actual == expected
        assert {"mixed", "group-staff", "alice"} <= actual
        assert not {"supplier", "v2-empty"} & actual
    data = collab("alice").get("/api/directory/members?org_unit_id=group-management").json()
    assert data["items"][0]["org_name"] == "集团总务"
    assert data["items"][0]["org_kind"] == "functional_unit"


def test_cursor_batches_receipt_privacy_and_cleanup_preserve_sent_assets(collab):
    a = collab("alice"); cid = direct(a)
    initial = a.get("/api/collaboration/bootstrap").json()["cursor"]
    send(a, cid)
    b = collab("bob")
    assert b.patch("/api/collaboration/me/preferences", json={"expected_version": 0, "read_receipts_enabled": True}).status_code == 200
    b.post(f"/api/collaboration/conversations/{cid}/read", json={"through_message_seq": 1})
    assert collab("alice").get(f"/api/collaboration/conversations/{cid}").json()["peer_read_seq"] == 1
    assert collab("bob").patch("/api/collaboration/me/preferences", json={"expected_version": 1, "read_receipts_enabled": False}).status_code == 200
    replay = collab("alice").get("/api/collaboration/sync", params={"cursor": initial}).json()
    assert any(e["type"] == "checkpoint" for e in replay["events"])
    dbm = importlib.import_module("app.db"); core = importlib.import_module("app.services.collaboration.core")
    with dbm.SessionLocal() as db:
        for i in range(205):
            core.emit(db, ("alice", 1), "profile.changed", str(i))
        db.commit()
    cursor, seqs = replay["cursor"], []
    for _ in range(3):
        batch = collab("alice").get("/api/collaboration/sync", params={"cursor": cursor}).json()
        seqs.extend(e["event_seq"] for e in batch["events"]); cursor = batch["cursor"]
    assert len(seqs) == 205 and len(set(seqs)) == 205
    assert seqs == list(range(seqs[0], seqs[0]+205))
    assert batch["has_more"] is False


def test_migration_empty_rollback_and_nonempty_history_guard(tmp_path):
    from pathlib import Path
    from sqlalchemy import create_engine, inspect, text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / "alembic/versions/20261009_0151_member_collaboration.py"
    spec = importlib.util.spec_from_file_location("collaboration_migration_test", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE auth_users (id VARCHAR(64) PRIMARY KEY)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert len(inspect(connection).get_table_names()) == 12
        unique = inspect(connection).get_unique_constraints("collab_messages")
        assert {tuple(u["column_names"]) for u in unique} >= {("conversation_id", "message_seq"), ("sender_user_id", "sender_epoch", "client_message_id")}
        migration.downgrade()
        assert inspect(connection).get_table_names() == ["auth_users"]
        migration.upgrade()
        connection.execute(text("INSERT INTO collab_user_streams (user_id,epoch,last_event_seq,minimum_valid_cursor) VALUES ('alice',1,1,0)"))
        with pytest.raises(RuntimeError, match="contains data"):
            migration.downgrade()
        assert "collab_messages" in inspect(connection).get_table_names()
    engine.dispose()


def test_business_references_recheck_permissions_and_expired_staging_keeps_text(collab):
    from sqlalchemy import select
    from datetime import timedelta
    dbm = importlib.import_module("app.db")
    core = importlib.import_module("app.services.collaboration.core")
    models = importlib.import_module("app.models.collaboration")
    authm = importlib.import_module("app.models.auth")
    auth = importlib.import_module("app.services.auth")
    molding = importlib.import_module("app.models.molding_sample")
    quotes = importlib.import_module("app.models.internal_quote")
    refs = importlib.import_module("app.services.collaboration.references")
    with dbm.SessionLocal() as db:
        db.add(molding.MoldingSampleOrder(id="reference-order", factory_id="huakang-a", product_name="SYNTHETIC", date="2026-10-10", doc_number="PRIVATE-ORDER"))
        db.add(quotes.InternalQuote(id="reference-quote", factory_id="huakang-a", workshop_code="A", workshop_name="A", quote_no="PRIVATE-QUOTE", product_name="SYNTHETIC", customer="SYNTHETIC", qty=1, version_label="v1", status="draft", created_by="admin", created_by_name="admin", created_at=core.stamp(), updated_at=core.stamp()))
        db.commit()
        admin = auth.build_auth_context(db, db.scalar(select(authm.AuthUser).where(authm.AuthUser.username == "admin")))
        alice = auth.build_auth_context(db, db.get(authm.AuthUser, "alice"))
        for kind, rid in [("molding_sample", "reference-order"), ("internal_quote", "reference-quote")]:
            reference = dict(resource_type=kind, resource_id=rid, factory_id="huakang-a")
            assert refs.project(db, admin, reference)["available"]
            denied = refs.project(db, alice, reference)
            assert denied == {"available": False, "label": "该业务记录当前不可查看"}
            assert not refs.project(db, admin, {**reference, "factory_id": "huakang-b"})["available"]
    a = collab("alice"); cid = direct(a)
    upload_path = f"/api/collaboration/conversations/{cid}/attachments"
    ids = []
    for key in ["pending-0001", "attached-001"]:
        result = a.post(upload_path, data={"client_upload_id": key}, files={"file": ("image.png", avatar_png(), "image/png")})
        assert result.status_code == 200; ids.append(result.json()["id"])
    draft_path = f"/api/collaboration/conversations/{cid}/draft"
    assert a.patch(draft_path, json={"expected_version": 0, "text": "保留这段文字", "attachment_ids": [ids[0]]}).status_code == 200
    send(a, cid, kind="attachment", attachment_ids=[ids[1]])
    with dbm.SessionLocal() as db:
        for aid in ids: db.get(models.Attachment, aid).created_at = core.stamp(core.utc_now() - timedelta(hours=25))
        db.commit()
        assert importlib.import_module("app.services.collaboration.assets").cleanup(db)["removed"] == 1
        assert db.get(models.Attachment, ids[1]).state == "attached"
    draft = a.get(draft_path).json()
    assert draft["text"] == "保留这段文字" and draft["unavailable_attachment_ids"] == [ids[0]]
