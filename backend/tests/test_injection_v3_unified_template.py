import io
import zipfile
from xml.etree import ElementTree as ET

import pytest
from app.models.injection_scheduling import (
    Demand,
    ImportBatch,
    Machine,
    MoldAsset,
    MoldMaster,
    Run,
)
from app.services.injection_scheduling.unified_plan import CONTRACT, TEMPLATE_PATH
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_injection_v3_api import BASE, ok, seed_job, write
from test_injection_v3_api import env as _env_fixture
from test_injection_v3_import_export import upload

env = _env_fixture
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def workbook(rows=(), factory="huaxing", overrides=None):
    """Test-only XML input mutations. The downloadable artifact remains untouched."""
    source = TEMPLATE_PATH.read_bytes()
    edits = {"B3": factory, "E3": 46275 + 8 / 24}
    keys = {key: index for index, (key, _, _) in enumerate(CONTRACT["columns"], 1)}
    from app.services.injection_scheduling.field_registry import column_name

    for n, data in enumerate(rows, 7):
        edits.update(
            {f"{column_name(keys[key])}{n}": value for key, value in data.items()}
        )
    edits.update(overrides or {})
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as archive,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for name in archive.namelist():
            content = archive.read(name)
            if name == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(content)
                sheet_data = root.find(f"{{{NS}}}sheetData")
                for address, value in edits.items():
                    row_no = "".join(filter(str.isdigit, address))
                    row = sheet_data.find(f'{{{NS}}}row[@r="{row_no}"]')
                    if row is None:
                        row = ET.SubElement(sheet_data, f"{{{NS}}}row", r=row_no)
                    cell = row.find(f'{{{NS}}}c[@r="{address}"]')
                    if cell is not None:
                        row.remove(cell)
                    if value is None:
                        continue
                    cell = ET.SubElement(row, f"{{{NS}}}c", r=address)
                    if isinstance(value, (int, float)):
                        ET.SubElement(cell, f"{{{NS}}}v").text = str(value)
                    else:
                        cell.set("t", "inlineStr")
                        ET.SubElement(
                            ET.SubElement(cell, f"{{{NS}}}is"), f"{{{NS}}}t"
                        ).text = value
                content = ET.tostring(root)
            target.writestr(name, content)
    return out.getvalue()


def row(identity="PLAN-001", **changes):
    return dict(
        source_line_id=identity,
        machine_code="01",
        queue_order=1,
        mold_code="M-01",
        order_no=identity,
        planned_shots=2400,
        completed_shots=400,
        target_shots_per_day=2400,
        color_name="白色",
        material_raw="PP",
        **changes,
    )


def counts(env):
    with Session(env[1]) as db:
        return [
            db.scalar(select(func.count()).select_from(model))
            for model in (Demand, Machine, MoldMaster, MoldAsset, Run)
        ]


def apply(env, content, factory="huaxing"):
    preview = ok(upload(env, content, factory=factory))
    return write(env, f"/imports/{preview['batch_id']}/apply", factory=factory)


@pytest.mark.parametrize("factory", ["huaxing", "huadeng", "huakang-a", "huakang-b"])
def test_four_factories_same_template_preserves_machine_order_and_opening(env, factory):
    _, machine, _ = seed_job(env, factory=factory)
    before = counts(env)
    rows = [row("SECOND"), row("FIRST"), row("PENDING")]
    rows[0]["queue_order"] = 2
    rows[2].update(machine_code="", queue_order=None)
    content = workbook(rows, factory)
    preview = ok(upload(env, content, factory=factory))
    assert preview["summary"]["assigned_count"] == 2
    assert preview["summary"]["conflicts"] == []
    assert counts(env) == before  # preview does not create business/master records
    result = ok(write(env, f"/imports/{preview['batch_id']}/apply", factory=factory))
    assert result["summary"]["applied_count"] == 3
    assert counts(env)[1:4] == before[1:4]
    with Session(env[1]) as db:
        demands = {
            d.source_line_id: d
            for d in db.scalars(
                select(Demand).where(Demand.source_system == "UNIFIED_PLAN")
            )
        }
        assert all(
            d.completed_shots == 400 and d.remaining_shots == 2000
            for d in demands.values()
        )
        assert demands["PENDING"].machine_code is None
        runs = list(db.scalars(select(Run).order_by(Run.sequence)))
        assert [run.id for run in runs] == [
            demands["FIRST"].extras["active_run_id"],
            demands["SECOND"].extras["active_run_id"],
        ]
        assert all(
            run.machine_id == machine["id"]
            and run.status == "PLANNED"
            and run.actual_start_at is None
            and run.physical_shots == 0
            for run in runs
        )
        assert runs[0].planned_end_at <= runs[1].planned_start_at
    repeated = ok(apply(env, content, factory))
    assert repeated["already_applied"]
    assert counts(env)[0] == before[0] + 3


def test_template_download_is_authorized_and_blank_is_not_importable(env):
    assert (
        env[0]
        .get(BASE + "/templates/plan", params={"factory_id": "huaxing"})
        .status_code
        == 422
    )
    ok(write(env, "/machines", {"code": "01", "machine_a": 12}))
    response = env[0].get(BASE + "/templates/plan", params={"factory_id": "huaxing"})
    from app.services.injection_scheduling.huaxing_template import VERSION
    from app.services.injection_scheduling.sparse_xlsx import read_sheet

    downloaded = read_sheet(response.content, "计划表")
    assert downloaded["rows"][1]["AY"]["cached_value"] == VERSION
    assert downloaded["rows"][2]["F"]["cached_value"] == "华兴"
    assert "spreadsheetml" in response.headers["content-type"]
    assert upload(env, workbook()).status_code == 422
    env[2].permissions.remove("plan")
    assert (
        env[0]
        .get(BASE + "/templates/plan", params={"factory_id": "huaxing"})
        .status_code
        == 403
    )


@pytest.mark.parametrize(
    "edit, message",
    [
        ({"B3": "huadeng"}, "厂区"),
        ({"A2": "RR_INJECTION_UNIFIED_V2"}, "版本"),
        ({"C6": "其它字段"}, "表头"),
        ({"E3": "无效日期"}, "排期起点"),
    ],
)
def test_wrong_contract_or_factory_rejected(env, edit, message):
    response = upload(env, workbook([row()], overrides=edit))
    assert response.status_code == 422 and message in response.text


@pytest.mark.parametrize(
    "edit, message",
    [
        ({"B7": "不存在"}, "本厂设备"),
        ({"C7": 0}, "机内顺序"),
        ({"J7": None}, "已啤数"),
        ({"I7": -1}, "非负"),
        ({"D7": "未知模号"}, "公共模具"),
        ({"Q7": 120}, "机安小于"),
        ({"L7": 0}, "大于 0"),
        ({"B7": None}, "同时留空"),
        ({"X7": "无效日期"}, "有效日期"),
    ],
)
def test_invalid_rows_block_atomic_apply_without_master_creation(env, edit, message):
    seed_job(env)
    before = counts(env)
    preview = ok(upload(env, workbook([row()], overrides=edit)))
    assert any(message in issue["message"] for issue in preview["rows"][0]["issues"])
    response, _ = write(env, f"/imports/{preview['batch_id']}/apply")
    assert response.status_code == 422
    assert counts(env) == before
    with Session(env[1]) as db:
        assert db.get(ImportBatch, preview["batch_id"]).status == "PREVIEW"


def test_duplicate_id_and_position_reported_and_explicit_skip(env):
    seed_job(env)
    content = workbook([row(), row()])
    preview = ok(upload(env, content))
    messages = [issue["message"] for issue in preview["rows"][1]["issues"]]
    assert any("编号重复" in text for text in messages)
    assert any("顺序" in text for text in messages)
    result = ok(write(env, f"/imports/{preview['batch_id']}/apply", skip_rows=[8]))
    assert result["summary"]["applied_count"] == 1


def test_repeat_edit_reorders_unstarted_queue_and_detects_server_changes(env):
    seed_job(env)
    rows = [row("FIRST"), row("SECOND")]
    rows[1]["queue_order"] = 2
    ok(apply(env, workbook(rows)))
    rows[0]["queue_order"], rows[1]["queue_order"] = 2, 1
    rows[0]["planned_shots"] = 3000
    result = ok(apply(env, workbook(rows)))
    assert result["summary"]["applied_count"] == 2
    with Session(env[1]) as db:
        d = db.scalar(select(Demand).where(Demand.source_line_id == "FIRST"))
        assert d.remaining_shots == 2600
        first_id = d.id
        fingerprints = [
            (run.id, run.revision, run.planned_start_at)
            for run in db.scalars(select(Run))
        ]
    result = ok(apply(env, workbook(rows, overrides={"A1": "只改说明"})))
    assert result["summary"]["unchanged_count"] == 2 and result["changed_runs"] == []
    with Session(env[1]) as db:
        assert [
            (run.id, run.revision, run.planned_start_at)
            for run in db.scalars(select(Run))
        ] == fingerprints
        d = db.get(Demand, first_id)
        d.planned_shots = 4444
        db.commit()
    rows[0]["planned_shots"] = 4000
    response, _ = apply(env, workbook(rows))
    assert response.status_code == 409
    with Session(env[1]) as db:
        assert db.get(Demand, first_id).planned_shots == 4444


def test_production_records_survive_unchanged_and_block_old_excel_updates(env):
    seed_job(env)
    rows = [row()]
    result = ok(apply(env, workbook(rows)))
    run_id = result["changed_runs"][0]["id"]
    ok(write(env, f"/runs/{run_id}/start"))
    ok(apply(env, workbook(rows, overrides={"A1": "说明变更"})))
    rows[0]["completed_shots"] = 800
    response, _ = apply(env, workbook(rows))
    assert response.status_code == 409
    with Session(env[1]) as db:
        assert db.get(Run, run_id).status == "RUNNING"
        assert (
            db.scalar(
                select(Demand).where(Demand.source_line_id == "PLAN-001")
            ).opening_shots
            == 400
        )


def test_pending_unknown_mold_does_not_create_master_and_missing_zero_differ(env):
    content = workbook(
        [
            dict(
                row(),
                machine_code="",
                queue_order=None,
                mold_code="NEW-MOLD",
                target_shots_per_day=None,
                completed_shots=0,
            )
        ]
    )
    result = ok(apply(env, content))
    assert result["changed_runs"] == []
    assert counts(env) == [1, 0, 0, 0, 0]
    with Session(env[1]) as db:
        demand = db.scalar(select(Demand))
        assert demand.remaining_shots == 2400 and demand.target_shots_per_day is None


def test_apply_revalidates_equipment_after_preview(env):
    _, machine, _ = seed_job(env)
    preview = ok(upload(env, workbook([row()])))
    assert preview["summary"]["conflicts"] == []
    with Session(env[1]) as db:
        db.get(Machine, machine["id"]).operating_status = "FAULT"
        db.commit()
    before = counts(env)
    response, _ = write(env, f"/imports/{preview['batch_id']}/apply")
    assert response.status_code == 422 and "停机" in response.text
    assert counts(env) == before


def test_existing_queue_remains_ahead_and_release_time_is_respected(env):
    seed_job(env)
    original = ok(write(env, "/schedule/auto", scope={"mode": "UNSCHEDULED"}))[
        "changed_runs"
    ][0]
    content = workbook([dict(row(), earliest_available_at="2026-09-12T08:00:00+08:00")])
    result = ok(apply(env, content))
    queue = sorted(result["changed_runs"], key=lambda run: run["sequence"])
    assert queue[0]["id"] == original["id"]
    assert queue[1]["planned_start_at"] >= "2026-09-12T08:00:00"


def test_same_source_identifier_is_scoped_to_factory(env):
    rows = [dict(row(), machine_code="", queue_order=None)]
    ok(apply(env, workbook(rows, "huaxing"), "huaxing"))
    ok(apply(env, workbook(rows, "huadeng"), "huadeng"))
    with Session(env[1]) as db:
        assert {d.factory_id for d in db.scalars(select(Demand))} == {
            "huaxing",
            "huadeng",
        }
    assert counts(env)[0] == 2


def test_completed_source_row_does_not_block_new_jobs_on_later_import(env):
    seed_job(env)
    rows = [dict(row("DONE"), completed_shots=2400)]
    ok(apply(env, workbook(rows)))
    rows.append(dict(row("NEXT"), queue_order=2))
    result = ok(apply(env, workbook(rows)))
    assert result["summary"]["applied_count"] == 1
    assert len(result["changed_runs"]) == 1


def test_unified_template_does_not_duplicate_existing_legacy_or_manual_orders(env):
    _, _, existing = seed_job(env)
    preview = ok(
        upload(
            env,
            workbook(
                [
                    dict(
                        row(),
                        order_no="001",
                        delivery_due_at=existing["delivery_due_at"],
                    )
                ]
            ),
        )
    )
    assert any(
        "已有相同业务需求" in issue["message"] for issue in preview["rows"][0]["issues"]
    )
    response, _ = write(env, f"/imports/{preview['batch_id']}/apply")
    assert response.status_code == 422
    assert counts(env)[0] == 1


def test_material_restrictions_and_hold_notes_survive_mapping(env):
    _, machine, _ = seed_job(env)
    with Session(env[1]) as db:
        db.get(Machine, machine["id"]).restrictions = {"forbidden_resins": ["PP"]}
        db.commit()
    response, _ = apply(env, workbook([row()]))
    assert response.status_code == 422 and "树脂" in response.text
    response, _ = apply(
        env, workbook([dict(row(), material_raw="ABS", order_note="暂停")])
    )
    assert response.status_code == 422 and "暂停" in response.text
    ok(
        apply(
            env,
            workbook(
                [dict(row(), machine_code="", queue_order=None, order_note="待料")]
            ),
        )
    )
    with Session(env[1]) as db:
        demand = db.scalar(select(Demand).where(Demand.source_line_id == "PLAN-001"))
        assert demand.resin == "PP" and demand.dispatch_state == "WAIT_MATERIAL"
