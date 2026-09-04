"""Pure, read-only statistics for legacy 3D state and validated image metadata.

This module neither opens the application database nor imports application config.
Only allowlisted fields reach the report; raw records and device config never do.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import math
import re
import statistics
import unicodedata
from typing import Any


def _number(value: Any) -> Decimal:
    if value is None or value == "" or isinstance(value, bool):
        return Decimal(0)
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else Decimal(0)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _report_number(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("numeric_report_value_out_of_range")
    return result


def _normalized(value: Any) -> str:
    return re.sub(r"[\s_]+", "", unicodedata.normalize("NFKC", _text(value))).casefold()


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone(timedelta(hours=8)))
        return result.astimezone(timezone.utc)
    except ValueError:
        return None


def _duplicates(values: list[Any]) -> tuple[int, int]:
    counts = Counter(values)
    return sum(v > 1 for v in counts.values()), sum(v - 1 for v in counts.values() if v > 1)


def _percentile(values: list[float | int], percentile: float) -> float | int | None:
    """Linear interpolation at (n - 1) * p, matching the supplied audit."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def derive_run_status(record: dict) -> str:
    """Legacy 'running' is a row type, never evidence of a live device job."""
    start, end = _time(record.get("printStartTime")), _time(record.get("printEndTime"))
    status = _text(record.get("status")).strip().casefold()
    remark = _text(record.get("remark")).strip().casefold()
    failed = status in {"failed", "failure", "error", "cancelled", "canceled", "失败"} or bool(
        re.search(r"(?:^|[\s:：,，;；])(?:failed|failure|cancelled|canceled)(?:$|[\s:：,，;；])", remark)
        or re.search(r"(?:打印失败|任务失败|已取消)", remark)
    )
    if end:
        if failed:
            return "failed"
        return "succeeded" if start else "succeeded_with_incomplete_timing"
    if start:
        return "running_pending_reconciliation"
    if status == "done":
        return "succeeded_with_incomplete_timing"
    return "unknown"


def analyze_state(state: dict, images: list[dict], *, source_kind: str = "sqlite") -> dict:
    """Return reproducible statistics without changing state or exposing config.

    ``images`` contains validated metadata, never image bytes. Embedded JSON image
    counts are diagnostic only; callers must explicitly authorize JSON fallback.
    """
    if not isinstance(state, dict):
        raise ValueError("invalid_state_shape")
    anomalies: list[dict] = []

    def issue(code: str, domain: str, row: dict, field: str | None = None) -> None:
        item = {"code": code, "domain": domain, "legacy_id": _text(row.get("_id", row.get("id", row.get("product_id"))))}
        if field:
            item["field"] = field
        anomalies.append(item)

    def rows(name: str) -> list[dict]:
        value = state.get(name, [])
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError(f"invalid_{name}_shape")
        return value

    products, materials = rows("products"), rows("materials")
    logs, schedules, maintenance = rows("stockInLogs"), rows("schedules"), rows("maintenance")
    days, inventory = state.get("records", {}), state.get("inventory", {})
    if not isinstance(days, dict) or not isinstance(inventory, dict):
        raise ValueError("invalid_records_or_inventory_shape")
    records: list[dict] = []
    for day, value in days.items():
        if not isinstance(value, dict) or not isinstance(value.get("items", []), list):
            raise ValueError("invalid_record_day_shape")
        if any(not isinstance(row, dict) for row in value.get("items", [])):
            raise ValueError("invalid_record_item_shape")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)) or _time(str(day)) is None:
            anomalies.append({"code": "invalid_business_date", "domain": "records"})
        records.extend(value.get("items", []))
    if any(not isinstance(value, dict) for value in inventory.values()):
        raise ValueError("invalid_inventory_item_shape")
    active = [row for row in records if not row.get("_deleted")]
    settings = state.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("invalid_settings_shape")
    safe_settings = {key: _report_number(_number(settings[key])) for key in (
        "machines", "elecPerMachine", "laborPerDay", "lossRate", "profitRate"
    ) if key in settings}
    numeric_domains = [
        ("products", products, ("weight", "time", "price", "qty")),
        ("records", records, ("weight", "time", "price", "qty", "designFee")),
        ("materials", materials, ("priceKg",)),
        ("stockInLogs", logs, ("amountG", "cost")),
        ("inventory", list(inventory.values()), ("stockG", "minStockG")),
        ("settings", [settings], tuple(safe_settings)),
    ]
    for domain, values, fields in numeric_domains:
        for row in values:
            for field in fields:
                value = row.get(field)
                if value is None or value == "":
                    continue
                try:
                    parsed = Decimal(str(value))
                    valid = not isinstance(value, bool) and parsed.is_finite()
                except (InvalidOperation, ValueError, TypeError):
                    valid = False
                if not valid:
                    issue("invalid_numeric", domain, row, field)
                elif parsed < 0:
                    issue("negative_numeric", domain, row, field)
    off_dates = sorted(day for day, value in days.items() if value.get("off"))
    counts = {
        "settings": safe_settings, "materials": len(materials), "products": len(products),
        "product_images": len(images), "record_dates": len(days),
        "date_min": min(days, default=None), "date_max": max(days, default=None),
        "off_days": len(off_dates), "off_day_dates": off_dates,
        "records_stored": len(records), "records_active": len(active),
        "records_tombstoned": len(records) - len(active), "inventory_items": len(inventory),
        "stock_in_logs": len(logs), "schedules": len(schedules), "maintenance": len(maintenance),
        "configured_machine_count": safe_settings.get("machines", 0),
    }
    id_quality = {}
    for domain, values, key in (("products", products, "id"), ("materials", materials, "id"), ("records", records, "_id")):
        ids = [_text(row.get(key)) for row in values]
        duplicates = Counter(ids)
        id_quality[domain] = {"missing": ids.count(""), "duplicate_groups": _duplicates([v for v in ids if v])[0]}
        for row in values:
            if not _text(row.get(key)):
                issue("missing_legacy_id", domain, row, key)
            elif duplicates[_text(row.get(key))] > 1:
                issue("duplicate_legacy_id", domain, row, key)

    product_names = [_text(row.get("name")) for row in products]
    product_name_counts = Counter(product_names)
    exact_groups, exact_extra = _duplicates(product_names)
    norm_groups, norm_extra = _duplicates([_normalized(name) for name in product_names])
    pq = {
        "ids_unique": not any(id_quality["products"].values()),
        "empty_name": sum(not name.strip() for name in product_names),
        "missing_customer": sum(not _text(row.get("customer")).strip() for row in products),
        "exact_duplicate_name_groups": exact_groups, "exact_duplicate_extra_rows": exact_extra,
        "normalized_duplicate_name_groups": norm_groups, "normalized_duplicate_extra_rows": norm_extra,
    }
    for field in ("weight", "time", "price"):
        pq[f"zero_or_missing_{field}"] = sum(_number(row.get(field)) <= 0 for row in products)
    for row in products:
        if not _text(row.get("name")).strip():
            issue("missing_product_name", "products", row, "name")
        elif product_name_counts[_text(row.get("name"))] > 1:
            issue("duplicate_product_name", "products", row, "name")
        for field in ("weight", "time", "price"):
            if _number(row.get(field)) <= 0:
                issue("zero_or_missing_numeric", "products", row, field)
        if not _text(row.get("customer")).strip():
            issue("missing_customer", "products", row, "customer")

    rq = {
        "machine_counts": dict(sorted(Counter(_text(row.get("machine")) for row in active).items())),
        "status_counts": dict(sorted(Counter(_text(row.get("status")) for row in active).items())),
        "auto_records": sum(bool(row.get("autoRecord")) for row in active),
        "manual_records": sum(not row.get("autoRecord") for row in active),
        "open_records_missing_end_time": sum(bool(row.get("printStartTime")) and not row.get("printEndTime") for row in active),
        "records_with_start_and_end": 0,
        "missing_start_with_end": sum(not row.get("printStartTime") and bool(row.get("printEndTime")) for row in active),
    }
    durations = []
    run_statuses: Counter = Counter()
    for row in active:
        run_status = derive_run_status(row)
        run_statuses[run_status] += 1
        if run_status == "running_pending_reconciliation":
            issue("pending_device_reconciliation", "records", row)
        start, end = _time(row.get("printStartTime")), _time(row.get("printEndTime"))
        for field in ("printStartTime", "printEndTime", "createdAt"):
            if row.get(field) and _time(row[field]) is None:
                issue("invalid_timestamp", "records", row, field)
        if start and end:
            rq["records_with_start_and_end"] += 1
            hours = (end - start).total_seconds() / 3600
            durations.append(hours)
            if hours < 0 or hours > 96:
                issue("negative_duration" if hours < 0 else "duration_over_96h", "records", row)
        for field in ("weight", "time", "price"):
            if _number(row.get(field)) <= 0:
                issue("zero_or_missing_numeric", "records", row, field)
        for field in ("material", "customer", "productName"):
            if not _text(row.get(field)).strip():
                issue("missing_field", "records", row, field)
    rq.update({
        "derived_run_status_counts": dict(sorted(run_statuses.items())),
        "negative_duration": sum(value < 0 for value in durations),
        "duration_over_96h": sum(value > 96 for value in durations),
        "duration_hours_median": round(statistics.median(durations), 3) if durations else None,
        "duration_hours_p95": round(_percentile(durations, .95), 3) if durations else None,
        "duration_hours_max": round(max(durations), 3) if durations else None,
    })
    for field in ("weight", "time", "price"):
        rq[f"zero_or_missing_{field}"] = sum(_number(row.get(field)) <= 0 for row in active)
    for field, output in (("material", "missing_material"), ("customer", "missing_customer"), ("productName", "missing_product_name")):
        rq[output] = sum(not _text(row.get(field)).strip() for row in active)
    fingerprints = [tuple(_text(row.get(key)) for key in ("machine", "printStartTime", "printEndTime", "_gcodeFile", "productName")) for row in active]
    rq["duplicate_fingerprint_groups"], rq["duplicate_fingerprint_extra_rows"] = _duplicates(fingerprints)
    master = defaultdict(list)
    for row in products:
        master[_text(row.get("name"))].append(row)
    # Blank names are counted separately, not treated as a distinct product.
    record_names = [_text(row.get("productName")) for row in active if _text(row.get("productName")).strip()]
    normalized_master = {_normalized(name) for name in master}
    rq.update({
        "unique_record_product_names": len(set(record_names)),
        "record_product_names_not_exact_master": len({name for name in record_names if name not in master}),
        "record_rows_not_exact_master": sum(name not in master for name in record_names),
        "record_product_names_not_normalized_master": len({name for name in record_names if _normalized(name) not in normalized_master}),
        "record_rows_not_normalized_master": sum(_normalized(name) not in normalized_master for name in record_names),
    })
    drift = {field: 0 for field in ("material", "qty", "customer", "weight", "time", "price")}
    compared = 0
    for row in active:
        candidates = master.get(_text(row.get("productName")), [])
        if len(candidates) != 1:
            issue("unmatched_product_name" if not candidates else "ambiguous_product_name", "records", row, "productName")
            continue
        compared += 1
        for field in drift:
            left, right = row.get(field), candidates[0].get(field)
            different = _text(left) != _text(right) if field in ("material", "customer") else _number(left) != _number(right)
            drift[field] += different
    rq["snapshot_rows_compared_to_unique_current_product"] = compared
    rq["snapshot_drift_counts"] = drift

    material_names = [_text(row.get("name")) for row in materials]
    aliases = defaultdict(set)
    for name in material_names + list(inventory):
        aliases[_normalized(name)].add(name)
    mq = {
        "material_master_names": material_names, "inventory_names": sorted(inventory),
        "inventory_not_in_master": sorted(set(inventory) - set(material_names)),
        "record_material_not_in_master": sorted({_text(row.get("material")) for row in active if _text(row.get("material")).strip()} - set(material_names)),
        "normalized_alias_groups": sorted([sorted(names) for names in aliases.values() if len(names) > 1]),
        "blank_material_record_rows": rq["missing_material"],
        "inventory_total_g": _report_number(sum((_number(row.get("stockG")) for row in inventory.values()), Decimal(0))),
        "inventory_below_min_count": sum(_number(row.get("stockG")) < _number(row.get("minStockG")) for row in inventory.values()),
        "inventory_at_or_below_min_count": sum(_number(row.get("stockG")) <= _number(row.get("minStockG")) for row in inventory.values()),
        "stock_in_total_g": _report_number(sum((_number(row.get("amountG")) for row in logs), Decimal(0))),
        "stock_in_total_cost": _report_number(sum((_number(row.get("cost")) for row in logs), Decimal(0))),
    }
    product_ids = {_text(row.get("id")) for row in products}
    image_ids = {_text(row.get("product_id")) for row in images}
    sizes = [int(_number(row.get("size_bytes"))) for row in images]
    hashes = [row["content_sha256"] for row in images if row.get("content_sha256")]
    groups, extras = _duplicates(hashes)
    iq = {
        "rows": len(images), "products_with_image": len(product_ids & image_ids),
        "products_missing_image": len(product_ids - image_ids),
        "orphan_image_rows": sum(_text(row.get("product_id")) not in product_ids for row in images),
        "coverage_percent": round(100 * len(product_ids & image_ids) / len(product_ids), 2) if product_ids else 0,
        "total_bytes": sum(sizes), "total_mib": round(sum(sizes) / 1024 ** 2, 2),
        "median_bytes": int(statistics.median(sizes)) if sizes else None,
        "p95_bytes": int(_percentile(sizes, .95)) if sizes else None, "max_bytes": max(sizes, default=None),
        "mime_counts": dict(sorted(Counter(_text(row.get("mime_type")) for row in images).items())),
        "duplicate_hash_groups": groups, "duplicate_extra_rows": extras,
        "invalid_images": sum(row.get("valid") is not True for row in images),
        "legacy_content_hash_mismatches": sum(bool(row.get("legacy_sha256")) and row.get("legacy_sha256") != row.get("content_sha256") for row in images),
    }
    for row in images:
        if row.get("valid") is not True:
            issue("invalid_image", "images", row)
        if _text(row.get("product_id")) not in product_ids:
            issue("orphan_image", "images", row)
    totals = {
        "quantity_total": _report_number(sum((_number(row.get("qty")) for row in active), Decimal(0))),
        "planned_material_g_total": _report_number(sum((_number(row.get("weight")) * _number(row.get("qty")) for row in active), Decimal(0))),
        "design_fee_total": _report_number(sum((_number(row.get("designFee")) for row in active), Decimal(0))),
        "quoted_revenue_total": _report_number(sum((_number(row.get("price")) * _number(row.get("qty")) for row in active), Decimal(0))),
    }
    report = {
        "source_kind": source_kind, "authoritative_sqlite" if source_kind == "sqlite" else "data_json_snapshot": counts,
        "products_quality": pq, "records_quality": rq, "materials_inventory_quality": mq,
        "images_quality": iq, "business_totals_active_records": totals,
        "legacy_id_quality": id_quality, "anomalies": anomalies,
        "anomaly_counts": dict(sorted(Counter(row["code"] for row in anomalies).items())),
        "analysis_semantics": {
            "percentiles": "linear_interpolation_image_byte_results_truncated", "business_totals": "active_records_only_decimal_arithmetic",
            "inventory": "opening_balance_only_stock_in_logs_do_not_affect_balance",
            "aliases": "suggestions_only_original_names_preserved",
            "historical_snapshots": "compared_to_unique_exact_master_name_never_rewritten",
            "configured_printers": "not_read_from_secret_config_machine_count_is_settings_only",
        },
    }
    if source_kind != "sqlite":
        counts["product_images_embedded"] = sum(bool(row.get("image")) for row in products)
        report["warnings"] = ["json_fallback_may_be_stale_not_authoritative_for_cutover"]
    return report
