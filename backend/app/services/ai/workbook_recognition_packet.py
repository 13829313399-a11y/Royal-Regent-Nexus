from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import date
from pathlib import PurePosixPath
from typing import Any

from fastapi import HTTPException
from lxml import etree

from app.schemas.ai.workbook import (
    AIWorkbookRecognitionCellV1,
    AIWorkbookRecognitionColumnProfileV1,
    AIWorkbookRecognitionHeaderRegionV1,
    AIWorkbookRecognitionPacketV1,
    AIWorkbookRecognitionRowV1,
    AIWorkbookRecognitionSheetV1,
    AIWorkbookRecognitionSourceV1,
)
from app.services.injection_scheduling_excel import (
    CELL_REF_RE,
    MAIN_NS,
    _clean_text,
    _column_from_ref,
    _excel_datetime,
    _WorkbookReader,
)

PACKET_SCHEMA_VERSION = "workbook-recognition-packet-v1"
MAX_SHEETS = 50
MAX_COLUMNS = 1_024
MAX_ROWS = 100_000
MAX_HEADER_ROWS = 20
MAX_SAMPLE_ROWS = 24
MAX_CELL_TEXT = 240
MAX_FORMULA_TEXT = 2_000
MAX_MERGED_REGIONS = 2_000
_DATE_FORMAT = re.compile(r"(?:^|[^a-z])[dmyhs]+", re.IGNORECASE)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _column_number(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - 64
    return result


def _sheet_states(reader: _WorkbookReader) -> dict[str, str]:
    root = etree.fromstring(reader.archive.read("xl/workbook.xml"))
    return {
        str(item.get("name", "")): str(item.get("state", "visible"))
        for item in root.findall(f".//{{{MAIN_NS}}}sheet")
    }


def _sheet_xml_metadata(
    reader: _WorkbookReader, sheet_name: str
) -> tuple[str, list[str]]:
    path = reader.sheet_paths[sheet_name]
    dimension = "A1"
    merged: list[str] = []
    merge_count = 0
    with reader.archive.open(path) as stream:
        for _event, element in etree.iterparse(
            stream,
            events=("end",),
            tag=(f"{{{MAIN_NS}}}dimension", f"{{{MAIN_NS}}}mergeCell"),
            resolve_entities=False,
            no_network=True,
            huge_tree=True,
        ):
            if element.tag == f"{{{MAIN_NS}}}dimension":
                dimension = str(element.get("ref", "A1"))[:64]
            else:
                merge_count += 1
                if merge_count > MAX_MERGED_REGIONS:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "WORKBOOK_TOO_COMPLEX",
                            "message": f"Sheet {sheet_name} 合并区域超过安全上限",
                        },
                    )
                if len(merged) < 200:
                    merged.append(str(element.get("ref", ""))[:64])
            element.clear()
    return dimension, merged


def _value_kind(reader: _WorkbookReader, cell: dict[str, Any]) -> str:
    if cell.get("formula_error") or _clean_text(cell.get("raw_value")).startswith("#"):
        return "ERROR"
    if cell.get("formula"):
        return "FORMULA"
    if cell.get("value") is None:
        return "BLANK"
    cell_type = cell.get("type")
    if cell_type == "b":
        return "BOOLEAN"
    if cell_type in {"s", "str", "inlineStr"}:
        return "TEXT"
    format_code = reader._format_code(cell.get("style_index"))
    if format_code and _DATE_FORMAT.search(format_code):
        return "DATE"
    return "NUMBER"


def _display_value(reader: _WorkbookReader, cell: dict[str, Any], kind: str) -> str:
    if cell.get("formula_cache_missing"):
        return ""
    if kind == "DATE":
        parsed = _excel_datetime(
            cell.get("value"), date_1904=reader.date_1904, date_only=False
        )
        if parsed:
            return parsed[:MAX_CELL_TEXT]
    return reader.identifier(cell)[:MAX_CELL_TEXT]


def _cell_payload(
    reader: _WorkbookReader, cell: dict[str, Any]
) -> AIWorkbookRecognitionCellV1:
    kind = _value_kind(reader, cell)
    cache_status = (
        "ERROR"
        if cell.get("formula_error")
        else "MISSING"
        if cell.get("formula_cache_missing")
        else "PRESENT"
        if cell.get("formula")
        else "NOT_FORMULA"
    )
    raw_value = cell.get("value")
    if raw_value is not None and not isinstance(raw_value, (str, int, float, bool)):
        raw_value = str(raw_value)
    if isinstance(raw_value, str):
        raw_value = raw_value[:MAX_CELL_TEXT]
    return AIWorkbookRecognitionCellV1(
        cell_ref=str(cell.get("reference", "")),
        raw_value=raw_value,
        display_value=_display_value(reader, cell, kind),
        value_kind=kind,
        formula=(str(cell.get("formula", ""))[:MAX_FORMULA_TEXT] or None),
        formula_cache_status=cache_status,
    )


def _representative_rows(
    first: list[AIWorkbookRecognitionRowV1],
    reservoir: list[AIWorkbookRecognitionRowV1],
    last: deque[AIWorkbookRecognitionRowV1],
) -> list[AIWorkbookRecognitionRowV1]:
    selected: dict[int, AIWorkbookRecognitionRowV1] = {}
    for item in [*first, *sorted(reservoir, key=lambda row: row.row), *last]:
        selected.setdefault(item.row, item)
    return list(selected.values())[:MAX_SAMPLE_ROWS]


def _sheet_packet(
    reader: _WorkbookReader,
    *,
    sheet_name: str,
    state: str,
) -> AIWorkbookRecognitionSheetV1:
    dimension, merged = _sheet_xml_metadata(reader, sheet_name)
    header_cells: list[AIWorkbookRecognitionCellV1] = []
    first_rows: list[AIWorkbookRecognitionRowV1] = []
    reservoir: list[AIWorkbookRecognitionRowV1] = []
    last_rows: deque[AIWorkbookRecognitionRowV1] = deque(maxlen=8)
    column_nonempty: defaultdict[str, int] = defaultdict(int)
    column_formulas: defaultdict[str, int] = defaultdict(int)
    column_missing: defaultdict[str, int] = defaultdict(int)
    column_samples: defaultdict[str, list[str]] = defaultdict(list)
    max_row = 1
    max_column = 1
    effective_max_row = 1
    semantic_row_count = 0

    for row_number, cells in reader.rows(sheet_name):
        max_row = max(max_row, row_number)
        if max_row > MAX_ROWS:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "WORKBOOK_DIMENSION_LIMIT",
                    "message": f"Sheet {sheet_name} 超过 {MAX_ROWS} 行安全上限",
                },
            )
        semantic_cells = [
            cell
            for cell in cells.values()
            if cell.get("value") not in (None, "") or cell.get("formula")
        ]
        # Styled empty cells may extend to XFD even though the business table ends
        # hundreds of columns earlier. Limit the semantic payload, not formatting.
        for cell in semantic_cells:
            column = _column_from_ref(str(cell.get("reference", "")))
            if column:
                max_column = max(max_column, _column_number(column))
        if max_column > MAX_COLUMNS:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "WORKBOOK_DIMENSION_LIMIT",
                    "message": f"Sheet {sheet_name} 超过 {MAX_COLUMNS} 列识别上限",
                },
            )
        if row_number <= MAX_HEADER_ROWS:
            header_cells.extend(
                _cell_payload(reader, cell)
                for cell in semantic_cells[:160]
                if len(header_cells) < 3_200
            )
        if not semantic_cells:
            continue
        effective_max_row = row_number
        semantic_row_count += 1
        for cell in semantic_cells:
            reference = str(cell.get("reference", ""))
            match = CELL_REF_RE.fullmatch(reference)
            if match is None:
                continue
            column = match.group(1)
            column_nonempty[column] += 1
            if cell.get("formula"):
                column_formulas[column] += 1
            if cell.get("formula_cache_missing"):
                column_missing[column] += 1
            display = _display_value(reader, cell, _value_kind(reader, cell))
            if display and display not in column_samples[column] and len(column_samples[column]) < 6:
                column_samples[column].append(display)

        row_payload = AIWorkbookRecognitionRowV1(
            row=row_number,
            cells=[_cell_payload(reader, cell) for cell in semantic_cells[:160]],
        )
        if len(first_rows) < 8:
            first_rows.append(row_payload)
        last_rows.append(row_payload)
        if len(reservoir) < 8:
            reservoir.append(row_payload)
        else:
            selector = int(
                hashlib.sha256(f"{sheet_name}:{row_number}".encode()).hexdigest()[:8],
                16,
            ) % semantic_row_count
            if selector < len(reservoir):
                reservoir[selector] = row_payload

    columns = sorted(column_nonempty, key=_column_number)
    return AIWorkbookRecognitionSheetV1(
        name=sheet_name,
        state=state if state in {"visible", "hidden", "veryHidden"} else "visible",
        dimension=dimension,
        max_row=max_row,
        max_column=max_column,
        effective_max_row=effective_max_row,
        merged_regions=merged,
        header_region=AIWorkbookRecognitionHeaderRegionV1(
            start_row=1,
            end_row=min(MAX_HEADER_ROWS, max_row),
            cells=header_cells,
        ),
        representative_rows=_representative_rows(
            first_rows, reservoir, last_rows
        ),
        column_profiles=[
            AIWorkbookRecognitionColumnProfileV1(
                column=column,
                non_empty_count=column_nonempty[column],
                formula_count=column_formulas[column],
                formula_cache_missing_count=column_missing[column],
                sample_values=column_samples[column],
            )
            for column in columns
        ],
    )


def build_workbook_recognition_packet(
    *,
    source_file_name: str,
    content: bytes,
    factory_id: str,
    business_date: date | str,
) -> AIWorkbookRecognitionPacketV1:
    if not content:
        raise HTTPException(status_code=422, detail="上传的 Excel 文件为空")
    portable_name = source_file_name.strip().replace("\\", "/")
    if PurePosixPath(portable_name).name != portable_name:
        raise HTTPException(status_code=422, detail="Excel 文件名或路径不安全")
    suffix = PurePosixPath(portable_name).suffix.lower()
    reader = _WorkbookReader(content)
    try:
        if not 1 <= len(reader.sheet_paths) <= MAX_SHEETS:
            raise HTTPException(status_code=413, detail="工作簿 Sheet 数超过安全上限")
        states = _sheet_states(reader)
        sheets = [
            _sheet_packet(
                reader,
                sheet_name=sheet_name,
                state=states.get(sheet_name, "visible"),
            )
            for sheet_name in reader.sheet_paths
        ]
    finally:
        reader.close()

    source_sha256 = hashlib.sha256(content).hexdigest()
    packet = AIWorkbookRecognitionPacketV1(
        factory_id=factory_id,
        business_date=(
            business_date.isoformat()
            if isinstance(business_date, date)
            else str(business_date)
        ),
        source=AIWorkbookRecognitionSourceV1(
            file_name=source_file_name,
            source_sha256=source_sha256,
            size_bytes=len(content),
            detected_format="XLSM" if suffix == ".xlsm" else "XLSX",
        ),
        sheets=sheets,
        packet_sha256="0" * 64,
    )
    digest_payload = packet.model_dump(mode="json", exclude={"packet_sha256"})
    return packet.model_copy(
        update={"packet_sha256": hashlib.sha256(_json(digest_payload).encode()).hexdigest()}
    )
