import io
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

import pytest
from app.models.injection_scheduling import Demand, Run
from app.services.injection_scheduling.calculations import TZ
from app.services.injection_scheduling.huaxing_template import (
    HEADERS,
    TEMPLATE_PATH,
    VERSION,
)
from app.services.injection_scheduling.import_plan import parse_plan
from app.services.injection_scheduling.sparse_xlsx import read_sheet
from app.services.injection_scheduling.template_download import NS, fill_template
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_injection_v3_api import BASE, ok, seed_job, write
from test_injection_v3_api import env as _env_fixture
from test_injection_v3_import_export import upload
from test_injection_v3_unified_template import counts

env = _env_fixture


def book(edits=None, factory="huaxing", source=None):
    edits = {"F2": factory, "I2": 46275 + 8 / 24, "A4": "01", **(edits or {})}
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source or TEMPLATE_PATH.read_bytes())) as z,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for name in z.namelist():
            content = z.read(name)
            if name == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(content)
                data = root.find(f"{{{NS}}}sheetData")
                for address, value in edits.items():
                    n = "".join(filter(str.isdigit, address))
                    row = data.find(f'{{{NS}}}row[@r="{n}"]')
                    if row is None:
                        row = ET.SubElement(data, f"{{{NS}}}row", r=n)
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


def task(row=5, order="BJB-001", **fields):
    values = {
        "G": "M-01",
        "I": order,
        "J": "ITEM-01",
        "L": 2400,
        "M": 400,
        "Q": "白色",
        "S": "PP",
        **fields,
    }
    return {f"{col}{row}": value for col, value in values.items()}


@pytest.mark.parametrize("factory", ["huaxing", "huadeng", "huakang-a", "huakang-b"])
def test_huaxing_layout_four_factory_import_infers_groups_and_order(env, factory):
    seed_job(env, factory=factory)
    before = counts(env)
    content = book(
        {**task(5, "SECOND"), **task(7, "FIRST"), **task(23, "PENDING")}, factory
    )
    parsed = parse_plan(content)
    assert [d["fields"]["queue_order"] for d in parsed["demands"]] == [1, 2, None]
    assert [d["source_row"] for d in parsed["demands"]] == [5, 7, 23]
    assert all(not d["issues"] for d in parsed["demands"])
    preview = ok(upload(env, content, factory=factory))
    assert preview["summary"]["assigned_count"] == 2
    assert counts(env) == before
    ok(write(env, f"/imports/{preview['batch_id']}/apply", factory=factory))
    with Session(env[1]) as db:
        demands = {
            d.order_no: d
            for d in db.scalars(
                select(Demand).where(Demand.source_system == "UNIFIED_PLAN")
            )
        }
        runs = list(db.scalars(select(Run).order_by(Run.sequence)))
        assert [r.id for r in runs] == [
            demands["SECOND"].extras["active_run_id"],
            demands["FIRST"].extras["active_run_id"],
        ]
        assert demands["PENDING"].machine_code is None
        assert all(
            d.completed_shots == 400 and d.remaining_shots == 2000
            for d in demands.values()
        )
        assert all(r.status == "PLANNED" and r.physical_shots == 0 for r in runs)
    assert counts(env)[1:4] == before[1:4]


def test_row_movement_retains_identity_and_reorders_without_duplicates(env):
    seed_job(env)
    first = ok(upload(env, book({**task(5, "ONE"), **task(6, "TWO")})))
    ok(write(env, f"/imports/{first['batch_id']}/apply"))
    before = counts(env)
    second = ok(upload(env, book({**task(5, "TWO"), **task(8, "ONE", L=3000)})))
    ok(write(env, f"/imports/{second['batch_id']}/apply"))
    assert counts(env)[:4] == before[:4]
    with Session(env[1]) as db:
        demands = list(
            db.scalars(select(Demand).where(Demand.source_system == "UNIFIED_PLAN"))
        )
        assert len(demands) == 2
        assert next(d for d in demands if d.order_no == "ONE").remaining_shots == 2600


@pytest.mark.parametrize(
    "edits, message",
    [
        ({"AY1": "RR_INJECTION_HUAXING_V3"}, "版本"),
        ({"AY1": None}, "标识"),
        ({"G3": "其他"}, "表头"),
        ({"F2": "未知厂"}, "F2"),
        ({"I2": "明天"}, "I2"),
    ],
)
def test_invalid_shape_and_metadata_are_not_legacy_fallback(edits, message):
    with pytest.raises(ValueError, match=message):
        parse_plan(book({**task(), **edits}))


@pytest.mark.parametrize(
    "edits, message",
    [
        ({"A4": "填写机号"}, "机号"),
        ({"B5": "02"}, "不一致"),
        ({"F5": "错误规格"}, "机型"),
        ({"L5": -1}, "非负"),
        ({"AW5": -1}, "非负"),
        ({"M5": None}, "已啤数"),
        ({**task(6)}, "相同"),
    ],
)
def test_invalid_selected_rows_abort_atomically(env, edits, message):
    seed_job(env)
    before = counts(env)
    preview = ok(upload(env, book({**task(), **edits})))
    response, _ = write(env, f"/imports/{preview['batch_id']}/apply")
    assert response.status_code == 422
    assert message in response.text
    assert counts(env) == before


def test_factory_download_expands_machine_bands_keeps_native_layout_and_no_orders(env):
    seed_job(env)
    for i in range(2, 6):
        ok(
            write(
                env,
                "/machines",
                {"code": f"{i:02}", "machine_a": 12, "machine_family": "HORIZONTAL"},
            )
        )
    response = env[0].get(
        BASE + "/templates/plan", params={"factory_id": "huaxing", "task_rows": 5}
    )
    assert response.status_code == 200
    source = read_sheet(response.content, "计划表")
    assert source["rows"][1]["AY"]["cached_value"] == VERSION
    assert [source["rows"][r]["A"]["cached_value"] for r in (4, 10, 16, 22, 28)] == [
        "01",
        "02",
        "03",
        "04",
        "05",
    ]
    assert source["rows"][34]["A"]["cached_value"] == "待排区"
    assert source["rows"][4]["DZ"]["cached_value"] == "M-01"
    assert (
        source["rows"][29]["M"]["formula_expanded"]
        == 'IF(G29="","",SUM(AW29:AX29,BA29:DJ29))'
    )
    assert source["rows"][29]["O"]["formula_expanded"].endswith(
        "VLOOKUP($G29,$DZ$4:$EL$4,4,FALSE))))"
    )
    with pytest.raises(ValueError, match="没有需求"):
        parse_plan(response.content)
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        cols = list(xml.find(f"{{{NS}}}cols"))
        assert next(c for c in cols if c.get("min") == "2").get("hidden") == "1"
        assert next(c for c in cols if c.get("min") == "130").get("hidden") == "1"
        assert (
            len(ET.fromstring(z.read("xl/workbook.xml")).find(f"{{{NS}}}sheets")) == 1
        )
        pane = xml.find(f"{{{NS}}}sheetViews/{{{NS}}}sheetView/{{{NS}}}pane")
        assert pane.get("xSplit") == "19" and pane.get("ySplit") == "3"


def test_dictionary_is_evidence_only_not_order_or_master_import(env):
    seed_job(env)
    content = book(
        task(),
        source=fill_template(
            {
                "factory": "华兴",
                "as_of": datetime(2026, 9, 10, 8, tzinfo=TZ),
                "machines": [],
                "molds": [["NOT-A-NEW-MASTER", "参考名称", "12A", 2400]],
                "lead_days": 3,
                "allowance_rate": 0.01,
            }
        ),
    )
    before = counts(env)
    preview = ok(upload(env, content))
    ok(write(env, f"/imports/{preview['batch_id']}/apply"))
    assert counts(env)[1:4] == before[1:4]
    assert counts(env)[0] == before[0] + 1


def test_original_business_headers_are_unchanged():
    source = read_sheet(TEMPLATE_PATH.read_bytes(), "计划表")
    from app.services.injection_scheduling.field_registry import column_name

    assert [
        source["rows"][3].get(column_name(i), {}).get("cached_value")
        for i in range(1, 51)
    ] == HEADERS


def test_duplicate_machine_bands_cannot_restart_the_same_machine_queue():
    with pytest.raises(ValueError, match="机台分组重复"):
        parse_plan(book({**task(), "A10": "01"}))


def test_machine_without_a_but_with_tonnage_is_not_mistaken_for_an_order():
    parsed = parse_plan(book({**task(), "G4": "320T"}))
    assert len(parsed["demands"]) == 1
    assert parsed["demands"][0]["fields"]["machine_code"] == "01"
