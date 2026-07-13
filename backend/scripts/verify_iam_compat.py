from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


CORE_QUERIES = {
    "users": """
        SELECT id, username, display_name, password_salt, password_hash, status,
               force_password_change, last_login_at, created_at, updated_at
        FROM auth_users ORDER BY id
    """,
    "sessions": """
        SELECT id, user_id, token_hash, status, expires_at, created_at, revoked_at
        FROM auth_sessions ORDER BY id
    """,
    "roles": "SELECT id, code, name, description FROM auth_roles ORDER BY id",
    "permissions": "SELECT id, code, name, description FROM auth_permissions ORDER BY id",
    "role_permissions": """
        SELECT id, role_id, permission_id
        FROM auth_role_permissions ORDER BY id
    """,
    "user_roles": """
        SELECT id, user_id, role_id, factory_id, department
        FROM auth_user_roles ORDER BY id
    """,
    "registrations": """
        SELECT id, user_id, username, display_name, phone, email, factory_id,
               department, position, status, reviewer_user_id, review_comment,
               submitted_at, reviewed_at, created_at, updated_at
        FROM auth_registration_requests ORDER BY id
    """,
}

MATRIX_QUERY = """
    SELECT DISTINCT ur.user_id, p.code AS permission_code,
           ur.factory_id, ur.department
    FROM auth_user_roles ur
    JOIN auth_role_permissions rp ON rp.role_id = ur.role_id
    JOIN auth_permissions p ON p.id = rp.permission_id
    JOIN auth_users u ON u.id = ur.user_id
    WHERE u.status IN ('active', 'suspended')
    ORDER BY ur.user_id, p.code, ur.factory_id, ur.department
"""


def read_rows(connection: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql)]


def read_snapshot(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        snapshot: dict[str, Any] = {}
        for name, sql in CORE_QUERIES.items():
            table_name = "auth_registration_requests" if name == "registrations" else f"auth_{name}"
            if name == "role_permissions":
                table_name = "auth_role_permissions"
            elif name == "user_roles":
                table_name = "auth_user_roles"
            snapshot[name] = read_rows(connection, sql) if table_name in tables else []

        snapshot["role_permission_matrix"] = read_rows(connection, MATRIX_QUERY)
        snapshot["iam_tables"] = sorted(name for name in tables if name.startswith("auth_") or name == "employee_profiles")
        return snapshot


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    differences: dict[str, Any] = {}
    additive_catalogs: dict[str, Any] = {}
    for name in ("users", "sessions", "user_roles", "registrations"):
        if before[name] != after[name]:
            differences[name] = {
                "before_count": len(before[name]),
                "after_count": len(after[name]),
                "before_sha256": digest(before[name]),
                "after_sha256": digest(after[name]),
            }

    for name in ("roles", "permissions", "role_permissions"):
        before_by_id = {row["id"]: row for row in before[name]}
        after_by_id = {row["id"]: row for row in after[name]}
        changed_or_removed = {
            row_id: {"before": row, "after": after_by_id.get(row_id)}
            for row_id, row in before_by_id.items()
            if after_by_id.get(row_id) != row
        }
        if changed_or_removed:
            differences[name] = {
                "changed_or_removed": changed_or_removed,
                "before_count": len(before[name]),
                "after_count": len(after[name]),
            }
        additive_catalogs[name] = {
            "added_count": len(set(after_by_id) - set(before_by_id)),
            "added_ids": sorted(set(after_by_id) - set(before_by_id)),
        }

    matrix_equal = before["role_permission_matrix"] == after["role_permission_matrix"]
    return {
        "compatible": not differences and matrix_equal,
        "core_differences": differences,
        "additive_catalogs": additive_catalogs,
        "role_permission_matrix": {
            "equal": matrix_equal,
            "before_count": len(before["role_permission_matrix"]),
            "after_count": len(after["role_permission_matrix"]),
            "before_sha256": digest(before["role_permission_matrix"]),
            "after_sha256": digest(after["role_permission_matrix"]),
        },
        "new_iam_tables": sorted(set(after["iam_tables"]) - set(before["iam_tables"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare IAM-sensitive SQLite data before and after an additive migration.")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()

    result = compare(read_snapshot(args.before.resolve()), read_snapshot(args.after.resolve()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
