"""Stable identities and conservative changes for imported business ITEM schedules."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any


TRACKED_TYPES = {"正单", "正式PO", "加单", "改单"}


def customer_key(row: dict[str, Any]) -> str:
    if row.get("schedule_customer_code"):
        return "master:" + unicodedata.normalize("NFKC", str(row["schedule_customer_code"])).strip().casefold()
    return unicodedata.normalize("NFKC", str(row.get("source_customer_name") or row.get("customer_name") or "")).strip().casefold()


def normalized(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def effective_po(row: dict[str, Any]) -> str:
    return normalized(row.get("source_reference")) or normalized(row.get("customer_po"))


def identity(row: dict[str, Any]) -> str:
    customer = customer_key(row)
    contract = unicodedata.normalize("NFKC", str(row.get("contract_no") or "")).strip().casefold()
    item = unicodedata.normalize("NFKC", str(row.get("item_no") or "")).strip().casefold()
    if not customer or not contract or not item:
        return ""
    # The matching identity uses SO first, falling back to P/O only when SO is blank.
    source_reference = effective_po(row)
    parts = [customer, contract, item, source_reference] if source_reference else [customer, contract, item]
    source = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def legacy_identity(row: dict[str, Any]) -> str:
    """Pre-SO identity, used only to migrate unambiguous audit evidence on read."""
    return identity({**row, "source_reference": "", "customer_po": ""})


def so_identity(row: dict[str, Any]) -> str:
    """The v4 identity, before blank SO started falling back to P/O."""
    return identity({**row, "customer_po": ""})


def demand_snapshot(row: dict[str, Any]) -> dict[str, str]:
    def number(value):
        try:
            parsed = Decimal(str(value))
            return format(parsed.normalize(), "f") if parsed.is_finite() else normalized(value)
        except (InvalidOperation, ValueError):
            return normalized(value)
    packing = re.sub(r"\s+", "", normalized(row.get("carton_rule")))
    if re.fullmatch(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?", packing):
        packing = "/".join(number(value) for value in packing.split("/"))
    return {
        "quantity": number(row.get("quantity")), "carton_rule": packing,
        "inspection_window": normalized(row.get("inspection_window") or row.get("source_inspection_window")),
        "customer_due_date": normalized(row.get("customer_due_date") or row.get("source_customer_due_date")),
    }


def mark_changes(row: dict[str, Any], mark: dict[str, Any] | None) -> list[str]:
    if mark and mark.get("review_required"):
        return ["原下单依据待核实"]
    if not mark or not mark.get("marked"):
        return []
    frozen = mark.get("demand_snapshot")
    if not isinstance(frozen, dict) or set(frozen) != set(demand_snapshot(row)):
        return ["原下单依据待核实"]
    labels = {"quantity": "数量", "carton_rule": "装箱", "inspection_window": "验货日期", "customer_due_date": "客户交期"}
    return [labels[key] for key, value in demand_snapshot(row).items() if frozen[key] != value]


def mark_for_row(row: dict[str, Any], marks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    key = str(row.get("schedule_identity") or identity(row))
    if key in marks:
        return marks[key]
    if any(marks.get(alias, {}).get("marked") or marks.get(alias, {}).get("review_required")
           for alias in {legacy_identity(row), so_identity(row)} - {key}):
        return {"marked": False, "review_required": True, "demand_snapshot": None}
    return {"marked": row.get("manual_ordered", False)}


def operation_identity(row: dict[str, Any], batch_id: str, duplicate: bool) -> str:
    key = identity(row)
    if not key or not duplicate:
        return key
    source = json.dumps([key, batch_id, row.get("source_sheet"), row.get("source_row")],
                        ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def tracked(row: dict[str, Any]) -> bool:
    order_type = str(row.get("order_type") or "").strip()
    return order_type in TRACKED_TYPES or (
        not order_type and row.get("schedule_section") in {"CANCELLED", "SHIPPED"}
    )


def annotate_changes(
    rows: list[dict[str, Any]],
    previous_by_customer: dict[str, list[dict[str, Any]]],
    ordered_marks: set[str],
) -> None:
    """Compare explicit sections only; absence from a later file is never cancellation."""
    current_counts = Counter(identity(row) for row in rows if tracked(row) and identity(row))
    previous_indexes: dict[str, dict[str, dict[str, Any]]] = {}
    previous_counts: dict[str, Counter[str]] = {}
    for customer, previous in previous_by_customer.items():
        previous_counts[customer] = Counter(identity(row) for row in previous if tracked(row) and identity(row))
        previous_indexes[customer] = {identity(row): row for row in previous if tracked(row) and identity(row)}

    for row in rows:
        key = identity(row)
        row["schedule_identity"] = key
        row["schedule_identity_duplicate"] = bool(key and current_counts[key] > 1)
        row["manual_ordered"] = key in ordered_marks if key else False
        row["schedule_change"] = "UNCHANGED"
        if not tracked(row):
            row["schedule_change"] = "NOT_TRACKED"
            continue
        if not key:
            row["schedule_change"] = "REVIEW_REQUIRED"
            continue
        customer = customer_key(row)
        if current_counts[key] > 1 or previous_counts.get(customer, Counter())[key] > 1:
            row["schedule_change"] = "REVIEW_REQUIRED"
            continue
        previous = previous_indexes.get(customer, {}).get(key)
        section = str(row.get("schedule_section") or "PENDING")
        if previous is None:
            if section == "CANCELLED" and (key in ordered_marks or row.get("order_id")):
                row["schedule_change"] = "CANCELLED_AFTER_ORDER"
                row["suggestion"] = "已下单订单出现在退单区；请核实供应商、在途及正式采购单，人工决定是否取消"
            elif customer in previous_by_customer and section == "PENDING":
                row["schedule_change"] = "NEW"
                row["suggestion"] = "相对该客户上次有效排期为新增待下单订单；请核对后再下单"
            else:
                row["schedule_change"] = "BASELINE"
            continue
        previous_section = str(previous.get("schedule_section") or "PENDING")
        if section == previous_section:
            if section == "PENDING" and demand_snapshot(row) != demand_snapshot(previous):
                row["schedule_change"] = "MODIFIED"
            continue
        if section == "CANCELLED":
            ordered = key in ordered_marks or bool(row.get("order_id")) or bool(previous.get("order_id")) or previous.get("procurement_state") in {"ORDERED", "COMPLETED"}
            row["schedule_change"] = "CANCELLED_AFTER_ORDER" if ordered else "CANCELLED"
            row["suggestion"] = (
                "该订单已下单却转入取消单区；请核实供应商、在途及正式采购单，人工决定是否取消"
                if ordered else "该订单从待下单区转入取消单区；请人工核实，不会自动取消采购单"
            )
        elif section == "SHIPPED":
            row["schedule_change"] = "SHIPPED"
        elif previous_section == "CANCELLED":
            row["schedule_change"] = "REOPENED"
