"""Synthetic migration goldens; no customer snapshot or credentials in the repo."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.legacy_three_d_analysis import analyze_state, derive_run_status


def sample_state():
    return {
        "settings": {"machines": 2, "lossRate": 1.2, "profitRate": 40},
        "materials": [{"id": "m1", "name": "PLA Black", "priceKg": 20}],
        "products": [
            {"id": 1, "name": "Part A", "material": "PLA Black", "weight": 10, "qty": 1, "time": 2, "price": 1.1, "customer": "Current"},
            {"id": 2, "name": "Part A", "weight": 0, "time": 0, "price": 0},
            {"id": 3, "name": "Unique Part", "material": "PLA Black", "weight": 10, "qty": 1, "time": 2, "price": 1.1, "customer": "Current"},
        ],
        "records": {
            "2026-09-03": {"off": False, "items": [
                {"_id": "r1", "machine": 1, "status": "running", "productName": "Unique Part", "material": "PLA Black", "qty": 3, "weight": .1, "time": 1, "price": .1, "designFee": 2.5, "customer": "Historical", "autoRecord": True, "printStartTime": "2026-09-03T23:00:00+08:00", "printEndTime": "2026-09-04T01:00:00+08:00"},
                {"_id": "dead", "_deleted": True, "productName": "Deleted", "qty": 999, "weight": 999, "price": 999, "designFee": 999},
            ]},
            "2026-09-04": {"off": True, "items": [
                {"_id": "r2", "machine": 2, "status": "running", "productName": "Part_A", "qty": 2, "weight": .2, "price": .2, "autoRecord": True, "printStartTime": "2026-09-04T01:00:00Z"},
                {"_id": "r3", "machine": 1, "status": "done", "productName": "", "qty": 1, "printEndTime": "2026-09-04T02:00:00Z"},
            ]},
        },
        "inventory": {"PLA Black": {"stockG": 10, "minStockG": 10}, "PLABlack": {"stockG": 0, "minStockG": 5}},
        "stockInLogs": [{"id": "in1", "amountG": 1000, "cost": 20}],
        "schedules": [], "maintenance": [],
    }


def test_counts_tombstones_decimal_totals_and_opening_balance():
    report = analyze_state(sample_state(), [])
    counts = report["authoritative_sqlite"]
    assert (counts["products"], counts["records_stored"], counts["records_active"], counts["records_tombstoned"]) == (3, 4, 3, 1)
    assert counts["off_day_dates"] == ["2026-09-04"]
    assert report["business_totals_active_records"] == {
        "quantity_total": 6, "planned_material_g_total": .7,
        "design_fee_total": 2.5, "quoted_revenue_total": .7,
    }
    inventory = report["materials_inventory_quality"]
    assert inventory["inventory_total_g"] == 10
    assert inventory["stock_in_total_g"] == 1000
    assert inventory["inventory_at_or_below_min_count"] == 2
    assert inventory["inventory_below_min_count"] == 1
    assert inventory["normalized_alias_groups"] == [["PLA Black", "PLABlack"]]


def test_names_and_historical_snapshot_preserved_including_blank_quality():
    state = sample_state()
    original = deepcopy(state)
    report = analyze_state(state, [])
    assert state == original
    assert report["products_quality"]["exact_duplicate_name_groups"] == 1
    assert report["products_quality"]["ids_unique"] is True
    quality = report["records_quality"]
    assert quality["unique_record_product_names"] == 2
    assert quality["missing_product_name"] == 1
    assert quality["record_rows_not_exact_master"] == 1
    assert quality["record_rows_not_normalized_master"] == 0
    assert quality["snapshot_rows_compared_to_unique_current_product"] == 1
    assert quality["snapshot_drift_counts"] == {"material": 0, "qty": 1, "customer": 1, "weight": 1, "time": 1, "price": 1}


def test_legacy_running_is_not_live_and_duration_crosses_midnight():
    quality = analyze_state(sample_state(), [])["records_quality"]
    assert quality["status_counts"] == {"done": 1, "running": 2}
    assert quality["derived_run_status_counts"] == {
        "running_pending_reconciliation": 1, "succeeded": 1,
        "succeeded_with_incomplete_timing": 1,
    }
    assert quality["duration_hours_median"] == 2
    assert quality["open_records_missing_end_time"] == 1
    assert quality["missing_start_with_end"] == 1
    assert derive_run_status({"status": "running"}) == "unknown"
    assert derive_run_status({"printEndTime": "2026-09-04T01:00:00Z", "remark": "打印失败"}) == "failed"


def test_images_content_hashes_orphans_invalid_and_percentiles():
    images = [
        {"product_id": "1", "storage_type": "base64", "mime_type": "image/jpeg", "size_bytes": 10, "legacy_sha256": "uri-hash", "content_sha256": "bytes-hash", "valid": True},
        {"product_id": "3", "mime_type": "image/jpeg", "size_bytes": 20, "legacy_sha256": "uri-hash", "content_sha256": "bytes-hash", "valid": True},
        {"product_id": "orphan", "mime_type": "image/png", "size_bytes": 30, "valid": False, "error_code": "decode_error"},
    ]
    report = analyze_state(sample_state(), images)
    quality = report["images_quality"]
    assert quality["products_with_image"] == 2
    assert quality["products_missing_image"] == 1
    assert quality["orphan_image_rows"] == 1
    assert quality["invalid_images"] == 1
    assert quality["duplicate_hash_groups"] == quality["duplicate_extra_rows"] == 1
    assert quality["legacy_content_hash_mismatches"] == 2
    assert quality["total_bytes"] == 60
    assert quality["median_bytes"] == 20
    assert quality["p95_bytes"] == 29


def test_json_fallback_is_explicitly_labeled_and_config_is_not_serialized():
    state = sample_state()
    state["products"][0]["image"] = "data:image/jpeg;base64,example"
    sentinel = "MUST-NOT-LEAK"
    state["config"] = {"accessCode": sentinel, "serial": sentinel}
    state["settings"]["password"] = "MUST-NOT-LEAK"
    state["records"]["2026-09-03"]["items"][0]["remark"] = "MUST-NOT-LEAK"
    report = analyze_state(state, [], source_kind="json")
    assert "authoritative_sqlite" not in report
    assert report["data_json_snapshot"]["product_images_embedded"] == 1
    assert report["warnings"]
    assert "MUST-NOT-LEAK" not in json.dumps(report)
    assert "printers_configured" not in report["data_json_snapshot"]


def test_ids_malformed_numbers_and_negative_time_are_reported():
    state = sample_state()
    state["products"][1]["id"] = 1
    record = state["records"]["2026-09-03"]["items"][0]
    record["qty"] = "NaN"
    record["printEndTime"] = "2026-09-03T01:00:00+08:00"
    state["records"]["2026-09-04"]["items"][0]["printStartTime"] = "not-a-date"
    report = analyze_state(state, [])
    assert report["products_quality"]["ids_unique"] is False
    assert report["legacy_id_quality"]["products"]["duplicate_groups"] == 1
    assert report["records_quality"]["negative_duration"] == 1
    assert report["anomaly_counts"]["invalid_timestamp"] == 1
    assert report["anomaly_counts"]["invalid_numeric"] == 1
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("key,value", [("products", {}), ("records", []), ("inventory", {"PLA": 123})])
def test_malformed_container_fails_without_echoing_input(key, value):
    state = sample_state()
    state[key] = value
    with pytest.raises(ValueError, match="invalid_"):
        analyze_state(state, [])


def test_empty_snapshot_is_finite_and_deterministic():
    report = analyze_state({}, [])
    assert report == analyze_state({}, [])
    assert report["records_quality"]["duration_hours_p95"] is None
    assert report["images_quality"]["coverage_percent"] == 0
    assert report["business_totals_active_records"]["quantity_total"] == 0
    json.dumps(report, allow_nan=False)
