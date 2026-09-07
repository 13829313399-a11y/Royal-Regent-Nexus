import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text
from test_three_d_connector import environment as environment_fixture
from test_three_d_connector import event, post, session

environment = environment_fixture
ROOT = Path(__file__).resolve().parents[2]


def tool(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "deploy/three-d-printing" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_printer_cutover_rollback_and_stale_plan(environment, tmp_path):
    env = environment
    cutover, recovery = tool("cutover"), tool("recovery")
    with env[1].engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('20260904_0099')"))
    with env[1].SessionLocal() as db:
        first = db.get(env[2].ThreeDPrintingPrinterConnection, env[5][0])
        first.connection_owner = "edge-legacy"
        first.connection_enabled = False
        db.commit()
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "image.bin").write_bytes(b"same-batch-asset")
    source = Path(env[1].engine.url.database)
    recovery.backup(source, assets, tmp_path / "backup", writers_stopped=True)
    with env[1].SessionLocal() as db:
        plan = cutover.plan(db, env[5][0], "cloud-connector")
        with pytest.raises(ValueError, match="writer-stop"):
            cutover.apply(
                db, plan, backup=tmp_path / "backup", actor="test", reason="test"
            )
        stale = {**plan, "connection_revision": 999}
        with pytest.raises(ValueError, match="stale"):
            cutover.apply(
                db,
                stale,
                backup=tmp_path / "backup",
                actor="test",
                reason="test",
                writers_stopped=True,
            )
        result = cutover.apply(
            db,
            plan,
            backup=tmp_path / "backup",
            actor="test",
            reason="isolated handoff",
            writers_stopped=True,
        )
        assert result["owner"] == "cloud-connector"
        assert (
            db.get(
                env[2].ThreeDPrintingPrinterConnection, env[5][1]
            ).connection_revision
            == 1
        )
        rollback = cutover.plan(db, env[5][0], "edge-legacy")
        result = cutover.apply(
            db,
            rollback,
            backup=tmp_path / "backup",
            actor="test",
            reason="isolated rollback",
            writers_stopped=True,
        )
        assert result["owner"] == "edge-legacy"
        assert not db.get(
            env[2].ThreeDPrintingPrinterConnection, env[5][0]
        ).connection_enabled
    assert recovery.verify(tmp_path / "backup")["assets"]["image.bin"]["size"] == 16


def test_raw_retention_keeps_normalized_state_and_audit(environment):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    retention = tool("retention")
    with env[1].SessionLocal() as db:
        row = db.query(env[2].ThreeDPrintingPrinterStateEvent).one()
        row.received_at = "2020-01-01T00:00:00+00:00"
        db.commit()
        audit_count = db.query(env[2].ThreeDPrintingAuditEvent).count()
        assert retention.retain(db)["raw_bodies"] == 1
        assert row.raw_payload_json != "{}"
        retention.retain(db, execute=True)
        db.refresh(row)
        assert row.raw_payload_json == "{}" and row.state == "RUNNING"
        assert db.query(env[2].ThreeDPrintingAuditEvent).count() == audit_count
        assert retention.retain(db, execute=True)["raw_bodies"] == 0


def test_windows_plan_generates_host_routes_without_changing_machine(tmp_path):
    import subprocess

    output = tmp_path / "review.json"
    script = ROOT / "deploy/three-d-printing/network/windows-tailscale-plan.ps1"
    command = f"& '{script}' -PrinterIPs @({','.join(repr('192.168.33.' + str(n)) for n in range(101, 112))}) -OutputPath '{output}'"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan["mode"] == "plan_only_no_network_changes"
    assert plan["reviewed_command"].count("/32") == 11
