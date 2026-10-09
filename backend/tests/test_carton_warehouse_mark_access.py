from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy import delete, select

from test_molding_sample_api import make_client, login_as


def test_warehouse_document_access_remains_factory_department_scoped_and_denies_win(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        profile = login_as(client, "warehouse_keeper")
        from app.db import SessionLocal
        from app.models.auth import AuthUserRole, AuthPermission, AuthUserPermissionOverride
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        output = BytesIO()
        writer.write(output)
        content = output.getvalue()
        for index, (role, department, cross_factory) in enumerate([
            ("warehouse_keeper", "pmc-warehouse", False),
            ("position_warehouse_keeper", "pmc-warehouse", False),
            ("position_warehouse_supervisor", "pmc-warehouse", False),
            ("position_warehouse_manager", "pmc-warehouse", True),
            ("position_carton_warehouse_keeper", "carton", False),
        ]):
            with SessionLocal() as db:
                db.execute(delete(AuthUserRole).where(AuthUserRole.user_id == profile["id"]))
                db.add(AuthUserRole(id=f"mark-position-{index}", user_id=profile["id"], role_id=role,
                                    factory_id="huaxing", department=department))
                db.commit()
            for factory, allowed in [("huaxing", True), ("huadeng", cross_factory)]:
                listing = client.get("/api/carton-mark/assets", params={"factory_id": factory})
                assert listing.status_code == (200 if allowed else 403), (role, listing.text)
                uploaded = client.post("/api/carton-mark/assets/batch", data={"factory_id": factory},
                    files={"files": ("4500222793.pdf", content, "application/pdf")})
                assert uploaded.status_code == (200 if allowed else 403), (role, uploaded.text)
                if allowed:
                    assert uploaded.json()[0]["status"] in {"created", "duplicate"}, uploaded.text
        with SessionLocal() as db:
            # A warehouse position bound to an unrelated department cannot upload documents.
            binding = db.get(AuthUserRole, "mark-position-4")
            binding.department = "engineering"
            db.commit()
        assert client.get("/api/carton-mark/assets", params={"factory_id": "huaxing"}).status_code == 403
        with SessionLocal() as db:
            binding.department = "carton"
            db.merge(binding)
            for code in ["carton_mark:read", "carton_mark:template_upload"]:
                permission = db.scalar(select(AuthPermission).where(AuthPermission.code == code))
                db.add(AuthUserPermissionOverride(id=f"deny-{permission.id}", user_id=profile["id"],
                    permission_id=permission.id, effect="deny", factory_id="huaxing", department="carton"))
            db.commit()
        assert client.get("/api/carton-mark/assets", params={"factory_id": "huaxing"}).status_code == 403
        assert client.post("/api/carton-mark/assets/batch", data={"factory_id": "huaxing"},
            files={"files": ("4500222793.pdf", content, "application/pdf")}).status_code == 403
        with SessionLocal() as db:
            db.execute(delete(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == profile["id"]))
            current = db.get(AuthUserRole, "mark-position-4")
            current.role_id = "position_external_carton_warehouse_keeper"
            current.department = "carton"
            db.commit()
        assert client.get("/api/carton-mark/assets", params={"factory_id": "huaxing"}).status_code == 200
        assert client.post("/api/carton-mark/assets/batch", data={"factory_id": "huaxing"},
            files={"files": ("4500222793.pdf", content, "application/pdf")}).status_code == 403


def test_legacy_backfill_invalidates_access_once_and_preserves_pinned_versions(monkeypatch):
    with make_client(monkeypatch) as client:
        profile = login_as(client, "warehouse_keeper")
        from app.db import SessionLocal
        from app.models.auth import (AuthRolePermission, AuthPermission, AuthUserRole,
                                     AuthUserAuthorizationRevision, AuthRoleMetadata, AuthIamState)
        from app.models.identity import IamRoleVersion
        from app.services.auth import seed_carton_mark_warehouse_grants_once
        from app.services.identity_sources import snapshot_role
        with SessionLocal() as db:
            codes = {"carton_mark:read", "carton_mark:template_upload"}
            permissions = list(db.scalars(select(AuthPermission).where(AuthPermission.code.in_(codes))))
            db.execute(delete(AuthRolePermission).where(AuthRolePermission.role_id == "warehouse_keeper",
                AuthRolePermission.permission_id.in_([p.id for p in permissions])))
            db.delete(db.get(AuthIamState, "carton_mark_warehouse_grants_v1"))
            db.flush()
            pinned = snapshot_role(db, "warehouse_keeper", profile["id"])
            pinned_json = pinned.definition_json
            before = [(r.id, r.factory_id, r.department) for r in db.scalars(select(AuthUserRole).order_by(AuthUserRole.id))]
            revision = db.get(AuthUserAuthorizationRevision, profile["id"])
            before_revision = revision.revision if revision else 0
            metadata = db.get(AuthRoleMetadata, "warehouse_keeper")
            before_version = metadata.version
            assert seed_carton_mark_warehouse_grants_once(db, "2026-10-06T10:00:00") == 2
            db.flush()
            assert db.get(AuthUserAuthorizationRevision, profile["id"]).revision == before_revision + 1
            assert metadata.version == before_version + 1
            assert db.get(IamRoleVersion, pinned.id).definition_json == pinned_json
            assert before == [(r.id, r.factory_id, r.department) for r in db.scalars(select(AuthUserRole).order_by(AuthUserRole.id))]
            db.execute(delete(AuthRolePermission).where(AuthRolePermission.role_id == "warehouse_keeper",
                AuthRolePermission.permission_id == permissions[0].id))
            db.flush()
            assert seed_carton_mark_warehouse_grants_once(db, "2026-10-06T10:00:01") == 0
            assert db.scalar(select(AuthRolePermission.id).where(AuthRolePermission.role_id == "warehouse_keeper",
                AuthRolePermission.permission_id == permissions[0].id)) is None
