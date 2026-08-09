from __future__ import annotations

import importlib
import json
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import func, select
from test_injection_scheduling_phase3_api import (
    ADMIN_TEST_PASSWORD,
    make_migrated_client,
)
from test_injection_scheduling_phase4_import import login

from app.services.injection_scheduling_master_consolidation import (
    consolidate_master_data_workbook,
)


def _workbook() -> bytes:
    workbook = Workbook()
    price = workbook.active
    price.title = "单价"
    price.append([])
    price.append(
        [
            "物料编号",
            "客户",
            "塑胶货号",
            "工模编号",
            "物料名称",
            "颜色",
            "用料名称",
            "整啤净重",
            "整啤模腔数",
            "啤机机型",
            "模具日产量",
            "单价",
        ]
    )
    price.append(
        ["MAT-1", "客户甲", "ITEM-1", "M-PRICE", "价表模具", "黑", "ABS", 20, 2, "7A", 3000, 0.5]
    )
    price.append(
        ["MAT-2", "客户乙", "ITEM-2", "M-BOTH", "重叠模具", "白", "PP", 30, 4, "7A", 2000, 0.8]
    )
    price.append(
        ["MAT-3", "客户丙", "ITEM-3", "M-CONFLICT", "冲突模具", "红", "ABS", 40, 1, "5A", 1000, 1.2]
    )

    machine = workbook.create_sheet("机安")
    machine.append(
        [
            "模号",
            "名称",
            "安数",
            "单双臂",
            "吸盘",
            "颜色",
            "用料",
            "工程重量（G）",
        ]
    )
    machine.append(["M-BOTH", "重叠模具", "14A模高", "单臂", "吸盘", "白", "PP", 30])
    machine.append(["M-CONFLICT", "冲突模具", "7A", "单臂", "吸盘", "红", "ABS", 40])
    machine.append(["M-CONFLICT", "冲突模具", "12A", "单臂", "吸盘", "红", "ABS", 40])

    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def test_consolidation_prefers_machine_sheet_and_falls_back_to_price_sheet():
    result = consolidate_master_data_workbook(
        _workbook(),
        "华兴测试.xlsx",
        factory_id="huaxing",
    )

    by_no = {item["canonical_mold_no"]: item for item in result["mold_entries"]}
    assert by_no["M-BOTH"]["recommended_machine_class_raw"] == "14A模高"
    assert by_no["M-BOTH"]["mold_a_class"] == 14
    assert by_no["M-BOTH"]["default_arm_type"] == "single"
    assert by_no["M-BOTH"]["default_fixture_type"] == "suction_cup"
    assert by_no["M-BOTH"]["source_priority"]["machine_class"] == "机安"

    assert by_no["M-PRICE"]["recommended_machine_class_raw"] == "7A"
    assert by_no["M-PRICE"]["mold_a_class"] == 7
    assert by_no["M-PRICE"]["source_priority"]["machine_class"] == "单价回退"

    assert "M-CONFLICT" not in by_no
    assert result["review_entries"][0]["code"] == "CAPABILITY_SOURCE_CONFLICT"
    assert result["summary"] == {
        "price_source_rows": 3,
        "machine_source_rows": 3,
        "mold_candidate_count": 2,
        "capability_candidate_count": 2,
        "rate_candidate_count": 3,
        "review_mold_count": 1,
        "invalid_rate_row_count": 0,
        "machine_priority_count": 1,
        "price_fallback_count": 1,
    }


def test_rate_candidates_remain_blocked_without_signed_scope_dimensions():
    result = consolidate_master_data_workbook(
        _workbook(),
        "华兴测试.xlsx",
        factory_id="huaxing",
    )

    assert len(result["rate_entries"]) == 3
    for rate in result["rate_entries"]:
        assert rate["amount"]
        assert rate["pricing_basis"] == ""
        assert rate["currency"] == ""
        assert "计价口径" in rate["activation_blockers"]
        assert "币种" in rate["activation_blockers"]
        assert "owner/厂区/客户/合同适用范围" in rate["activation_blockers"]


def test_approved_bundle_activation_creates_shared_mold_outputs_and_factory_capability(
    monkeypatch,
):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        db_module = importlib.import_module("app.db")
        shared = importlib.import_module("app.models.injection_scheduling_shared")
        timestamp = "2026-08-10T09:00:00+08:00"
        mold_payload = {
            "source_namespace_id": "master-data:factory:huaxing:test",
            "source_file_hash": "a" * 64,
            "entries": [
                {
                    "mold_key": "m-bundle",
                    "canonical_mold_no": "M-BUNDLE",
                    "display_mold_no": "M-BUNDLE",
                    "raw_aliases": ["M-BUNDLE", "M BUNDLE"],
                    "standard_name": "测试组合模具",
                    "recommended_machine_class_raw": "14A模高",
                    "mold_a_class": 14,
                    "default_arm_type": "single",
                    "default_fixture_type": "suction_cup",
                    "process_tags": ["mold_height"],
                    "engineering": {"length_mm": "300"},
                    "source_priority": {"machine_class": "机安"},
                    "outputs": [
                        {
                            "output_key": "b" * 64,
                            "item_no": "ITEM-BUNDLE",
                            "variant_code": "",
                            "product_name": "组合上壳",
                            "cavity_count": 2,
                            "whole_shot_net_weight_g": "21",
                            "whole_shot_gross_weight_g": "24",
                            "default_material": "ABS",
                            "default_color": "黑色",
                            "nominal_daily_capacity": "1600",
                            "source_rows": [],
                        }
                    ],
                }
            ],
        }
        capability_payload = {
            "source_file_hash": "a" * 64,
            "entries": [
                {
                    "mold_key": "m-bundle",
                    "canonical_mold_no": "M-BUNDLE",
                    "machine_class": 14,
                    "machine_class_raw": "14A模高",
                    "required_arm_type": "single",
                    "required_fixture_type": "suction_cup",
                    "process_limits": {"length_mm": "300"},
                    "source_priority": "机安",
                }
            ],
        }
        rate_payload = {
            "source_file_hash": "a" * 64,
            "entries": [
                {
                    "rate_key": "c" * 64,
                    "mold_key": "m-bundle",
                    "canonical_mold_no": "M-BUNDLE",
                    "output_key": "b" * 64,
                    "item_no": "ITEM-BUNDLE",
                    "product_name": "组合上壳",
                    "customer_text": "客户甲",
                    "amount": "0.8",
                    "pricing_basis": "",
                    "currency": "",
                    "tax_mode": "",
                    "activation_blockers": ["计价口径", "币种", "税制", "适用范围"],
                    "source": {"sheet_name": "单价", "source_row": 3},
                }
            ],
        }
        with db_module.SessionLocal() as db:
            db.add_all(
                [
                    shared.InjectionSchedulingMasterDataProposal(
                        id="proposal:mold-bundle",
                        entity_type="MOLD_DEFINITION_BUNDLE",
                        action_type="CREATE",
                        target_entity_id="",
                        scope_type="COMPANY",
                        scope_id="company:royal-regent",
                        payload_json=json.dumps(mold_payload, ensure_ascii=False),
                        evidence_digest="mold-evidence",
                        status="PROPOSED",
                        revision=1,
                        request_id="bundle-mold-proposal",
                        proposed_by="system:controlled-import",
                        proposed_by_name="受控导入",
                        approved_by="",
                        approved_by_name="",
                        reason="测试组合提案",
                        created_at=timestamp,
                        reviewed_at="",
                    ),
                    shared.InjectionSchedulingMasterDataProposal(
                        id="proposal:capability-bundle",
                        entity_type="FACTORY_MOLD_CAPABILITY_BUNDLE",
                        action_type="CREATE",
                        target_entity_id="",
                        scope_type="FACTORY",
                        scope_id="huaxing",
                        payload_json=json.dumps(capability_payload, ensure_ascii=False),
                        evidence_digest="capability-evidence",
                        status="PROPOSED",
                        revision=1,
                        request_id="bundle-capability-proposal",
                        proposed_by="system:controlled-import",
                        proposed_by_name="受控导入",
                        approved_by="",
                        approved_by_name="",
                        reason="测试机安提案",
                        created_at=timestamp,
                        reviewed_at="",
                    ),
                    shared.InjectionSchedulingMasterDataProposal(
                        id="proposal:rate-bundle",
                        entity_type="COMMERCIAL_RATE_RULE",
                        action_type="CREATE",
                        target_entity_id="",
                        scope_type="FACTORY",
                        scope_id="huaxing",
                        payload_json=json.dumps(rate_payload, ensure_ascii=False),
                        evidence_digest="rate-evidence",
                        status="PROPOSED",
                        revision=1,
                        request_id="bundle-rate-proposal",
                        proposed_by="system:controlled-import",
                        proposed_by_name="受控导入",
                        approved_by="",
                        approved_by_name="",
                        reason="测试价格提案",
                        created_at=timestamp,
                        reviewed_at="",
                    ),
                ]
            )
            db.commit()

        for proposal_id in (
            "proposal:mold-bundle",
            "proposal:capability-bundle",
            "proposal:rate-bundle",
        ):
            approved = client.post(
                f"/api/injection-scheduling/master-data-proposals/{proposal_id}/approve",
                json={
                    "factory_id": "huaxing",
                    "expected_revision": 1,
                    "request_id": f"approve-{proposal_id}",
                    "reason": "独立复核测试资料",
                },
            )
            assert approved.status_code == 200, approved.text

        activated_mold = client.post(
            "/api/injection-scheduling/master-data-proposals/proposal:mold-bundle/activate",
            json={
                "factory_id": "huaxing",
                "expected_revision": 2,
                "request_id": "activate-mold-bundle",
                "reason": "激活已批准共享模具",
            },
        )
        assert activated_mold.status_code == 200, activated_mold.text
        assert activated_mold.json()["activated_entity"]["created_definitions"] == 1
        assert activated_mold.json()["activated_entity"]["created_outputs"] == 1

        activated_capability = client.post(
            "/api/injection-scheduling/master-data-proposals/proposal:capability-bundle/activate",
            json={
                "factory_id": "huaxing",
                "expected_revision": 2,
                "request_id": "activate-capability-bundle",
                "reason": "激活已批准华兴机安能力",
            },
        )
        assert activated_capability.status_code == 200, activated_capability.text
        assert (
            activated_capability.json()["activated_entity"][
                "created_capabilities"
            ]
            == 1
        )

        activated_rate = client.post(
            "/api/injection-scheduling/master-data-proposals/proposal:rate-bundle/activate",
            json={
                "factory_id": "huaxing",
                "expected_revision": 2,
                "request_id": "activate-rate-bundle",
                "reason": "确认按单价表人民币每啤原值激活",
                "price_confirmation": {
                    "pricing_basis": "PER_SHOT",
                    "currency": "CNY",
                    "tax_mode": "AS_LISTED",
                    "owner_scope_type": "FACTORY",
                    "applicable_factory_mode": "SPECIFIC",
                    "applicable_customer_mode": "ANY",
                    "contract_mode": "ANY",
                    "confirmed_business_signoff": True,
                },
            },
        )
        assert activated_rate.status_code == 200, activated_rate.text
        assert activated_rate.json()["activated_entity"] == {
            "created_rate_rules": 1,
            "updated_rate_rules": 0,
            "missing_output_entry_count": 0,
            "duplicate_output_count": 0,
            "duplicate_rate_entry_count": 0,
            "review_samples": [],
        }

        with db_module.SessionLocal() as db:
            assert db.scalar(
                select(func.count()).select_from(
                    shared.InjectionSchedulingMoldDefinition
                )
            ) == 1
            output = db.scalar(select(shared.InjectionSchedulingMoldOutputSpec))
            assert output is not None
            assert output.item_no == "ITEM-BUNDLE"
            assert output.default_material == "ABS"
            capability = db.scalar(
                select(shared.InjectionSchedulingFactoryMoldCapability)
            )
            assert capability is not None
            assert capability.machine_class == 14
            assert capability.required_fixture_type == "suction_cup"
            rate = db.scalar(select(shared.InjectionSchedulingCommercialRateRule))
            assert rate is not None
            assert str(rate.amount) == "0.800000"
            assert rate.pricing_basis == "PER_SHOT"
            assert rate.currency == "CNY"
            assert rate.tax_mode == "AS_LISTED"
            assert rate.owner_scope_type == "FACTORY"
            assert rate.owner_scope_id == "huaxing"
            assert rate.applicable_factory_id == "huaxing"
            assert rate.applicable_customer_mode == "ANY"
            assert rate.contract_mode == "ANY"
            policy = db.get(shared.InjectionSchedulingRolloutPolicy, "huaxing")
            assert policy is not None
            assert policy.master_data_mode == "APPROVAL_ACTIVE"
            assert policy.business_contract_status == "SIGNED"
            assert policy.price_activation_enabled is True
