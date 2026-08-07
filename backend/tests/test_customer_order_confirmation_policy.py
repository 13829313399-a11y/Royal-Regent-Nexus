from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from app.api import customer_order
from app.core.config import Settings


PREVIEW = {
    "summary": {"total": 1, "valid": 0, "warning": 0, "blocked": 1},
    "rows": [
        {
            "id": "row-1",
            "status": "blocked",
            "status_label": "阻断",
            "issues": [
                {
                    "severity": "blocked",
                    "code": "duplicate_reference",
                    "field": "reference_no",
                    "message": "Reference 已存在；测试阶段可人工确认后重复导入",
                    "can_skip": True,
                    "skip_key": "row-1|duplicate_reference|reference_no",
                    "skip_label": "测试阶段确认重复导入",
                }
            ],
        }
    ],
}


def test_duplicate_confirmation_defaults_off_in_production_and_on_elsewhere():
    production = Settings(
        app_env="production",
        customer_order_test_duplicate_confirmation_enabled=None,
        _env_file=None,
    )
    testing = Settings(
        app_env="testing",
        customer_order_test_duplicate_confirmation_enabled=None,
        _env_file=None,
    )

    assert not production.effective_customer_order_test_duplicate_confirmation_enabled
    assert testing.effective_customer_order_test_duplicate_confirmation_enabled


def test_preview_exposes_duplicate_as_confirmation_when_test_policy_is_enabled(monkeypatch):
    monkeypatch.setattr(
        customer_order.settings,
        "customer_order_test_duplicate_confirmation_enabled",
        True,
    )

    preview = customer_order._apply_customer_order_confirmation_policy(deepcopy(PREVIEW))

    issue = preview["rows"][0]["issues"][0]
    assert preview["duplicate_confirmation_enabled"] is True
    assert preview["confirmation_count"] == 1
    assert issue["severity"] == "confirmation"
    assert issue["can_skip"] is True
    assert preview["rows"][0]["status"] == "warning"
    assert preview["summary"] == {
        "total": 1,
        "valid": 0,
        "warning": 1,
        "blocked": 0,
    }


def test_preview_keeps_duplicate_blocked_when_test_policy_is_disabled(monkeypatch):
    monkeypatch.setattr(
        customer_order.settings,
        "customer_order_test_duplicate_confirmation_enabled",
        False,
    )

    preview = customer_order._apply_customer_order_confirmation_policy(deepcopy(PREVIEW))

    issue = preview["rows"][0]["issues"][0]
    assert preview["duplicate_confirmation_enabled"] is False
    assert preview["confirmation_count"] == 0
    assert issue["severity"] == "blocked"
    assert issue["can_skip"] is False
    assert issue["skip_label"] == ""
    assert "当前环境未启用重复订单确认" in issue["message"]
    assert preview["summary"]["blocked"] == 1


def test_preview_keeps_duplicate_blocked_without_independent_confirmation_permission(monkeypatch):
    monkeypatch.setattr(
        customer_order.settings,
        "customer_order_test_duplicate_confirmation_enabled",
        True,
    )

    preview = customer_order._apply_customer_order_confirmation_policy(
        deepcopy(PREVIEW),
        duplicate_confirmation_authorized=False,
    )

    issue = preview["rows"][0]["issues"][0]
    assert preview["duplicate_confirmation_enabled"] is True
    assert preview["duplicate_confirmation_authorized"] is False
    assert preview["confirmation_count"] == 0
    assert issue["severity"] == "blocked"
    assert issue["can_skip"] is False
    assert "没有重复订单确认权限" in issue["message"]


def test_export_rejects_duplicate_confirmation_key_when_policy_is_disabled(monkeypatch):
    monkeypatch.setattr(
        customer_order.settings,
        "customer_order_test_duplicate_confirmation_enabled",
        False,
    )

    with pytest.raises(HTTPException) as exc_info:
        customer_order._ensure_test_duplicate_confirmation_allowed(
            {"row-1|duplicate_reference|reference_no"}
        )

    assert exc_info.value.status_code == 409
    assert "未启用" in exc_info.value.detail


def test_confirmation_key_limit_supports_large_test_batches():
    keys = [f"row-{index}|missing_optional|field" for index in range(101)]

    assert customer_order._parse_skipped_issue_keys(json.dumps(keys)) == set(keys)


def test_confirmation_reason_is_required_only_when_an_issue_is_confirmed():
    assert customer_order._validated_confirmation_reason(set(), "") == ""
    with pytest.raises(HTTPException) as exc_info:
        customer_order._validated_confirmation_reason({"row-1|missing|field"}, "测试")
    assert exc_info.value.status_code == 400

    assert customer_order._validated_confirmation_reason(
        {"row-1|missing|field"},
        "  测试阶段人工核对  ",
    ) == "测试阶段人工核对"


def test_hard_blocker_exposes_manual_edit_and_confirm_release_paths():
    preview = {
        "summary": {"total": 1, "valid": 0, "warning": 0, "blocked": 1},
        "rows": [{
            "id": "360-1",
            "status": "blocked",
            "status_label": "已阻断",
            "issues": [{
                "severity": "blocked",
                "code": "missing_inspection_result",
                "field": "inspection_result",
                "message": "验货日期已过，结果未登记",
                "can_skip": False,
                "skip_key": "360-1:missing_inspection_result",
                "skip_label": "",
            }],
        }],
    }

    finalized = customer_order._apply_customer_order_confirmation_policy(preview)
    issue = finalized["rows"][0]["issues"][0]

    assert issue["severity"] == "blocked"
    assert issue["can_skip"] is True
    assert issue["can_edit"] is True
    assert issue["edit_field"] == "inspection_result"
    assert issue["edit_label"] == "验货结果"
    assert issue["skip_label"] == "资料暂缺，已人工核对并确认放行"


def test_manual_override_payload_is_typed_and_bound_to_current_preview():
    raw = json.dumps([{
        "row_id": "360-1",
        "issue_key": "360-1:missing_inspection_result",
        "field": "inspection_result",
        "value": "  合格  ",
    }], ensure_ascii=False)
    overrides = customer_order._parse_manual_overrides(raw)
    preview = {
        "rows": [{
            "id": "360-1",
            "issues": [{
                "severity": "blocked",
                "code": "missing_inspection_result",
                "field": "inspection_result",
                "message": "验货日期已过，结果未登记",
                "can_skip": False,
                "skip_key": "360-1:missing_inspection_result",
                "skip_label": "",
            }],
        }],
    }

    assert overrides[0]["value"] == "合格"
    assert customer_order._actual_manual_overrides(preview, overrides) == overrides

    changed = deepcopy(overrides)
    changed[0]["field"] = "quantity"
    with pytest.raises(HTTPException) as exc_info:
        customer_order._actual_manual_overrides(preview, changed)
    assert exc_info.value.status_code == 409


def test_preview_fingerprint_changes_when_source_version_or_received_date_changes():
    preview = {
        "preview_schema_version": "v1",
        "customer_code": "dickie",
        "factory_id": "huaxing",
        "po_file_names": ["a.pdf"],
        "source_po_sha256s": ["po-v1"],
        "schedule_file_name": "schedule.xlsx",
        "source_schedule_sha256": "schedule-v1",
        "input_template": "input-v1",
        "target_template": "target-v1",
        "output_file_name": "schedule.xlsx",
    }
    original = customer_order._preview_fingerprint(preview, "2026-08-04")
    assert original == customer_order._preview_fingerprint(deepcopy(preview), "2026-08-04")

    changed_source = deepcopy(preview)
    changed_source["source_schedule_sha256"] = "schedule-v2"
    assert original != customer_order._preview_fingerprint(changed_source, "2026-08-04")
    assert original != customer_order._preview_fingerprint(preview, "2026-08-05")
