"""Optional live PostgreSQL concurrency, isolated in a random test schema."""
import concurrent.futures
import os
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.auth import AuthUser
from app.models.document_tools import DocumentToolArtifact as Artifact, DocumentToolCorrection as Correction, DocumentToolJob as Job, DocumentToolSource as Source
from app.services.document_tools import job_service as jobs


@pytest.fixture
def pg():
    url = os.getenv("DOCUMENT_TOOLS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set DOCUMENT_TOOLS_TEST_POSTGRES_URL for a dedicated test database")
    schema = "rrdoc_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text('CREATE SCHEMA "' + schema + '"'))
    engine = create_engine(url, connect_args={"options": "-csearch_path=" + schema}, pool_size=8)
    Base.metadata.create_all(engine, tables=[AuthUser.__table__, Source.__table__, Job.__table__, Artifact.__table__, Correction.__table__])
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as db:
        db.add(AuthUser(id="owner", username="owner", password_salt="test", password_hash="test"))
        db.commit()
        for index in range(20):
            jobs.enqueue(db, "owner", None, "package", {"artifact_ids": []}, kind="package", client_request_id=str(index))
        db.commit()
    yield sessions
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
    admin.dispose()


def test_skip_locked_and_concurrent_claims(pg):
    # A locked oldest job cannot stall a second connection's claim.
    with pg() as locked:
        oldest = locked.scalar(select(Job.id).order_by(Job.created_at, Job.id).limit(1).with_for_update())
        start = time.monotonic()
        other = jobs.claim_job(pg)
        assert other[0] != oldest and time.monotonic() - start < 3
        locked.rollback()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: jobs.claim_job(pg), range(25)))
    claims = [other] + [row for row in claims if row]
    assert len(claims) == 20 and len({row[0] for row in claims}) == 20
    assert jobs.claim_job(pg) is None


def test_expiry_reclaim_and_fenced_publish(pg):
    claimed = jobs.claim_job(pg)
    with pg() as db:
        db.execute(update(Job).where(Job.id == claimed[0]).values(lease_until=time.time() - 1))
        db.commit()
    recovered = jobs.claim_job(pg)
    assert recovered[0] == claimed[0] and recovered[1] != claimed[1]
    assert not jobs.renew(pg, *claimed)
    assert jobs.renew(pg, *recovered)
    with pg() as db:
        assert db.execute(update(Job).where(jobs.lease_filter(*claimed)).values(execution_status="succeeded")).rowcount == 0
        db.rollback()


def test_atomic_owner_request_dedup(pg):
    def submit(_):
        with pg() as db:
            result = jobs.enqueue(db, "owner", None, "package", {"artifact_ids": []}, kind="package", client_request_id="same-concurrent-request")
            identity = result.id
            db.commit()
            return identity
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(submit, range(12)))
    assert len(set(ids)) == 1
