import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from test_three_d_connector_postgres import environment as environment_fixture
from test_three_d_connector_postgres import postgres as postgres_fixture
from test_three_d_release_tools import tool

environment = environment_fixture
postgres = postgres_fixture


def test_postgres_competing_spool_assignments_use_factory_lock(postgres):
    import importlib
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from fastapi import HTTPException

    env, _engine, sessions, _url = postgres
    service = importlib.import_module("app.services.three_d_operations")
    schema = importlib.import_module("app.schemas.three_d_operations")
    user = SimpleNamespace(id="test-admin", display_name="Isolated operator")

    def assign(number):
        with sessions() as db:
            try:
                service.save(
                    db,
                    kind="spool",
                    payload=schema.SaveResource(
                        resource_key=f"spool-{number}",
                        reason="isolated race",
                        idempotency_key=f"spool-race-{number}",
                        data={
                            "material": "PLA",
                            "lot": "test",
                            "initial_g": 1000,
                            "remaining_g": 500,
                            "machine_no": 1,
                            "slot": 0,
                        },
                    ),
                    user=user,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(assign, [1, 2])) == [200, 409]
    with sessions() as db:
        assert (
            db.query(env[2].ThreeDPrintingOperationsItem)
            .filter_by(kind="spool")
            .count()
            == 1
        )


def test_postgres_dump_bundle_restore_and_row_equality(postgres, tmp_path):
    _env, engine, _sessions, url = postgres
    directory = os.environ.get("THREE_D_TEST_PG_BIN")
    if not directory:
        pytest.skip("Set THREE_D_TEST_PG_BIN to local PostgreSQL binaries")
    binary = Path(directory)
    with engine.begin() as db:
        schema = db.execute(text("SELECT current_schema()")).scalar_one()
        db.execute(
            text("CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY)")
        )
        db.execute(text("INSERT INTO alembic_version VALUES ('20260904_0099')"))
        before = db.execute(
            text(
                "SELECT machine_no,name FROM three_d_printing_printers ORDER BY machine_no"
            )
        ).all()
    archive = tmp_path / "database.dump"
    subprocess.run(
        [
            str(binary / "pg_dump.exe"),
            "-h",
            url.host,
            "-p",
            str(url.port),
            "-U",
            url.username,
            "-d",
            url.database,
            "--schema",
            schema,
            "--no-owner",
            "--no-acl",
            "-Fc",
            "-f",
            str(archive),
        ],
        check=True,
        capture_output=True,
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "proof.txt").write_text("isolated asset")
    recovery = tool("recovery")
    recovery.backup(
        archive,
        assets,
        tmp_path / "bundle",
        writers_stopped=True,
        postgres=True,
        revision="20260904_0099",
        pg_restore=binary / "pg_restore.exe",
    )
    recovery.restore(tmp_path / "bundle", tmp_path / "restored")
    name = "pr0709_restore_" + uuid4().hex
    admin = create_engine(url.set(query={}), isolation_level="AUTOCOMMIT")
    with admin.connect() as db:
        db.execute(text(f'CREATE DATABASE "{name}"'))
    restored_engine = None
    try:
        subprocess.run(
            [
                str(binary / "pg_restore.exe"),
                "-h",
                url.host,
                "-p",
                str(url.port),
                "-U",
                url.username,
                "-d",
                name,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                str(tmp_path / "restored/database.dump"),
            ],
            check=True,
            capture_output=True,
        )
        restored_engine = create_engine(url.set(database=name))
        with restored_engine.connect() as db:
            assert (
                db.execute(
                    text(
                        "SELECT machine_no,name FROM three_d_printing_printers ORDER BY machine_no"
                    )
                ).all()
                == before
            )
            assert (
                db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260904_0099"
            )
    finally:
        if restored_engine:
            restored_engine.dispose()
        with admin.connect() as db:
            db.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
