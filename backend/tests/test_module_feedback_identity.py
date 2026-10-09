"""Feedback consumes the same runtime V2 identity as canonical authorization."""
from datetime import timedelta
from dataclasses import replace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import Base
from app.models.auth import AuthPermission, AuthUser, EmployeeProfile
from app.models.identity import EmployeeAssignment, IamOrgDepartment, IamOrgUnit
from app.services.auth import build_auth_context
from app.services.identity_resolver import stamp, utc_now
from app.services.module_feedback import capabilities, MANAGE, SUBMIT
from test_module_feedback import developer, user


@pytest.mark.parametrize("mode", ["legacy", "shadow", "enforce"])
@pytest.mark.parametrize("state", ["active", "future", "ended", "revoked", "old_epoch", "left", "suspended", "org_inactive", "department_inactive"])
def test_v2_runtime_membership_without_roles_cannot_revive_unavailable_identity(monkeypatch, mode, state):
    monkeypatch.setattr(settings, "authz_mode", mode)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[t for n, t in Base.metadata.tables.items()
        if n.startswith(("auth_", "employee_", "iam_"))])
    checked_at = utc_now()
    with Session(engine) as db:
        for code in (SUBMIT, MANAGE, "customer_order:read"):
            db.add(AuthPermission(id=code, code=code, name=code))
        account = AuthUser(id="runtime-employee", username="runtime-employee", display_name="员工",
            password_salt="synthetic", password_hash="synthetic", status="suspended" if state == "suspended" else "active")
        profile = EmployeeProfile(user_id=account.id, identity_mode="v2", confirmation_status="confirmed",
            primary_factory_id="huadeng", primary_department="management", employment_epoch=2,
            employment_status="left" if state == "left" else "active")
        db.add_all([account, profile, IamOrgUnit(id="huaxing", name="华兴", kind="factory", legacy_factory_id="huaxing",
            status="inactive" if state == "org_inactive" else "active"),
            IamOrgDepartment(org_unit_id="huaxing", department_code="sales-business", status="inactive" if state == "department_inactive" else "active")])
        assignment = EmployeeAssignment(id="runtime-assignment", user_id=account.id, org_unit_id="huaxing",
            department_code="sales-business", official_position_title="已确认员工", is_primary=True,
            employment_epoch=1 if state == "old_epoch" else 2,
            lifecycle_state="revoked" if state == "revoked" else "approved",
            valid_from=stamp(checked_at + timedelta(days=1) if state == "future" else checked_at - timedelta(days=2)),
            valid_until=stamp(checked_at) if state == "ended" else None,
            created_by="admin", confirmed_by="admin", created_at=stamp(), updated_at=stamp())
        db.add(assignment)
        db.commit()
        context = build_auth_context(db, account, at=checked_at)
        assert context.grants == ()
        caps = capabilities(context, "huaxing", "customer-order-center")
        assert caps["can_submit"] is (state == "active")
        assert caps["can_manage"] is False and caps["can_link_order"] is False
        # The compatibility profile is stale; the new runtime identity controls home scope.
        assert capabilities(context, "huadeng", "customer-order-center")["can_submit"] is False
    engine.dispose()


def test_v2_transfer_boundary_changes_home_without_materializing_profile():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[t for n, t in Base.metadata.tables.items()
        if n.startswith(("auth_", "employee_", "iam_"))])
    boundary = utc_now() + timedelta(days=1)
    with Session(engine) as db:
        db.add(AuthPermission(id=SUBMIT, code=SUBMIT, name=SUBMIT))
        account = AuthUser(id="transfer", username="transfer", display_name="调厂员工", password_salt="synthetic", password_hash="synthetic")
        profile = EmployeeProfile(user_id=account.id, identity_mode="v2", confirmation_status="confirmed", primary_factory_id="huaxing",
            primary_department="sales-business", employment_epoch=1, employment_status="active")
        db.add_all([account, profile])
        for factory in ("huaxing", "huadeng"):
            db.add(IamOrgUnit(id=factory, name=factory, kind="factory", legacy_factory_id=factory))
            db.add(IamOrgDepartment(org_unit_id=factory, department_code="sales-business"))
            db.add(EmployeeAssignment(id=factory, user_id=account.id, org_unit_id=factory, department_code="sales-business",
                official_position_title="员工", is_primary=True, employment_epoch=1, created_by="admin", confirmed_by="admin",
                created_at=stamp(), updated_at=stamp(), valid_from=stamp(boundary - timedelta(days=2) if factory == "huaxing" else boundary),
                valid_until=stamp(boundary) if factory == "huaxing" else None))
        db.commit()
        for at, home in ((boundary - timedelta(microseconds=1), "huaxing"), (boundary, "huadeng")):
            context = build_auth_context(db, account, at=at)
            for factory in ("huaxing", "huadeng"):
                assert capabilities(context, factory, "customer-order-center")["can_submit"] is (factory == home)
        assert profile.primary_factory_id == "huaxing"
    engine.dispose()


def test_canonical_account_catalog_and_factory_ceilings_remain_authoritative():
    unavailable = replace(user(), account_available=False)
    assert not any(capabilities(unavailable, "huaxing", "customer-order-center")[key]
        for key in ("can_submit", "can_manage", "can_link_order"))
    disabled = replace(user(), permission_catalog_loaded=True, active_permission_codes=frozenset())
    assert capabilities(disabled, "huaxing", "customer-order-center")["can_submit"] is False
    manager = developer()
    manager = replace(manager, grants=(replace(manager.grants[0], factory_ceiling=("huadeng",)),))
    assert capabilities(manager, "huaxing", "customer-order-center")["can_manage"] is False
    reader = user()
    reader = replace(reader, grants=(replace(reader.grants[0], factory_ceiling=("huadeng",)),))
    assert capabilities(reader, "huaxing", "customer-order-center")["can_link_order"] is False
