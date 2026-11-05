"""Raw, request-local inputs for constructing a bounded group of auth contexts.

The canonical identity/authorization evaluators still decide every permission.
This is not an authorization cache and must not be retained after the read.
"""
from collections import defaultdict
from sqlalchemy import select

from app.models.auth import (AuthPermission, AuthPermissionMetadata, AuthUserRole,
    AuthRoleBindingMetadata, AuthRole, AuthRoleMetadata, AuthRolePermission,
    AuthUserPermissionOverride, AuthUserAuthorizationRevision, EmployeeProfile)
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamOrgDepartment, IamRoleVersion


class AuthReadInputs:
    def __init__(self, db, user_ids):
        self.db = db
        self.user_ids = set(user_ids)
        if not self.user_ids or len(self.user_ids) > 100:
            raise ValueError('Auth inputs require 1–100 users')
        self.permissions = list(db.scalars(select(AuthPermission).order_by(AuthPermission.code)))
        self.permission_metadata = list(db.scalars(select(AuthPermissionMetadata)))
        self.profiles = {r.user_id: r for r in db.scalars(select(EmployeeProfile).where(EmployeeProfile.user_id.in_(self.user_ids)))}
        self.revisions = {r.user_id: r for r in db.scalars(select(AuthUserAuthorizationRevision).where(AuthUserAuthorizationRevision.user_id.in_(self.user_ids)))}
        self.user_roles, self.overrides, self.assignments = defaultdict(list), defaultdict(list), defaultdict(list)
        bindings = list(db.scalars(select(AuthUserRole).where(AuthUserRole.user_id.in_(self.user_ids)).order_by(AuthUserRole.id)))
        for row in bindings:
            self.user_roles[row.user_id].append(row)
        role_ids = {row.role_id for row in bindings}
        self.binding_metadata = {r.user_role_id: r for r in db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.user_role_id.in_([row.id for row in bindings])))}
        self.roles = {r.id: r for r in db.scalars(select(AuthRole).where(AuthRole.id.in_(role_ids)))}
        self.role_metadata = {r.role_id: r for r in db.scalars(select(AuthRoleMetadata).where(AuthRoleMetadata.role_id.in_(role_ids)))}
        self.role_permissions = list(db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id.in_(role_ids))))
        for row in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id.in_(self.user_ids),
                          AuthUserPermissionOverride.status == 'active').order_by(AuthUserPermissionOverride.id)):
            self.overrides[row.user_id].append(row)
        for assignment, org in db.execute(select(EmployeeAssignment, IamOrgUnit).select_from(EmployeeAssignment).join(IamOrgUnit)
                .where(EmployeeAssignment.user_id.in_(self.user_ids)).order_by(EmployeeAssignment.valid_from, EmployeeAssignment.id)):
            self.assignments[assignment.user_id].append((assignment, org))
        # Keep strong references for source_is_active/binding_grants Session.get.
        self.departments = list(db.scalars(select(IamOrgDepartment)))
        self.active_departments = {(r.org_unit_id, r.department_code) for r in self.departments if r.status == 'active'}
        versions = {r.role_version_id for r in self.binding_metadata.values() if r.role_version_id}
        self.role_versions = list(db.scalars(select(IamRoleVersion).where(IamRoleVersion.id.in_(versions))))
        self.transaction = db.get_transaction()

    def check(self, db, user_id):
        if db is not self.db or db.get_transaction() is not self.transaction or user_id not in self.user_ids:
            raise ValueError('Auth inputs belong to a different read scope')
