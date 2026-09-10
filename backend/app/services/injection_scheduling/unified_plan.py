"""Versioned four-factory input contract. Never derives master data from orders."""

import json
from pathlib import Path

from .calculations import decimal, quantities, timestamp
from .common import jsonable
from .field_registry import FACTORIES, column_name
from .requirement_parser import dispatch_from_text
from .sparse_xlsx import excel_date

CONTRACT = json.loads(
    Path(__file__).with_name("unified_template.json").read_text("utf-8")
)
VERSION = CONTRACT["version"]
TEMPLATE_PATH = Path(__file__).with_name("templates") / "injection-plan-v1.xlsx"


def text(value):
    return "" if value is None else str(value).strip()


def date_value(value, date1904):
    dt = excel_date(value, date1904)
    if dt is None:
        try:
            dt = timestamp(value)
        except (ValueError, TypeError):
            return None
    return dt.isoformat() if dt and 2000 <= dt.year <= 2100 else None


def process_fields(fields):
    parts = text(fields.get("material_raw")).split(maxsplit=1)
    return {
        "dispatch_state": dispatch_from_text(
            f"{fields.get('order_note') or ''} {fields.get('production_note') or ''}"
        ),
        "resin": parts[0].upper() if parts else fields.get("resin"),
        "material_grade": (parts[1] if len(parts) > 1 else None)
        if parts
        else fields.get("material_grade"),
    }


def read_unified(source):
    rows = source["rows"]

    def cell(row, col):
        return rows.get(row, {}).get(col, {})

    def value(row, col):
        return cell(row, col).get("cached_value")

    marker = text(value(2, "A"))
    # A damaged version marker must not fall through to the legacy fuzzy header path.
    looks_unified = value(6, "A") == "需求编号" and value(6, "C") == "机内顺序"
    if not marker.startswith("RR_INJECTION_UNIFIED") and not looks_unified:
        return None
    if marker != VERSION or cell(2, "A").get("formula_expanded"):
        raise ValueError("统一模板版本不支持或标识已修改，请重新下载统一模板")
    for i, (_, label, _) in enumerate(CONTRACT["columns"], 1):
        if value(6, column_name(i)) != label:
            raise ValueError(
                f"统一模板第 6 行表头不符：{column_name(i)} 列应为“{label}”"
            )
    factory = text(value(3, "B"))
    factory = next(
        (
            key
            for key, label in FACTORIES.items()
            if factory.replace(" ", "") == label.replace(" ", "")
        ),
        factory,
    )
    if factory not in FACTORIES or cell(3, "B").get("formula_expanded"):
        raise ValueError("请在 B3 选择华兴、华登、华康A或华康B厂区")
    start = date_value(value(3, "E"), source["date1904"])
    if not start or cell(3, "E").get("formula_expanded"):
        raise ValueError("请在 E3 填写固定排期起点（日期和时间，不使用 NOW 公式）")
    demands, identities, positions = [], set(), set()
    columns = [(column_name(i), *spec) for i, spec in enumerate(CONTRACT["columns"], 1)]
    for number in sorted(r for r in rows if r >= 7):
        if not any(
            value(number, col) not in (None, "")
            or cell(number, col).get("formula_expanded")
            for col, _, _, kind in columns
            if kind != "calculated"
        ):
            continue
        if len(demands) >= 5000:
            raise ValueError("统一模板每次最多导入 5000 条需求")
        fields, issues = {}, []

        def issue(message, field=None, issues=issues):
            issues.append(
                {"code": "UNIFIED_INVALID_ROW", "message": message, "field": field}
            )

        for col, key, label, kind in columns:
            if kind == "calculated":
                continue  # Recompute from inputs; Excel caches are not operational facts.
            raw, evidence = value(number, col), cell(number, col)
            if evidence.get("type") == "e" or (
                evidence.get("formula_expanded") and raw is None
            ):
                issue(f"{label}公式结果缺失或错误，请在 Excel 重新计算保存", key)
                fields[key] = None
                continue
            if kind in {"number", "integer"}:
                n = decimal(raw)
                if raw not in (None, "") and (
                    n is None or n < 0 or n >= 1e14 or kind == "integer" and n % 1
                ):
                    issue(
                        f"{label}必须为有效非负{'整数' if kind == 'integer' else '数字'}",
                        key,
                    )
                    n = None
                fields[key] = float(n) if n is not None else None
            elif kind == "datetime":
                fields[key] = (
                    date_value(raw, source["date1904"])
                    if raw not in (None, "")
                    else None
                )
                if raw not in (None, "") and fields[key] is None:
                    issue(f"{label}不是有效日期", key)
            else:
                fields[key] = text(raw)
                if len(fields[key]) > (4000 if key.endswith("note") else 200):
                    issue(f"{label}文字过长", key)
        for key, label in (("source_line_id", "需求编号"), ("mold_code", "模号")):
            if not fields.get(key):
                issue(f"{label}不能为空", key)
        identity = fields.get("source_line_id")
        if identity in identities:
            issue("需求编号重复；同单拆行也应各用一个固定编号", "source_line_id")
        identities.add(identity)
        for key, label in (
            ("planned_shots", "计划啤数"),
            ("completed_shots", "已啤数"),
        ):
            if fields.get(key) is None:
                issue(f"{label}不能为空；没有已啤数请填 0", key)
        for key, label in (
            ("required_machine_a", "模具机安 A"),
            ("target_shots_per_day", "计划日目标"),
        ):
            if fields.get(key) == 0:
                issue(f"{label}须大于 0，未知时留空", key)
        machine, order = fields.get("machine_code"), fields.get("queue_order")
        if machine:
            if order is None or order < 1:
                issue("已排机行必须填写大于 0 的机内顺序", "queue_order")
            if (machine, order) in positions:
                issue("同一机号的机内顺序不能重复", "queue_order")
            positions.add((machine, order))
        elif order is not None:
            issue("未排机行请同时留空机号和机内顺序", "queue_order")
        fields.update(
            jsonable(
                quantities({**fields, "opening_shots": fields.get("completed_shots")})
            )
        )
        fields.update(process_fields(fields))
        demands.append(
            {
                "source_row": number,
                "row_role": "demand",
                "fields": fields,
                "issues": issues,
                "source_cells": {
                    col: cell(number, col) for col, *_ in columns if cell(number, col)
                },
            }
        )
    if not demands:
        raise ValueError(
            "统一模板没有需求，请从第 7 行填写正式数据；填写说明中的示例不参与导入"
        )
    return {
        "sha256": source["sha256"],
        "unified": {"version": VERSION, "factory_id": factory, "as_of": start},
        "demands": demands,
        "machines": [],
        "structure_rows": [],
        "statistics": {
            "demand_count": len(demands),
            "assigned_count": sum(bool(d["fields"]["machine_code"]) for d in demands),
        },
    }
