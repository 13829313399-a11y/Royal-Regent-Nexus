import importlib
import json
from dataclasses import replace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SENTINEL = "DoNotExpose" + "MigrationRawSource9321"
PREFIX = "/api/three-d-printing/migration-batches"


@pytest.fixture
def api():
    routes = importlib.import_module("app.api.three_d_printing")
    models = importlib.import_module("app.models.three_d_printing")
    auth = importlib.import_module("app.services.auth")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in (
        models.ThreeDPrintingSite,
        models.ThreeDPrintingMigrationBatch,
        models.ThreeDPrintingMigrationRowResult,
    ):
        model.__table__.create(engine)
    db = Session(engine)
    db.add(
        models.ThreeDPrintingSite(
            id="site-a", factory_id="huakang-a", site_code="heyuan", name="河源"
        )
    )
    db.flush()
    for i, factory in enumerate(("huakang-a", "huakang-a", "huaxing")):
        # The foreign fixture deliberately represents pre-existing corrupt data;
        # query isolation must hold independently of database FK protection.
        db.add(
            models.ThreeDPrintingMigrationBatch(
                id=f"batch-{i}",
                factory_id=factory,
                site_id="site-a",
                source_system="legacy_sqlite",
                source_sha256=str(i) * 64,
                source_updated_at_ms=1788490000000,
                migration_version="v2",
                status="imported",
                started_at=f"2026-09-04 00:00:0{i}",
                expected_counts_json=json.dumps(
                    {"products": 3, "source_path": SENTINEL}
                ),
                summary_json=json.dumps(
                    {
                        "counts": {"products": 3, "raw_json": SENTINEL},
                        "row_status_counts": {"imported": 2, "failed": 1},
                        "password": SENTINEL,
                    }
                ),
                reconciliation_json=json.dumps(
                    {
                        "passed": False,
                        "expected": {"products": 3},
                        "actual": {"products": 2},
                        "issues": [{"code": SENTINEL, "legacy_id": SENTINEL}],
                        "business_totals": {
                            "expected": {"quantity_total": 10, "password": SENTINEL},
                            "actual": {"quantity_total": 9},
                        },
                        "raw_source": SENTINEL,
                    }
                ),
                checkpoint_json=json.dumps({"credential": SENTINEL}),
                lease_id=SENTINEL,
                code_revision=SENTINEL,
                error_code=SENTINEL,
            )
        )
    db.flush()
    for i, status in enumerate(("imported", "failed", "failed")):
        db.add(
            models.ThreeDPrintingMigrationRowResult(
                id=f"row-{i}",
                factory_id="huakang-a",
                batch_id="batch-0",
                entity_type="products",
                legacy_id=str(i),
                target_id=f"product-{i}",
                source_hash="a" * 64,
                status=status,
                error_code=SENTINEL if status == "failed" else "",
                updated_at="2026-09-04 00:01:00",
            )
        )
    db.commit()
    permissions = frozenset(
        {
            "three_d_printing:read",
            "three_d_printing:operate",
            "three_d_printing:audit_read",
        }
    )
    grant = auth.AuthGrantContext(
        role_id="admin",
        role_name="系统管理员",
        role_code="admin",
        factory_id="*",
        department="*",
        permissions=permissions,
    )
    admin = auth.AuthContext(
        id="admin",
        username="admin",
        display_name="管理员",
        roles=("系统管理员",),
        role_codes=("admin",),
        permissions=permissions,
        factory_scopes=("*",),
        department_scopes=("*",),
        grants=(grant,),
    )
    state = {"user": admin, "db": db, "models": models}

    def current_user():
        if state["user"] is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return state["user"]

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_db] = lambda: db
    app.dependency_overrides[routes.get_current_user] = current_user
    with TestClient(app) as client:
        yield client, state, admin, auth
    db.close()
    engine.dispose()


@pytest.mark.parametrize(
    "suffix",
    ["", "/batch-0", "/batch-0/rows", "/batch-0/row-errors", "/batch-0/reconciliation"],
)
def test_all_migration_endpoints_require_admin(api, suffix):
    client, state, admin, _ = api
    state["user"] = None
    assert (
        client.get(PREFIX + suffix, params={"factory_id": "huakang-a"}).status_code
        == 401
    )
    for role in (
        "viewer",
        "position_3d_operator",
        "position_production_manager",
        "position_general_manager",
    ):
        grant = replace(admin.grants[0], role_id=role, role_code=role)
        state["user"] = replace(admin, role_codes=(role,), grants=(grant,))
        assert (
            client.get(PREFIX + suffix, params={"factory_id": "huakang-a"}).status_code
            == 403
        )


def test_admin_pagination_and_safe_projections(api):
    client, _, _, _ = api
    params = {"factory_id": "huakang-a", "page_size": 1}
    first = client.get(PREFIX, params=params)
    second = client.get(PREFIX, params={**params, "page": 2})
    assert first.status_code == 200
    assert first.json()["total"] == 2
    assert first.json()["items"][0]["id"] == "batch-1"
    assert second.json()["items"][0]["id"] == "batch-0"
    detail = client.get(PREFIX + "/batch-0", params=params)
    assert detail.json()["expected_counts"] == {"products": 3}
    assert detail.json()["summary"]["counts"] == {"products": 3}
    assert detail.json()["code_revision"] == ""
    assert detail.json()["error_code"] == "unknown"
    for response in (first, second, detail):
        assert SENTINEL not in response.text
        assert "checkpoint" not in response.text
        assert "lease_id" not in response.text
    for bad in ({"page": 0}, {"page_size": 101}):
        assert client.get(PREFIX, params={**params, **bad}).status_code == 422


def test_rows_filter_reconciliation_and_read_only(api):
    client, _, _, _ = api
    params = {"factory_id": "huakang-a", "status": "failed", "page_size": 1}
    rows = client.get(PREFIX + "/batch-0/rows", params=params)
    assert rows.status_code == 200
    assert rows.json()["total"] == 2
    assert len(rows.json()["items"]) == 1
    assert rows.json()["items"][0]["status"] == "failed"
    assert rows.json()["items"][0]["error_code"] == "unknown"
    errors = client.get(PREFIX + "/batch-0/row-errors", params=params)
    assert errors.json() == rows.json()
    report = client.get(PREFIX + "/batch-0/reconciliation", params=params)
    assert report.json()["passed"] is False
    assert report.json()["issue_count"] == 1
    assert report.json()["issues"][0]["code"] == "unknown"
    assert report.json()["issues"][0]["legacy_key"].startswith("legacy-")
    assert report.json()["business_totals"]["actual"] == {"quantity_total": 9}
    assert SENTINEL not in rows.text + errors.text + report.text
    assert (
        client.get(
            PREFIX + "/batch-0/rows", params={**params, "status": "invalid"}
        ).status_code
        == 422
    )
    assert client.post(PREFIX, params=params, json={}).status_code == 405


def test_static_error_codes_are_actionable_without_raw_details(api):
    client, state, _, _ = api
    db, models = state["db"], state["models"]
    db.get(
        models.ThreeDPrintingMigrationRowResult, "row-1"
    ).error_code = "invalid_numeric_field"
    batch = db.get(models.ThreeDPrintingMigrationBatch, "batch-0")
    batch.error_code = "migration_reconciliation_failed"
    batch.reconciliation_json = json.dumps(
        {
            "passed": False,
            "issues": [
                {
                    "code": "reconciliation_counts_mismatch",
                    "entity_type": "products",
                    "legacy_id": SENTINEL,
                }
            ],
        }
    )
    db.commit()
    params = {"factory_id": "huakang-a"}
    detail = client.get(PREFIX + "/batch-0", params=params)
    assert detail.json()["error_code"] == "migration_reconciliation_failed"
    rows = client.get(PREFIX + "/batch-0/row-errors", params=params)
    assert rows.json()["items"][0]["error_code"] == "invalid_numeric_field"
    checked = client.get(PREFIX + "/batch-0/reconciliation", params=params)
    assert checked.json()["issues"][0]["code"] == "reconciliation_counts_mismatch"
    assert SENTINEL not in detail.text + rows.text + checked.text


def test_factory_filter_and_missing_batch_are_opaque(api):
    client, _, _, _ = api
    for suffix in ("", "/rows", "/row-errors", "/reconciliation"):
        foreign = client.get(
            PREFIX + "/batch-2" + suffix, params={"factory_id": "huakang-a"}
        )
        missing = client.get(
            PREFIX + "/missing" + suffix, params={"factory_id": "huakang-a"}
        )
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
    assert client.get(PREFIX, params={"factory_id": "huaxing"}).status_code == 400


def test_expired_admin_foreign_admin_and_explicit_denies(api):
    client, state, admin, auth = api
    for grant in (
        replace(admin.grants[0], valid_until="2000-01-01 00:00:00"),
        replace(admin.grants[0], factory_id="huaxing"),
    ):
        state["user"] = replace(admin, grants=(grant,))
        assert client.get(PREFIX, params={"factory_id": "huakang-a"}).status_code == 403
    deny = auth.AuthOverrideContext(
        id="deny",
        permission_code="three_d_printing:audit_read",
        effect="deny",
        factory_id="*",
        department="*",
    )
    state["user"] = replace(admin, overrides=(deny,))
    assert client.get(PREFIX, params={"factory_id": "huakang-a"}).status_code == 403
    state["user"] = replace(
        admin, overrides=(replace(deny, department="three-d-printing"),)
    )
    assert client.get(PREFIX, params={"factory_id": "huakang-a"}).status_code == 403


def test_real_importer_report_contract(api, tmp_path, monkeypatch):
    from pathlib import Path

    from test_legacy_three_d_cli import source

    client, state, _, _ = api
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    importer = importlib.import_module("legacy_three_d_importer")
    reader = importlib.import_module("legacy_sqlite_reader")
    db, models = state["db"], state["models"]
    models.ThreeDPrintingSite.metadata.create_all(
        db.get_bind(),
        tables=[
            table
            for table in models.ThreeDPrintingSite.metadata.sorted_tables
            if table.name.startswith("three_d_printing_")
        ],
    )
    db.add(
        models.ThreeDPrintingSite(
            id=importer.SITE,
            factory_id="huakang-a",
            site_code="heyuan-real",
            name="河源",
        )
    )
    # Use the canonical site's code; the unrelated fixture site has a different code.
    db.get(models.ThreeDPrintingSite, "site-a").site_code = "fixture"
    db.flush()
    db.get(models.ThreeDPrintingSite, importer.SITE).site_code = "heyuan"
    db.commit()
    captured = reader.capture_snapshot(source(tmp_path), tmp_path / "captured")
    report = importer.run_migration(
        captured.path,
        captured.manifest,
        session_factory=sessionmaker(bind=db.get_bind()),
        asset_dir=tmp_path / "assets",
        code_revision="a" * 40,
    )
    assert report["reconciliation"]["passed"] is True, report["reconciliation"][
        "issues"
    ]
    params = {"factory_id": "huakang-a"}
    batch = client.get(PREFIX + "/" + report["batch_id"], params=params)
    assert batch.status_code == 200
    assert batch.json()["summary"]["counts"] == report["counts"]
    assert batch.json()["expected_counts"] == report["reconciliation"]["expected"]
    assert batch.json()["code_revision"] == "a" * 40
    reconciliation = client.get(
        PREFIX + "/" + report["batch_id"] + "/reconciliation", params=params
    )
    assert reconciliation.json()["actual_counts"] == report["reconciliation"]["actual"]
    assert (
        reconciliation.json()["business_totals"]
        == report["reconciliation"]["business_totals"]
    )
    assert reconciliation.json()["passed"] is True
