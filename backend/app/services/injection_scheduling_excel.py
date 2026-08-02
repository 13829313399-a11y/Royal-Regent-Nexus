from __future__ import annotations

import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException
from lxml import etree

PARSER_VERSION = "injection-scheduling-phase4-v1"
PREVIEW_SCHEMA_VERSION = "phase4-import-v1"
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ZIP_ENTRY_BYTES = 64 * 1024 * 1024

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_REF_RE = re.compile(r"^([A-Z]+)([0-9]+)$")
DIMENSION_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*(?:MM)?\s*[×xX*]\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"[-+]?[0-9]+(?:\.[0-9]+)?")
ERROR_VALUES = {
    "#N/A",
    "#REF!",
    "#VALUE!",
    "#DIV/0!",
    "#NAME?",
    "#NUM!",
    "#NULL!",
}
BUILTIN_DATE_FORMAT_IDS = {
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    27,
    30,
    36,
    45,
    46,
    47,
    50,
    57,
}
TASK_COLUMNS = {
    "B": "machine_code",
    "D": "automation_mode",
    "E": "legacy_marker",
    "F": "legacy_machine_class_text",
    "G": "mold_no",
    "H": "product_name",
    "I": "order_no",
    "J": "item_no",
    "K": "set_quantity",
    "L": "order_quantity",
    "M": "completed_quantity",
    "O": "shift_target_quantity",
    "P": "sprue_ratio",
    "Q": "color_name",
    "R": "color_powder_code",
    "S": "material_name",
    "T": "whole_shot_net_weight_g",
    "U": "whole_shot_gross_weight_g",
    "Z": "order_date",
    "AA": "delivery_start_date",
    "AB": "delivery_due_date",
    "AG": "planned_start",
    "AH": "planned_finish",
    "AL": "requires_spray_paint",
    "AR": "warehouse_text",
    "AS": "remark",
    "AU": "required_arm_type",
    "AV": "required_fixture_type",
}
FORMULA_BLOCKING_FIELDS = {
    "machine_code",
    "mold_no",
    "order_no",
    "order_quantity",
    "completed_quantity",
    "planned_start",
    "planned_finish",
}


def _xml_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\u3000", " ").strip()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _issue(
    *,
    code: str,
    message: str,
    sheet_name: str,
    source_row: int | None = None,
    field_name: str = "",
    cell_ref: str = "",
    raw_value: str = "",
    formula_text: str = "",
    blocking: bool = False,
) -> dict[str, Any]:
    return {
        "severity": "ERROR" if blocking else "WARNING",
        "code": code,
        "message": message,
        "sheet_name": sheet_name,
        "source_row": source_row,
        "field_name": field_name,
        "cell_ref": cell_ref,
        "raw_value": raw_value[:1000],
        "formula_text": formula_text[:4000],
        "blocking": blocking,
    }


def _safe_decimal(value: Any) -> Decimal | None:
    text = _clean_text(value).replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        match = NUMBER_RE.search(text)
        if match is None:
            return None
        try:
            return Decimal(match.group(0))
        except InvalidOperation:
            return None


def _number(value: Any) -> float | None:
    parsed = _safe_decimal(value)
    return float(parsed) if parsed is not None else None


def _integer_text(value: Any) -> str:
    parsed = _safe_decimal(value)
    if parsed is None:
        return _clean_text(value)
    if parsed == parsed.to_integral_value():
        return str(int(parsed))
    return format(parsed.normalize(), "f")


def _excel_datetime(value: Any, *, date_1904: bool, date_only: bool) -> str:
    parsed = _safe_decimal(value)
    if parsed is None:
        return ""
    epoch = (
        datetime(1904, 1, 1)  # noqa: DTZ001 -- Excel serials are local wall time.
        if date_1904
        else datetime(1899, 12, 30)  # noqa: DTZ001
    )
    result = epoch + timedelta(days=float(parsed))
    return result.date().isoformat() if date_only else result.isoformat(timespec="seconds")


def _column_from_ref(reference: str) -> str:
    match = CELL_REF_RE.match(reference)
    return match.group(1) if match else ""


def _shared_text(element: etree._Element) -> str:
    return "".join(element.itertext())


class _WorkbookReader:
    def __init__(self, content: bytes):
        self.content = content
        self.archive = ZipFile(io.BytesIO(content))
        self._validate_zip()
        self.shared_strings = self._read_shared_strings()
        self.number_formats, self.cell_style_formats = self._read_styles()
        self.sheet_paths, self.date_1904 = self._read_workbook()

    def close(self) -> None:
        self.archive.close()

    def _validate_zip(self) -> None:
        entries = self.archive.infolist()
        total_size = sum(entry.file_size for entry in entries)
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise HTTPException(status_code=413, detail="Excel 解压后体积超过 250 MB 限制")
        if any(entry.file_size > MAX_ZIP_ENTRY_BYTES for entry in entries):
            raise HTTPException(status_code=413, detail="Excel 内部单个文件超过 64 MB 限制")
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required <= set(self.archive.namelist()):
            raise HTTPException(status_code=422, detail="文件不是有效的 Excel .xlsx 工作簿")

    def _read_shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self.archive.namelist():
            return []
        values: list[str] = []
        with self.archive.open("xl/sharedStrings.xml") as stream:
            for _, element in etree.iterparse(
                stream,
                events=("end",),
                tag=f"{{{MAIN_NS}}}si",
                resolve_entities=False,
                no_network=True,
                huge_tree=True,
            ):
                values.append(_shared_text(element))
                element.clear()
        return values

    def _read_styles(self) -> tuple[dict[int, str], list[int]]:
        if "xl/styles.xml" not in self.archive.namelist():
            return {}, []
        root = etree.fromstring(self.archive.read("xl/styles.xml"), parser=_xml_parser())
        formats = {
            int(item.get("numFmtId")): item.get("formatCode", "")
            for item in root.findall(f".//{{{MAIN_NS}}}numFmt")
        }
        cell_xfs = root.find(f"{{{MAIN_NS}}}cellXfs")
        style_formats = (
            [int(item.get("numFmtId", "0")) for item in cell_xfs]
            if cell_xfs is not None
            else []
        )
        return formats, style_formats

    def _read_workbook(self) -> tuple[dict[str, str], bool]:
        workbook = etree.fromstring(
            self.archive.read("xl/workbook.xml"), parser=_xml_parser()
        )
        rels = etree.fromstring(
            self.archive.read("xl/_rels/workbook.xml.rels"), parser=_xml_parser()
        )
        targets = {
            rel.get("Id"): rel.get("Target", "")
            for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship")
        }
        paths: dict[str, str] = {}
        for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
            relation_id = sheet.get(f"{{{DOC_REL_NS}}}id", "")
            target = targets.get(relation_id, "").lstrip("/")
            if target and not target.startswith("xl/"):
                target = "xl/" + target
            paths[sheet.get("name", "")] = target
        workbook_properties = workbook.find(f"{{{MAIN_NS}}}workbookPr")
        date_1904 = (
            workbook_properties is not None
            and workbook_properties.get("date1904", "0") in {"1", "true", "True"}
        )
        return paths, date_1904

    def _format_code(self, style_index: int | None) -> str:
        if style_index is None or style_index >= len(self.cell_style_formats):
            return ""
        num_fmt_id = self.cell_style_formats[style_index]
        return self.number_formats.get(num_fmt_id, "")

    def _display_numeric_identifier(self, raw_value: str, style_index: int | None) -> str:
        format_code = self._format_code(style_index)
        simple_code = re.sub(r'"[^"]*"|\\.', "", format_code).strip()
        if re.fullmatch(r"0+", simple_code):
            parsed = _safe_decimal(raw_value)
            if parsed is not None and parsed == parsed.to_integral_value():
                return str(int(parsed)).zfill(len(simple_code))
        return _integer_text(raw_value)

    def rows(self, sheet_name: str):
        path = self.sheet_paths.get(sheet_name)
        if not path or path not in self.archive.namelist():
            return
        with self.archive.open(path) as stream:
            for _, row in etree.iterparse(
                stream,
                events=("end",),
                tag=f"{{{MAIN_NS}}}row",
                resolve_entities=False,
                no_network=True,
                huge_tree=True,
            ):
                row_number = int(row.get("r", "0"))
                values: dict[str, dict[str, Any]] = {}
                for cell in row.findall(f"{{{MAIN_NS}}}c"):
                    reference = cell.get("r", "")
                    column = _column_from_ref(reference)
                    if not column:
                        continue
                    cell_type = cell.get("t", "n")
                    style_index = int(cell.get("s", "0")) if cell.get("s") else None
                    formula_node = cell.find(f"{{{MAIN_NS}}}f")
                    value_node = cell.find(f"{{{MAIN_NS}}}v")
                    inline_node = cell.find(f"{{{MAIN_NS}}}is")
                    raw_value = value_node.text if value_node is not None else None
                    if cell_type == "s" and raw_value is not None:
                        try:
                            value: Any = self.shared_strings[int(raw_value)]
                        except (ValueError, IndexError):
                            value = raw_value
                    elif cell_type == "inlineStr" and inline_node is not None:
                        value = _shared_text(inline_node)
                    else:
                        value = raw_value
                    values[column] = {
                        "reference": reference,
                        "type": cell_type,
                        "style_index": style_index,
                        "raw_value": raw_value,
                        "value": value,
                        "formula": formula_node.text if formula_node is not None else "",
                        "formula_cache_missing": (
                            formula_node is not None
                            and (value_node is None or value_node.text is None)
                        ),
                        "formula_error": (
                            formula_node is not None
                            and (cell_type == "e" or raw_value in ERROR_VALUES)
                        ),
                    }
                yield row_number, values
                row.clear()

    def identifier(self, cell: dict[str, Any] | None) -> str:
        if not cell:
            return ""
        value = cell.get("value")
        if value is None:
            return ""
        if cell.get("type") in {"s", "str", "inlineStr"}:
            return _clean_text(value)
        return _clean_text(
            self._display_numeric_identifier(
                _clean_text(value), cell.get("style_index")
            )
        )


def _machine_code(area: str, position: str) -> str:
    area_text = _clean_text(area)
    position_text = _integer_text(position)
    if "老" in area_text:
        return f"旧{position_text}"
    if "新" in area_text:
        return f"新{position_text}"
    return f"{area_text}{position_text}".strip()


def _machine_class(value: str) -> str:
    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?A)",
        _clean_text(value),
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else _clean_text(value)[:64]


def _robot_capabilities(value: str) -> list[str]:
    text = _clean_text(value)
    if not text or text in {"无", "没有"}:
        return []
    if "双" in text:
        return ["single", "dual"]
    if "单" in text:
        return ["single"]
    return [text[:64]]


def _arm_type(value: str) -> str:
    text = _clean_text(value)
    if "双" in text:
        return "dual"
    if "单" in text:
        return "single"
    if "半自动" in text:
        return "manual"
    return "none" if text in {"", "无"} else text[:64]


def _fixture_type(value: str) -> str:
    text = _clean_text(value)
    if "吸盘" in text:
        return "suction_cup"
    if "夹" in text:
        return "clamp"
    if "气剪" in text:
        return "air_nipper"
    if "半自动" in text:
        return "manual"
    return text[:128]


def _parse_machines(reader: _WorkbookReader, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    machines: dict[str, dict[str, Any]] = {}
    if "华兴机器设备" in reader.sheet_paths:
        for row_number, cells in reader.rows("华兴机器设备"):
            if row_number < 4:
                continue
            area = _clean_text(cells.get("A", {}).get("value"))
            position = _clean_text(cells.get("B", {}).get("value"))
            if not area or not position:
                continue
            code = _machine_code(area, position)
            dimensions = DIMENSION_RE.search(_clean_text(cells.get("I", {}).get("value")))
            machine = {
                "machine_code": code,
                "area": area,
                "position": _integer_text(position),
                "machine_class": _machine_class(_clean_text(cells.get("E", {}).get("value"))),
                "clamping_force_tons": _number(cells.get("J", {}).get("value")),
                "injection_capacity_g": _number(cells.get("H", {}).get("value")),
                "tie_bar_x_mm": float(dimensions.group(1)) if dimensions else None,
                "tie_bar_y_mm": float(dimensions.group(2)) if dimensions else None,
                "machine_type": _clean_text(cells.get("L", {}).get("value")) or "standard",
                "robot_capabilities": _robot_capabilities(_clean_text(cells.get("M", {}).get("value"))),
                "fixture_capabilities": [],
                "process_restrictions": [
                    text
                    for text in [_clean_text(cells.get("V", {}).get("value"))]
                    if text
                ],
                "status": "available",
                "source": {"sheet_name": "华兴机器设备", "source_row": row_number},
            }
            if code in machines and machines[code] != machine:
                issues.append(
                    _issue(
                        code="DUPLICATE_MACHINE",
                        message=f"机台 {code} 在设备表中重复，预览保留首条记录",
                        sheet_name="华兴机器设备",
                        source_row=row_number,
                        field_name="machine_code",
                        raw_value=code,
                    )
                )
                continue
            machines[code] = machine

    if "计划表" in reader.sheet_paths:
        for row_number, cells in reader.rows("计划表"):
            if row_number < 4:
                continue
            code_a = reader.identifier(cells.get("A"))
            code_b = reader.identifier(cells.get("B"))
            is_heading = bool(code_a and code_a == code_b)
            if not is_heading:
                continue
            existing = machines.get(code_a)
            heading = {
                "machine_code": code_a,
                "area": existing["area"] if existing else "",
                "position": existing["position"] if existing else code_a,
                "machine_class": _machine_class(reader.identifier(cells.get("G"))),
                "clamping_force_tons": existing["clamping_force_tons"] if existing else _number(reader.identifier(cells.get("G"))),
                "injection_capacity_g": existing["injection_capacity_g"] if existing else None,
                "tie_bar_x_mm": existing["tie_bar_x_mm"] if existing else None,
                "tie_bar_y_mm": existing["tie_bar_y_mm"] if existing else None,
                "machine_type": reader.identifier(cells.get("H")) or (existing["machine_type"] if existing else "standard"),
                "robot_capabilities": _robot_capabilities(reader.identifier(cells.get("I"))) or (existing["robot_capabilities"] if existing else []),
                "fixture_capabilities": existing["fixture_capabilities"] if existing else [],
                "process_restrictions": list(dict.fromkeys((existing["process_restrictions"] if existing else []) + [reader.identifier(cells.get(col)) for col in ("J", "K", "L") if reader.identifier(cells.get(col))])),
                "status": existing["status"] if existing else "available",
                "source": {"sheet_name": "计划表", "source_row": row_number},
            }
            machines[code_a] = heading
    return sorted(machines.values(), key=lambda item: item["machine_code"])


def _parse_molds(reader: _WorkbookReader, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    molds: dict[str, dict[str, Any]] = {}
    if "机安" not in reader.sheet_paths:
        issues.append(
            _issue(
                code="SHEET_MISSING",
                message="缺少“机安”工作表，无法导入模具主数据",
                sheet_name="机安",
                blocking=True,
            )
        )
        return []
    for row_number, cells in reader.rows("机安"):
        if row_number < 2:
            continue
        mold_no = reader.identifier(cells.get("A"))
        if not mold_no:
            continue
        length_mm = _number(cells.get("T", {}).get("value"))
        width_mm = _number(cells.get("U", {}).get("value"))
        height_mm = _number(cells.get("V", {}).get("value"))
        net_weight = _number(cells.get("M", {}).get("value"))
        remarks = "；".join(
            text
            for text in (
                reader.identifier(cells.get("N")),
                reader.identifier(cells.get("O")),
                reader.identifier(cells.get("P")),
                reader.identifier(cells.get("Q")),
            )
            if text
        )
        mold = {
            "mold_no": mold_no,
            "name": reader.identifier(cells.get("B")),
            "length_mm": length_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "weight_kg": _number(cells.get("W", {}).get("value")),
            "recommended_machine_class": reader.identifier(cells.get("G"))[:64],
            "whole_shot_net_weight_g": net_weight,
            "whole_shot_gross_weight_g": None,
            "required_arm_type": _arm_type(reader.identifier(cells.get("H"))),
            "required_fixture_type": _fixture_type(reader.identifier(cells.get("I"))),
            "material_code": reader.identifier(cells.get("L"))[:128],
            "material_name": reader.identifier(cells.get("L"))[:255],
            "color_profile": reader.identifier(cells.get("J"))[:128],
            "process_requirements": [remarks] if remarks else [],
            "copy_count": 1,
            "data_quality_status": (
                "complete"
                if all(value is not None for value in (length_mm, width_mm, height_mm, net_weight))
                else "needs_review"
            ),
            "status": "available",
            "source": {"sheet_name": "机安", "source_row": row_number},
        }
        if mold_no in molds:
            issues.append(
                _issue(
                    code="DUPLICATE_MOLD",
                    message=f"模号 {mold_no} 在机安表中重复，预览保留资料较完整的一条",
                    sheet_name="机安",
                    source_row=row_number,
                    field_name="mold_no",
                    raw_value=mold_no,
                )
            )
            current_score = sum(value not in (None, "", []) for value in molds[mold_no].values())
            candidate_score = sum(value not in (None, "", []) for value in mold.values())
            if candidate_score > current_score:
                molds[mold_no] = mold
            continue
        molds[mold_no] = mold
    return sorted(molds.values(), key=lambda item: item["mold_no"])


def _task_formula_issues(
    row_number: int,
    cells: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    for column, field_name in TASK_COLUMNS.items():
        cell = cells.get(column)
        if not cell or not cell.get("formula"):
            continue
        blocking = field_name in FORMULA_BLOCKING_FIELDS
        if cell.get("formula_cache_missing"):
            issues.append(
                _issue(
                    code="FORMULA_CACHE_MISSING",
                    message=f"第 {row_number} 行“{field_name}”公式没有缓存值，不能按 0 导入",
                    sheet_name="计划表",
                    source_row=row_number,
                    field_name=field_name,
                    cell_ref=cell["reference"],
                    formula_text=cell["formula"],
                    blocking=blocking,
                )
            )
        elif cell.get("formula_error"):
            issues.append(
                _issue(
                    code="FORMULA_ERROR",
                    message=f"第 {row_number} 行“{field_name}”公式结果为 {cell.get('raw_value')}",
                    sheet_name="计划表",
                    source_row=row_number,
                    field_name=field_name,
                    cell_ref=cell["reference"],
                    raw_value=_clean_text(cell.get("raw_value")),
                    formula_text=cell["formula"],
                    blocking=blocking,
                )
            )


def _parse_tasks(
    reader: _WorkbookReader,
    molds: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if "计划表" not in reader.sheet_paths:
        issues.append(
            _issue(
                code="SHEET_MISSING",
                message="缺少“计划表”工作表",
                sheet_name="计划表",
                blocking=True,
            )
        )
        return [], molds
    mold_by_no = {item["mold_no"]: item for item in molds}
    tasks: list[dict[str, Any]] = []
    current_machine = ""
    sequence_by_machine: defaultdict[str, int] = defaultdict(int)
    for row_number, cells in reader.rows("计划表"):
        if row_number < 4:
            continue
        code_a = reader.identifier(cells.get("A"))
        code_b = reader.identifier(cells.get("B"))
        is_heading = bool(code_a and code_a == code_b)
        if is_heading:
            current_machine = code_a
            continue
        machine_code = code_b or current_machine
        mold_no = reader.identifier(cells.get("G"))
        order_no = reader.identifier(cells.get("I"))
        if not mold_no and not order_no:
            continue
        _task_formula_issues(row_number, cells, issues)
        missing_fields = [
            label
            for label, value in (
                ("machine_code", machine_code),
                ("mold_no", mold_no),
                ("order_no", order_no),
            )
            if not value
        ]
        order_quantity = _number(cells.get("L", {}).get("value"))
        completed_quantity = _number(cells.get("M", {}).get("value"))
        if order_quantity is None or order_quantity <= 0:
            missing_fields.append("order_quantity")
        if completed_quantity is None:
            missing_fields.append("completed_quantity")
        planned_start = _excel_datetime(
            cells.get("AG", {}).get("value"), date_1904=reader.date_1904, date_only=False
        )
        planned_finish = _excel_datetime(
            cells.get("AH", {}).get("value"), date_1904=reader.date_1904, date_only=False
        )
        if not planned_start:
            missing_fields.append("planned_start")
        if not planned_finish:
            missing_fields.append("planned_finish")
        if planned_start and planned_finish and planned_start >= planned_finish:
            missing_fields.append("planned_window")
        if completed_quantity is not None and order_quantity is not None and completed_quantity > order_quantity:
            missing_fields.append("completed_quantity_range")
        for field_name in dict.fromkeys(missing_fields):
            issues.append(
                _issue(
                    code="TASK_FIELD_INVALID",
                    message=f"第 {row_number} 行任务字段 {field_name} 缺失或无效",
                    sheet_name="计划表",
                    source_row=row_number,
                    field_name=field_name,
                    raw_value=_clean_text(cells.get(next((column for column, name in TASK_COLUMNS.items() if name == field_name), ""), {}).get("value")),
                    blocking=True,
                )
            )
        if missing_fields:
            continue
        legacy_marker = reader.identifier(cells.get("E"))
        item_no = reader.identifier(cells.get("J"))
        task = {
            "machine_code": machine_code,
            "sequence_no": sequence_by_machine[machine_code],
            "execution_status": "QUEUED",
            "status_inferred": True,
            "legacy_marker": legacy_marker,
            "automation_mode": reader.identifier(cells.get("D")),
            "legacy_machine_class_text": reader.identifier(cells.get("F")),
            "mold_no": mold_no,
            "product_name": reader.identifier(cells.get("H"))[:255],
            "order_no": order_no,
            "item_no": item_no,
            "set_quantity": _number(cells.get("K", {}).get("value")),
            "order_quantity": order_quantity,
            "completed_quantity": completed_quantity,
            "shift_target_quantity": _number(cells.get("O", {}).get("value")) or 0,
            "color_name": reader.identifier(cells.get("Q"))[:128],
            "color_powder_code": reader.identifier(cells.get("R"))[:128],
            "material_name": reader.identifier(cells.get("S"))[:255],
            "whole_shot_net_weight_g": _number(cells.get("T", {}).get("value")),
            "whole_shot_gross_weight_g": _number(cells.get("U", {}).get("value")),
            "order_date": _excel_datetime(cells.get("Z", {}).get("value"), date_1904=reader.date_1904, date_only=True),
            "delivery_start_date": _excel_datetime(cells.get("AA", {}).get("value"), date_1904=reader.date_1904, date_only=True),
            "delivery_due_date": _excel_datetime(cells.get("AB", {}).get("value"), date_1904=reader.date_1904, date_only=True),
            "planned_start": planned_start,
            "planned_finish": planned_finish,
            "requires_spray_paint": reader.identifier(cells.get("AL")),
            "warehouse_text": reader.identifier(cells.get("AR"))[:255],
            "remark": reader.identifier(cells.get("AS"))[:2000],
            "required_arm_type": _arm_type(reader.identifier(cells.get("AU"))),
            "required_fixture_type": _fixture_type(reader.identifier(cells.get("AV"))),
            "priority_code": "CRITICAL" if "特急" in legacy_marker else ("URGENT" if "急" in legacy_marker else "NORMAL"),
            "source": {
                "sheet_name": "计划表",
                "source_row": row_number,
                "formula_cells": {
                    TASK_COLUMNS[column]: {
                        "cell_ref": cells[column]["reference"],
                        "formula": cells[column]["formula"],
                        "cached_value": cells[column]["raw_value"],
                    }
                    for column in TASK_COLUMNS
                    if column in cells and cells[column].get("formula")
                },
            },
        }
        tasks.append(task)
        sequence_by_machine[machine_code] += 1
        if mold_no and mold_no not in mold_by_no:
            fallback_mold = {
                "mold_no": mold_no,
                "name": task["product_name"],
                "length_mm": None,
                "width_mm": None,
                "height_mm": None,
                "weight_kg": None,
                "recommended_machine_class": task["legacy_machine_class_text"][:64],
                "whole_shot_net_weight_g": task["whole_shot_net_weight_g"],
                "whole_shot_gross_weight_g": task["whole_shot_gross_weight_g"],
                "required_arm_type": task["required_arm_type"],
                "required_fixture_type": task["required_fixture_type"],
                "material_code": task["material_name"][:128],
                "material_name": task["material_name"],
                "color_profile": task["color_name"],
                "process_requirements": [task["remark"]] if task["remark"] else [],
                "copy_count": 1,
                "data_quality_status": "needs_review",
                "status": "available",
                "source": {"sheet_name": "计划表", "source_row": row_number},
            }
            mold_by_no[mold_no] = fallback_mold
            issues.append(
                _issue(
                    code="MOLD_MASTER_MISSING",
                    message=f"模号 {mold_no} 未在机安表找到，将按计划行建立待复核模具",
                    sheet_name="计划表",
                    source_row=row_number,
                    field_name="mold_no",
                    raw_value=mold_no,
                )
            )

    by_machine: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        by_machine[task["machine_code"]].append(task)
    for machine_code, machine_tasks in by_machine.items():
        incomplete = [
            task
            for task in machine_tasks
            if task["order_quantity"] is None
            or task["completed_quantity"] is None
            or task["completed_quantity"] < task["order_quantity"]
        ]
        if not incomplete:
            for task in machine_tasks:
                task["execution_status"] = "COMPLETED"
            continue
        marked = [task for task in incomplete if "▲" in task["legacy_marker"]]
        running = marked[0] if marked else incomplete[0]
        running["execution_status"] = "RUNNING"
        if len(marked) > 1:
            issues.append(
                _issue(
                    code="MULTIPLE_RUNNING_MARKERS",
                    message=f"机台 {machine_code} 有 {len(marked)} 条“▲”，仅首条被推断为 RUNNING，请人工确认",
                    sheet_name="计划表",
                    source_row=running["source"]["source_row"],
                    field_name="legacy_marker",
                )
            )
        issues.append(
            _issue(
                code="STATUS_INFERRED",
                message=f"机台 {machine_code} 的第 {running['source']['source_row']} 行被推断为 RUNNING，确认导入前请复核",
                sheet_name="计划表",
                source_row=running["source"]["source_row"],
                field_name="execution_status",
            )
        )
        for task in machine_tasks:
            if task is running:
                continue
            if task["order_quantity"] is not None and task["completed_quantity"] is not None and task["completed_quantity"] >= task["order_quantity"]:
                task["execution_status"] = "COMPLETED"
    return tasks, sorted(mold_by_no.values(), key=lambda item: item["mold_no"])


def parse_injection_scheduling_workbook(content: bytes, source_file_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not content:
        raise HTTPException(status_code=422, detail="上传的 Excel 文件为空")
    if len(content) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="Excel 文件超过 50 MB 限制")
    if not source_file_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 格式的注塑排产文件")
    source_hash = hashlib.sha256(content).hexdigest()
    try:
        reader = _WorkbookReader(content)
    except (BadZipFile, KeyError, etree.XMLSyntaxError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Excel 文件结构损坏或无法解析") from exc
    try:
        issues: list[dict[str, Any]] = []
        required_sheets = {"计划表", "机安", "华兴机器设备"}
        for sheet_name in sorted(required_sheets - set(reader.sheet_paths)):
            issues.append(
                _issue(
                    code="SHEET_MISSING",
                    message=f"缺少必需工作表“{sheet_name}”",
                    sheet_name=sheet_name,
                    blocking=True,
                )
            )
        machines = _parse_machines(reader, issues)
        molds = _parse_molds(reader, issues)
        tasks, molds = _parse_tasks(reader, molds, issues)
        known_machine_codes = {item["machine_code"] for item in machines}
        for task in tasks:
            if task["machine_code"] and task["machine_code"] not in known_machine_codes:
                issues.append(
                    _issue(
                        code="MACHINE_MASTER_MISSING",
                        message=f"机台 {task['machine_code']} 未在设备或标题行找到",
                        sheet_name="计划表",
                        source_row=task["source"]["source_row"],
                        field_name="machine_code",
                        raw_value=task["machine_code"],
                        blocking=True,
                    )
                )
        order_keys: set[tuple[Any, ...]] = set()
        duplicate_order_rows = 0
        for task in tasks:
            key = (
                task["order_no"],
                task["item_no"],
                task["mold_no"],
                task["product_name"],
                task["order_quantity"],
            )
            if key in order_keys:
                duplicate_order_rows += 1
            order_keys.add(key)
        blocking_count = sum(bool(item["blocking"]) for item in issues)
        normalized = {
            "schema_version": PREVIEW_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "source_file_name": source_file_name,
            "source_file_hash": source_hash,
            "source_size_bytes": len(content),
            "sheet_names": list(reader.sheet_paths),
            "machines": machines,
            "molds": molds,
            "tasks": tasks,
            "summary": {
                "machine_count": len(machines),
                "mold_count": len(molds),
                "task_count": len(tasks),
                "order_count": len(order_keys),
                "duplicate_order_rows": duplicate_order_rows,
                "issue_count": len(issues),
                "blocking_issue_count": blocking_count,
                "can_confirm": blocking_count == 0,
            },
        }
        normalized["normalized_sha256"] = hashlib.sha256(
            _json_text(normalized).encode("utf-8")
        ).hexdigest()
        return normalized, issues
    finally:
        reader.close()
