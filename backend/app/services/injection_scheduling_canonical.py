from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.services.injection_scheduling_excel import (
    ERROR_VALUES,
    _arm_type,
    _clean_text,
    _enrich_class_normalization,
    _excel_datetime,
    _fixture_type,
    _issue,
    _machine_class,
    _machine_code,
    _number,
    _robot_capabilities,
    _safe_decimal,
    _WorkbookReader,
)
from app.services.injection_scheduling_profiles import (
    BUILTIN_IMPORT_PROFILES,
    CANONICAL_FIELD_CATALOG,
    FieldRule,
    ImportProfile,
    normalize_header,
    profile_definition_digest,
    profiles_for_factory,
)
from app.services.injection_scheduling_projection import (
    CALCULATION_VERSION,
    quantity_metrics,
)

CANONICAL_SCHEMA_VERSION = "injection-scheduling-canonical-v1"
PARSER_VERSION = "injection-scheduling-profile-parser-v1"
DATE_TEXT_RE = re.compile(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})")
TITLE_FACTORY_TOKENS = {
    "huaxing": ("华兴",),
    "huakang-a": ("华康a", "华康A"),
    "huakang-b": ("华康b", "华康B"),
    "huakang-c": ("华康c", "华康C"),
    "huakang-d": ("华康d", "华康D"),
    "huadeng": ("华登",),
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _column_number(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - 64
    return result


def _row(
    reader: _WorkbookReader, sheet_name: str, row_number: int
) -> dict[str, dict[str, Any]]:
    for source_row, cells in reader.rows(sheet_name):
        if source_row == row_number:
            return cells
        if source_row > row_number:
            break
    return {}


def _sheet_roles(
    reader: _WorkbookReader, profile: ImportProfile
) -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    for rule in profile.sheet_roles:
        matches = [name for name in rule.names if name in reader.sheet_paths]
        roles[rule.role] = {
            "role": rule.role,
            "sheet_name": matches[0] if matches else "",
            "aliases": list(rule.names),
            "required": rule.required,
            "status": "MATCHED" if matches else "MISSING",
            "header_row": rule.header_row,
        }
    return roles


def _mapping_for_profile(
    reader: _WorkbookReader,
    profile: ImportProfile,
    roles: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    current = roles["CURRENT_PLAN"]
    if not current["sheet_name"]:
        return [], ["CURRENT_PLAN"]
    header_row = int(current["header_row"] or 1)
    cells = _row(reader, current["sheet_name"], header_row)
    mapping: list[dict[str, Any]] = []
    blocking: list[str] = []
    normalized_header_counts = Counter(
        normalize_header(reader.identifier(cell))
        for cell in cells.values()
        if reader.identifier(cell)
    )
    for rule in profile.fields:
        cell = cells.get(rule.column)
        raw_header = reader.identifier(cell)
        normalized = normalize_header(raw_header)
        aliases = {normalize_header(item) for item in rule.headers}
        matched = bool(normalized and normalized in aliases)
        status = "MAPPED" if matched else "UNMAPPED"
        if rule.required and not matched:
            status = (
                "AMBIGUOUS"
                if normalized and normalized_header_counts[normalized] > 1
                else "MISSING"
            )
            blocking.append(rule.canonical_field)
        mapping.append(
            {
                "rule_id": rule.rule_id,
                "rule_revision": profile.revision,
                "sheet_role": "CURRENT_PLAN",
                "sheet_name": current["sheet_name"],
                "header_row": header_row,
                "column": rule.column,
                "raw_header": raw_header,
                "normalized_header": normalized,
                "canonical_field": rule.canonical_field,
                "converter": rule.converter,
                "unit": rule.unit,
                "required": rule.required,
                "status": status,
                "mapping_method": "PROFILE_COLUMN_AND_HEADER"
                if matched
                else "PROFILE_COLUMN_HINT",
                "confidence": "EXACT" if matched else "NONE",
                "authority": CANONICAL_FIELD_CATALOG[rule.canonical_field].authority,
                "sample_values": [],
            }
        )
    return mapping, blocking


def _select_profile(
    reader: _WorkbookReader,
    factory_id: str,
    profiles: Iterable[ImportProfile] | None = None,
) -> tuple[
    ImportProfile | None, dict[str, dict[str, Any]], list[dict[str, Any]], list[str]
]:
    candidates: Iterable[ImportProfile] = (
        profiles
        if profiles is not None
        else (
            profiles_for_factory(factory_id)
            if factory_id
            else tuple(
                item
                for item in BUILTIN_IMPORT_PROFILES
                if item.document_kind == "PLANNED_SCHEDULE"
            )
        )
    )
    compatible: list[
        tuple[
            int,
            ImportProfile,
            dict[str, dict[str, Any]],
            list[dict[str, Any]],
            list[str],
        ]
    ] = []
    for profile in candidates:
        roles = _sheet_roles(reader, profile)
        mapping, blocking = _mapping_for_profile(reader, profile, roles)
        current_matched = roles["CURRENT_PLAN"]["status"] == "MATCHED"
        missing_required_roles = [
            role
            for role, value in roles.items()
            if value["required"] and value["status"] != "MATCHED"
        ]
        score = (100 if current_matched else 0) + sum(
            1 for item in mapping if item["status"] == "MAPPED"
        )
        if current_matched:
            compatible.append(
                (score, profile, roles, mapping, [*missing_required_roles, *blocking])
            )
    if not compatible:
        return None, {}, [], ["PROFILE_NOT_FOUND"]
    compatible.sort(key=lambda item: (item[0], item[1].profile_code), reverse=True)
    _, profile, roles, mapping, blocking = compatible[0]
    if len(compatible) > 1 and compatible[1][0] == compatible[0][0]:
        blocking = [*blocking, "PROFILE_SELECTION_AMBIGUOUS"]
    if blocking:
        return profile, roles, mapping, blocking
    return profile, roles, mapping, []


def _date_value(
    reader: _WorkbookReader,
    cell: dict[str, Any] | None,
    *,
    date_only: bool,
) -> str:
    if not cell or cell.get("formula_error") or cell.get("formula_cache_missing"):
        return ""
    value = cell.get("value")
    if value is None or _clean_text(value) in ERROR_VALUES:
        return ""
    parsed = _safe_decimal(value)
    if parsed is not None:
        result = _excel_datetime(value, date_1904=reader.date_1904, date_only=date_only)
        try:
            year = datetime.fromisoformat(result).year
        except ValueError:
            return ""
        return "" if year < 2000 else result
    text = _clean_text(value)
    match = DATE_TEXT_RE.match(text)
    if match:
        try:
            result = datetime(  # noqa: DTZ001 - factory-local wall time
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            )
        except ValueError:
            return ""
        return (
            result.date().isoformat()
            if date_only
            else result.isoformat(timespec="seconds")
        )
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return ""
    return (
        result.date().isoformat() if date_only else result.isoformat(timespec="seconds")
    )


def _convert(
    reader: _WorkbookReader,
    cell: dict[str, Any] | None,
    converter: str,
) -> Any:
    if not cell or cell.get("formula_error") or cell.get("formula_cache_missing"):
        return (
            ""
            if converter in {"trim", "identifier", "text", "date", "datetime"}
            else None
        )
    if converter == "identifier":
        return reader.identifier(cell)
    if converter in {"trim", "text"}:
        return _clean_text(cell.get("value"))
    if converter == "number":
        return _number(cell.get("value"))
    if converter == "percent":
        raw = _clean_text(cell.get("value"))
        parsed = _number(raw)
        if parsed is None:
            return None
        return parsed / 100 if "%" in raw else parsed
    if converter == "date":
        return _date_value(reader, cell, date_only=True)
    if converter == "datetime":
        return _date_value(reader, cell, date_only=False)
    raise RuntimeError(f"unsupported converter: {converter}")


def _lineage(
    *,
    profile: ImportProfile,
    rule: FieldRule,
    mapping: dict[str, Any],
    sheet_name: str,
    source_row: int,
    cell: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "source_sheet": sheet_name,
        "source_row": source_row,
        "source_column": rule.column,
        "cell_ref": (cell or {}).get("reference", f"{rule.column}{source_row}"),
        "raw_header": mapping["raw_header"],
        "normalized_header": mapping["normalized_header"],
        "raw_value": (cell or {}).get("value"),
        "formula_text": (cell or {}).get("formula", ""),
        "cached_value": (cell or {}).get("raw_value"),
        "cached_status": (
            "ERROR"
            if (cell or {}).get("formula_error")
            else "MISSING"
            if (cell or {}).get("formula_cache_missing")
            else "PRESENT"
            if (cell or {}).get("formula")
            else "NOT_FORMULA"
        ),
        "canonical_field": rule.canonical_field,
        "profile_id": profile.profile_id,
        "profile_revision": profile.revision,
        "mapping_rule_id": rule.rule_id,
        "mapping_rule_revision": profile.revision,
        "mapping_method": mapping["mapping_method"],
        "confidence": mapping["confidence"],
    }


def _parse_huaxing_machines(
    reader: _WorkbookReader,
    sheet_name: str,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    machines: dict[str, dict[str, Any]] = {}
    if not sheet_name:
        return []
    for row_number, cells in reader.rows(sheet_name):
        if row_number < 4:
            continue
        area = _clean_text(cells.get("A", {}).get("value"))
        position = _clean_text(cells.get("B", {}).get("value"))
        if not area or not position:
            continue
        code = _machine_code(area, position)
        dimensions = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:MM)?\s*[×xX*]\s*([0-9]+(?:\.[0-9]+)?)",
            _clean_text(cells.get("I", {}).get("value")),
            re.IGNORECASE,
        )
        machines[code] = {
            "machine_code": code,
            "area": area,
            "position": reader.identifier(cells.get("B")),
            "machine_class": _machine_class(reader.identifier(cells.get("E"))),
            "clamping_force_tons": _number(cells.get("J", {}).get("value")),
            "injection_capacity_g": _number(cells.get("H", {}).get("value")),
            "tie_bar_x_mm": float(dimensions.group(1)) if dimensions else None,
            "tie_bar_y_mm": float(dimensions.group(2)) if dimensions else None,
            "machine_type": reader.identifier(cells.get("L")) or "standard",
            "robot_capabilities": _robot_capabilities(
                reader.identifier(cells.get("M"))
            ),
            "fixture_capabilities": [],
            "process_restrictions": [reader.identifier(cells.get("V"))]
            if reader.identifier(cells.get("V"))
            else [],
            "status": "available",
            "source": {"sheet_name": sheet_name, "source_row": row_number},
        }
    return sorted(machines.values(), key=lambda item: item["machine_code"])


def _parse_huakang_b_machines(
    reader: _WorkbookReader,
    sheet_name: str,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    machines: dict[str, dict[str, Any]] = {}
    if not sheet_name:
        return []
    for row_number, cells in reader.rows(sheet_name):
        if row_number < 4:
            continue
        code = reader.identifier(cells.get("A"))
        name = reader.identifier(cells.get("B"))
        if not code or not name:
            continue
        dimensions = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:MM)?\s*[×xX*]\s*([0-9]+(?:\.[0-9]+)?)",
            reader.identifier(cells.get("G")),
            re.IGNORECASE,
        )
        if code in machines:
            issues.append(
                _issue(
                    code="DUPLICATE_MACHINE",
                    message=f"机台 {code} 在设备表中重复",
                    sheet_name=sheet_name,
                    source_row=row_number,
                )
            )
            continue
        restrictions = [
            value
            for value in (
                reader.identifier(cells.get("S")),
                reader.identifier(cells.get("W")),
            )
            if value
        ]
        machines[code] = {
            "machine_code": code,
            "area": "华康 B",
            "position": code,
            "machine_class": _machine_class(reader.identifier(cells.get("D"))),
            "clamping_force_tons": _number(cells.get("H", {}).get("value")),
            "injection_capacity_g": _number(cells.get("F", {}).get("value")),
            "tie_bar_x_mm": float(dimensions.group(1)) if dimensions else None,
            "tie_bar_y_mm": float(dimensions.group(2)) if dimensions else None,
            "machine_type": reader.identifier(cells.get("I")) or name,
            "robot_capabilities": _robot_capabilities(
                reader.identifier(cells.get("J"))
            ),
            "fixture_capabilities": [],
            "process_restrictions": restrictions,
            "status": "available",
            "source": {"sheet_name": sheet_name, "source_row": row_number},
        }
    return sorted(machines.values(), key=lambda item: item["machine_code"])


def _parse_huaxing_molds(
    reader: _WorkbookReader,
    sheet_name: str,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    molds: dict[str, dict[str, Any]] = {}
    if not sheet_name:
        return []
    for row_number, cells in reader.rows(sheet_name):
        if row_number < 2:
            continue
        mold_no = reader.identifier(cells.get("A"))
        if not mold_no:
            continue
        mold = {
            "mold_no": mold_no,
            "name": reader.identifier(cells.get("B")),
            "length_mm": _number(cells.get("T", {}).get("value")),
            "width_mm": _number(cells.get("U", {}).get("value")),
            "height_mm": _number(cells.get("V", {}).get("value")),
            "weight_kg": _number(cells.get("W", {}).get("value")),
            "recommended_machine_class": reader.identifier(cells.get("G"))[:64],
            "whole_shot_net_weight_g": _number(cells.get("M", {}).get("value")),
            "whole_shot_gross_weight_g": None,
            "required_arm_type": _arm_type(reader.identifier(cells.get("H"))),
            "required_fixture_type": _fixture_type(reader.identifier(cells.get("I"))),
            "material_code": reader.identifier(cells.get("L"))[:128],
            "material_name": reader.identifier(cells.get("L"))[:255],
            "color_profile": reader.identifier(cells.get("J"))[:128],
            "process_requirements": [],
            "copy_count": 1,
            "data_quality_status": "needs_review",
            "status": "available",
            "source": {"sheet_name": sheet_name, "source_row": row_number},
        }
        if mold_no in molds:
            issues.append(
                _issue(
                    code="DUPLICATE_MOLD",
                    message=f"模号 {mold_no} 在模具资料中重复，保留首条",
                    sheet_name=sheet_name,
                    source_row=row_number,
                )
            )
            continue
        molds[mold_no] = mold
    return sorted(molds.values(), key=lambda item: item["mold_no"])


def _profile_title_warning(
    reader: _WorkbookReader,
    profile: ImportProfile,
    sheet_name: str,
    issues: list[dict[str, Any]],
) -> None:
    if not profile.factories or not sheet_name:
        return
    title_cells = _row(reader, sheet_name, 1)
    title = " ".join(reader.identifier(cell) for cell in title_cells.values())
    tokens = TITLE_FACTORY_TOKENS.get(profile.factories[0], ())
    if title and tokens and not any(token in title for token in tokens):
        issues.append(
            _issue(
                code="WORKBOOK_TITLE_FACTORY_MISMATCH",
                message="工作簿展示标题与所选厂区不一致；厂区作用域仍以用户选择为准",
                sheet_name=sheet_name,
                source_row=1,
                raw_value=title,
            )
        )


def _formula_issue(
    *,
    profile: ImportProfile,
    rule: FieldRule,
    sheet_name: str,
    source_row: int,
    cell: dict[str, Any] | None,
    issues: list[dict[str, Any]],
) -> bool:
    if not cell or not cell.get("formula"):
        return False
    missing = cell.get("formula_cache_missing")
    error = cell.get("formula_error")
    if not missing and not error:
        return False
    authority = CANONICAL_FIELD_CATALOG[rule.canonical_field].authority
    blocking = authority in {"SOURCE_FACT", "BASELINE_DECISION"} and rule.required
    issues.append(
        _issue(
            code="FORMULA_CACHE_MISSING" if missing else "FORMULA_ERROR",
            message=(
                f"第 {source_row} 行 {rule.canonical_field} 的公式没有可靠缓存值"
                if missing
                else f"第 {source_row} 行 {rule.canonical_field} 的公式缓存为错误值"
            ),
            sheet_name=sheet_name,
            source_row=source_row,
            field_name=rule.canonical_field,
            cell_ref=cell.get("reference", ""),
            raw_value=_clean_text(cell.get("raw_value")),
            formula_text=cell.get("formula", ""),
            blocking=blocking,
        )
    )
    return blocking


def _row_key(parts: list[str]) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _dynamic_cells(
    reader: _WorkbookReader,
    cells: dict[str, dict[str, Any]],
    profile: ImportProfile,
) -> list[dict[str, Any]]:
    start = _column_number(profile.dynamic_shift_start)
    end = _column_number(profile.dynamic_shift_end)
    return [
        {
            "column": column,
            "cell_ref": cell.get("reference", ""),
            "raw_value": cell.get("value"),
            "formula_text": cell.get("formula", ""),
            "cached_value": cell.get("raw_value"),
            "cached_status": (
                "ERROR"
                if cell.get("formula_error")
                else "MISSING"
                if cell.get("formula_cache_missing")
                else "PRESENT"
                if cell.get("formula")
                else "NOT_FORMULA"
            ),
        }
        for column, cell in cells.items()
        if start <= _column_number(column) <= end
        and (cell.get("value") is not None or cell.get("formula"))
    ]


def _parse_plan_rows(
    reader: _WorkbookReader,
    *,
    profile: ImportProfile,
    roles: dict[str, dict[str, Any]],
    mapping: list[dict[str, Any]],
    known_machine_codes: set[str],
    authoritative_machine_codes: set[str],
    authoritative_mold_nos: set[str],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    sheet_name = roles["CURRENT_PLAN"]["sheet_name"]
    header_row = int(roles["CURRENT_PLAN"]["header_row"] or 1)
    mapping_by_field = {item["canonical_field"]: item for item in mapping}
    scheduled: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    master_differences: dict[tuple[str, str], dict[str, Any]] = {}
    current_machine = ""
    sequence_by_machine: defaultdict[str, int] = defaultdict(int)
    running_candidates: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for row_number, cells in reader.rows(sheet_name):
        if row_number <= header_row:
            continue
        values: dict[str, Any] = {}
        field_lineage: dict[str, Any] = {}
        blocking_formula = False
        for rule in profile.fields:
            mapping_item = mapping_by_field[rule.canonical_field]
            cell = cells.get(rule.column)
            values[rule.canonical_field] = _convert(reader, cell, rule.converter)
            field_lineage[rule.canonical_field] = _lineage(
                profile=profile,
                rule=rule,
                mapping=mapping_item,
                sheet_name=sheet_name,
                source_row=row_number,
                cell=cell,
            )
            blocking_formula = (
                _formula_issue(
                    profile=profile,
                    rule=rule,
                    sheet_name=sheet_name,
                    source_row=row_number,
                    cell=cell,
                    issues=issues,
                )
                or blocking_formula
            )
            if len(mapping_item["sample_values"]) < 3 and values[
                rule.canonical_field
            ] not in (None, ""):
                mapping_item["sample_values"].append(values[rule.canonical_field])

        order_quantity = values.get("order_quantity")
        order_no = _clean_text(values.get("order_no"))
        order_like = bool(
            order_no
            and order_quantity is not None
            and order_quantity > 0
            and any(
                _clean_text(values.get(field))
                for field in ("item_no", "mold_no", "product_name")
            )
        )
        raw_machine = _clean_text(values.get("machine_code"))
        is_machine_header = bool(
            raw_machine
            and raw_machine in known_machine_codes
            and not order_like
            and order_quantity is None
        )
        if is_machine_header:
            current_machine = raw_machine
            ignored.append(
                {
                    "classification": "MACHINE_HEADER",
                    "source": {"sheet_name": sheet_name, "source_row": row_number},
                    "machine_code": raw_machine,
                }
            )
            continue
        if not order_like:
            if any(_clean_text(value) for value in values.values()):
                ignored.append(
                    {
                        "classification": "IGNORED",
                        "source": {"sheet_name": sheet_name, "source_row": row_number},
                        "reason": "not_an_order_row",
                    }
                )
            continue

        explicit_machine = raw_machine
        planned_start = _clean_text(values.get("planned_start"))
        planned_finish = _clean_text(values.get("planned_finish"))
        inherited_machine = ""
        if (
            not explicit_machine
            and current_machine
            and planned_start
            and planned_finish
        ):
            inherited_machine = current_machine
        machine_code = explicit_machine or inherited_machine
        completed = values.get("completed_quantity")
        row_errors: list[str] = []
        if completed is None or completed < 0:
            row_errors.append("completed_quantity")
        if machine_code and machine_code not in known_machine_codes:
            row_errors.append("machine_code")
        if machine_code and machine_code not in authoritative_machine_codes:
            master_differences.setdefault(
                ("MACHINE", machine_code),
                {
                    "entity_type": "MACHINE",
                    "business_key": machine_code,
                    "status": "MISSING_IN_SYSTEM_MASTER",
                    "source_sheet": sheet_name,
                    "source_row": row_number,
                },
            )
        mold_no = _clean_text(values.get("mold_no"))
        if mold_no and mold_no not in authoritative_mold_nos:
            master_differences.setdefault(
                ("MOLD", mold_no),
                {
                    "entity_type": "MOLD",
                    "business_key": mold_no,
                    "status": "MISSING_IN_SYSTEM_MASTER",
                    "source_sheet": sheet_name,
                    "source_row": row_number,
                },
            )
        has_window = bool(
            planned_start and planned_finish and planned_start < planned_finish
        )
        scheduled_evidence = bool(machine_code or planned_start or planned_finish)
        if completed is not None and completed > order_quantity:
            issues.append(
                _issue(
                    code="OVERPRODUCED",
                    message=f"第 {row_number} 行已啤数大于订单数，按超产保留并视为完成",
                    sheet_name=sheet_name,
                    source_row=row_number,
                    field_name="completed_quantity",
                    raw_value=str(completed),
                )
            )
        if scheduled_evidence and not has_window:
            row_errors.append("planned_window")
        if blocking_formula:
            row_errors.append("formula_source")

        product_name = _clean_text(values.get("product_name"))
        stable_order_key = _row_key(
            [
                profile.profile_family,
                order_no,
                _clean_text(values.get("item_no")),
                mold_no,
                product_name,
            ]
        )
        split_key = _row_key(
            [
                profile.profile_family,
                order_no,
                _clean_text(values.get("item_no")),
                mold_no,
                product_name,
                machine_code,
            ]
        )
        row = {
            **values,
            "machine_code": machine_code,
            "sequence_no": sequence_by_machine[machine_code] if machine_code else 0,
            "execution_status": (
                "COMPLETED"
                if completed is not None and completed >= order_quantity
                else "RUNNING"
                if "▲" in _clean_text(values.get("legacy_marker"))
                else "QUEUED"
            ),
            "status_inferred": True,
            "priority_code": (
                "CRITICAL"
                if "特急" in _clean_text(values.get("legacy_marker"))
                else "URGENT"
                if "急" in _clean_text(values.get("legacy_marker"))
                else "NORMAL"
            ),
            "stable_order_key": stable_order_key,
            "stable_row_key": split_key,
            "split_key": split_key,
            "quantity_scope": profile.quantity_scope,
            "planned_quantity": None,
            "source": {
                "sheet_name": sheet_name,
                "source_row": row_number,
                "profile_id": profile.profile_id,
                "profile_revision": profile.revision,
                "field_lineage": field_lineage,
                "dynamic_shift_cells": _dynamic_cells(reader, cells, profile),
            },
            "legacy_fields": {
                key: value
                for key, value in values.items()
                if CANONICAL_FIELD_CATALOG[key].authority == "LEGACY_DISPLAY"
            },
        }
        if row_errors:
            row["classification"] = "INVALID"
            row["invalid_reasons"] = list(dict.fromkeys(row_errors))
            invalid.append(row)
            for field_name in dict.fromkeys(row_errors):
                issues.append(
                    _issue(
                        code="CANONICAL_ROW_INVALID",
                        message=f"第 {row_number} 行已排证据存在，但规范字段 {field_name} 无法安全确认",
                        sheet_name=sheet_name,
                        source_row=row_number,
                        field_name=field_name,
                        blocking=True,
                    )
                )
            continue
        if machine_code and has_window:
            row["classification"] = "SCHEDULED_BASELINE"
            sequence_by_machine[machine_code] += 1
            scheduled.append(row)
            if row["execution_status"] == "RUNNING":
                running_candidates[machine_code].append(row)
        elif not machine_code and not has_window:
            row["classification"] = "BACKLOG"
            row["execution_status"] = (
                "COMPLETED"
                if completed is not None and completed >= order_quantity
                else "QUEUED"
            )
            backlog.append(row)
        else:
            row["classification"] = "INVALID"
            row["invalid_reasons"] = ["ambiguous_schedule_state"]
            invalid.append(row)
            issues.append(
                _issue(
                    code="ROW_CLASSIFICATION_AMBIGUOUS",
                    message=f"第 {row_number} 行无法安全区分已排与待排",
                    sheet_name=sheet_name,
                    source_row=row_number,
                    blocking=True,
                )
            )

    rows_by_split: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_order: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in [*scheduled, *backlog]:
        rows_by_split[row["stable_row_key"]].append(row)
        rows_by_order[row["stable_order_key"]].append(row)
    for split_key, rows in rows_by_split.items():
        if len(rows) <= 1:
            continue
        for row in rows:
            issues.append(
                _issue(
                    code="STABLE_IDENTITY_AMBIGUOUS",
                    message="旧表存在业务身份完全相同的重复拆分行，不能用行序号猜测身份",
                    sheet_name=row["source"]["sheet_name"],
                    source_row=row["source"]["source_row"],
                    field_name="stable_row_key",
                    raw_value=split_key,
                    blocking=True,
                )
            )
    for order_key, rows in rows_by_order.items():
        active = [
            item for item in rows if item["classification"] == "SCHEDULED_BASELINE"
        ]
        if len(active) == 1:
            active[0]["planned_quantity"] = max(
                float(active[0]["order_quantity"])
                - float(active[0].get("completed_quantity") or 0),
                0.0,
            )
        elif len(active) > 1:
            for row in active:
                issues.append(
                    _issue(
                        code="SPLIT_QUANTITY_REQUIRED",
                        message="同一订单存在多条已排基线但模板未提供可验证的 split 分配量",
                        sheet_name=row["source"]["sheet_name"],
                        source_row=row["source"]["source_row"],
                        field_name="planned_quantity",
                        raw_value=order_key,
                        blocking=True,
                    )
                )
    for machine_code, rows in running_candidates.items():
        if len(rows) <= 1:
            continue
        for row in rows[1:]:
            row["execution_status"] = "QUEUED"
        issues.append(
            _issue(
                code="MULTIPLE_RUNNING_MARKERS",
                message=f"机台 {machine_code} 存在多个 RUNNING 候选，仅首条保留为候选",
                sheet_name=sheet_name,
                source_row=rows[0]["source"]["source_row"],
            )
        )

    orders: dict[str, dict[str, Any]] = {}
    for row in [*scheduled, *backlog]:
        current = orders.get(row["stable_order_key"])
        if current is None:
            orders[row["stable_order_key"]] = {
                "stable_order_key": row["stable_order_key"],
                "order_no": row["order_no"],
                "item_no": row.get("item_no", ""),
                "product_name": row.get("product_name", ""),
                "mold_no": row.get("mold_no", ""),
                "order_quantity": row["order_quantity"],
                "completed_quantity": row.get("completed_quantity") or 0,
                "delivery_start_date": row.get("delivery_start_date", ""),
                "delivery_due_date": row.get("delivery_due_date", ""),
                "warehouse_text": row.get("warehouse_text", ""),
                "remark": row.get("remark", ""),
                "priority_code": row["priority_code"],
                "source_rows": [row["source"]["source_row"]],
            }
        else:
            current["source_rows"].append(row["source"]["source_row"])

    comparisons: list[dict[str, Any]] = []
    for row in [*scheduled, *backlog]:
        metrics = quantity_metrics(
            order_quantity=row["order_quantity"],
            completed_quantity=row.get("completed_quantity") or 0,
            shift_target_quantity=row.get("shift_target_quantity") or 0,
        )
        for field, source_field in (
            ("outstanding_quantity", "source_outstanding_quantity"),
            ("completion_rate", "source_completion_rate"),
            ("overproduction_quantity", "source_overproduction_quantity"),
            ("estimated_remaining_shifts", "source_remaining_shifts"),
        ):
            comparisons.append(
                {
                    "stable_order_key": row["stable_order_key"],
                    "source_row": row["source"]["source_row"],
                    "field": field,
                    "excel_value": row.get(source_field),
                    "system_value": metrics[field],
                    "difference": None
                    if row.get(source_field) is None
                    else float(metrics[field]) - float(row[source_field]),
                    "adopted_source": "SYSTEM_DERIVED",
                    "calculation_version": CALCULATION_VERSION,
                    "basis": {
                        "order_quantity": metrics["order_quantity"],
                        "completed_quantity": metrics["completed_quantity"],
                        "shift_target_quantity": metrics["shift_target_quantity"],
                    },
                }
            )
    return {
        "orders": list(orders.values()),
        "scheduled_baseline_tasks": scheduled,
        "backlog_orders": backlog,
        "ignored_rows": ignored,
        "invalid_rows": invalid,
        "master_differences": list(master_differences.values()),
        "calculation_comparisons": comparisons,
    }


def parse_canonical_workbook(
    reader: _WorkbookReader,
    *,
    source_file_name: str,
    source_file_hash: str,
    source_size_bytes: int,
    factory_id: str = "",
    system_machine_codes: set[str] | None = None,
    system_mold_nos: set[str] | None = None,
    profiles: Iterable[ImportProfile] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    profile, roles, mapping, mapping_blockers = _select_profile(
        reader, factory_id, profiles
    )
    if profile is None:
        issues.append(
            _issue(
                code="PROFILE_NOT_IDENTIFIED",
                message="没有找到适用于所选厂区的 ACTIVE 模板 Profile，批次进入 MAPPING_REQUIRED",
                sheet_name="",
                blocking=True,
            )
        )
        normalized = {
            "schema_version": CANONICAL_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "source_file_name": source_file_name,
            "source_file_hash": source_file_hash,
            "source_size_bytes": source_size_bytes,
            "sheet_names": list(reader.sheet_paths),
            "batch_state": "MAPPING_REQUIRED",
            "profile": None,
            "sheet_roles": [],
            "mapping": [],
            "machines": [],
            "molds": [],
            "orders": [],
            "scheduled_baseline_tasks": [],
            "tasks": [],
            "backlog_orders": [],
            "optional_completed_history": [],
            "optional_cancelled_history": [],
            "optional_outsourced_plan": [],
            "ignored_rows": [],
            "invalid_rows": [],
            "master_differences": [],
            "reconciliation_actions": [],
            "calculation_comparisons": [],
            "continuation_anchors": [],
        }
        normalized["summary"] = {
            "machine_count": 0,
            "mold_count": 0,
            "task_count": 0,
            "scheduled_baseline_count": 0,
            "backlog_count": 0,
            "order_count": 0,
            "ignored_row_count": 0,
            "invalid_row_count": 0,
            "issue_count": 1,
            "blocking_issue_count": 1,
            "can_confirm": False,
        }
        normalized["normalized_sha256"] = _hash(normalized)
        return normalized, issues

    current_sheet = roles["CURRENT_PLAN"]["sheet_name"]
    _profile_title_warning(reader, profile, current_sheet, issues)
    if mapping_blockers:
        for blocker in mapping_blockers:
            issues.append(
                _issue(
                    code="REQUIRED_MAPPING_MISSING",
                    message=f"Profile 必填映射 {blocker} 缺失或歧义",
                    sheet_name=current_sheet,
                    blocking=True,
                )
            )

    machine_sheet = roles.get("MACHINE_MASTER", {}).get("sheet_name", "")
    mold_sheet = roles.get("MOLD_MASTER", {}).get("sheet_name", "")
    if profile.machine_adapter == "huaxing_machine_v1":
        machines = _parse_huaxing_machines(reader, machine_sheet, issues)
    elif profile.machine_adapter == "huakang_b_machine_v1":
        machines = _parse_huakang_b_machines(reader, machine_sheet, issues)
    else:
        machines = []
    molds = (
        _parse_huaxing_molds(reader, mold_sheet, issues)
        if profile.mold_adapter == "huaxing_mold_v1"
        else []
    )
    _enrich_class_normalization(
        machines,
        raw_key="machine_class",
        class_key="machine",
        entity_label="机台",
        issues=issues,
    )
    _enrich_class_normalization(
        molds,
        raw_key="recommended_machine_class",
        class_key="mold",
        entity_label="模具",
        issues=issues,
    )
    known_machine_codes = {item["machine_code"] for item in machines} | set(
        system_machine_codes or set()
    )
    parsed = _parse_plan_rows(
        reader,
        profile=profile,
        roles=roles,
        mapping=mapping,
        known_machine_codes=known_machine_codes,
        authoritative_machine_codes=set(system_machine_codes or set()),
        authoritative_mold_nos=set(system_mold_nos or set()),
        issues=issues,
    )
    signature_payload = {
        "profile_family": profile.profile_family,
        "sheet_roles": {
            role: value["sheet_name"]
            for role, value in roles.items()
            if value["sheet_name"]
        },
        "headers": [
            [item["sheet_role"], item["column"], item["normalized_header"]]
            for item in mapping
            if item["normalized_header"]
            and not (
                profile.dynamic_shift_start
                and _column_number(item["column"])
                >= _column_number(profile.dynamic_shift_start)
            )
        ],
    }
    template_signature = _hash(signature_payload)
    mapping_fingerprint = _hash(
        [
            {key: value for key, value in item.items() if key != "sample_values"}
            for item in mapping
        ]
    )
    blocking_count = sum(bool(item["blocking"]) for item in issues)
    batch_state = (
        "MAPPING_REQUIRED"
        if mapping_blockers
        else (
            "MASTER_REVIEW_REQUIRED"
            if parsed["master_differences"]
            else "PREVIEW_READY"
        )
    )
    history_stats = {
        role: {
            "sheet_name": value["sheet_name"],
            "recognized": bool(value["sheet_name"]),
            "persisted": False,
        }
        for role, value in roles.items()
        if role in {"COMPLETED_HISTORY", "CANCELLED_ORDER_HISTORY", "OUTSOURCED_PLAN"}
    }
    normalized = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "source_file_name": source_file_name,
        "source_file_hash": source_file_hash,
        "source_size_bytes": source_size_bytes,
        "sheet_names": list(reader.sheet_paths),
        "batch_state": batch_state,
        "profile": {
            "profile_id": profile.profile_id,
            "profile_code": profile.profile_code,
            "profile_family": profile.profile_family,
            "profile_version": profile.revision,
            "revision": profile.revision,
            "name": profile.name,
            "status": profile.status,
            "factories": list(profile.factories),
            "recognition_method": (
                "ACTIVE_PROFILE_EXACT"
                if all(item["status"] == "MAPPED" for item in mapping)
                else "ACTIVE_PROFILE_COMPATIBLE_HEADER_FINGERPRINT"
            ),
            "template_signature": template_signature,
            "definition_digest": profile_definition_digest(profile),
            "quantity_scope": profile.quantity_scope,
            "renderer_code": profile.renderer_code,
        },
        "sheet_roles": list(roles.values()),
        "mapping": mapping,
        "mapping_fingerprint": mapping_fingerprint,
        "template_signature": template_signature,
        "machines": machines,
        "molds": molds,
        **parsed,
        "tasks": parsed["scheduled_baseline_tasks"],
        "optional_completed_history": [history_stats["COMPLETED_HISTORY"]]
        if history_stats.get("COMPLETED_HISTORY", {}).get("recognized")
        else [],
        "optional_cancelled_history": [history_stats["CANCELLED_ORDER_HISTORY"]]
        if history_stats.get("CANCELLED_ORDER_HISTORY", {}).get("recognized")
        else [],
        "optional_outsourced_plan": [history_stats["OUTSOURCED_PLAN"]]
        if history_stats.get("OUTSOURCED_PLAN", {}).get("recognized")
        else [],
        "reconciliation_actions": [],
        "continuation_anchors": [],
        "versions": {
            "parsing": PARSER_VERSION,
            "profile": profile.revision,
            "mapping": profile.revision,
            "calculation": "injection-scheduling-calculation-v1",
        },
    }
    normalized["summary"] = {
        "profile_code": profile.profile_code,
        "machine_count": len(machines),
        "mold_count": len(molds),
        "task_count": len(parsed["scheduled_baseline_tasks"]),
        "scheduled_baseline_count": len(parsed["scheduled_baseline_tasks"]),
        "backlog_count": len(parsed["backlog_orders"]),
        "order_count": len(parsed["orders"]),
        "ignored_row_count": len(parsed["ignored_rows"]),
        "invalid_row_count": len(parsed["invalid_rows"]),
        "master_difference_count": len(parsed["master_differences"]),
        "issue_count": len(issues),
        "blocking_issue_count": blocking_count,
        "can_confirm": blocking_count == 0 and batch_state == "PREVIEW_READY",
    }
    normalized["normalized_sha256"] = _hash(normalized)
    return normalized, issues
