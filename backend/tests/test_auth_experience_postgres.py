"""Real PostgreSQL lock ordering using a disposable per-test schema."""
import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from test_identity_changes import client
from test_identity_postgres import postgres
from test_password_reset_workflow import create_user, login, submit_reset, approve_reset, EMPLOYEE_PASSWORD, ADMIN_TEST_PASSWORD, NEW_PASSWORD


def request_for(browser, path):
    return Request({"type":"http", "method":"POST", "path":path, "headers":[
        (b"cookie", f"rr_session={browser.cookies.get('rr_session')}".encode()),
    ], "client":("testclient",1)})


def ordered_jobs(monkeypatch, jobs):
    policy=importlib.import_module("app.services.identity_policy")
    original=policy.lock_mutation
    acquired=Event(); release=Event(); second_started=Event()
    def lock(db):
        if current_thread().name.startswith("auth-second"): second_started.set()
        original(db)
        if current_thread().name.startswith("auth-first"):
            acquired.set()
            assert release.wait(20)
    monkeypatch.setattr(policy,"lock_mutation",lock)
    with ThreadPoolExecutor(1,thread_name_prefix="auth-first") as one, ThreadPoolExecutor(1,thread_name_prefix="auth-second") as two:
        first=one.submit(jobs[0]); assert acquired.wait(20)
        second=two.submit(jobs[1]); assert second_started.wait(20)
        assert not second.done(), "Second writer must wait on the shared database lock"
        release.set()
        return first.result(30), second.result(30)


@pytest.mark.parametrize("first_action",["change","claim"])
def test_password_change_and_claim_have_one_valid_order(postgres,monkeypatch,first_action):
    admin,dbm=postgres
    uid=create_user("pg-auth-order")
    app=importlib.import_module("app.main").app
    browser=TestClient(app); recovery=TestClient(app)
    assert login(browser,"pg-auth-order",EMPLOYEE_PASSWORD).status_code==200
    assert login(admin,"admin",ADMIN_TEST_PASSWORD).status_code==200
    rid=submit_reset(recovery,"pg-auth-order").json()["request_id"]
    assert approve_reset(admin,rid).status_code==200
    auth=importlib.import_module("app.services.auth"); schema=importlib.import_module("app.schemas.auth")
    request=request_for(browser,"/api/auth/change-password")
    with dbm.SessionLocal() as stale:
        actor=auth.get_current_user(request,stale)
    def change():
        with dbm.SessionLocal() as db:
            try:
                auth.change_current_password(db,actor,schema.ChangePasswordRequest(current_password=EMPLOYEE_PASSWORD,new_password=NEW_PASSWORD,confirm_password=NEW_PASSWORD),request=request)
                return 200
            except HTTPException as error: db.rollback(); return error.status_code
    def claim():
        with dbm.SessionLocal() as db:
            try:
                auth.complete_password_reset_claim(db,recovery.cookies.get('rr_password_reset_claim'),schema.PasswordResetClaimCompleteRequest(new_password="ClaimWinner123!",confirm_password="ClaimWinner123!"))
                return 200
            except HTTPException as error: db.rollback(); return error.status_code
    results=ordered_jobs(monkeypatch,[change,claim] if first_action=="change" else [claim,change])
    assert results==(200,409 if first_action=="change" else 401),results
    models=importlib.import_module("app.models.auth")
    with dbm.SessionLocal() as db:
        user=db.get(models.AuthUser,uid)
        assert auth.verify_password(NEW_PASSWORD if first_action=="change" else "ClaimWinner123!",user)
        from sqlalchemy import select
        active=list(db.scalars(select(models.AuthSession).where(models.AuthSession.user_id==uid,models.AuthSession.status=="active")))
        assert len(active)==(1 if first_action=="change" else 0)
    browser.close();recovery.close()


@pytest.mark.parametrize("read_first",[True,False])
def test_expiring_read_cannot_overwrite_a_reopened_window(postgres,monkeypatch,read_first):
    admin,dbm=postgres
    create_user("pg-reopen-order")
    app=importlib.import_module("app.main").app; recovery=TestClient(app)
    assert login(admin,"admin",ADMIN_TEST_PASSWORD).status_code==200
    rid=submit_reset(recovery,"pg-reopen-order").json()["request_id"]
    assert approve_reset(admin,rid).status_code==200
    models=importlib.import_module("app.models.auth"); auth=importlib.import_module("app.services.auth")
    system=importlib.import_module("app.services.system"); schema=importlib.import_module("app.schemas.system")
    request=request_for(admin,f"/api/system/password-reset-requests/{rid}/reissue")
    with dbm.SessionLocal() as db:
        actor=auth.get_current_user(request,db)
        row=db.get(models.AuthPasswordResetRequest,rid); row.expires_at="2000-01-01 00:00:00"; db.commit()
    def read():
        with dbm.SessionLocal() as db:
            # Load the obsolete deadline BEFORE obtaining the mutation lock.
            db.get(models.AuthPasswordResetRequest,rid)
            result=auth.get_password_reset_claim(db,recovery.cookies.get('rr_password_reset_claim'))
            db.commit()
            return result.status
    def reopen():
        with dbm.SessionLocal() as db:
            return system.open_password_reset_claim_window(db,actor,rid,schema.PasswordResetReviewRequest(review_comment="重新核验",identity_verified=True),"reopen",request=request).request.status
    ordered_jobs(monkeypatch,[read,reopen] if read_first else [reopen,read])
    with dbm.SessionLocal() as db:
        row=db.get(models.AuthPasswordResetRequest,rid)
        assert row.status=="approved" and row.issue_count==2
        assert not auth.password_reset_can_reopen(row)
    recovery.close()
