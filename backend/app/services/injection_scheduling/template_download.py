"""Populate only the authored template's factory/master input cells.

The original hidden columns are native XLSX metadata; there is no second sheet.
"""

import io
import re
import zipfile
from copy import deepcopy
from datetime import datetime
from xml.etree import ElementTree as ET

from openpyxl.formula.translate import Translator
from sqlalchemy import select

from app.models.injection_scheduling import FactorySettings, Machine, MoldMaster

from .calculations import TZ
from .field_registry import FACTORIES, column_name
from .huaxing_template import (
    BLOCK_SIZE,
    FIRST_MACHINE_ROW,
    LAST_ROW,
    LOOKUP_FIRST_COLUMN,
    LOOKUP_LIMIT,
    MACHINE_SLOTS,
    PENDING_ROW,
    TEMPLATE_PATH,
)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def template_data(db, factory):
    machines = list(db.scalars(select(Machine).where(Machine.factory_id == factory)))
    machines.sort(
        key=lambda m: (
            {"旧车间": 0, "老车间": 0, "新车间": 1}.get(m.workshop, 2),
            m.workshop,
            re.sub(r"\d+$", "", m.code),
            int(re.search(r"\d+$", m.code).group())
            if re.search(r"\d+$", m.code)
            else 0,
            m.code,
        )
    )
    if len(machines) > 500:
        raise ValueError("本厂设备超过 500 台，请按车间分批制作模板")
    settings = db.get(FactorySettings, factory).parameters
    masters = list(db.scalars(select(MoldMaster).order_by(MoldMaster.mold_code)))
    if len(masters) > LOOKUP_LIMIT:
        raise ValueError("公共模具资料超过模板查找容量，请扩充模板后下载")
    reference = settings.get("changeover_reference", {})
    molds = []
    for master in masters:
        default = master.defaults or {}
        a = (
            format(master.required_machine_a, "f").rstrip("0").rstrip(".")
            if master.required_machine_a is not None
            else None
        )
        # Decimal 50.000 -> 50; never stringify a numeric zero as missing.
        raw = master.requirement_raw or (f"{a}A" if a else "")
        change = reference.get(a, [0, 0])
        molds.append(
            [
                master.mold_code,
                master.part_name,
                raw,
                default.get("target_shots_per_day"),
                default.get("net_weight_g"),
                default.get("gross_weight_g"),
                default.get("price_per_shot"),
                default.get("manipulator_requirement"),
                default.get("fixture_requirement"),
                default.get("automation_requirement"),
                float(change[0]) / 1440,
                float(change[1]) / 1440,
                float(master.required_machine_a)
                if master.required_machine_a is not None
                else None,
            ]
        )
    return {
        "factory": FACTORIES[factory],
        "as_of": datetime.now(TZ).replace(hour=8, minute=0, second=0, microsecond=0),
        "machines": [
            {
                "code": m.code,
                "workshop": m.workshop,
                "status": {
                    "FAULT": "故障",
                    "DISABLED": "停用",
                    "MAINTENANCE": "检修",
                    "IDLE": "可用",
                }.get(m.operating_status, m.operating_status),
                "notes": m.notes,
                "spec": " ".join(
                    f"{float(v):g}{unit}"
                    for v, unit in ((m.machine_a, "A"), (m.clamp_ton, "T"))
                    if v is not None
                ),
                "type": {"VERTICAL": "立式", "TWO_COLOR": "双色"}.get(
                    m.machine_family,
                    {"HIGH_SPEED": "高速", "ELECTRIC": "全电"}.get(
                        m.speed_class, "普通"
                    ),
                ),
                "manipulator": m.manipulator,
            }
            for m in machines
        ],
        "molds": molds,
        "lead_days": settings.get("downstream_lead_days", 3),
        "allowance_rate": settings.get("allowance_rate", 0.01),
    }


def fill_template(data, content=None, task_rows=5):
    if task_rows not in (5, 10, 20):
        raise ValueError("每台预留任务行只能选择 5、10 或 20 行")
    content = content or TEMPLATE_PATH.read_bytes()
    target = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as archive,
        zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out,
    ):
        for name in archive.namelist():
            value = archive.read(name)
            if name == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(value)
                sheet = root.find(f"{{{NS}}}sheetData")
                rows = {int(r.get("r")): r for r in sheet}
                count = len(data["machines"]) or MACHINE_SLOTS
                block_size = task_rows + 1
                delta = count * block_size - BLOCK_SIZE * MACHINE_SLOTS

                def shifted(row, offset):
                    clone = deepcopy(row)
                    clone.set("r", str(int(row.get("r")) + offset))
                    for cell in clone:
                        old = cell.get("r")
                        address = re.sub(
                            r"\d+",
                            str(int(re.search(r"\d+", old).group()) + offset),
                            old,
                        )
                        cell.set("r", address)
                        formula = cell.find(f"{{{NS}}}f")
                        if formula is not None and formula.text:
                            formula.text = Translator(
                                "=" + formula.text, origin=old
                            ).translate_formula(address)[1:]
                    return clone

                original_rows = rows
                rows = {n: r for n, r in original_rows.items() if n < FIRST_MACHINE_ROW}
                for i in range(count):
                    for j in range(block_size):
                        n = FIRST_MACHINE_ROW + i * block_size + j
                        prototype = FIRST_MACHINE_ROW + bool(j)
                        rows[n] = shifted(original_rows[prototype], n - prototype)
                for n, row in original_rows.items():
                    if n >= PENDING_ROW:
                        rows[n + delta] = shifted(row, delta)
                merges = root.find(f"{{{NS}}}mergeCells")
                original_merges = list(merges)
                merges[:] = [
                    m
                    for m in original_merges
                    if int(re.search(r"\d+", m.get("ref")).group()) < FIRST_MACHINE_ROW
                ]
                for merge in original_merges:
                    address = merge.get("ref")
                    if int(re.search(r"\d+", address).group()) >= PENDING_ROW:
                        ET.SubElement(
                            merges,
                            f"{{{NS}}}mergeCell",
                            ref=re.sub(
                                r"\d+",
                                lambda m, delta=delta: str(int(m.group()) + delta),
                                address,
                            ),
                        )
                merges.set("count", str(len(merges)))

                def put(address, payload, rows=rows):
                    number = int(re.search(r"\d+", address).group())
                    if number not in rows:
                        rows[number] = ET.Element(f"{{{NS}}}row", r=str(number))
                    row = rows[number]
                    cell = row.find(f'{{{NS}}}c[@r="{address}"]')
                    if cell is None:
                        cell = ET.SubElement(row, f"{{{NS}}}c", r=address)
                    for child in list(cell):
                        cell.remove(child)
                    cell.attrib.pop("t", None)
                    if payload is None:
                        return
                    if isinstance(payload, (int, float)):
                        ET.SubElement(cell, f"{{{NS}}}v").text = str(payload)
                    else:
                        cell.set("t", "inlineStr")
                        ET.SubElement(
                            ET.SubElement(cell, f"{{{NS}}}is"), f"{{{NS}}}t"
                        ).text = str(payload)

                put("F2", data["factory"])
                put("EN1", data["factory"])
                put("A1", f"{data['factory']}厂啤机排产日计划表")
                origin = data["as_of"]
                put(
                    "I2",
                    (
                        origin.astimezone(TZ) - datetime(1899, 12, 30, tzinfo=TZ)
                    ).total_seconds()
                    / 86400,
                )
                put("EM1", data["lead_days"])
                put("EM2", data["allowance_rate"])
                rows[2].find(
                    f'{{{NS}}}c[@r="H2"]/{{{NS}}}f'
                ).text = f"SUM(N4:N{LAST_ROW + delta})"
                for i in range(count):
                    r = FIRST_MACHINE_ROW + i * block_size
                    machine = data["machines"][i] if i < len(data["machines"]) else None
                    for j in range(block_size):
                        rows[r + j].attrib.pop("hidden", None)
                    if machine:
                        put(f"A{r}", machine["code"])
                        put(f"EN{i + 4}", machine["code"])
                        put(f"EO{i + 4}", "M:" + machine["code"])
                        for col, key in enumerate(
                            (
                                "spec",
                                "type",
                                "manipulator",
                                "workshop",
                                "status",
                                "notes",
                            ),
                            146,
                        ):
                            put(f"{column_name(col)}{i + 4}", machine.get(key, ""))
                validations = root.find(f"{{{NS}}}dataValidations")
                if validations is not None:
                    # Populate authored validation controls with this factory's register.
                    machine_validation = next(
                        (deepcopy(v) for v in validations if v.get("sqref") == "A4"),
                        None,
                    )
                    validations[:] = [v for v in validations if v.get("sqref") == "F2"]
                    for v in validations:
                        v.find(f"{{{NS}}}formula1").text = '"' + data["factory"] + '"'
                    if machine_validation is not None:
                        machine_validation.set(
                            "sqref",
                            " ".join(f"A{4 + i * block_size}" for i in range(count)),
                        )
                        machine_validation.find(
                            f"{{{NS}}}formula1"
                        ).text = f"$EN$4:$EN${3 + max(1, len(data['machines']))}"
                        validations.append(machine_validation)
                    validations.set("count", str(len(validations)))
                for r, mold in enumerate(data["molds"], 4):
                    for c, field in enumerate(mold, LOOKUP_FIRST_COLUMN):
                        put(f"{column_name(c)}{r}", field)
                from .sparse_xlsx import column_number

                for row in rows.values():
                    for formula in row.iter(f"{{{NS}}}f"):
                        formula.text = re.sub(
                            r"(\$(?:DZ|E[A-L])\$4:\$(?:DZ|E[A-L])\$)4\b",
                            lambda m: m.group(1) + str(3 + max(1, len(data["molds"]))),
                            formula.text or "",
                        )
                        formula.text = re.sub(
                            r"(\$EO\$4:\$(?:EO|EU)\$)4\b",
                            lambda m: (
                                m.group(1) + str(3 + max(1, len(data["machines"])))
                            ),
                            formula.text or "",
                        )
                    row[:] = sorted(
                        row,
                        key=lambda cell: column_number(
                            re.sub(r"\d+", "", cell.get("r"))
                        ),
                    )
                sheet[:] = [rows[n] for n in sorted(rows)]
                hidden = {
                    2,
                    3,
                    4,
                    16,
                    21,
                    *range(23, 44),
                    46,
                    47,
                    48,
                    51,
                    52,
                    *range(130, 152),
                }
                columns = root.find(f"{{{NS}}}cols")
                existing = list(columns)
                columns[:] = []
                for item in existing:
                    for n in range(int(item.get("min")), int(item.get("max")) + 1):
                        attrs = {**item.attrib, "min": str(n), "max": str(n)}
                        if n in hidden:
                            attrs.update(hidden="1", width="10", outlineLevel="1")
                        columns.append(ET.Element(f"{{{NS}}}col", attrs))
                dimension = root.find(f"{{{NS}}}dimension")
                if dimension is not None:
                    dimension.set("ref", f"A1:EU{max(rows)}")
                value = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif name == "xl/workbook.xml":
                root = ET.fromstring(value)
                calc = root.find(f"{{{NS}}}calcPr")
                if calc is None:
                    calc = ET.SubElement(root, f"{{{NS}}}calcPr")
                calc.set("fullCalcOnLoad", "1")
                calc.set("forceFullCalc", "1")
                calc.set("calcMode", "auto")
                value = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            out.writestr(name, value)
    return target.getvalue()


def download_template(db, factory, task_rows=10):
    data = template_data(db, factory)
    if not data["machines"]:
        raise ValueError(
            "本厂还没有设备档案，请先在基础资料维护本厂设备，再下载统一模板"
        )
    return fill_template(data, task_rows=task_rows)
