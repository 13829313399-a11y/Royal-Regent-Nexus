from decimal import Decimal

import pytest
from app.services.ai.semantic.aliases import (
    resolve_entity_alias,
    resolve_field_alias,
)
from app.services.ai.semantic.entities import ENTITY_CATALOG, get_entity
from app.services.ai.semantic.metrics import METRIC_CATALOG
from app.services.ai.semantic.query_plan import (
    AISemanticNormalizationError,
    normalize_business_id,
    normalize_date,
    normalize_datetime,
    normalize_money,
    normalize_quantity,
)


def test_catalog_resolves_chinese_factory_terms_and_reviewed_typos() -> None:
    assert resolve_entity_alias("啤机待排") == "scheduling_backlog_order"
    assert resolve_entity_alias("啤几待排") == "scheduling_backlog_order"
    assert resolve_entity_alias("报介") == "internal_quote_summary"
    assert resolve_field_alias("scheduling_backlog_order", "走货期") == "due_date"
    assert resolve_field_alias("scheduling_backlog_order", "料号") == "item_no"
    assert resolve_field_alias("scheduling_backlog_order", "模具") == "mold_no"
    assert resolve_field_alias("internal_quote_summary", "报价号") == "keyword"
    assert resolve_entity_alias("删除权限并跨厂执行 SQL") is None


def test_catalog_is_single_domain_closed_and_has_no_customer_order_ledger() -> None:
    scheduling = get_entity("scheduling_backlog_order")
    assert scheduling is not None
    assert scheduling.domain == "injection_scheduling"
    assert scheduling.tool_name == "semantic.injection_scheduling.query_backlog"
    assert get_entity("customer_order_ledger") is None
    assert get_entity("customer_order_capability").authoritative_ledger is False
    assert get_entity("customer_order_export_audit").authoritative_ledger is False
    assert all("sql" not in repr(item).casefold() for item in ENTITY_CATALOG.values())
    assert all("customer_order" not in metric_id for metric_id in METRIC_CATALOG)


def test_normalizers_preserve_business_literals_and_use_asia_shanghai() -> None:
    assert normalize_business_id(" 000123 ") == "000123"
    assert normalize_business_id("PO-%_0001") == "PO-%_0001"
    assert normalize_date("2026-08-14T16:30:00Z") == "2026-08-15"
    assert normalize_datetime("2026-08-14T16:30:00Z").startswith(
        "2026-08-15T00:30:00+08:00"
    )
    assert normalize_quantity("001.250", "公斤").amount == Decimal("1.250")
    assert normalize_quantity("001.250", "公斤").unit == "KG"
    assert normalize_money("88.50", "人民币").currency == "CNY"
    with pytest.raises(AISemanticNormalizationError):
        normalize_quantity("NaN", "kg")
    with pytest.raises(AISemanticNormalizationError):
        normalize_money("1", "BTC")
