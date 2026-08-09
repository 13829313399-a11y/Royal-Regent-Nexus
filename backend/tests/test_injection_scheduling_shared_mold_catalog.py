from __future__ import annotations

import importlib
from decimal import Decimal

from test_injection_scheduling_demand_import import _seed_shared_resolution_data
from test_injection_scheduling_phase3_api import ADMIN_TEST_PASSWORD, make_migrated_client
from test_injection_scheduling_phase4_import import login


def test_shared_mold_catalog_is_paginated_and_returns_factory_detail(monkeypatch):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        _seed_shared_resolution_data()
        db_module = importlib.import_module("app.db")
        shared = importlib.import_module("app.models.injection_scheduling_shared")
        timestamp = "2026-08-10T10:00:00+08:00"
        with db_module.SessionLocal() as db:
            db.add_all(
                [
                    shared.InjectionSchedulingPhysicalMoldAsset(
                        id="asset:catalog-test",
                        mold_definition_id="mold-definition:test-001",
                        owner_scope_type="FACTORY",
                        owner_scope_id="huaxing",
                        asset_code="HX-M-001-01",
                        current_factory_id="huaxing",
                        current_location="模具仓 A 区",
                        status="AVAILABLE",
                        actual_cavity_count=2,
                        revision=1,
                        created_at=timestamp,
                    ),
                    shared.InjectionSchedulingFactoryMoldCapability(
                        id="capability:catalog-test",
                        factory_id="huaxing",
                        mold_definition_id="mold-definition:test-001",
                        mold_output_spec_id=None,
                        physical_asset_id=None,
                        machine_class=14,
                        applicability_key="catalog-test-definition-default",
                        required_arm_type="单臂",
                        required_fixture_type="吸盘",
                        priority=100,
                        status="ACTIVE",
                        revision=1,
                        valid_from=timestamp,
                        approved_by="reviewer",
                        approved_at=timestamp,
                        created_at=timestamp,
                    ),
                    shared.InjectionSchedulingCommercialRateRule(
                        id="rate:catalog-test",
                        owner_scope_type="FACTORY",
                        owner_scope_id="huaxing",
                        applicable_factory_mode="SPECIFIC",
                        applicable_factory_id="huaxing",
                        applicable_customer_mode="ANY",
                        applicable_customer_id=None,
                        mold_definition_id="mold-definition:test-001",
                        mold_output_spec_id="mold-output:test-001-style-01",
                        contract_mode="ANY",
                        contract_id=None,
                        pricing_basis="PER_SHOT",
                        amount=Decimal("0.4656"),
                        currency="CNY",
                        tax_mode="AS_LISTED",
                        priority=100,
                        status="ACTIVE",
                        revision=1,
                        valid_from=timestamp,
                        proposed_by="proposer",
                        approved_by="reviewer",
                        created_at=timestamp,
                        approved_at=timestamp,
                    ),
                ]
            )
            db.commit()

        response = client.get(
            "/api/injection-scheduling/shared-molds/catalog",
            params={
                "factory_id": "huaxing",
                "q": "STYLE-01",
                "readiness": "FACTORY_READY",
                "page": 1,
                "page_size": 10,
            },
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 1
        assert page["summary"]["factory_ready"] == 1
        assert page["items"][0]["canonical_mold_no"] == "M-001"
        assert page["items"][0]["price"]["amount"] == 0.4656
        assert page["items"][0]["factory_readiness"]["status"] == "FACTORY_READY"

        detail_response = client.get(
            "/api/injection-scheduling/shared-molds/catalog/mold-definition:test-001",
            params={"factory_id": "huaxing"},
        )
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["outputs"][0]["item_no"] == "STYLE-01"
        assert detail["capabilities"][0]["machine_class"] == 14
        assert detail["assets"][0]["asset_code"] == "HX-M-001-01"
        assert detail["prices"][0]["currency"] == "CNY"


def test_manual_shared_mold_submission_creates_separate_governance_proposals(monkeypatch):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        response = client.post(
            "/api/injection-scheduling/shared-molds/proposals",
            json={
                "factory_id": "huaxing",
                "request_id": "manual-mold-proposal-0001",
                "reason": "依据工程确认资料新增模具",
                "canonical_mold_no": " 20 330 2018-001 ",
                "display_mold_no": "20 330 2018-001",
                "standard_name": "车面",
                "raw_aliases": ["20-330-2018-001"],
                "recommended_machine_class_raw": "14A 模高",
                "mold_a_class": 14,
                "default_arm_type": "单臂",
                "default_fixture_type": "吸盘",
                "outputs": [
                    {
                        "item_no": "BJ-TEST-001",
                        "product_name": "车面",
                        "cavity_count": 2,
                        "whole_shot_net_weight_g": 29,
                        "whole_shot_gross_weight_g": 31,
                        "default_material": "ABS",
                        "default_color": "黑色",
                        "nominal_daily_capacity": 3200,
                        "unit_price_cny": 0.4656,
                    }
                ],
                "capability": {
                    "machine_class": 14,
                    "machine_class_raw": "14A 模高",
                    "required_arm_type": "单臂",
                    "required_fixture_type": "吸盘",
                },
            },
        )
        assert response.status_code == 201, response.text
        proposals = response.json()["proposals"]
        assert {item["entity_type"] for item in proposals} == {
            "MOLD_DEFINITION_BUNDLE",
            "FACTORY_MOLD_CAPABILITY_BUNDLE",
            "COMMERCIAL_RATE_RULE",
        }
        assert {item["status"] for item in proposals} == {"PROPOSED"}
        assert all(not item["approved_by"] for item in proposals)

        replay = client.post(
            "/api/injection-scheduling/shared-molds/proposals",
            json={
                "factory_id": "huaxing",
                "request_id": "manual-mold-proposal-0001",
                "reason": "依据工程确认资料新增模具",
                "canonical_mold_no": "20 330 2018-001",
                "standard_name": "车面",
                "outputs": [{"product_name": "车面"}],
            },
        )
        assert replay.status_code == 201, replay.text
        assert {item["id"] for item in replay.json()["proposals"]} == {
            item["id"] for item in proposals
        }
