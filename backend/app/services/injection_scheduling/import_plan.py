"""Deterministic header/section parser. Source evidence never becomes live facts."""

import re
from collections import Counter

from .calculations import decimal
from .field_registry import FIELDS
from .requirement_parser import (
    dispatch_from_text,
    machine_capabilities,
    machine_requirement,
)
from .sparse_xlsx import column_number, excel_date, read_sheet

PARSER_VERSION = "injection-v3-plan-1"
ALIASES = {
    "机号": "machine_code",
    "工模": "mold_code",
    "模号": "mold_code",
    "名称": "part_name",
    "单号": "order_no",
    "货号": "item_no",
    "数量(套)": "demand_sets",
    "数量（套）": "demand_sets",
    "订单数": "planned_shots",
    "已啤数": "completed_shots",
    "欠数": "remaining_shots",
    "计划目标": "target_shots_per_day",
    "计划日目标": "target_shots_per_day",
    "颜色": "color_name",
    "色粉": "colorant_code",
    "用料": "material_raw",
    "净重": "net_weight_g",
    "毛重": "gross_weight_g",
    "下单期": "ordered_on",
    "开始交货期": "delivery_window_start",
    "交货完成期": "delivery_due_at",
    "计划生产期": "planned_start_at",
    "计划完成期": "planned_end_at",
    "单价/啤": "price_per_shot",
}


def text(value):
    return str(value).strip() if value is not None else ""


def parse_plan(content, sheet_name="计划表", explicit_mapping=None):
    source = read_sheet(content, sheet_name)
    from .huaxing_template import read_huaxing_template
    from .unified_plan import read_unified

    unified = read_huaxing_template(source) or read_unified(source)
    if unified is not None:
        if explicit_mapping:
            raise ValueError("统一模板使用固定映射，不接受自定义列映射")
        return unified
    from .exchange import read_exchange

    exchange = read_exchange(source)
    if exchange is not None:
        return exchange
    rows = source["rows"]

    def val(row, col):
        return rows.get(row, {}).get(col, {}).get("cached_value")

    headers = {s.label: s.key for s in FIELDS.values()}
    headers.update(ALIASES)
    header_row, mapping = None, {}
    for row in sorted(rows):
        if row > 100:
            break
        candidate = {
            headers[text(c["cached_value"])]: col
            for col, c in rows[row].items()
            if text(c["cached_value"]) in headers
        }
        if {"mold_code", "order_no", "planned_shots"} <= candidate.keys() and len(
            candidate
        ) >= 7:
            header_row, mapping = row, candidate
            break
    if header_row is None:
        raise ValueError("未识别计划表表头：需要模号、单号、订单数及其他计划字段")
    # Only a verified positional fingerprint enables legacy duplicate-header aliases.
    huaxing_shape = all(
        val(header_row, col) == label
        for col, label in {
            "B": "机号",
            "G": "工模",
            "I": "单号",
            "J": "货号",
            "L": "订单数",
            "N": "欠数",
        }.items()
    )
    if huaxing_shape:
        mapping.update(
            {k: s.legacy_column for k, s in FIELDS.items() if s.legacy_column}
        )
    if explicit_mapping:
        for key, col in explicit_mapping.items():
            if key not in FIELDS or not re.fullmatch(r"[A-Z]{1,3}", col):
                raise ValueError("字段映射不合法")
        mapping.update(explicit_mapping)

    shifts = {}
    for col, cell in rows[header_row].items():
        shift = cell["cached_value"]
        if shift not in {"白班", "夜班"}:
            continue
        n = column_number(col)
        dates = [
            (c, v)
            for c, v in rows.get(header_row - 1, {}).items()
            if column_number(c) in {n, n - 1}
        ]
        dt, date_col = None, None
        for c, v in dates:
            dt = excel_date(v["cached_value"], source["date1904"])
            if dt and 2000 <= dt.year <= 2100:
                date_col = c
                break
            dt = None
        if dt:
            shifts[col] = {
                "date": dt.date().isoformat(),
                "shift_code": "DAY" if shift == "白班" else "NIGHT",
                "date_header_cell": f"{date_col}{header_row - 1}",
            }

    machines, demands, evidence_rows = [], [], []
    context = None
    workshop = ""
    last_business_row = header_row
    for row in sorted(r for r in rows if r > header_row):
        core = {col: cell for col, cell in rows[row].items() if col in mapping.values()}
        meaningful = {
            c: cell for c, cell in core.items() if cell["cached_value"] is not None
        }
        if not meaningful:
            continue
        if row > last_business_row + 1:
            context = None
        last_business_row = row
        raw = {k: val(row, col) for k, col in mapping.items()}
        mold = text(raw.get("mold_code"))
        code = text(raw.get("machine_code"))
        repeated = sum(text(c["cached_value"]) in headers for c in core.values()) >= 6
        section = bool(
            re.fullmatch(r".*(?:新车间|旧车间|待排区|待排订单|未排订单|需求池)", mold)
        )
        if repeated or section:
            if section:
                workshop, context = mold, None
            evidence_rows.append(
                {
                    "source_row": row,
                    "row_role": "HEADER" if repeated else "SECTION",
                    "core_cells": core,
                }
            )
            continue
        # A machine record needs a code, a specification and a machine-family cell.
        machine_spec = bool(
            re.fullmatch(
                r"\s*\d+(?:\.\d+)?\s*A(?:\s*\d+(?:\.\d+)?\s*T)?\s*", mold, re.IGNORECASE
            )
            or re.fullmatch(r"(?:大|小)?立式机?|双色机", mold)
        )
        machine_type = text(raw.get("part_name"))
        if code and machine_spec and (machine_type or raw.get("machine_block_marker")):
            note = "；".join(
                text(raw.get(k))
                for k in ("item_no", "planned_shots", "order_note", "production_note")
                if raw.get(k) is not None
            )
            props = machine_capabilities(
                mold, machine_type, note, text(raw.get("order_no"))
            )
            if code.startswith("旧"):
                workshop = "旧车间"
            elif code.startswith("新"):
                workshop = "新车间"
            context = code
            machines.append(
                {
                    "source_row": row,
                    "code": code,
                    "workshop": workshop,
                    "specification_raw": mold,
                    "type_raw": machine_type,
                    **props,
                    "raw_header_cells": core,
                }
            )
            evidence_rows.append(
                {"source_row": row, "row_role": "MACHINE", "core_cells": core}
            )
            continue
        if not mold and not (raw.get("order_no") or raw.get("item_no")):
            evidence_rows.append(
                {"source_row": row, "row_role": "NOTE", "core_cells": core}
            )
            context = None
            continue
        if not mold or mold in {"工模", "模号"}:
            continue
        issues = []
        fields = {}
        for key, value in raw.items():
            spec = FIELDS[key]
            if key == "required_machine_a":
                continue
            if spec.value_type in {"number", "integer"}:
                num = decimal(value)
                fields[key] = float(num) if num is not None else None
            elif spec.value_type == "datetime":
                dt = excel_date(value, source["date1904"])
                fields[key] = dt.isoformat() if dt and 2009 <= dt.year <= 2100 else None
                if value is not None and fields[key] is None:
                    issues.append(
                        {"field": key, "code": "INVALID_LEGACY_DATE", "raw": value}
                    )
            else:
                fields[key] = text(value) if value is not None else None
            cell = core.get(mapping[key], {})
            if (
                cell.get("formula_attributes") is not None
                and cell.get("cached_value") is None
            ):
                issues.append(
                    {
                        "field": key,
                        "code": "FORMULA_CACHE_MISSING",
                        "message": "公式尚无缓存，保留缺失状态，不能当作 0",
                    }
                )
            if cell.get("type") == "e" or cell.get("formula_issue"):
                issues.append({"field": key, "code": "SOURCE_CELL_ERROR", "raw": value})
            if "#REF!" in (cell.get("formula_expanded") or ""):
                issues.append({"field": key, "code": "FORMULA_REF_ERROR"})
        requirement = machine_requirement(raw.get("required_machine_a"))
        fields["required_machine_a"] = requirement["required_machine_a"]
        fields["requirements_snapshot"] = requirement
        fields["quantity_basis"] = "legacy_plan_shots"
        fields["weight_basis"] = "legacy_per_shot"
        fields["target_basis_hours"] = 24
        fields["allowance_rate"] = 0.01
        fields["downstream_lead_days"] = 3
        fields["dispatch_state"] = dispatch_from_text(
            f"{fields.get('order_note') or ''} {fields.get('production_note') or ''}"
        )
        material = text(raw.get("material_raw"))
        parts = material.split(maxsplit=1)
        fields["resin"] = parts[0].upper() if parts else None
        fields["material_grade"] = parts[1] if len(parts) > 1 else None
        history = []
        for col, header in shifts.items():
            qty = decimal(val(row, col))
            if qty is not None:
                history.append(
                    {**header, "raw_quantity": float(qty), "source_cell": f"{col}{row}"}
                )
        planned, completed = fields.get("planned_shots"), fields.get("completed_shots")
        total = sum(h["raw_quantity"] for h in history)
        fields["allocation_mode"] = (
            "SEQUENTIAL_SHOTS"
            if planned is not None and completed is not None
            else "LEGACY_UNRESOLVED"
        )
        if planned is None:
            issues.append({"field": "planned_shots", "code": "MISSING_QUANTITY"})
        if (
            planned is not None
            and completed is not None
            and raw.get("remaining_shots") is None
        ):
            issues.append(
                {
                    "field": "remaining_shots",
                    "code": "MISSING_REMAINING_FORMULA",
                    "raw": None,
                    "corrected": planned - completed,
                }
            )
        ae = (
            core.get(mapping.get("changeover_minutes"), {}).get("formula_expanded")
            or ""
        )
        if re.search(r"\bAS\d+\b", ae):
            issues.append({"field": "changeover_minutes", "code": "WRONG_AS_REFERENCE"})
        demands.append(
            {
                "source_row": row,
                "row_role": "MACHINE_AREA_DEMAND" if context else "TAIL_DEMAND",
                "inferred_machine_block": context,
                "raw_machine_cell": code,
                "fields": fields,
                "raw_fields": raw,
                "core_cells": core,
                "history": history,
                "numeric_shift_sum": total,
                "issues": issues,
            }
        )
    sums = {
        key: sum(decimal(d["raw_fields"].get(key), 0) for d in demands)
        for key in ("planned_shots", "completed_shots", "remaining_shots")
    }
    history_total = sum(d["numeric_shift_sum"] for d in demands)
    errors = [
        {"cell": f"{c}{r}", **cell}
        for r, cells in rows.items()
        for c, cell in cells.items()
        if cell.get("type") == "e"
    ]
    return {
        "parser_version": PARSER_VERSION,
        "sha256": source["sha256"],
        "sheet_name": sheet_name,
        "mapping": mapping,
        "header_row": header_row,
        "read_worksheets": source["read_worksheets"],
        "machines": machines,
        "demands": demands,
        "structure_rows": evidence_rows,
        "formula_cells": source["formula_cells"],
        "cached_errors": errors,
        "shift_columns": shifts,
        "statistics": {
            "machine_count": len(machines),
            "task_candidate_count": len(demands),
            "old_machine_count": sum(m["code"].startswith("旧") for m in machines),
            "new_machine_count": sum(m["code"].startswith("新") for m in machines),
            "machine_area_task_count": sum(
                d["inferred_machine_block"] is not None for d in demands
            ),
            "tail_task_count": sum(
                d["inferred_machine_block"] is None for d in demands
            ),
            "numeric_order_quantity_rows": sum(
                d["fields"].get("planned_shots") is not None for d in demands
            ),
            "cached_remaining_quantity_rows": sum(
                d["fields"].get("remaining_shots") is not None for d in demands
            ),
            "order_quantity_sum": float(sums["planned_shots"]),
            "cached_produced_quantity_sum": float(sums["completed_shots"]),
            "cached_remaining_quantity_sum": float(sums["remaining_shots"]),
            "standard_remaining_sum": float(
                sums["planned_shots"] - sums["completed_shots"]
            ),
            "quantity_sum_gap": float(
                sums["planned_shots"]
                - sums["completed_shots"]
                - sums["remaining_shots"]
            ),
            "numeric_shift_cell_count": sum(len(d["history"]) for d in demands),
            "numeric_shift_quantity_sum": history_total,
            "shift_sum_minus_cached_M": history_total - float(sums["completed_shots"]),
            "formula_cell_count": len(source["formula_cells"]),
            "cached_na_cells": sum(c["cached_value"] == "#N/A" for c in errors),
            "stored_cell_count": source["stored_cell_count"],
            "declared_dimension": source["declared_dimension"],
            "dated_shift_column_count": len(shifts),
            "states": dict(Counter(d["fields"]["dispatch_state"] for d in demands)),
        },
    }
