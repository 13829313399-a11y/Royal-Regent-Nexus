"""Selected-sheet exchange with per-field and per-report optimistic merging."""

import json
from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from .calculations import decimal, timestamp
from .common import record, touch
from .enrichment import apply_demand_fields
from .export_plan import SCHEMA
from .field_registry import FIELDS, column_name
from .sparse_xlsx import excel_date


def same_value(key, left, right):
    """Excel dates lose sub-millisecond precision; blank is not numeric zero."""
    if left in (None, "") and right in (None, ""):
        return True
    spec = FIELDS.get(key)
    if spec and spec.value_type == "datetime" and left and right:
        try:
            return abs(timestamp(left) - timestamp(right)) < timedelta(milliseconds=2)
        except (ValueError, TypeError):
            return False
    if spec and spec.value_type in {"integer", "number"} or "|" in key:
        a, b = decimal(left), decimal(right)
        return a is not None and b is not None and a == b or left == right
    return left == right


def read_exchange(source):
    rows = source["rows"]
    marker = rows.get(2, {}).get("A", {}).get("cached_value")
    if not isinstance(marker, str) or not marker.startswith("INJECTION_V3:"):
        return None
    try:
        meta = json.loads(marker[len("INJECTION_V3:") :])
    except (ValueError, TypeError):
        raise ValueError("交换表元数据损坏") from None
    if not isinstance(meta, dict) or meta.get("schema_version") != SCHEMA:
        raise ValueError("交换表版本不支持")
    keys = meta.get("field_keys", [])
    if (
        not isinstance(keys, list)
        or not keys
        or len(keys) > 1000
        or not all(isinstance(k, str) for k in keys)
        or len(keys) != len(set(keys))
        or not {"id", "roundtrip_baseline"} <= set(keys)
    ):
        raise ValueError("交换表字段契约不正确")
    baseline_parts = meta.get("baseline_parts", ["roundtrip_baseline"])
    if (
        not isinstance(baseline_parts, list)
        or not baseline_parts
        or len(baseline_parts) > 32
        or baseline_parts[0] != "roundtrip_baseline"
        or any(
            not isinstance(k, str)
            or k not in keys
            or not k.startswith("roundtrip_baseline")
            for k in baseline_parts
        )
    ):
        raise ValueError("交换表基线分段不正确")
    parsed = []
    for row, cells in sorted(rows.items()):
        if row <= 3:
            continue
        values = {
            key: cells.get(column_name(i), {}).get("cached_value")
            for i, key in enumerate(keys, 1)
        }
        if not values.get("id"):
            continue
        issues = []
        for i, key in enumerate(keys, 1):
            cell = cells.get(column_name(i), {})
            if (
                cell.get("formula_attributes") is not None
                and cell.get("cached_value") is None
            ):
                issues.append(
                    {
                        "field": key,
                        "code": "FORMULA_CACHE_MISSING",
                        "message": "公式尚无计算缓存，请在 Excel/WPS 重算；此格保持服务器值。",
                    }
                )
            if cell.get("type") == "e":
                issues.append(
                    {
                        "field": key,
                        "code": "SOURCE_CELL_ERROR",
                        "raw": cell.get("cached_value"),
                    }
                )
            if (
                key in FIELDS
                and FIELDS[key].value_type == "datetime"
                and values[key] is not None
            ):
                try:
                    dt = (
                        excel_date(values[key], source["date1904"])
                        if isinstance(values[key], (int, float))
                        else timestamp(values[key])
                    )
                    values[key] = dt.isoformat() if dt else None
                    if dt is None:
                        raise ValueError
                except (TypeError, ValueError):
                    issues.append({"field": key, "code": "INVALID_DATE"})
            elif (
                key in FIELDS
                and FIELDS[key].value_type == "json"
                and isinstance(values[key], str)
            ):
                try:
                    values[key] = json.loads(values[key])
                except ValueError:
                    issues.append({"field": key, "code": "INVALID_JSON"})
        try:
            baseline = json.loads(
                "".join(values.get(part) or "" for part in baseline_parts) or "null"
            )
            if not isinstance(baseline, dict) or not isinstance(
                baseline.get("fields"), dict
            ):
                raise TypeError
            if any(
                not isinstance(baseline.get(key, {}), dict)
                for key in ("reports", "shift_values", "report_targets")
            ):
                raise TypeError
        except (TypeError, ValueError):
            baseline = {}
            issues.append({"code": "MISSING_ROUNDTRIP_BASELINE"})
        parsed.append(
            {
                "source_row": row,
                "row_role": "EXCHANGE_DEMAND",
                "fields": values,
                "baseline": baseline,
                "issues": issues,
                "history": [],
            }
        )
    return {
        "parser_version": "injection-v3-plan-1",
        "sha256": source["sha256"],
        "sheet_name": source["sheet_name"],
        "exchange": meta,
        "demands": parsed,
        "machines": [],
        "structure_rows": [],
        "statistics": {
            "task_candidate_count": len(parsed),
            "machine_count": 0,
            "numeric_shift_cell_count": 0,
        },
        "read_worksheets": source["read_worksheets"],
        "formula_cells": source["formula_cells"],
    }


def apply_exchange(db, batch, actor):
    from app.models.injection_scheduling import (
        Demand,
        ImportRow,
        Run,
        RunDemand,
        ShiftReport,
    )
    from app.schemas.injection_scheduling import ReportWrite

    from .reports import reallocate_factory, save_report

    meta = batch.evidence["exchange"]
    if meta.get("factory_id") != batch.factory_id:
        raise HTTPException(422, "交换表厂区与当前厂区不一致")
    applied, unchanged, conflicts, report_changes = [], [], [], []
    seen_reports = {}
    requested_reports = {}
    for candidate in batch.evidence["demands"]:
        baseline = candidate.get("baseline", {})
        for key, incoming in candidate["fields"].items():
            if "|" not in key or same_value(
                key, incoming, baseline.get("shift_values", {}).get(key)
            ):
                continue
            target = baseline.get("report_targets", {}).get(key, {})
            report_key = (
                target.get("report_key", {}) if isinstance(target, dict) else {}
            )
            if not isinstance(report_key, dict):
                continue
            identity = tuple(
                str(report_key.get(k, "default" if k == "segment_key" else ""))
                for k in ("run_id", "production_date", "shift_code", "segment_key")
            )
            requested_reports.setdefault(identity, set()).add(
                str(decimal(incoming))
                if decimal(incoming) is not None
                else repr(incoming)
            )
    for row in batch.evidence["demands"]:
        value = row["fields"]
        obj = db.get(Demand, value["id"])
        local = []
        changed = False

        def conflict(
            code,
            field=None,
            source_row=row["source_row"],
            demand_id=value["id"],
            items=local,
            **details,
        ):
            entry = {
                "source_row": source_row,
                "demand_id": demand_id,
                "code": code,
                **details,
            }
            if field:
                entry["field"] = field
            items.append(entry)

        if obj is None or obj.factory_id != batch.factory_id:
            conflict("UNKNOWN_SCOPED_DEMAND")
        elif any(not issue.get("field") for issue in row["issues"]):
            conflict("MISSING_ROUNDTRIP_BASELINE")
        else:
            baseline = row["baseline"].get("fields", {})
            blocked = {
                issue["field"]: issue for issue in row["issues"] if issue.get("field")
            }
            current = record(obj)
            active = (
                db.get(Run, (obj.extras or {}).get("active_run_id"))
                if (obj.extras or {}).get("active_run_id")
                else None
            )
            for key, incoming in value.items():
                if key not in FIELDS or not FIELDS[key].editable:
                    continue
                if key in blocked:
                    conflict(blocked[key]["code"], key)
                    continue
                if key not in baseline:
                    conflict("MISSING_FIELD_BASELINE", key)
                    continue
                if same_value(key, incoming, baseline[key]) or same_value(
                    key, incoming, current.get(key)
                ):
                    continue
                if not same_value(key, current.get(key), baseline[key]):
                    conflict(
                        "FIELD_CONFLICT",
                        key,
                        baseline=baseline[key],
                        server=current.get(key),
                        incoming=incoming,
                    )
                    continue
                if (
                    active
                    and active.status in {"RUNNING", "PAUSED"}
                    and key
                    not in {
                        "planned_shots",
                        "adjustment_shots",
                        "required_units",
                        "order_note",
                        "production_note",
                        "warehouse_note",
                        "delivery_due_at",
                        "priority_level",
                    }
                ):
                    conflict("RUNNING_SNAPSHOT", key)
                    continue
                try:
                    with db.begin_nested():
                        apply_demand_fields(db, obj, {key: incoming}, actor)
                    changed = True
                except HTTPException as exc:
                    conflict("INVALID_FIELD", key, message=str(exc.detail))
            for key, incoming in value.items():
                if "|" not in key:
                    continue
                if key in blocked:
                    conflict(blocked[key]["code"], key)
                    continue
                old = row["baseline"].get("shift_values", {}).get(key)
                if same_value(key, incoming, old):
                    continue
                target = row["baseline"].get("report_targets", {}).get(key)
                if not isinstance(target, dict) or not isinstance(
                    target.get("report_key"), dict
                ):
                    conflict(
                        "SHIFT_NOT_UNIQUE_PHYSICAL_REPORT",
                        key,
                        message="历史格、组批分配格或多个执行段不能当作单一物理报数，请在班次报工面修改。",
                    )
                    continue
                report_key = target["report_key"]
                try:
                    production_date, shift_code = key.split("|")
                    run = db.get(Run, report_key.get("run_id"))
                    link = db.scalar(
                        select(RunDemand).where(
                            RunDemand.run_id == report_key.get("run_id"),
                            RunDemand.demand_id == obj.id,
                            RunDemand.factory_id == batch.factory_id,
                        )
                    )
                    count = db.scalar(
                        select(func.count())
                        .select_from(RunDemand)
                        .where(RunDemand.run_id == report_key.get("run_id"))
                    )
                    if (
                        not run
                        or run.factory_id != batch.factory_id
                        or not link
                        or count != 1
                        or link.allocation_mode != "SEQUENTIAL_SHOTS"
                        or report_key.get("production_date") != production_date
                        or report_key.get("shift_code") != shift_code
                    ):
                        raise HTTPException(422, "报工映射与当前需求或物理批次不一致")
                    number = decimal(incoming)
                    if number is None or number < 0 or number % 1:
                        raise HTTPException(
                            422, "班次数必须为非负整数；空白不表示删除报工，请明确填 0"
                        )
                    identity = (
                        run.id,
                        production_date,
                        shift_code,
                        report_key.get("segment_key", "default"),
                    )
                    if len(requested_reports.get(identity, ())) > 1:
                        conflict(
                            "DUPLICATE_REPORT_CONFLICT",
                            key,
                            message="同一文件对同一个物理报工键给出多个不同数量，相关格均未应用。",
                        )
                        continue
                    if identity in seen_reports:
                        if seen_reports[identity] != number:
                            conflict("DUPLICATE_REPORT_CONFLICT", key)
                        continue
                    report = db.scalar(
                        select(ShiftReport).where(
                            ShiftReport.run_id == run.id,
                            ShiftReport.production_date
                            == date.fromisoformat(production_date),
                            ShiftReport.shift_code == shift_code,
                            ShiftReport.segment_key == identity[3],
                        )
                    )
                    if report and report.physical_shots == number:
                        seen_reports[identity] = number
                        continue
                    payload = ReportWrite(
                        factory_id=batch.factory_id,
                        base_revision=0,
                        client_operation_id=f"excel:{batch.id}:{row['source_row']}:{key}",
                        **report_key,
                        physical_shots=int(number),
                        report_revision=target.get("revision", 0),
                        good_units=report.good_units if report else {},
                        scrap_units=report.scrap_units if report else {},
                    )
                    with db.begin_nested():
                        result = save_report(db, payload, actor)
                    seen_reports[identity] = number
                    report_changes.append(
                        {
                            "source_row": row["source_row"],
                            "field": key,
                            "report_key": report_key,
                            "report_id": result["report"]["id"],
                            "physical_delta": result["physical_delta"],
                        }
                    )
                    changed = True
                except HTTPException as exc:
                    conflict(
                        "REPORT_CONFLICT"
                        if exc.status_code == 409
                        else "INVALID_SHIFT_VALUE",
                        key,
                        message=str(exc.detail),
                    )
                except (ValueError, TypeError, ValidationError):
                    conflict("INVALID_REPORT_METADATA", key)
            (applied if changed else unchanged).append(obj.id)
        conflicts.extend(local)
        db.add(
            ImportRow(
                batch_id=batch.id,
                source_row=row["source_row"],
                row_role="EXCHANGE_DEMAND",
                demand_id=obj.id
                if obj and obj.factory_id == batch.factory_id
                else None,
                evidence=row,
                issues=local,
            )
        )
    db.flush()
    if applied:
        reallocate_factory(db, batch.factory_id)
    batch.status = "APPLIED"
    batch.summary = {
        **batch.summary,
        "applied_count": len(set(applied)),
        "unchanged_count": len(set(unchanged) - set(applied)),
        "report_changes": report_changes,
        "conflicts": conflicts,
        "original_assignments": [],
    }
    touch(batch, actor)
    return {
        "batch_id": batch.id,
        "summary": batch.summary,
        "demand_ids": list(dict.fromkeys(applied)),
        "recalculate_required": bool(applied or report_changes),
        "changed_runs": [],
    }
