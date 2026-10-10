"""Real PostgreSQL competition. Opt-in, loopback-only, synthetic isolated schema."""
import importlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    url = os.getenv("COLLABORATION_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("COLLABORATION_TEST_POSTGRES_URL not provided")
    parsed = make_url(url)
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database == "rr_connect_acceptance"
    patch = pytest.MonkeyPatch()
    patch.setenv("DATABASE_URL", url)
    patch.setenv("COLLABORATION_STORAGE_DIR", str(tmp_path_factory.mktemp("collab_pg_assets")))
    importlib.import_module("app.main")
    dbm = importlib.import_module("app.db")
    core = importlib.import_module("app.services.collaboration.core")
    assets = importlib.import_module("app.services.collaboration.assets")
    schema = "collab_pg_" + uuid4().hex
    control = create_engine(url)
    with control.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    dbm.Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    models = importlib.import_module("app.models.auth")
    policy = importlib.import_module("app.services.identity_policy")
    auth = importlib.import_module("app.services.auth")
    with sessions() as db:
        db.add(models.AuthIamState(key=policy.LOCK_KEY))
        db.commit()
    env = SimpleNamespace(db=sessions, engine=engine, core=core, assets=assets, schema=schema, url=url,
        model=importlib.import_module("app.models.collaboration"),
        payload=importlib.import_module("app.schemas.collaboration"), authmodels=models, auth=auth, policy=policy)
    def actor(db, uid):
        return auth.build_auth_context(db, db.get(models.AuthUser, uid))
    def command(uid, fn, *args):
        with sessions() as db:
            policy.lock_mutation(db)
            return fn(db, actor(db, uid), *args)
    env.actor, env.command = actor, command
    try:
        yield env
    finally:
        engine.dispose()
        assert schema.startswith("collab_pg_") and len(schema) == 42
        with control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()
        patch.undo()


@pytest.fixture
def actors(pg):
    ids = ["pg_" + uuid4().hex for _ in range(3)]
    with pg.db() as db:
        for uid in ids:
            db.add(pg.authmodels.AuthUser(id=uid, username=uid, display_name=uid, password_salt="test", password_hash="test"))
        db.flush()
        for uid in ids:
            db.add(pg.authmodels.EmployeeProfile(user_id=uid, primary_factory_id="huakang-a", primary_department="engineering", position="synthetic"))
        db.commit()
    return ids


def parallel(jobs):
    barrier = Barrier(len(jobs))
    def run(job):
        barrier.wait(timeout=20)
        return job()
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(run, jobs))


def message(pg, key, **extra):
    return pg.payload.MessageRequest(client_message_id=key, body="synthetic", **extra)


def test_simultaneous_pair_and_idempotent_send(pg, actors):
    a, b, _ = actors
    pairs = parallel([lambda: pg.command(a, pg.core.direct, b), lambda: pg.command(b, pg.core.direct, a)] * 3)
    assert len({r["id"] for r in pairs}) == 1
    cid = pairs[0]["id"]
    messages = parallel([lambda: pg.command(a, pg.core.send, cid, message(pg, "same-message-001"))] * 6)
    assert len({r["id"] for r in messages}) == 1
    with pg.db() as db:
        assert db.scalar(select(func.count()).select_from(pg.model.Message).where(pg.model.Message.conversation_id == cid)) == 1


@pytest.mark.parametrize("rollback", [False, True])
def test_blocked_counter_commit_order_and_rollback_have_no_gap(pg, actors, rollback):
    uid = actors[0]
    allocated, release = Event(), Event()
    def first():
        with pg.db() as db:
            pg.policy.lock_mutation(db)
            pg.core.lock_streams(db, [(uid, 1)])
            pg.core.emit(db, (uid, 1), "checkpoint")
            allocated.set()
            assert release.wait(10)
            db.rollback() if rollback else db.commit()
    def second():
        with pg.db() as db:
            pg.policy.lock_mutation(db)
            pg.core.lock_streams(db, [(uid, 1)])
            pg.core.emit(db, (uid, 1), "checkpoint")
            db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(first)
        assert allocated.wait(10)
        two = pool.submit(second)
        try:
            with pytest.raises(TimeoutError):
                two.result(timeout=.15)
            with pg.db() as db:
                snap = pg.core.sync(db, pg.actor(db, uid), pg.core.cursor((uid, 1), 0))
                assert snap["events"] == []
        finally:
            release.set()
        one.result(timeout=15); two.result(timeout=15)
    with pg.db() as db:
        events = pg.core.sync(db, pg.actor(db, uid), pg.core.cursor((uid, 1), 0))["events"]
        assert [e["event_seq"] for e in events] == ([1] if rollback else [1, 2])


def test_read_send_retract_and_draft_cas(pg, actors):
    a, b, _ = actors
    cid = pg.command(a, pg.core.direct, b)["id"]
    first = pg.command(a, pg.core.send, cid, message(pg, "first-message"))
    parallel([lambda: pg.command(b, pg.core.mark_read, cid, 1),
              lambda: pg.command(a, pg.core.retract, first["id"]),
              lambda: pg.command(a, pg.core.send, cid, message(pg, "second-message"))])
    with pg.db() as db:
        conv, _ = pg.core.conversation(db, pg.actor(db, b), cid)
        result = pg.core.conversation_out(db, pg.actor(db, b), conv)
        assert result["unread"] == 1 and result["last_message_seq"] == 2 and result["last_read_seq"] == 1
    def draft(value):
        try:
            return pg.command(a, pg.core.patch_draft, cid, pg.payload.DraftPatch(expected_version=0, text=value))
        except HTTPException as error:
            return error.status_code
    results = parallel([lambda: draft("A"), lambda: draft("B")])
    assert sum(r == 409 for r in results) == 1
    assert sum(isinstance(r, dict) and r["version"] == 1 for r in results) == 1


@pytest.mark.parametrize("expired", [False, True])
def test_attachment_send_races_cleanup(pg, actors, expired):
    a, b, _ = actors
    cid = pg.command(a, pg.core.direct, b)["id"]
    uploaded = pg.command(a, pg.assets.upload, cid, "upload-key-001", "test.pdf", "application/pdf", b"%PDF-1.4 synthetic")
    if expired:
        with pg.db() as db:
            db.get(pg.model.Attachment, uploaded["id"]).created_at = pg.core.stamp(pg.core.utc_now() - timedelta(hours=25))
            db.commit()
    def sending():
        try:
            return pg.command(a, pg.core.send, cid, message(pg, "file-message-001", kind="attachment", attachment_ids=[uploaded["id"]]))
        except HTTPException as error:
            return error.status_code
    def cleaning():
        with pg.db() as db:
            return pg.assets.cleanup(db)
    sent, _ = parallel([sending, cleaning])
    with pg.db() as db:
        row = db.get(pg.model.Attachment, uploaded["id"])
        assert row.state == ("deleted" if expired else "attached")
        assert pg.assets.path_for(row.storage_key).exists() is not expired
        assert sent == 404 if expired else isinstance(sent, dict)


def test_commit_survives_writer_process_exit(pg, actors):
    a, b, _ = actors
    cid = pg.command(a, pg.core.direct, b)["id"]
    env = dict(os.environ, DATABASE_URL=pg.url, PGOPTIONS=f"-csearch_path={pg.schema}")
    script = """
import os, sys
from app.db import SessionLocal
from app.models.auth import AuthUser
from app.services.auth import build_auth_context
from app.services.identity_policy import lock_mutation
from app.services.collaboration.core import send
from app.schemas.collaboration import MessageRequest
with SessionLocal() as db:
    lock_mutation(db)
    actor = build_auth_context(db, db.get(AuthUser, sys.argv[1]))
    send(db, actor, sys.argv[2], MessageRequest(client_message_id="exit-after-commit", body="durable"))
os._exit(77)
"""
    result = subprocess.run([sys.executable, "-c", script, a, cid], env=env, capture_output=True, timeout=30)
    assert result.returncode == 77, result.stderr.decode(errors="replace")
    recovered = pg.command(a, pg.core.submitted, "exit-after-commit")
    retried = pg.command(a, pg.core.send, cid, pg.payload.MessageRequest(client_message_id="exit-after-commit", body="durable"))
    assert recovered["id"] == retried["id"]
    with pg.db() as db:
        events = pg.core.sync(db, pg.actor(db, b), pg.core.cursor((b, 1), 0))["events"]
        assert sum(e.get("message", {}).get("id") == recovered["id"] for e in events) == 1
