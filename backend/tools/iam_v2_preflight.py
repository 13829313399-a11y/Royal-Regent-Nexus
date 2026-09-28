"""Read-only, explicit-target preflight. Never imports the application engine.

Usage: python backend/tools/iam_v2_preflight.py --sqlite-copy PATH --output PATH
Only use a controlled, offline backup copy; output contains stable IDs, no names.
"""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def inspect_copy(path, *, at=None, legacy_timezone="Asia/Shanghai"):
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        report = {"mode": "read_only_copy", "integrity": db.execute("PRAGMA quick_check").fetchone()[0],
                  "revision": [r[0] for r in db.execute("SELECT version_num FROM alembic_version")] if "alembic_version" in tables else [],
                  "runtime_authz_mode": "not_observable_from_database_copy", "counts": {}, "review": []}
        for table in ["auth_users", "employee_profiles", "auth_user_roles", "auth_role_binding_metadata", "auth_user_permission_overrides", "auth_sessions", "auth_access_requests", "employee_assignments", "iam_outbox"]:
            if table in tables:
                report["counts"][table] = db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        if {"auth_users", "employee_profiles"} <= tables:
            profile_columns = {r[1] for r in db.execute('PRAGMA table_info("employee_profiles")')}
            org_column = "p.primary_org_unit_id" if "primary_org_unit_id" in profile_columns else "NULL"
            for row in db.execute(f"SELECT u.id, p.primary_factory_id, p.primary_department, {org_column} AS org_unit_id FROM auth_users u LEFT JOIN employee_profiles p ON p.user_id=u.id"):
                functional_group = row["org_unit_id"] == "group-management" and not row["primary_factory_id"] and row["primary_department"] == "management"
                if functional_group:
                    continue
                if not row["primary_factory_id"] or not row["primary_department"]:
                    report["review"].append({"user_id": row["id"], "issue": "MISSING_CONFIRMED_ORGANIZATION"})
                elif row["primary_factory_id"] not in {"huakang-a", "huakang-b", "huakang-c", "huakang-d", "huaxing", "huadeng"}:
                    report["review"].append({"user_id": row["id"], "issue": "REVIEW_ORGANIZATION_MAPPING"})
        if {"auth_user_roles", "auth_role_binding_metadata"} <= tables:
            for row in db.execute("SELECT b.id,b.user_id,m.state,m.source_type FROM auth_user_roles b LEFT JOIN auth_role_binding_metadata m ON m.user_role_id=b.id"):
                if row["state"] is None or row["source_type"] in {None, "legacy_import", "manual"}:
                    report["review"].append({"user_id": row["user_id"], "binding_id": row["id"], "issue": "SOURCE_CLASSIFICATION_REQUIRED"})
        if "auth_user_permission_overrides" in tables:
            report["override_effect_counts"] = dict(db.execute("SELECT effect,count(*) FROM auth_user_permission_overrides GROUP BY effect"))
        if "auth_sessions" in tables:
            report["session_state_counts"] = dict(db.execute("SELECT status,count(*) FROM auth_sessions GROUP BY status"))
        report.update(source_inventory(db, tables, at or datetime.now(timezone.utc), legacy_timezone))
        report["note"] = "本报告不修改来源、不推断主职；窗口分类不等于有效授权。授权保持性须经逐人预览矩阵与业务对象验证。运行配置须由运维另外核实。"
        return report


def source_inventory(db, tables, at, legacy_timezone):
    """Explicit column allowlists exclude credentials, contacts and token hashes."""
    findings = []
    def rows(table, columns):
        if table not in tables:
            return []
        present = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
        fields = [name for name in columns.split() if name in present]
        return [dict(r) for r in db.execute('SELECT ' + ','.join('"' + c + '"' for c in fields) + f' FROM "{table}"')] if fields else []

    def window(row):
        if row.get("state", row.get("status", "active")) in {"revoked", "inactive", "cancelled"}:
            return "revoked"
        parsed = []
        for key in ("valid_from", "valid_until"):
            value = row.get(key)
            try:
                time = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
                if time and time.tzinfo is None:
                    time = time.replace(tzinfo=ZoneInfo(legacy_timezone))
                parsed.append(time)
            except ValueError:
                return "invalid_time"
        start, end = parsed
        if start and end and end <= start:
            return "invalid_time"
        return "expired" if end and end <= at else "future" if start and start > at else "active"

    profiles = {r["user_id"]: r for r in rows("employee_profiles", "user_id primary_factory_id primary_department confirmation_status identity_mode primary_org_unit_id employment_epoch")}
    users = rows("auth_users", "id status")
    roles = {r["id"]: r for r in rows("auth_roles", "id code")}
    role_meta = {r["role_id"]: r for r in rows("auth_role_metadata", "role_id scope_mode")}
    metadata = {r["user_role_id"]: r for r in rows("auth_role_binding_metadata", "user_role_id state source_type source_id valid_from valid_until assignment_id employment_epoch role_version_id")}
    bindings = rows("auth_user_roles", "id user_id role_id factory_id department")
    overrides = rows("auth_user_permission_overrides", "id user_id permission_id effect factory_id department status source_type source_id valid_from valid_until assignment_id employment_epoch")
    permissions = {r["id"]: r for r in rows("auth_permissions", "id code")}
    permission_meta = {r["permission_id"]: r for r in rows("auth_permission_metadata", "permission_id status")}
    assignments = rows("employee_assignments", "id user_id org_unit_id department_code is_primary valid_from valid_until lifecycle_state employment_epoch")
    source_rows = []
    duplicates = defaultdict(list)
    categories = defaultdict(set)
    for binding in bindings:
        meta = metadata.get(binding["id"])
        combined = {**binding, **(meta or {})}
        state = window(combined)
        source_rows.append({**combined, "kind": "role_binding", "window": state})
        if meta is None:
            findings.append({"user_id": binding["user_id"], "binding_id": binding["id"], "issue": "MISSING_BINDING_SIDECAR"})
        if state in {"active", "future"}:
            duplicates[(binding["user_id"], binding["role_id"], binding["factory_id"], binding["department"])].append(binding["id"])
            categories["internal_role_users"].add(binding["user_id"])
        code = roles.get(binding["role_id"], {}).get("code", "")
        if not code:
            findings.append({"user_id": binding["user_id"], "binding_id": binding["id"], "issue": "MISSING_ROLE"})
        if code == "admin" and binding["factory_id"] == "*":
            categories["wildcard_administrators"].add(binding["user_id"])
        if code == "position_general_manager":
            categories["general_managers"].add(binding["user_id"])
        if code == "position_warehouse_manager" or role_meta.get(binding["role_id"], {}).get("scope_mode") == "cross_factory_operate":
            categories["cross_factory_operators"].add(binding["user_id"])
        profile = profiles.get(binding["user_id"], {})
        if (state in {"active", "future"} and profile and binding["factory_id"] != "*"
                and (binding["factory_id"], binding["department"]) != (profile.get("primary_factory_id"), profile.get("primary_department"))):
            findings.append({"user_id": binding["user_id"], "binding_id": binding["id"], "issue": "ROLE_ORGANIZATION_DIFF_REQUIRES_CLASSIFICATION"})
    for override in overrides:
        source_rows.append({**override, "kind": "override", "window": window(override)})
        if permissions.get(override["permission_id"], {}).get("code", "").startswith("carton_supplier:"):
            categories["supplier_users"].add(override["user_id"])
    references = [{"kind": "override", "id": r["id"], "permission_id": r["permission_id"]} for r in overrides]
    references += [{"kind": "role_permission", **r} for r in rows("auth_role_permissions", "id role_id permission_id")]
    for ref in references:
        permission = permissions.get(ref["permission_id"], {})
        code = permission.get("code", "")
        if not code or ":" not in code or permission_meta.get(ref["permission_id"], {}).get("status") == "inactive":
            findings.append({**ref, "issue": "INVALID_OR_INACTIVE_PERMISSION_REFERENCE"})
        elif ref["permission_id"] not in permission_meta:
            findings.append({**ref, "issue": "MISSING_PERMISSION_SIDECAR"})
    for keys, ids in duplicates.items():
        if len(ids) > 1:
            findings.append({"user_id": keys[0], "binding_ids": ids, "issue": "POSSIBLE_DUPLICATE_SOURCE"})
    for source in source_rows:
        if source["window"] == "invalid_time":
            findings.append({"source_id": source["id"], "kind": source["kind"], "issue": "INVALID_SOURCE_TIME"})
    known_departments = {r["department_code"] for r in rows("iam_org_departments", "department_code")}
    known_departments |= {"management", "system", "engineering", "production", "molding", "pmc-warehouse", "sales-business",
                          "qc", "qa", "painting", "assembly", "electronic", "sewing", "slush", "hair", "carton", "three-d-printing"}
    for uid, profile in profiles.items():
        if profile.get("primary_department") not in known_departments:
            findings.append({"user_id": uid, "issue": "DEPARTMENT_ALIAS_OR_UNKNOWN"})
        if profile.get("confirmation_status") != "confirmed":
            findings.append({"user_id": uid, "issue": "PROFILE_NOT_CONFIRMED"})
    primaries = defaultdict(list)
    for assignment in assignments:
        if assignment.get("is_primary") and assignment.get("lifecycle_state") == "approved" and window(assignment) == "active":
            if assignment.get("employment_epoch") == profiles.get(assignment["user_id"], {}).get("employment_epoch"):
                primaries[assignment["user_id"]].append(assignment["id"])
    for uid, ids in primaries.items():
        if len(ids) > 1:
            findings.append({"user_id": uid, "assignment_ids": ids, "issue": "MULTIPLE_ACTIVE_PRIMARY_ASSIGNMENTS"})
    previews = rows("auth_authorization_previews", "id actor_user_id target_id target_type expires_at consumed_at")
    requests = rows("auth_access_requests", "id requester_user_id target_user_id status lifecycle_state request_type effective_at")
    registrations = rows("auth_registration_requests", "id user_id status")
    responsibilities = rows("internal_quotes", "id factory_id business_owner_id status header_revision")
    responsibilities = [r for r in responsibilities if r.get("business_owner_id") and r.get("status") in {"drafting", "ready_for_final_review"}]
    categories["supplier_and_internal_users"] = categories["supplier_users"] & categories["internal_role_users"]
    return {"as_of": at.isoformat(), "legacy_timestamp_timezone": legacy_timezone,
        "runtime_authz_writes_enabled": "not_observable_from_database_copy",
        "source_window_counts": dict(Counter(r["window"] for r in source_rows)), "sources": source_rows,
        "special_accounts": {key: sorted(value) for key, value in categories.items()}, "findings": findings,
        "unconsumed_previews": [r for r in previews if not r.get("consumed_at")],
        "pending_requests": [r for r in requests if r.get("status") == "pending" or r.get("lifecycle_state") in {"draft", "pending_approval", "scheduled"}],
        "pending_registrations": [r for r in registrations if r.get("status") == "pending"],
        "pending_user_ids": [r["id"] for r in users if r.get("status") == "pending"],
        "business_responsibility_review": responsibilities,
        "business_qualification_review": "按正式任职核实销售/业务候选和当前报价负责人；未适配模块按交接覆盖清单人工核实，不自动推导。"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-copy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-timezone", default="Asia/Shanghai")
    args = parser.parse_args()
    if args.output.resolve() == args.sqlite_copy.resolve():
        parser.error("报告路径不能覆盖输入数据库")
    report = inspect_copy(args.sqlite_copy, legacy_timezone=args.legacy_timezone)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"integrity": report["integrity"], "review_count": len(report["review"]), "output": str(args.output)}, ensure_ascii=False))
