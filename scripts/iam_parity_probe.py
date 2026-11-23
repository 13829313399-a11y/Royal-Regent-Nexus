"""A subprocess imports exactly one checkout and only connects to its isolated clone."""
import hashlib
import itertools
import json
import os
import sys
import socket
import time
from collections import defaultdict
from importlib.metadata import version
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic_settings.sources import DotEnvSettingsSource
from sqlalchemy import select, text


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), default=str).encode()).hexdigest()


def inventory(db, anchor):
    from app.models import auth as a, identity as i
    from app.services.identity_catalog import FACTORIES, DEPARTMENTS
    from app.services.identity_resolver import instant
    users = {u: {"account": [status, forced, fingerprint([username, salt, hashed])]} for u, username, status, forced, salt, hashed in
             db.execute(select(a.AuthUser.id, a.AuthUser.username, a.AuthUser.status, a.AuthUser.force_password_change,
                               a.AuthUser.password_salt, a.AuthUser.password_hash))}
    if not users:
        raise ValueError("Snapshot contains no existing accounts")
    times = {uid: {anchor} for uid in users}
    session_times = defaultdict(dict)
    factories = set(FACTORIES) | {"*", "group-management"}
    departments = set(DEPARTMENTS) | {"*", "system"}
    for org, dept in db.execute(select(i.IamOrgDepartment.org_unit_id, i.IamOrgDepartment.department_code)):
        factories.add(org)
        departments.add(dept)
    from app.services.identity_sources import role_definition
    roles = {r.id: r for r in db.scalars(select(a.AuthRole))}
    definition_hashes = {}
    versions = {v.id: v for v in db.scalars(select(i.IamRoleVersion))}
    permissions = {p.id: p.code for p in db.scalars(select(a.AuthPermission))}
    def copy_fields(row, names):
        return {k: getattr(row, k) for k in names.split()}
    def boundary_points(values):
        points = set()
        for raw in values:
            if raw:
                when = instant(raw)
                for shift in (-1, 0, 1):
                    points.add((when + timedelta(microseconds=shift)).isoformat())
        return points
    def bounds(uid, values):
        times[uid].update(boundary_points(values))
    def put(uid, collection, key, value):
        users[uid].setdefault(collection, {})[key] = value
    for p in db.scalars(select(a.EmployeeProfile)):
        users[p.user_id]["profile"] = copy_fields(p, "identity_mode identity_version employment_status employment_epoch primary_assignment_id primary_org_unit_id primary_factory_id primary_department position confirmation_status")
    for revision in db.scalars(select(a.AuthUserAuthorizationRevision)):
        users[revision.user_id]["authorization_version"] = revision.revision
    for row in db.scalars(select(i.EmployeeAssignment)):
        put(row.user_id, "assignments", row.id, copy_fields(row, "org_unit_id department_code official_position_title assignment_type is_primary valid_from valid_until lifecycle_state employment_epoch source_request_id revision revoked_at"))
        bounds(row.user_id, [row.valid_from, row.valid_until])
    for b, m in db.execute(select(a.AuthUserRole, a.AuthRoleBindingMetadata)
                           .outerjoin(a.AuthRoleBindingMetadata, a.AuthRoleBindingMetadata.user_role_id == a.AuthUserRole.id)):
        factories.add(b.factory_id or "*")
        departments.add(b.department or "*")
        value = copy_fields(b, "role_id factory_id department")
        value["role_code"] = roles[b.role_id].code if b.role_id in roles else None
        if m:
            value.update(copy_fields(m, "state assignment_id role_version_id scope_ceiling_json employment_epoch source_type source_id valid_from valid_until version"))
            if m.scope_ceiling_json:
                factories.update(json.loads(m.scope_ceiling_json))
            v = versions.get(m.role_version_id)
            if v:
                value["pinned_hash"] = v.definition_hash
                value["pinned_definition"] = fingerprint(json.loads(v.definition_json))
            bounds(b.user_id, [m.valid_from, m.valid_until])
        if b.role_id in roles and (m is None or not m.role_version_id):
            if b.role_id not in definition_hashes:
                definition_hashes[b.role_id] = fingerprint(role_definition(db, b.role_id))
            value["unversioned_definition"] = definition_hashes[b.role_id]
        put(b.user_id, "bindings", b.id, value)
    for o in db.scalars(select(a.AuthUserPermissionOverride)):
        value = copy_fields(o, "permission_id factory_id department effect status valid_from valid_until assignment_id employment_epoch lifecycle_policy source_type")
        value["code"] = permissions.get(o.permission_id)
        put(o.user_id, "overrides", o.id, value)
        factories.add(o.factory_id or "*")
        departments.add(o.department or "*")
        bounds(o.user_id, [o.valid_from, o.valid_until])
    for row in db.scalars(select(i.IamDelegation)):
        put(row.user_id, "delegations", row.id, copy_fields(row, "org_unit_id department role_ids_json factory_ids_json status revision"))
    for s in db.scalars(select(a.AuthSession)):
        # Never write cookie hashes or login credentials to the report.
        put(s.user_id, "sessions", s.id, {"status": s.status, "expires_at": s.expires_at, "revoked_at": s.revoked_at,
                                        "lookup_fingerprint": fingerprint(s.token_hash)})
        session_times[s.user_id][s.id] = sorted(boundary_points([s.expires_at]))
    return {"sources": users, "session_times": session_times, "times": {uid: sorted(values) for uid, values in times.items()},
            "factories": sorted(factories), "departments": sorted(departments), "codes": sorted(permissions.values())}


def session_decisions(db, sessions, when, load_context):
    from app.models.auth import AuthSession
    from app.services import auth, identity_resolver
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.astimezone(tz) if tz else when.astimezone().replace(tzinfo=None)
    outcomes = {}
    with patch.object(auth, "datetime", Clock), patch.object(db, "commit", lambda: None), \
            patch.object(identity_resolver, "utc_now", lambda: when), patch.object(auth, "build_auth_context", load_context):
        for s in sessions:
            statuses = []
            for path in ("/api/auth/me", "/api/system/people"):
                copy = AuthSession(user_id=s.user_id, status=s.status, expires_at=s.expires_at)
                try:
                    auth.authenticated_session_user(db, copy, method="GET", path=path)
                    statuses.append(200)
                except HTTPException as exc:
                    statuses.append(exc.status_code)
            outcomes[s.id] = statuses
    return outcomes


def evaluate(db, domain, out):
    from app.models.auth import AuthUser, AuthSession
    from app.services.auth import authorization_decision, build_auth_context, has_permission_in_scope
    from app.services import identity_resolver
    from app.services.auth_read_inputs import AuthReadInputs
    sessions = defaultdict(dict)
    done, session_checks, started, last_update = 0, 0, time.monotonic(), 0
    progress = os.environ.get("IAM_PARITY_PROGRESS_FILE")
    def update_progress():
        target = Path(progress)
        staging = target.with_suffix(".tmp")
        staging.write_text(json.dumps({"completed_matrix_instants": done, "completed_session_paths": session_checks,
                "elapsed_seconds": round(time.monotonic()-started), "observed_utc": datetime.now(timezone.utc).isoformat()}),encoding="utf-8")
        staging.replace(target)
    for session in db.scalars(select(AuthSession)):
        sessions[session.user_id][session.id] = session
    for uid, grant_times in sorted(domain["times"].items()):
        row = db.get(AuthUser, uid)
        if not row:
            continue
        inputs = AuthReadInputs(db, [uid])
        permission_points = set(grant_times)
        # Every session is checked at all grant checkpoints, plus its OWN expiry
        # boundaries. Session expiry cannot change another session or any grant.
        checks = defaultdict(list)
        session_points = domain.get("session_times", {}).get(uid, {})
        for sid, session in sessions[uid].items():
            dates = session_points.get(sid, [])
            for point in permission_points.union(dates):
                checks[point].append(session)
        all_points = permission_points | {t for dates in session_points.values() for t in dates}
        for point in sorted(all_points):
            at = datetime.fromisoformat(point)
            context = None
            def load_context(request_db, request_user):
                nonlocal context
                if request_db is not db or request_user.id != uid:
                    raise RuntimeError("Session checked an unexpected employee")
                if context is None:
                    context = build_auth_context(db, row, at=at, read_inputs=inputs)
                return context
            bits = bytearray()
            if point in permission_points:
                context = load_context(db, row)
                bits = bytearray((len(domain["evaluators"])*len(domain["codes"])*len(domain["factories"])*len(domain["departments"])+7)//8)
                cells = itertools.product(domain["evaluators"], domain["codes"], domain["factories"], domain["departments"])
                with patch.object(identity_resolver, "utc_now", lambda: at):
                    for n, (evaluator, code, factory, department) in enumerate(cells):
                        allowed = (authorization_decision(context, code, factory, department, at=at)[0]
                                   if evaluator == "canonical" else has_permission_in_scope(context, code, factory, department))
                        if allowed:
                            bits[n//8] |= 1 << (n%8)
            out.write(json.dumps([uid, point, bits.hex(), session_decisions(db, checks[point], at, load_context)]) + "\n")
            done += int(bool(bits))
            session_checks += 2 * len(checks[point])
            if progress and time.monotonic()-last_update >= 15:
                update_progress()
                last_update = time.monotonic()
    if progress:
        update_progress()


def main():
    root, mode, output, input_arg = sys.argv[1:]
    if os.environ.get("IAM_PARITY_OFFLINE") == "1":
        from sqlalchemy.engine import make_url
        database = make_url(os.environ["DATABASE_URL"])
        allowed = {"localhost", "127.0.0.1", "::1"}
        if database.get_backend_name() != "sqlite" and database.host not in allowed:
            raise ValueError("Offline rehearsal requires a loopback database")
        def local_only(event, args):
            if event == "socket.getaddrinfo" and args[0] and args[0] not in allowed:
                raise PermissionError("Offline rehearsal blocks external name resolution")
            if event == "socket.connect" and isinstance(args[1], tuple):
                host, port = args[1][:2]
                caller = sys._getframe(1)
                if host in allowed and caller.f_code is getattr(socket.socketpair, "__code__", None):
                    return  # Windows asyncio creates its private wake-up pipe with socket.socketpair.
                if host not in allowed or port != database.port:
                    raise PermissionError("Offline rehearsal blocks non-database TCP")
        sys.addaudithook(local_only)
    sys.path.insert(0, str(Path(root) / "backend"))
    # Environment comes from a single explicit configuration on the coordinator, independent of checkout-local .env files.
    with patch.object(DotEnvSettingsSource, "_read_env_files", lambda self: {}):
        from app.core.config import settings
        from app.db import SessionLocal, engine
        if engine.url.render_as_string(hide_password=False) != os.environ["DATABASE_URL"]:
            raise ValueError("Isolated database configuration mismatch")
        offsets = {str(month): datetime(2026, month, 1).astimezone().utcoffset().total_seconds() for month in (1, 7)}
        if os.environ.get("IAM_PARITY_REQUIRE_UTC") == "1":
            if any(offsets.values()) or abs((datetime.now() - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) > 2:
                raise RuntimeError("UTC wall clock or legacy timestamp conversion does not match production")
        if mode == "migrate":
            from alembic import command
            from alembic.config import Config
            command.upgrade(Config(str(Path(root)/"backend"/"alembic.ini")), "head")
            return
        if mode == "startup":
            from app.main import app
            from fastapi.testclient import TestClient
            with TestClient(app) as c:
                c.get("/health").raise_for_status()
            return
        with SessionLocal() as db, open(output, "w", encoding="utf-8") as stream:
            if mode == "inventory":
                result = inventory(db, input_arg)
                result["settings"] = {k: getattr(settings, k) for k in ("authz_mode", "authz_writes_enabled",
                    "iam_identity_writes_enabled", "iam_position_workbench_enabled", "iam_identity_scheduling_enabled",
                    "seed_default_accounts", "session_cookie_secure", "app_env")}
                result["settings"]["process_timezone"] = list(time.tzname)
                result["settings"]["wall_clock_offsets_seconds"] = offsets
                result["runtime"] = {"python": sys.version, "studio_writes_enabled": getattr(settings, "iam_access_studio_writes_enabled", None), **{p:version(p) for p in ("SQLAlchemy","fastapi","pydantic")}}
                result["engine_version"] = db.scalar(text("select sqlite_version()" if engine.dialect.name == "sqlite" else "select version()"))
                json.dump(result, stream, ensure_ascii=False)
            elif mode == "evaluate":
                evaluate(db, json.loads(Path(input_arg).read_text(encoding="utf-8")), stream)
            else:
                raise ValueError("unknown probe mode")
        engine.dispose()


if __name__ == "__main__":
    main()
