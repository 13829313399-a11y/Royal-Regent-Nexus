"""Batch loading must preserve the canonical permission and identity decisions."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models.auth import (AuthUser, EmployeeProfile, AuthRole, AuthPermission, AuthRolePermission,
    AuthUserRole, AuthRoleBindingMetadata, AuthUserPermissionOverride)
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamOrgDepartment, IamRoleVersion
from app.services.auth import build_auth_context, has_permission_in_scope
from app.services.auth_read_inputs import AuthReadInputs
from app.services.identity_resolver import stamp


def test_batch_auth_contexts_match_legacy_v2_denies_frozen_roles_and_time_boundaries(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'authz_mode', 'enforce')
    engine = create_engine('sqlite:///' + (tmp_path / 'auth.db').as_posix())
    Base.metadata.create_all(engine, tables=[t for name, t in Base.metadata.tables.items()
        if name.startswith(('auth_', 'employee_', 'iam_'))])
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    cases = ['legacy', 'active', 'deny', 'future', 'expired', 'old_epoch', 'left', 'inactive_department', 'suspended']
    read = 'carton_procurement:read'
    with Session(engine) as db:
        db.add_all([AuthPermission(id=read, code=read, name='读取'), AuthRole(id='reader', name='读取角色', code='reader'),
            AuthRolePermission(id='reader-read', role_id='reader', permission_id=read)])
        definition = dict(role_id='reader', role_code='reader', role_name='读取角色', permissions=[read],
            read_permissions=[read], scope_mode='own_factory', unrestricted_department=False)
        db.add(IamRoleVersion(id='frozen', role_id='reader', definition_hash='synthetic', definition_json=json.dumps(definition), created_at=stamp(now)))
        for case in cases:
            db.add_all([AuthUser(id=case, username=case, display_name=case, password_salt='synthetic', password_hash='synthetic',
                          status='suspended' if case == 'suspended' else 'active'),
                EmployeeProfile(user_id=case, identity_mode='legacy' if case == 'legacy' else 'v2', confirmation_status='confirmed',
                    employment_status='left' if case == 'left' else 'active', employment_epoch=2,
                    primary_factory_id='huaxing', primary_department='pmc-warehouse'),
                IamOrgUnit(id=case, name=case, kind='factory', legacy_factory_id='huaxing', status='active'),
                IamOrgDepartment(org_unit_id=case, department_code='pmc-warehouse', status='inactive' if case == 'inactive_department' else 'active'),
                AuthUserRole(id=case, user_id=case, role_id='reader', factory_id='huaxing', department='pmc-warehouse')])
            if case != 'legacy':
                db.add(EmployeeAssignment(id=case, user_id=case, org_unit_id=case, department_code='pmc-warehouse',
                    official_position_title='仓管', is_primary=True, lifecycle_state='approved',
                    employment_epoch=1 if case == 'old_epoch' else 2,
                    valid_from=stamp(now + timedelta(days=1) if case == 'future' else now - timedelta(days=2)),
                    valid_until=stamp(now) if case == 'expired' else None,
                    created_by='synthetic', confirmed_by='synthetic', created_at=stamp(now), updated_at=stamp(now)))
                db.add(AuthRoleBindingMetadata(user_role_id=case, state='active', assignment_id=case,
                    employment_epoch=2, role_version_id='frozen'))
            if case == 'deny':
                db.add(AuthUserPermissionOverride(id='deny-read', user_id=case, permission_id=read, effect='deny',
                    factory_id='huaxing', department='pmc-warehouse', status='active', source_type='manual', employment_epoch=2))
        db.commit()
    count = [0]
    def counted(*args): count[0] += 1
    event.listen(engine, 'before_cursor_execute', counted)
    try:
        with Session(engine) as db:
            users = list(db.scalars(select(AuthUser).order_by(AuthUser.id)))
            count[0] = 0
            expected = {u.id: build_auth_context(db, u, at=now) for u in users}
            original_queries = count[0]
        with Session(engine) as db:
            users = list(db.scalars(select(AuthUser).order_by(AuthUser.id)))
            count[0] = 0
            inputs = AuthReadInputs(db, [u.id for u in users])
            actual = {u.id: build_auth_context(db, u, at=now, read_inputs=inputs) for u in users}
            batch_queries = count[0]
            assert actual == expected
            assert batch_queries < original_queries / 2, (original_queries, batch_queries)
            assert has_permission_in_scope(actual['active'], read, 'huaxing', 'pmc-warehouse')
            assert not has_permission_in_scope(actual['deny'], read, 'huaxing', 'pmc-warehouse')
            for case in ['future', 'expired', 'old_epoch', 'left', 'inactive_department', 'suspended']:
                assert not has_permission_in_scope(actual[case], read, 'huaxing', 'pmc-warehouse'), case
            future = next(u for u in users if u.id == 'future')
            assert build_auth_context(db, future, at=now + timedelta(days=2), read_inputs=inputs) == build_auth_context(db, future, at=now + timedelta(days=2))
            with pytest.raises(ValueError): inputs.check(db, 'outside-batch')
            db.rollback()
            with pytest.raises(ValueError): inputs.check(db, 'active')
        print('AUTH_QUERIES', original_queries, batch_queries)
    finally:
        event.remove(engine, 'before_cursor_execute', counted)
        engine.dispose()
