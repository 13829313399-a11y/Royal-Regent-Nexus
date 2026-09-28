import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def test_offline_inventory_reports_windows_sources_queues_without_secrets(tmp_path):
    target = tmp_path / "offline.db"
    with sqlite3.connect(target) as db:
        db.executescript("""
            CREATE TABLE auth_users(id TEXT, status TEXT, password_hash TEXT);
            INSERT INTO auth_users VALUES ('u','pending','never-output-this-secret');
            CREATE TABLE employee_profiles(user_id TEXT,primary_factory_id TEXT,primary_department TEXT,confirmation_status TEXT,primary_org_unit_id TEXT);
            INSERT INTO employee_profiles VALUES ('u','huakang-a','工程','unconfirmed','huakang-a'),('group','','management','confirmed','group-management');
            INSERT INTO auth_users VALUES ('group','active','never-output-group-secret');
            CREATE TABLE auth_roles(id TEXT,code TEXT);
            INSERT INTO auth_roles VALUES ('admin','admin');
            CREATE TABLE auth_user_roles(id TEXT,user_id TEXT,role_id TEXT,factory_id TEXT,department TEXT);
            INSERT INTO auth_user_roles VALUES ('missing','u','admin','*','*'),('duplicate','u','admin','*','*'),('future','u','admin','*','*');
            CREATE TABLE auth_role_binding_metadata(user_role_id TEXT,state TEXT,source_type TEXT,valid_from TEXT,valid_until TEXT);
            INSERT INTO auth_role_binding_metadata VALUES ('duplicate','active','manual','',''),('future','active','manual','2027-01-01T00:00:00Z','');
            CREATE TABLE auth_permissions(id TEXT,code TEXT);
            INSERT INTO auth_permissions VALUES ('supplier','carton_supplier:read'),('invalid','bad-code');
            CREATE TABLE auth_user_permission_overrides(id TEXT,user_id TEXT,permission_id TEXT,effect TEXT,factory_id TEXT,department TEXT,status TEXT,valid_until TEXT);
            INSERT INTO auth_user_permission_overrides VALUES ('past','u','supplier','allow','*','*','active','2025-01-01 00:00:00'),('bad','u','invalid','deny','*','*','active','');
            CREATE TABLE auth_authorization_previews(id TEXT,consumed_at TEXT,expires_at TEXT,token_hash TEXT);
            INSERT INTO auth_authorization_previews VALUES ('preview','','2027-01-01','never-output-token');
            CREATE TABLE auth_access_requests(id TEXT,status TEXT,lifecycle_state TEXT);
            INSERT INTO auth_access_requests VALUES ('request','pending','scheduled');
            CREATE TABLE auth_registration_requests(id TEXT,user_id TEXT,status TEXT);
            INSERT INTO auth_registration_requests VALUES ('registration','u','pending');
        """)
    source = Path(__file__).resolve().parents[1] / "tools/iam_v2_preflight.py"
    spec = importlib.util.spec_from_file_location("iam_preflight", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    content, modified = target.read_bytes(), target.stat().st_mtime_ns
    result = module.inspect_copy(target, at=datetime(2026, 9, 27, tzinfo=timezone.utc))
    assert result["source_window_counts"] == {"active": 3, "future": 1, "expired": 1}
    issues = {item["issue"] for item in result["findings"]}
    assert {"MISSING_BINDING_SIDECAR", "POSSIBLE_DUPLICATE_SOURCE", "INVALID_OR_INACTIVE_PERMISSION_REFERENCE",
            "DEPARTMENT_ALIAS_OR_UNKNOWN", "PROFILE_NOT_CONFIRMED"} <= issues
    assert result["special_accounts"]["wildcard_administrators"] == ["u"]
    assert result["special_accounts"]["supplier_and_internal_users"] == ["u"]
    assert len(result["pending_requests"]) == len(result["pending_registrations"]) == len(result["unconsumed_previews"]) == 1
    assert "never-output" not in json.dumps(result)
    assert not any(item["user_id"] == "group" for item in result["review"])
    assert target.read_bytes() == content and target.stat().st_mtime_ns == modified
