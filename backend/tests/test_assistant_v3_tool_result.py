"""Validate handoff examples and semantic failure boundaries, not just shapes."""
import json
from pathlib import Path

import pytest
from app.services.assistant.tool_result import validate_result


@pytest.fixture
def example():
    return json.loads((Path(__file__).parent / "fixtures/assistant_v3/tool-result-example.json").read_text(encoding="utf-8-sig"))


def validate(value, **changes):
    return validate_result(value, **(dict(registered_sources={"biz_o1", "biz_o3"},
        registered_resources={"SYN-O-A001", "SYN-O-A003"}, row_fields={"resource_ref", "open_quantity"}) | changes))


def test_handoff_example_and_decimal_precision_are_preserved(example):
    example["metrics"]["open_quantity"]["value"] = "900.00000000000000001"
    result = validate(example)
    assert result["contract_version"] == 3
    assert result["metrics"]["open_quantity"]["value"] == "900.00000000000000001"
    assert result["as_of"] == example["as_of"]


@pytest.mark.parametrize("mutation", ["float", "boolean", "nan", "unknown-zero", "undefined-metric", "row-count", "empty",
    "forbidden", "foreign-source", "foreign-resource", "object-resource", "unexpected-field", "stale-ok", "cursor-complete", "naive-time", "cached-no-time", "empty-ok"])
def test_rejects_false_certainty_leaks_and_unregistered_references(example, mutation):
    if mutation == "float": example["metrics"]["open_quantity"]["value"] = 0.1
    if mutation == "boolean": example["metrics"]["open_quantity"]["value"] = True
    if mutation == "nan": example["metrics"]["open_quantity"]["value"] = "NaN"
    if mutation == "unknown-zero": example["metrics"]["open_quantity"].update(value=0, status="unknown")
    if mutation == "undefined-metric": example["definitions"].clear()
    if mutation == "row-count": example["returned_count"] = 1
    if mutation == "empty": example["status"] = "empty"
    if mutation == "forbidden": example["status"] = "forbidden"
    if mutation == "foreign-source": example["source_refs"].append("hidden-source")
    if mutation == "foreign-resource": example["rows"][0]["resource_ref"] = "hidden-resource"
    if mutation == "object-resource": example["rows"][0]["resource_ref"] = {"id": "hidden-resource"}
    if mutation == "unexpected-field": example["rows"][0]["internal_margin"] = "100.00"
    if mutation == "stale-ok": example["freshness"]["state"] = "stale"
    if mutation == "cursor-complete": example["next_cursor"] = "2"
    if mutation == "naive-time": example["observed_at"] = "2026-10-23T01:00:00"
    if mutation == "cached-no-time": example["freshness"]["cache_hit"] = True
    if mutation == "empty-ok": example.update(rows=[], returned_count=0, total_count=0)
    with pytest.raises(ValueError): validate(example)


def test_old_cache_keeps_origin_time_and_null_is_not_zero(example):
    example.update(status="stale", requested_at="2026-10-23T02:00:00Z", retrieved_at="2026-10-23T02:00:01Z")
    example["freshness"].update(state="stale", cache_hit=True, cache_created_at="2026-10-23T01:00:00Z")
    example["metrics"]["open_quantity"].update(value=None, status="unknown")
    example["unknown_fields"] = [dict(field="open_quantity", reason="原系统缺失数量")]
    result = validate(example)
    assert result["as_of"] == "2026-10-23T01:00:00Z" and result["observed_at"] is None
    assert result["metrics"]["open_quantity"]["value"] is None


def test_business_date_is_a_calendar_value_separate_from_numeric_metrics(example):
    example["business_date"] = "2026-10-24"
    assert validate(example)["business_date"] == "2026-10-24"
    for invalid in ("2026-02-30", "20261024", "2026-10-24T00:00:00", 20261024):
        example["business_date"] = invalid
        with pytest.raises(ValueError): validate(example)


def test_failure_does_not_masquerade_as_empty(example):
    example.update(status="failed", rows=[], metrics={}, total_count=None, returned_count=0,
                   source_refs=[], allowed_actions=[], data_mode="unavailable", as_of=None, diagnostic_code="upstream_unavailable")
    example["freshness"]["state"] = "unknown"
    result = validate(example)
    assert result["total_count"] is None
    example["status"] = "empty"
    with pytest.raises(ValueError): validate(example)
