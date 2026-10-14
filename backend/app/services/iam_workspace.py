"""Read-only, scope-first projection of IAM workflows. Never invokes write planners.

Adapters read unpaged, bounded-column source metadata; the combined authorized
projection is filtered, counted, stably ordered and paged exactly once. Source
failures are explicit and make counts unknown instead of reporting a false zero.
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func, literal, union_all, or_
from sqlalchemy.orm import load_only
from fastapi import HTTPException
from app.core.config import settings
from app.core.time import serialize_process_local_timestamp
from app.models.auth import AuthUser, EmployeeProfile, AuthRegistrationRequest, AuthPasswordResetRequest, AuthAccessRequest, AuthUserPermissionOverride, AuthUserRole, AuthRoleBindingMetadata
from app.models.identity import IamOrgUnit, EmployeeAssignment, IamRoleVersion
from app.models.position_review import PositionReview
from app.services.auth import can, parse_time
from app.services.identity_policy import fail, is_group_manager, additional_source_scopes, ensure_change_authority
from app.services.identity_resolver import identity_columns, instant, stamp, utc_now
from app.services.identity_catalog import FACTORIES, DEPARTMENTS
from app.services.identity_sources import role_definition
from app.services import position_workbench_read as positions, position_reviews, system

KINDS = ("position", "registration", "password-reset", "identity-change")
log = logging.getLogger(__name__)


def complete_scopes(scopes):
    """Retain wildcard authority requirements and evaluate concrete deny tuples."""
    result = set(scopes)
    for factory, department in scopes:
        result.update((f, d) for f in (FACTORIES if factory == "*" else [factory])
                      for d in (DEPARTMENTS if department == "*" else [department]))
    return result


def local_stamp(value):
    return serialize_process_local_timestamp(value) or ""


def password_state(row, user, now):
    raw = row.status
    expires = instant(parse_time(row.expires_at))
    if not row.claim_token_hash and raw in {"pending", "approved", "expired"}:
        return "legacy_invalid", "closed", [], ["旧申请已失效，请本人重新申请"]
    if raw == "approved" and (not expires or expires <= now):
        raw = "expired"
    if raw == "approved":
        return raw, "waiting_employee", [], []
    enabled = settings.authz_mode == "enforce" and settings.authz_writes_enabled
    if raw == "pending":
        actions = (["approve", "reject"] if user and user.status == "active" else ["reject"]) if enabled else []
        return raw, "actionable" if actions else "blocked", actions, ([] if actions else ["当前仅可查看"])
    if raw == "expired" and row.claim_token_hash and expires and expires <= now and user and user.status == "active":
        return raw, "actionable" if enabled else "blocked", ["reissue"] if enabled else [], [] if enabled else ["当前仅可查看"]
    return raw, "closed", [], []


def password_detail(db, actor, request_id):
    # The legacy GET expires rows, emits audit events and commits. This adapter
    # derives expiry without changing the request, notifications or audit log.
    if not ("system:user_manage" in actor.permissions):
        fail("FORBIDDEN", "无权查看密码找回申请", 403)
    row = db.get(AuthPasswordResetRequest, request_id)
    if row is None:
        fail("NOT_FOUND", "申请不存在", 404)
    required = system.target_users_scopes(db, [row.user_id]).get(row.user_id, set()) if row.user_id else set()
    if (not required and not system.is_superadmin(actor)) or any(not can(actor, "system:user_manage", f, d) for f, d in complete_scopes(required)):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "申请超出管理范围", 403)
    if not can(actor, "system:user_manage", row.factory_id or "*", row.department or "*"):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "申请范围超出管理范围", 403)
    out = system.password_reset_request_to_out(db, row)
    raw, _, actions, _ = password_state(row, db.get(AuthUser, row.user_id) if row.user_id else None, utc_now())
    return {**out.model_dump(), "status": raw, "can_reopen": "reissue" in actions, "available_actions": actions}


class Projection:
    def __init__(self, db, actor, now):
        self.db, self.actor, self.now = db, actor, now
        self._people = None
        self._scopes = None

    @property
    def people(self):
        if self._people is None:
            f, d, title, org = identity_columns(include_org=True)
            self._people = {u.id: (u, p, o or factory or "", dept or "", t or "") for u, p, factory, dept, t, o in
                self.db.execute(select(AuthUser, EmployeeProfile, f, d, title, org).outerjoin(EmployeeProfile).options(
                    load_only(AuthUser.id, AuthUser.username, AuthUser.display_name, AuthUser.status),
                    load_only(EmployeeProfile.user_id, EmployeeProfile.identity_mode, EmployeeProfile.employment_epoch, EmployeeProfile.employment_status)))}
        return self._people

    @property
    def scopes(self):
        if self._scopes is None:
            self._scopes = system.target_users_scopes(self.db, list(self.people))
        return self._scopes

    def allowed(self, uid, codes):
        required = self.scopes.get(uid, set())
        return all(can(self.actor, code, f, d) for f, d in complete_scopes(required or {("*", "*")}) for code in codes)

    def task(self, kind, row, uid, org, dept, proposed, raw, state, actions, blocked, created, revision):
        person = self.people.get(uid)
        u = person[0] if person else None
        return {"key": f"{kind}:{row.id}", "kind": kind, "source_id": row.id, "source_revision": str(revision),
            "subject": {"user_id": uid or "", "display_name": u.display_name if u else getattr(row, "display_name", "未匹配账号"),
                        "username": u.username if u else getattr(row, "username", "")},
            "org_unit_id": org, "department": dept, "current_position": person[4] if person else "", "proposed_position": proposed,
            "raw_status": raw, "state": state, "created_at": created, "available_actions": actions, "blocked_reasons": blocked}

    def position(self, registration=False):
        position_reviews.require_schema(self.db)
        codes = ("system:user_manage", "system:access_manage")
        provisional = positions.provisional_registration_users(self.db) if registration else set()
        extras = additional_source_scopes(self.db) if registration else {}
        rows = self.db.scalars(select(AuthRegistrationRequest if registration else PositionReview))
        output = []
        for row in rows:
            declared = positions.declaration(row)
            org, dept = declared["org_unit_id"], declared["department_code"]
            provisional_visible = registration and row.status == "pending" and row.user_id in provisional and all(
                positions.allowed_scope(self.actor, f, d) for f, d in extras.get(row.user_id, set()))
            if not (provisional_visible or self.allowed(row.user_id, codes)) or not positions.allowed_scope(self.actor, org, dept):
                continue
            u, profile, *_ = self.people[row.user_id]
            blocked = []
            if not position_reviews.writes_enabled(): blocked.append("当前仅可查看，岗位更新暂不可提交")
            if not registration and (not profile or profile.identity_mode != "v2"):
                blocked.append("需先核实历史授权来源")
            if not registration and profile and (profile.employment_epoch != row.employment_epoch or profile.employment_status == "left"):
                blocked.append("任职周期已变化，此申请不再适用")
            if u.status != ("pending" if registration else "active"): blocked.append("账号当前不可办理")
            pending = row.status == "pending"
            actions = ["preview", "commit", "reject" if registration else "return"] if pending and not blocked else []
            output.append(self.task("registration" if registration else "position", row, row.user_id, org, dept, declared["position"],
                row.status, ("blocked" if blocked else "actionable") if pending else "waiting_employee" if row.status == "returned" else "closed", actions, blocked if pending else [],
                local_stamp(row.created_at) if registration else row.created_at, positions.revision(row)))
        return output

    def password(self):
        output = []
        for row in self.db.scalars(select(AuthPasswordResetRequest)):
            if not (self.allowed(row.user_id, ("system:user_manage",)) if row.user_id else system.is_superadmin(self.actor)):
                continue
            if not can(self.actor, "system:user_manage", row.factory_id or "*", row.department or "*"): continue
            person = self.people.get(row.user_id)
            raw, state, actions, blocked = password_state(row, person[0] if person else None, self.now)
            output.append(self.task("password-reset", row, row.user_id, row.factory_id, row.department, "密码找回", row.status, state, actions,
                blocked, local_stamp(row.submitted_at or row.created_at), f"{row.status}:{row.issue_count}:{row.updated_at}"))
        return output

    def changes(self):
        output = []
        orgs = {o.id: o.legacy_factory_id or o.id for o in self.db.scalars(select(IamOrgUnit))}
        for row in self.db.scalars(select(AuthAccessRequest).where(AuthAccessRequest.request_type.like("identity:%"))):
            if not is_group_manager(self.actor) and row.requester_user_id != self.actor.id: continue
            if not self.allowed(row.target_user_id, ("system:user_manage",)): continue
            payload = json.loads(row.payload_json)
            spec = payload.get("new_assignment") or {}
            required = set()
            authority_scopes = {(o, orgs.get(o, o), d) for o, d in self.scopes.get(row.target_user_id, set())}
            roles = []
            invalid_reference = False
            def include_binding(binding, meta, upgrade=False):
                if not binding or binding.user_id != row.target_user_id:
                    return False
                required.add((binding.factory_id or "*", binding.department or "*"))
                definition = role_definition(self.db, binding.role_id)
                fixed = self.db.get(IamRoleVersion, meta.role_version_id) if meta and meta.role_version_id else None
                definitions = [json.loads(fixed.definition_json) if fixed else definition]
                if upgrade: definitions.append(definition)
                for value in definitions:
                    factories = json.loads(meta.scope_ceiling_json) if meta and meta.scope_ceiling_json is not None else (
                        ["*"] if value["scope_mode"] == "cross_factory_operate" else [binding.factory_id])
                    required.update((f or "*", binding.department or "*") for f in factories)
                    authority_scopes.update((f, f, binding.department or "*") for f in factories)
                if row.request_type == "identity:confirm_identity":
                    # Confirmation repins the latest definition and removes the
                    # old ceiling in the existing domain transition.
                    proposed = ["*"] if definition["scope_mode"] == "cross_factory_operate" else [binding.factory_id]
                    required.update((f or "*", binding.department or "*") for f in proposed)
                    authority_scopes.update((f, f, binding.department or "*") for f in proposed)
                if upgrade:
                    roles.append({"role_id": binding.role_id, "factories": json.loads(meta.scope_ceiling_json) if meta.scope_ceiling_json else list(FACTORIES)})
                return True
            source_id = payload.get("source_assignment_id")
            if source_id:
                assignment = self.db.get(EmployeeAssignment, source_id)
                if not assignment or assignment.user_id != row.target_user_id: continue
                required.add((orgs.get(assignment.org_unit_id, assignment.org_unit_id), assignment.department_code))
                authority_scopes.add((assignment.org_unit_id, orgs.get(assignment.org_unit_id, assignment.org_unit_id), assignment.department_code))
                if row.request_type == "identity:upgrade_packages":
                    for meta in self.db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.assignment_id == source_id)):
                        if not include_binding(self.db.get(AuthUserRole, meta.user_role_id), meta, True): invalid_reference = True
            decisions = {v["binding_id"] for v in payload.get("binding_dispositions", [])}
            if row.request_type == "identity:confirm_identity" or decisions:
                found = set()
                for binding, meta in self.db.execute(select(AuthUserRole, AuthRoleBindingMetadata).outerjoin(
                    AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id).where(AuthUserRole.user_id == row.target_user_id)):
                    if binding.id in decisions or row.request_type == "identity:confirm_identity" and (not meta or meta.state == "active"):
                        include_binding(binding, meta); found.add(binding.id)
                if decisions - found: invalid_reference = True
            if invalid_reference: continue
            for decision in payload.get("exception_decisions", []):
                override = self.db.get(AuthUserPermissionOverride, decision.get("override_id"))
                if override and override.user_id == row.target_user_id:
                    required.add((override.factory_id, override.department))
                    authority_scopes.add((override.factory_id, override.factory_id, override.department))
            if spec:
                if spec["org_unit_id"] not in orgs: continue
                required.add((orgs[spec["org_unit_id"]], spec["department_code"]))
                authority_scopes.add((spec["org_unit_id"], orgs[spec["org_unit_id"]], spec["department_code"]))
                for binding in spec.get("role_bindings", []):
                    scope = binding.get("factory_scope") or {"kind": "home"}
                    factories = list(FACTORIES) if scope["kind"] == "all_current" else scope.get("factory_ids", []) if scope["kind"] == "selected" else [orgs[spec["org_unit_id"]]]
                    required.update((f, binding["department"]) for f in factories)
                    authority_scopes.update((f, f, binding["department"]) for f in factories)
                    roles.append({"role_id": binding["role_id"], "factories": factories})
            # Payload destinations are part of read visibility too, independently
            # of the target's current identity. Never run prepare/snapshot_role.
            required = complete_scopes(required)
            if any(not can(self.actor, "system:user_manage", f, d) for f, d in required): continue
            authority_scopes.update((f, f, d) for f, d in required)
            raw = row.lifecycle_state
            if raw == "scheduled" and row.effective_at and instant(row.effective_at) <= self.now: raw = "applied"
            writes = settings.authz_mode == "enforce" and settings.authz_writes_enabled and settings.iam_identity_writes_enabled
            authority = True
            try: ensure_change_authority(self.db, self.actor, row.target_user_id, authority_scopes, roles)
            except HTTPException: authority = False
            # A user's draft can still be previewed and submitted for approval.
            editable = writes and (raw == "draft" and row.requester_user_id == self.actor.id or authority)
            actions = ["preview"] if editable and raw in {"draft", "pending_approval"} else []
            state = "scheduled" if raw == "scheduled" else ("actionable" if actions else "blocked") if raw in {"draft", "pending_approval"} else "closed"
            person = self.people.get(row.target_user_id)
            output.append(self.task("identity-change", row, row.target_user_id, spec.get("org_unit_id") or (person[2] if person else ""),
                spec.get("department_code") or (person[3] if person else ""), spec.get("official_position_title") or payload.get("official_position_title") or "高级任职变更",
                row.lifecycle_state, state, actions, ["需由有权管理员核对"] if state == "blocked" else [], row.created_at, row.revision))
        return output


def tasks(db, actor, *, page=1, page_size=30, q="", kind="", state="open", org_unit_id="", target_user_id="", from_at="", to_at=""):
    if not (("system:user_manage" in actor.permissions) or ("system:access_manage" in actor.permissions)):
        fail("FORBIDDEN", "无权查看办理工作区", 403)
    now = utc_now()
    projection = Projection(db, actor, now)
    coverage, items, partial = [], [], False
    readers = {"position": lambda: projection.position(), "registration": lambda: projection.position(True),
               "password-reset": projection.password, "identity-change": projection.changes}
    for source in KINDS:
        readable = ("system:user_manage" in actor.permissions) and (source not in {"position", "registration"} or ("system:access_manage" in actor.permissions))
        if not readable:
            coverage.append({"kind": source, "readable": False, "state": "not_authorized"})
            continue
        if kind and kind != source and not (kind == "position-registration" and source in {"position", "registration"}):
            coverage.append({"kind": source, "readable": True, "state": "ready"})
            continue
        try:
            with db.no_autoflush:
                items.extend(readers[source]())
            coverage.append({"kind": source, "readable": True, "state": "ready"})
        except Exception:
            # A failed read transaction must not poison subsequent adapters.
            db.rollback()
            partial = True
            coverage.append({"kind": source, "readable": True, "state": "unavailable", "message": "此来源暂不可用，请重试"})
            log.exception("IAM workspace source unavailable: %s", source)
    # Scope and derived lifecycle eligibility precede SQL COUNT / UNION paging.
    eligible = {r["key"]: r for r in items if (not org_unit_id or org_unit_id == r["org_unit_id"])
        and (not state or (state == "open" and r["state"] != "closed") or r["state"] == state)}
    branches = []
    models = {"position": PositionReview, "registration": AuthRegistrationRequest,
              "password-reset": AuthPasswordResetRequest, "identity-change": AuthAccessRequest}
    from app.services.work_center.service import Epoch
    for source, model in models.items():
        ids = [r["source_id"] for r in eligible.values() if r["kind"] == source]
        if not ids: continue
        uid = model.target_user_id if source == "identity-change" else model.user_id
        created = model.submitted_at if source == "password-reset" else model.created_at
        name = func.coalesce(AuthUser.display_name, model.display_name) if source == "password-reset" else AuthUser.display_name
        username = func.coalesce(AuthUser.username, model.username) if source == "password-reset" else AuthUser.username
        branch = select(literal(source).label("kind"), model.id.label("id"), Epoch(created).label("created"))\
            .select_from(model).outerjoin(AuthUser, AuthUser.id == uid).where(model.id.in_(ids))
        if q.strip(): branch = branch.where(or_(name.contains(q.strip(), autoescape=True), username.contains(q.strip(), autoescape=True)))
        if target_user_id: branch = branch.where(uid == target_user_id)
        if from_at: branch = branch.where(Epoch(created) >= instant(from_at).timestamp())
        if to_at: branch = branch.where(Epoch(created) <= instant(to_at).timestamp())
        branches.append(branch)
    total, actionable, result = 0, 0, []
    if branches:
        union = union_all(*branches).subquery()
        total = db.scalar(select(func.count()).select_from(union))
        actionable_ids = [r["key"] for r in eligible.values() if r["state"] == "actionable"]
        actionable = db.scalar(select(func.count()).select_from(union).where((union.c.kind + ":" + union.c.id).in_(actionable_ids)))
        keys = db.execute(select(union).order_by(union.c.created, union.c.id, union.c.kind).offset((page-1)*page_size).limit(page_size)).mappings()
        result = [eligible[f"{r['kind']}:{r['id']}"] for r in keys]
    return {"items": result, "page": page, "page_size": page_size,
        "visible_total": None if partial else total, "actionable_total": None if partial else actionable,
        "count_scope": "current_normalized_filter", "coverage": coverage, "partial": partial, "server_now": stamp(now)}
