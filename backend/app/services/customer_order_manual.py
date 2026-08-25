from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


MANUAL_EDITABLE_FIELDS: dict[str, dict[str, str]] = {
    "po_no": {"label": "P/O#", "input_type": "text"},
    "so_no": {"label": "SO", "input_type": "text"},
    "contract_no": {"label": "Contract No.", "input_type": "text"},
    "customer_country": {"label": "客名/国家", "input_type": "text"},
    "customer_name": {"label": "客户名称", "input_type": "text"},
    "country": {"label": "国家", "input_type": "text"},
    "product_no": {"label": "产品编号", "input_type": "text"},
    "product_name_zh": {"label": "中文名称", "input_type": "text"},
    "product_name_en": {"label": "产品名称", "input_type": "text"},
    "quantity": {"label": "数量", "input_type": "number"},
    "units_per_carton": {"label": "装箱数", "input_type": "number"},
    "carton_count": {"label": "箱数", "input_type": "number"},
    "standard": {"label": "国家标准", "input_type": "text"},
    "unit_price_hkd": {"label": "单价 HKD", "input_type": "number"},
    "amount_hkd": {"label": "金额 HKD", "input_type": "number"},
    "packaging": {"label": "包装", "input_type": "text"},
    "line_q": {"label": "行Q/验货日期", "input_type": "date"},
    "customer_q": {"label": "客Q/FCD", "input_type": "date"},
    "requested_ship_date": {"label": "客要求走货期", "input_type": "date"},
    # Customer-specific schedule fields that are not part of the 17-column preview.
    "inspection_result": {"label": "验货结果", "input_type": "text"},
    "inspection_date": {"label": "验货日期", "input_type": "date"},
    "fcd_date": {"label": "FCD期", "input_type": "date"},
    "po_ship_date": {"label": "走货期", "input_type": "date"},
    "date_code": {"label": "日期码", "input_type": "text"},
    "factory_price_hkd": {"label": "出厂价 HKD", "input_type": "number"},
    "outer_pack": {"label": "外箱装箱数", "input_type": "number"},
    "cartons": {"label": "箱数", "input_type": "number"},
    "customer_release_no": {"label": "客户 Release 号", "input_type": "text"},
    "merchandiser": {"label": "跟单", "input_type": "text"},
    "unit_price_usd": {"label": "订单单价 USD", "input_type": "number"},
    "contact": {"label": "联系人", "input_type": "text"},
    "item": {"label": "产品编号", "input_type": "text"},
    "item_no": {"label": "产品编号", "input_type": "text"},
    "product_name": {"label": "产品名称", "input_type": "text"},
    "description": {"label": "产品名称", "input_type": "text"},
    "po_number": {"label": "P/O#", "input_type": "text"},
    "customer_po": {"label": "客户 P/O#", "input_type": "text"},
    "customer": {"label": "客户名称", "input_type": "text"},
    "ship_date": {"label": "走货期", "input_type": "date"},
    "factory_commit_date": {"label": "FCD期", "input_type": "date"},
    "planned_inspection_date": {"label": "验货日期", "input_type": "date"},
    "case_pack": {"label": "装箱数", "input_type": "number"},
    "pack_qty": {"label": "装箱数", "input_type": "number"},
    "master_carton_qty": {"label": "装箱数", "input_type": "number"},
    "unit_price": {"label": "单价", "input_type": "number"},
}

PREVIEW_VALUE_FIELDS = frozenset({
    "po_no", "contract_no", "customer_country", "customer_name", "country",
    "product_no", "product_name_zh", "product_name_en", "quantity",
    "units_per_carton", "carton_count", "standard", "unit_price_hkd",
    "amount_hkd", "packaging", "line_q", "customer_q", "requested_ship_date",
})
DUPLICATE_CONFIRMATION_CODES = frozenset({
    "duplicate_reference",
    "existing_order_line",
    "duplicate_batch_order_line",
    "duplicate_existing_order",
})


def _manual_field(issue: dict[str, Any]) -> str:
    field = str(issue.get("field") or "").strip()
    if field in MANUAL_EDITABLE_FIELDS:
        return field
    code = str(issue.get("code") or "").strip()
    if code.startswith("missing_"):
        candidate = code.removeprefix("missing_")
        if candidate in MANUAL_EDITABLE_FIELDS:
            return candidate
    message = str(issue.get("message") or "")
    message_fields = (
        ("验货日期已过，结果未登记", "inspection_result"),
        ("缺验货结果", "inspection_result"),
        ("缺验货日期", "inspection_date"),
        ("缺外箱装箱数", "outer_pack"),
        ("缺日期码", "date_code"),
    )
    return next((target for token, target in message_fields if token in message), "")


def decorate_manual_resolution_policy(preview: dict[str, Any]) -> dict[str, Any]:
    """Expose a controlled manual-resolution path for non-duplicate blockers."""
    for row in preview.get("rows", []):
        for issue in row.get("issues", []):
            if not issue.get("skip_key"):
                issue["skip_key"] = "|".join((
                    str(row.get("id") or "row"),
                    str(issue.get("code") or "issue"),
                    str(issue.get("field") or "row"),
                ))
            issue.setdefault("can_edit", False)
            issue.setdefault("edit_field", "")
            issue.setdefault("edit_label", "")
            issue.setdefault("edit_input_type", "text")
            if (
                issue.get("severity") != "blocked"
                or str(issue.get("code") or "") in DUPLICATE_CONFIRMATION_CODES
            ):
                continue
            # Caixing parent rows are calculated summaries and have no physical
            # output row of their own. They may be confirmed, but presenting an
            # edit box would falsely imply that the entered value is exported.
            field = "" if row.get("row_role") == "parent" else _manual_field(issue)
            if field:
                meta = MANUAL_EDITABLE_FIELDS[field]
                issue.update({
                    "can_edit": True,
                    "edit_field": field,
                    "edit_label": meta["label"],
                    "edit_input_type": meta["input_type"],
                })
            issue["can_skip"] = True
            if not issue.get("skip_label"):
                issue["skip_label"] = "资料暂缺，已人工核对并确认放行"
    return preview


def coerce_manual_value(field: str, value: str) -> Any:
    meta = MANUAL_EDITABLE_FIELDS[field]
    normalized = value.strip()
    if meta["input_type"] == "number":
        try:
            number = Decimal(normalized.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"{meta['label']}必须是有效数字") from exc
        if not number.is_finite() or number < 0:
            raise ValueError(f"{meta['label']}不能是负数或无效数字")
        return int(number) if number == number.to_integral_value() else number
    if meta["input_type"] == "date":
        try:
            return date.fromisoformat(normalized).isoformat()
        except ValueError as exc:
            raise ValueError(f"{meta['label']}必须是 YYYY-MM-DD 日期") from exc
    return normalized


def apply_overrides_to_preview(
    preview: dict[str, Any],
    overrides: Iterable[dict[str, str]],
) -> dict[str, Any]:
    rows = {str(row.get("id") or ""): row for row in preview.get("rows", [])}
    for override in overrides:
        row = rows.get(override["row_id"])
        if row is None:
            continue
        field = override["field"]
        value = override["value"]
        if field in PREVIEW_VALUE_FIELDS:
            row[field] = value
        export_record = row.get("_export_record")
        if isinstance(export_record, dict) and field in export_record:
            export_record[field] = coerce_manual_value(field, value)
    return preview


def apply_overrides_to_records(
    records: list[dict[str, Any]],
    row_ids: list[str],
    overrides: Iterable[dict[str, str]],
    *,
    field_aliases: dict[str, str] | None = None,
) -> None:
    record_by_row = {
        row_id: record for row_id, record in zip(row_ids, records, strict=True)
    }
    aliases = field_aliases or {}
    for override in overrides:
        record = record_by_row.get(override["row_id"])
        if record is None:
            continue
        field = override["field"]
        record[aliases.get(field, field)] = coerce_manual_value(field, override["value"])
