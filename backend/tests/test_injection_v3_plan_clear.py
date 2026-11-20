"""Factory reset is preview-bound, audited, atomic, and allows the same file again."""

from datetime import timedelta

from app.api import injection_scheduling as api
from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    FactorySettings,
    ImportBatch,
    Machine,
    MoldAsset,
    MoldMaster,
    Operation,
    SavedView,
    SharedRevision,
)
from app.services.injection_scheduling import plan_clear
from app.services.injection_scheduling.calculations import now
from app.services.injection_scheduling.common import record
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from test_injection_v3_api import BASE, ok, seed_job, write
from test_injection_v3_api import env as env  # noqa: PLC0414
from test_injection_v3_excel_merge import apply_legacy, legacy_book
from test_injection_v3_iam_migration import account, login
from test_injection_v3_iam_migration import iam_env as iam_env  # noqa: PLC0414
from test_injection_v3_import_export import upload


def preview(env, factory="huaxing"):
    return ok(
        env[0].post(BASE + "/plan-data/clear-preview", json={"factory_id": factory})
    )


def clear(env, impact=None, **changes):
    impact = impact or preview(env)
    args = {
        "expected_revision": impact["revision"],
        "preview_token": impact["preview_token"],
        "confirmation": impact["confirmation_text"],
        "reason": "误导入旧版计划",
        **changes,
    }
    return write(env, "/plan-data/clear", factory=impact["factory_id"], **args)


def rows(db, model, where=True):
    return [
        record(row)
        for row in db.scalars(
            select(model)
            .where(where)
            .order_by(model.__table__.primary_key.columns.values()[0])
        )
    ]


def all_state(engine):
    with Session(engine) as db:
        return {
            table: [
                tuple(r)
                for r in db.execute(text(f'SELECT * FROM "{table}" ORDER BY 1'))
            ]
            for table in db.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            ).scalars()
        }


def test_clear_import_execution_transfer_and_same_file_reimport(env):
    content = legacy_book(duplicate=True)
    first, _ = apply_legacy(env, content)
    _, other_machine, other_demand = seed_job(env, factory="huadeng", code="OTHER")
    _, machine, manual = seed_job(env, code="HX-RUN")
    target = ok(write(env, "/machines", {"code": "02", "machine_a": 12}))["record"]
    scheduled = ok(write(env, "/schedule/auto"))["changed_runs"]
    run = next(r for r in scheduled if r["status"] == "PLANNED")
    ok(write(env, f"/runs/{run['id']}/start"))
    instant = now()
    production_day = (
        (instant - timedelta(days=1)).date() if instant.hour < 8 else instant.date()
    )
    ok(
        write(
            env,
            "/shift-reports/current",
            method="put",
            run_id=run["id"],
            production_date=production_day.isoformat(),
            shift_code="DAY" if 8 <= instant.hour < 20 else "NIGHT",
            physical_shots=23,
            report_revision=0,
        )
    )
    ok(write(env, f"/runs/{run['id']}/pause", reason="转机"))
    destination = target if run["machine_id"] == machine["id"] else machine
    ok(
        write(
            env,
            f"/runs/{run['id']}/transfer",
            reason="转机",
            target_machine_id=destination["id"],
        )
    )
    with Session(env[1]) as db:
        fixed = {
            m.__tablename__: rows(db, m)
            for m in (MoldMaster, MoldAsset, CalendarEvent, SavedView)
        }
        other_before = {
            "machine": record(db.get(Machine, other_machine["id"])),
            "demand": record(db.get(Demand, other_demand["id"])),
            "settings": record(db.get(FactorySettings, "huadeng")),
        }
        specs = {
            m.id: {
                k: v
                for k, v in record(m).items()
                if k
                not in {
                    "operating_status",
                    "current_setup",
                    "revision",
                    "updated_at",
                    "updated_by",
                }
            }
            for m in db.scalars(select(Machine))
        }
    impact = preview(env)
    assert impact["counts"]["demands"] == 3 and impact["counts"]["manual_demands"] == 1
    assert impact["requires_execution_confirmation"]
    assert impact["counts"]["shift_reports"] == 1
    assert impact["counts"]["historical_outputs"] == 2
    assert clear(env, impact)[0].status_code == 409
    response, payload = clear(env, impact, include_execution=True)
    result = ok(response)
    assert result["cleared"] and result["counts"] == impact["counts"]
    with Session(env[1]) as db:
        for model, where in plan_clear.selections("huaxing"):
            assert not rows(db, model, where)
        assert not db.execute(text("PRAGMA foreign_key_check")).all()
        assert fixed == {
            m.__tablename__: rows(db, m)
            for m in (MoldMaster, MoldAsset, CalendarEvent, SavedView)
        }
        assert other_before == {
            "machine": record(db.get(Machine, other_machine["id"])),
            "demand": record(db.get(Demand, other_demand["id"])),
            "settings": record(db.get(FactorySettings, "huadeng")),
        }
        for m in db.scalars(select(Machine)):
            assert all(record(m)[k] == v for k, v in specs[m.id].items())
        op = db.scalar(select(Operation).where(Operation.kind == "plan.clear"))
        assert (
            op.actor_id == "test-operator" and op.result["reason"] == "误导入旧版计划"
        )
        assert manual["id"] in {r["id"] for r in op.before[Demand.__tablename__]}
        assert op.before[ImportBatch.__tablename__][0]["id"] == first["batch_id"]
        assert db.get(SharedRevision, "shared").revision == result["shared_revision"]
    assert not preview(env)["can_clear"]
    assert write(env, "/schedule/undo")[0].status_code == 409
    assert write(env, f"/imports/{first['batch_id']}/apply")[0].status_code == 404
    again = ok(upload(env, content))
    assert again["batch_id"] != first["batch_id"]
    assert again["summary"]["creates"] == 2
    reapplied = ok(write(env, f"/imports/{again['batch_id']}/apply"))
    assert reapplied["summary"]["applied_count"] == 2
    # A lost-response retry must return the first receipt, never clear the new import.
    assert ok(env[0].post(BASE + "/plan-data/clear", json=payload)) == result
    assert preview(env)["counts"]["demands"] == 2


def test_preview_is_read_only_and_rejects_scope_filters_and_invalid_factory(env):
    seed_job(env)
    before = all_state(env[1])
    assert preview(env)["counts"]["demands"] == 1
    assert all_state(env[1]) == before
    for extra in (
        {"filter": {"mold_code": "M-01"}},
        {"factory_id": "*"},
        {"cursor": 100},
    ):
        response = env[0].post(
            BASE + "/plan-data/clear-preview", json={"factory_id": "huaxing", **extra}
        )
        assert response.status_code == 422


def test_confirmation_stale_preview_and_tampered_token_cannot_delete(env):
    seed_job(env)
    impact = preview(env)
    before = all_state(env[1])
    for changes, status in [
        ({"confirmation": "清空华登计划数据"}, 422),
        ({"reason": "  "}, 422),
        ({"preview_token": "0" * 64}, 409),
    ]:
        assert clear(env, impact, **changes)[0].status_code == status
        assert all_state(env[1]) == before
    ok(write(env, "/demands", {"mold_code": "NEW", "planned_shots": 1}))
    before = all_state(env[1])
    assert clear(env, impact)[0].status_code == 409
    assert all_state(env[1]) == before
    fresh = preview(env)
    # Fingerprints also detect source changes that did not advance a revision.
    with Session(env[1]) as db:
        row = db.scalar(select(Demand))
        row.planned_shots = 9000
        db.commit()
    before = all_state(env[1])
    assert clear(env, fresh)[0].status_code == 409
    assert all_state(env[1]) == before


def test_permissions_are_rechecked_for_both_factory_and_execution(env):
    seed_job(env)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    impact = preview(env)
    before = all_state(env[1])
    env[2].permissions.remove("report")
    assert clear(env, impact, include_execution=True)[0].status_code == 403
    assert clear(env, impact)[0].status_code == 409
    env[2].permissions.remove("plan")
    assert (
        env[0]
        .post(BASE + "/plan-data/clear-preview", json={"factory_id": "huaxing"})
        .status_code
        == 403
    )
    denied, payload = clear(env, impact)
    assert denied.status_code == 403
    env[2].permissions.update({"plan", "report"})
    env[2].factories.remove("huaxing")
    assert (
        env[0]
        .post(BASE + "/plan-data/clear", json={**payload, "include_execution": True})
        .status_code
        == 403
    )
    assert all_state(env[1]) == before


def test_failed_audit_rolls_back_every_deletion_and_revision(env, monkeypatch):
    apply_legacy(env, legacy_book())
    impact = preview(env)
    before = all_state(env[1])

    def fail(*args, **kwargs):
        raise HTTPException(503, "audit unavailable")

    monkeypatch.setattr(api, "finish_write", fail)
    assert clear(env, impact)[0].status_code == 503
    assert all_state(env[1]) == before


def test_empty_plan_and_preview_only_import_cleanup(env):
    assert not preview(env)["can_clear"]
    assert clear(env)[0].status_code == 409
    batch = ok(upload(env, legacy_book()))
    impact = preview(env)
    assert impact["counts"]["demands"] == 0 and impact["counts"]["import_batches"] == 1
    assert ok(clear(env, impact))["cleared"]
    assert ok(upload(env, legacy_book()))["batch_id"] != batch["batch_id"]


def test_clear_preserves_fault_and_maintenance_and_resets_running_machine(env):
    _, machine, _ = seed_job(env)
    with Session(env[1]) as db:
        m = db.get(Machine, machine["id"])
        m.operating_status = "MAINTENANCE"
        m.recovery_at = now() + timedelta(days=2)
        m.current_setup = {"mold_code": "last-used"}
        before = record(m)
        db.commit()
    ok(clear(env))
    with Session(env[1]) as db:
        assert record(db.get(Machine, machine["id"])) == before


def test_deletion_statements_compile_for_postgres():
    from sqlalchemy import delete

    for model, where in plan_clear.selections("huaxing"):
        sql = str(delete(model).where(where).compile(dialect=postgresql.dialect()))
        assert "DELETE FROM injection_v3_" in sql and "factory_id" in sql


def test_real_iam_cookie_scope_and_separate_report_permission(iam_env):
    client, _ = iam_env
    assert (
        client.post(
            BASE + "/plan-data/clear-preview", json={"factory_id": "huaxing"}
        ).status_code
        == 401
    )
    identity = account(
        iam_env, permissions={"injection_scheduling:read", "injection_scheduling:plan"}
    )
    login(iam_env, identity)
    local = (client, iam_env[1], None)
    ok(write(local, "/demands", {"mold_code": "CLEAR-IAM", "planned_shots": 5}))
    impact = preview(local)
    assert (
        client.post(
            BASE + "/plan-data/clear-preview", json={"factory_id": "huadeng"}
        ).status_code
        == 403
    )
    assert clear(local, impact, include_execution=True)[0].status_code == 403
    assert ok(clear(local, impact))["cleared"]
