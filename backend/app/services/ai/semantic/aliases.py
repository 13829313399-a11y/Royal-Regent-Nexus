from __future__ import annotations

import re
import unicodedata

ALIAS_CATALOG_VERSION = "semantic-alias-catalog-v1"

_ENTITY_ALIASES = {
    "scheduling_backlog_order": (
        "scheduling_backlog_order",
        "注塑待排订单",
        "注塑待排",
        "待排订单",
        "待排",
        "啤塑待排",
        "啤机待排",
        "啤几待排",
    ),
    "internal_quote_summary": (
        "internal_quote_summary",
        "内部报价摘要",
        "内部报价",
        "报价单",
        "报价",
        "报介",
    ),
    "customer_order_capability": (
        "customer_order_capability",
        "客户订单能力",
        "订单导入能力",
    ),
    "customer_order_export_audit": (
        "customer_order_export_audit",
        "客户订单导出审计",
        "订单导出审计",
        "导出审计",
    ),
}

_FIELD_ALIASES = {
    "scheduling_backlog_order": {
        "due_date": ("due_date", "走货期", "交期", "交货期", "出货期"),
        "order_no": ("order_no", "订单号", "单号"),
        "item_no": ("item_no", "料号", "货号", "产品编号"),
        "mold_no": ("mold_no", "模具", "模具号", "模号"),
        "priority": ("priority", "优先级", "紧急程度"),
    },
    "internal_quote_summary": {
        "status": ("status", "状态", "报价状态"),
        "keyword": ("keyword", "关键词", "报价号", "客户"),
        "updated_at": ("updated_at", "更新时间", "最近更新"),
    },
    "customer_order_export_audit": {
        "customer_code": ("customer_code", "客户代码", "客户编号"),
        "created_at": ("created_at", "导出时间", "创建时间"),
    },
}


def normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"[\s\-_/]+", "", normalized)


def _resolve(value: str, catalog: dict[str, tuple[str, ...]]) -> str | None:
    needle = normalize_alias(value)
    matches = [
        canonical
        for canonical, aliases in catalog.items()
        if needle in {normalize_alias(alias) for alias in aliases}
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_entity_alias(value: str) -> str | None:
    return _resolve(value, _ENTITY_ALIASES)


def resolve_field_alias(entity_id: str, value: str) -> str | None:
    return _resolve(value, _FIELD_ALIASES.get(entity_id, {}))
