import io
import os
import zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    FactorySettings,
    Machine,
    Run,
)
from app.services.injection_scheduling.import_plan import parse_plan
from app.services.injection_scheduling.machine_register import (
    apply_register,
    inspect_register,
)
from app.services.injection_scheduling.sparse_xlsx import read_sheet
from app.services.injection_scheduling.template_download import NS
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_injection_v3_api import BASE, ok, seed_job, write
from test_injection_v3_api import env as _env_fixture
from test_injection_v3_huaxing_template import book, task
from test_injection_v3_import_export import upload

env = _env_fixture


def test_erased_machine_band_does_not_inherit_the_previous_machine():
    parsed = parse_plan(book({**task(5, "FIRST"), **task(11, "SECOND"), "A10": None}))
    missing = parsed["demands"][1]
    assert not missing["fields"]["machine_code"]
    assert any(
        "机台分组尚未填写机号" in issue["message"] for issue in missing["issues"]
    )


@pytest.mark.parametrize(
    "factory,rows", [("huaxing", 5), ("huakang-a", 10), ("huakang-b", 20)]
)
def test_download_options_and_dynamic_group_queue(env, factory, rows):
    seed_job(env, factory=factory)
    content = (
        env[0]
        .get(
            BASE + "/templates/plan", params={"factory_id": factory, "task_rows": rows}
        )
        .content
    )
    source = read_sheet(content, "计划表")
    assert source["rows"][4]["A"]["cached_value"] == "01"
    assert source["rows"][4 + rows + 1]["A"]["cached_value"] == "待排区"
    # The last slot and gaps must remain in the first machine's queue.
    content = book(
        {
            **task(5, "FIRST"),
            **task(4 + rows, "LAST"),
            **task(5 + rows + 1, "PENDING"),
        },
        factory,
        content,
    )
    parsed = parse_plan(content)
    assert [r["fields"]["queue_order"] for r in parsed["demands"]] == [1, 2, None]
    preview = ok(upload(env, content, factory=factory))
    ok(write(env, f"/imports/{preview['batch_id']}/apply", factory=factory))
    with Session(env[1]) as db:
        runs = list(
            db.scalars(
                select(Run).where(Run.factory_id == factory).order_by(Run.sequence)
            )
        )
        assert len(runs) == 2 and all(r.status == "PLANNED" for r in runs)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        choices = xml.find(f"{{{NS}}}dataValidations")
        band = next(v for v in choices if v.get("sqref").startswith("A4"))
        assert band.find(f"{{{NS}}}formula1").text == "$EN$4:$EN$4"
        assert band.get("sqref").split() == ["A4"]


def test_factory_identity_cannot_be_changed_by_relabeling_f2(env):
    seed_job(env)
    content = (
        env[0].get(BASE + "/templates/plan", params={"factory_id": "huaxing"}).content
    )
    with pytest.raises(ValueError, match="所属厂区不一致"):
        parse_plan(book(task(), "huakang-b", content))


def test_rows_option_is_validated_and_empty_factory_does_not_create_fake_machines(env):
    assert (
        env[0]
        .get(BASE + "/templates/plan", params={"factory_id": "huakang-b"})
        .status_code
        == 422
    )
    seed_job(env)
    for number in (-1, 0, 11, 100000):
        assert (
            env[0]
            .get(
                BASE + "/templates/plan",
                params={"factory_id": "huaxing", "task_rows": number},
            )
            .status_code
            == 422
        )


def test_machine_codes_preserve_prefix_and_leading_zero_with_factory_isolation(env):
    master = ok(
        write(
            env,
            "/molds",
            {
                "mold_code": "M-01",
                "required_machine_a": 12,
                "defaults": {"target_shots_per_day": 2400},
            },
        )
    )["record"]
    bound = {}
    for factory in ("huakang-a", "huakang-b"):
        ok(
            write(
                env,
                "/mold-assets",
                {
                    "master_id": master["id"],
                    "asset_code": factory + "-mold",
                    "current_factory_id": factory,
                },
                factory,
            )
        )
        for code in ("1", "01", "B1"):
            bound[factory, code] = ok(
                write(env, "/machines", {"code": code, "machine_a": 12}, factory)
            )["record"]["id"]
        assert (
            write(env, "/machines", {"code": "b1", "machine_a": 12}, factory)[
                0
            ].status_code
            == 409
        )
        response = env[0].get(
            BASE + "/templates/plan", params={"factory_id": factory, "task_rows": 5}
        )
        source = read_sheet(response.content, "计划表")
        assert [source["rows"][r]["A"]["cached_value"] for r in (4, 10, 16)] == [
            "01",
            "1",
            "B1",
        ]
        content = book(task(17), factory, response.content)
        preview = ok(upload(env, content, factory=factory))
        ok(write(env, f"/imports/{preview['batch_id']}/apply", factory=factory))
    with Session(env[1]) as db:
        for run in db.scalars(select(Run)):
            assert run.machine_id == bound[run.factory_id, "B1"]
        assert db.scalar(select(func.count()).select_from(Machine)) == 6


@pytest.mark.parametrize(
    "profile,variable,count,conflict_rows,stops",
    [
        ("huakang-a-equipment-v1", "INJECTION_HUAKANG_A", 55, [51, 117], 5),
        ("huakang-b-equipment-v1", "INJECTION_HUAKANG_B", 96, [303, 304], 0),
    ],
)
def test_real_register_preview_and_atomic_add_preserves_plans(
    env, profile, variable, count, conflict_rows, stops
):
    path = os.environ.get(variable)
    if not path:
        pytest.skip("real source supplied through environment")
    report = inspect_register(Path(path).read_bytes(), profile)
    assert len(report["machines"]) == count
    assert [c["source_row"] for c in report["assignment_conflicts"]] == conflict_rows
    assert all(not m["data"]["capabilities"] for m in report["machines"])
    assert sum(m["operating_status"] != "IDLE" for m in report["machines"]) == stops
    seed_job(env)  # Existing Huaxing business rows must survive unchanged.
    with Session(env[1]) as db:
        factory = report["factory_id"]
        payload = {
            "factory_id": factory,
            "base_revision": db.get(FactorySettings, factory).revision,
            "client_operation_id": uuid4().hex,
            "source_sha256": report["sha256"],
        }
        result = apply_register(db, report, payload, "test")
        assert result["created_count"] == count
        assert apply_register(db, report, payload, "test")["created_count"] == count
        assert db.scalar(select(func.count()).select_from(Machine)) == count + 1
        assert db.scalar(select(func.count()).select_from(Demand)) == 1
        assert db.scalar(select(func.count()).select_from(CalendarEvent)) == stops
        item = db.scalar(
            select(Machine).where(Machine.factory_id == factory, Machine.code == "1")
        )
        assert item.machine_a == (7 if count == 55 else 60)
        if count == 96:
            b1 = db.scalar(
                select(Machine).where(
                    Machine.factory_id == factory, Machine.code == "B1"
                )
            )
            assert b1.machine_a == 80 and b1.clamp_ton == 600
            assert (
                db.scalar(
                    select(Machine).where(
                        Machine.factory_id == factory, Machine.code == "B14"
                    )
                ).clamp_ton
                is None
            )
        else:
            assert report["unassigned_source_rows"] == list(range(229, 242))
            assert db.scalar(
                select(Machine).where(
                    Machine.factory_id == factory, Machine.code == "37"
                )
            ).restrictions["forbidden_resins"] == ["PVC", "TPU"]


def test_register_conflict_rolls_back_instead_of_overwriting_existing_machine(env):
    seed_job(env)
    report = {
        "factory_id": "huaxing",
        "sha256": "source",
        "assignment_conflicts": [],
        "machines": [
            {
                "source_row": 4,
                "data": {"code": "NEW", "machine_a": 12},
                "evidence": {},
                "operating_status": "IDLE",
            },
            {
                "source_row": 5,
                "data": {"code": "01", "machine_a": 99},
                "evidence": {},
                "operating_status": "IDLE",
            },
        ],
    }
    with Session(env[1]) as db:
        payload = {
            "factory_id": "huaxing",
            "base_revision": db.get(FactorySettings, "huaxing").revision,
            "client_operation_id": uuid4().hex,
            "source_sha256": "source",
        }
        with pytest.raises(HTTPException):
            apply_register(db, report, payload, "test")
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Machine)) == 1
        assert db.scalar(select(Machine)).machine_a == 12
