"""Known differences must block the gate; a realistic disposable seed also exercises the probe."""
import importlib
import sys
from pathlib import Path
from sqlalchemy import select

from test_position_reviews import client, employee
from test_iam_api import create_user

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import iam_parity as gate
import iam_parity_probe as probe


def test_matrix_merge_reports_grant_revoke_session_and_missing_employee(tmp_path):
    first, second = tmp_path/"old", tmp_path/"candidate"
    first.write_text('["a","t","01",{"one":[200,200]}]\n["b","t","00",{}]\n')
    second.write_text('["a","t","02",{"one":[401,401]}]\n')
    found = []
    count = gate.compare_streams(first, second, {"codes":["a","b"],"factories":["f"],"departments":["d"]}, found.append)
    assert count == 2
    assert [(r["code"], r["after_allow"]) for r in found if "code" in r] == [("a", False), ("b", True)]
    assert {"employee":"b","time":"t","matrix":"removed"} in found
    assert any(r.get("before") == [200,200] and r.get("after") == [401,401] for r in found)
    assert list(gate.differences({"u":{"state":"active"}},{"u":{"state":"disabled"}})) == [(("u","state"),"changed")]


def test_inventory_handles_historical_cross_factory_and_functional_sources(client):
    # This database is also a reproducible synthetic input for the full two-release CLI.
    import json
    uid = employee(client, "qa-parity-existing")
    create_user("qa-parity-disabled", "position_engineering_engineer", "huakang-b", "engineering")
    group = create_user("qa-parity-group", "position_general_manager", "huakang-a", "management")
    auth, identity, dbm = (importlib.import_module("app."+name) for name in ("models.auth", "models.identity", "db"))
    with dbm.SessionLocal() as db:
        db.get(auth.AuthUser, "user-qa-parity-disabled").status = "disabled"
        group_profile = db.get(auth.EmployeeProfile, group)
        group_profile.primary_org_unit_id = "group-management"
        group_profile.primary_factory_id = ""
        original = db.scalar(select(auth.AuthUserRole).where(auth.AuthUserRole.user_id == uid))
        meta = db.get(auth.AuthRoleBindingMetadata, original.id)
        latest = db.get(identity.IamRoleVersion, meta.role_version_id)
        definition = json.loads(latest.definition_json)
        historical = definition["permissions"][0]
        definition["permissions"] = [historical]
        definition["read_permissions"] = [historical] if historical in definition["read_permissions"] else []
        sources = importlib.import_module("app.services.identity_sources")
        old = identity.IamRoleVersion(id="fixed-historical", role_id=original.role_id,
             definition_hash=sources.definition_hash(definition), definition_json=json.dumps(definition), created_at=latest.created_at)
        db.add(old)
        db.flush()
        meta.role_version_id = old.id
        anchor = db.get(identity.EmployeeAssignment, meta.assignment_id)
        def add_assignment(user_id, key, org, dept, title, primary, kind):
            row = identity.EmployeeAssignment(id=key, user_id=user_id, org_unit_id=org, department_code=dept,
                    official_position_title=title, assignment_type=kind, is_primary=primary, valid_from=anchor.valid_from,
                    lifecycle_state="approved", employment_epoch=1, created_by="user-admin", confirmed_by="user-admin",
                    created_at=anchor.created_at, updated_at=anchor.updated_at)
            db.add(row)
            db.flush()
            return row
        secondary = add_assignment(uid, "qa-second-assignment", "huakang-b", "engineering", "兼任工程师", False, "part_time")
        functional = add_assignment(group, "qa-group-assignment", "group-management", "management", "总经理", True, "regular")
        group_profile.primary_assignment_id = functional.id
        group_profile.identity_mode = "v2"
        group_profile.identity_version = 1
        group_binding = db.scalar(select(auth.AuthUserRole).where(auth.AuthUserRole.user_id == group))
        group_meta = db.get(auth.AuthRoleBindingMetadata, group_binding.id)
        group_meta.assignment_id = functional.id
        group_meta.source_type = "assignment"
        group_meta.role_version_id = sources.snapshot_role(db, group_binding.role_id, "user-admin").id
        group_meta.employment_epoch = 1
        group_meta.scope_ceiling_json = '["huakang-a","huakang-b"]'
        db.add(auth.AuthUserRole(id="cross-factory", user_id=uid, role_id=original.role_id,
                                 factory_id="huakang-b", department="engineering"))
        db.flush()
        db.add(auth.AuthRoleBindingMetadata(user_role_id="cross-factory", state="active", source_type="assignment",
               assignment_id=secondary.id, employment_epoch=1, role_version_id=old.id, scope_ceiling_json='["huakang-b"]'))
        permission = db.scalar(select(auth.AuthPermission).where(auth.AuthPermission.code==historical))
        for key, effect in (("qa-allow", "allow"), ("qa-deny", "deny")):
            db.add(auth.AuthUserPermissionOverride(id=key, user_id=uid, permission_id=permission.id,
                   employment_epoch=1, factory_id="huakang-b", department="engineering", status="active",
                   effect=effect, valid_from="2026-12-01T00:00:00Z", valid_until="2026-12-31T00:00:00Z"))
        db.commit()
        snap = probe.inventory(db, "2026-11-19T00:00:00+00:00")
        assert snap["sources"][uid]["bindings"][original.id]["role_version_id"] == "fixed-historical"
        assert snap["sources"][uid]["assignments"]["qa-second-assignment"]["assignment_type"] == "part_time"
        assert snap["sources"][group]["assignments"]["qa-group-assignment"]["org_unit_id"] == "group-management"
        assert snap["sources"][uid]["sessions"]
        assert snap["sources"][group]["profile"]["primary_org_unit_id"] == "group-management"
        assert "2026-11-30T23:59:59.999999+00:00" in snap["times"][uid]
        assert "2026-12-31T00:00:00+00:00" in snap["times"][uid]

def test_session_only_boundaries_do_not_duplicate_permission_decisions(tmp_path):
    inventory = {"codes": ["permit"], "factories": ["factory"], "departments": ["dept"],
                 "times": {"u": ["current"]}, "session_times": {"u": {"s1": ["expiry1"], "s2": ["expiry2"]}}}
    domain = gate.union_domain([inventory, inventory])
    assert domain["times"]["u"] == ["current"]
    assert domain["session_times"]["u"] == {"s1": ["expiry1"], "s2": ["expiry2"]}
    first, second = tmp_path/"before", tmp_path/"after"
    regular = '["u","current","00",{"s1":[200,200],"s2":[200,200]}]\n'
    first.write_text(regular + '["u","expiry1","",{"s1":[401,401]}]\n')
    second.write_text(regular + '["u","expiry1","",{"s1":[200,403]}]\n')
    found = []
    assert gate.compare_streams(first, second, domain, found.append) == 4
    assert found == [{"employee":"u","time":"expiry1","session":["s1"],"change":"changed",
                      "before":[401,401],"after":[200,403]}]
