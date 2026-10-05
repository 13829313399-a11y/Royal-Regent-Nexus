import importlib
import json
import pytest

from test_internal_quote_api import create_payload, ensure_user, grant_user_permission, login, logout, make_client


def mark_whole_quote_ready(quote_id: str) -> None:
    db_module = importlib.import_module("app.db")
    quote_models = importlib.import_module("app.models.internal_quote")
    quote_service = importlib.import_module("app.services.internal_quote")
    with db_module.SessionLocal() as db:
        quote = db.get(quote_models.InternalQuote, quote_id)
        sections = db.query(quote_models.InternalQuoteSection).filter_by(quote_id=quote_id).all()
        for section in sections:
            if not section.is_required:
                continue
            section.payload_json = json.dumps(
                {"confirmed": True, "department": section.department},
                ensure_ascii=False,
                sort_keys=True,
            )
            section.calculation_json = json.dumps(
                {"status": "valid", "totals": {"total_hkd": "0"}, "warnings": []},
                ensure_ascii=False,
                sort_keys=True,
            )
            section.calculation_status = "valid"
            section.calculation_hash = f"valid-{section.department}"
            section.dependency_status = "current"
            section.filled_by = quote.created_by_name
            section.filled_at = quote.updated_at
            section.status = "draft"
        quote_service._derive_quote_status(db, quote)
        assert quote.status == "ready_for_final_review"
        db.commit()


def whole_review_payload(suffix: str, reviewer_id: str, reviewer_name: str) -> dict:
    payload = create_payload(suffix=suffix)
    payload.update(
        {
            "business_owner_id": reviewer_id,
            "business_owner_name": reviewer_name,
            "workflow_mode": "whole_quote_review",
        }
    )
    return payload


@pytest.mark.parametrize('decision', ['approve', 'reject'])
@pytest.mark.parametrize('count', [1, 2])
@pytest.mark.parametrize('creator', ['engineer', 'reviewer'])
def test_selected_reviewer_can_review_own_whole_submission(monkeypatch, decision, count, creator):
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    monkeypatch.setenv('AUTHZ_WRITES_ENABLED', 'true')
    with make_client(monkeypatch) as client:
        ensure_user('reviewer', 'sales_customer_owner', 'sales-business')
        grant_user_permission('reviewer', 'internal_quote:sales_review', 'sales-business')
        if creator == 'engineer':
            login(client, creator, 'engineer', 'engineering')
        else:
            login(client, creator, 'sales_customer_owner', 'sales-business')
        payload = whole_review_payload('SAME-SUBMITTER', 'user-reviewer', 'reviewer')
        payload['initiator_department'] = 'engineering' if creator == 'engineer' else 'sales-business'
        if count == 2:
            payload.update(quote_type='series', products=[
                {'product_name': '第一款', 'qty': 5000}, {'product_name': '第二款', 'qty': 5000},
            ])
        created = client.post('/api/internal-quotes', json=payload)
        assert created.status_code == 201, created.text
        root = created.json()
        products = client.get(f"/api/internal-quotes/{root['id']}/batch-products").json()
        ids = [item['quote_id'] for item in products]
        assert len(ids) == count
        for quote_id in ids:
            mark_whole_quote_ready(quote_id)
        logout(client)
        profile = login(client, 'reviewer', 'sales_customer_owner', 'sales-business')
        assert 'internal_quote:self_review' not in profile['permissions']
        submitted = client.post(f"/api/internal-quotes/{ids[0]}/final-submit", json={'revision': 1})
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()['quote']['final_submitted_by'] == 'user-reviewer'
        reviewed = client.post(f"/api/internal-quotes/{ids[-1]}/final-review", json={
            'revision': 2, 'decision': decision, 'reason': '指定审核人自行提交后复核',
        })
        assert reviewed.status_code == 200, reviewed.text
        for quote_id in ids:
            result = client.get(f'/api/internal-quotes/{quote_id}').json()
            assert result['status'] == ('fully_approved' if decision == 'approve' else 'rejected')
            assert result['final_submitted_by'] == result['final_reviewed_by'] == 'user-reviewer'
            history = client.get(f'/api/internal-quotes/{quote_id}/final-reviews').json()
            assert len(history) == 1 and history[0]['actor_id'] == 'user-reviewer'
            assert history[0]['decision'] == decision
        duplicate = client.post(f"/api/internal-quotes/{ids[0]}/final-review", json={
            'revision': 2, 'decision': decision, 'reason': '重复操作',
        })
        assert duplicate.status_code == 409


def test_whole_quote_review_submits_once_and_only_selected_reviewer_can_approve(monkeypatch):
    with make_client(monkeypatch) as client:
        reviewer_username = "iq_whole_selected_reviewer"
        ensure_user(
            reviewer_username,
            "sales_customer_supervisor",
            "sales-business",
        )
        ensure_user(
            "iq_whole_other_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        submitter = login(
            client,
            "iq_whole_submitter",
            "sales_customer_owner",
            "sales-business",
        )
        assert "internal_quote:final_submit" in submitter["permissions"]

        created = client.post(
            "/api/internal-quotes",
            json=whole_review_payload(
                "WHOLE-APPROVE",
                f"user-{reviewer_username}",
                reviewer_username,
            ),
        )
        assert created.status_code == 201, created.text
        quote = created.json()
        quote_id = quote["id"]
        assert quote["module_version"] == "v3"

        legacy_section_submit = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/submit",
            json={"revision": 1},
        )
        assert legacy_section_submit.status_code == 409
        assert "整单审核" in legacy_section_submit.json()["detail"]

        mark_whole_quote_ready(quote_id)
        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        )
        assert submitted.status_code == 200, submitted.text
        submitted_body = submitted.json()
        assert submitted_body["review"] is None
        assert submitted_body["export"] is None
        assert submitted_body["quote"]["status"] == "final_reviewing"
        assert submitted_body["quote"]["final_release_status"] == "pending"
        assert submitted_body["quote"]["header_revision"] == 2
        assert all(
            section["status"] == "pending_review"
            for section in submitted_body["quote"]["sections"]
            if section["is_required"]
        )

        logout(client)
        login(
            client,
            "iq_whole_other_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        forbidden = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "非指定审核人"},
        )
        assert forbidden.status_code == 403
        assert "指定的业务审核负责人" in forbidden.json()["detail"]

        logout(client)
        login(
            client,
            "iq_whole_selected_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        approved = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "整单复核通过"},
        )
        assert approved.status_code == 200, approved.text
        approved_body = approved.json()
        assert approved_body["quote"]["status"] == "fully_approved"
        assert approved_body["quote"]["final_release_status"] == "approved"
        assert approved_body["quote"]["final_release_revision"] == 1
        assert approved_body["review"]["decision"] == "approve"
        assert approved_body["review"]["actor_id"] == f"user-{reviewer_username}"
        assert approved_body["export"] is None
        assert all(
            section["status"] == "approved"
            for section in approved_body["quote"]["sections"]
            if section["is_required"]
        )


def test_whole_quote_rejection_unlocks_every_participating_section(monkeypatch):
    with make_client(monkeypatch) as client:
        reviewer_username = "iq_whole_reject_reviewer"
        ensure_user(
            reviewer_username,
            "sales_customer_supervisor",
            "sales-business",
        )
        login(
            client,
            "iq_whole_reject_submitter",
            "sales_customer_owner",
            "sales-business",
        )
        created = client.post(
            "/api/internal-quotes",
            json=whole_review_payload(
                "WHOLE-REJECT",
                f"user-{reviewer_username}",
                reviewer_username,
            ),
        )
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        mark_whole_quote_ready(quote_id)

        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        )
        assert submitted.status_code == 200, submitted.text

        logout(client)
        login(
            client,
            "iq_whole_reject_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        rejected = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "reject", "reason": "整单资料需要修正"},
        )
        assert rejected.status_code == 200, rejected.text
        rejected_body = rejected.json()
        assert rejected_body["quote"]["status"] == "rejected"
        assert rejected_body["quote"]["final_release_status"] == "rejected"
        assert rejected_body["review"]["decision"] == "reject"
        assert all(
            section["status"] == "rejected"
            for section in rejected_body["quote"]["sections"]
            if section["is_required"]
        )

        logout(client)
        login(
            client,
            "iq_whole_reject_submitter",
            "sales_customer_owner",
            "sales-business",
        )
        header_unlocked = client.patch(
            f"/api/internal-quotes/{quote_id}",
            json={
                "revision": rejected_body["quote"]["header_revision"],
                "remark": "退回后整单资料已解锁",
            },
        )
        assert header_unlocked.status_code == 200, header_unlocked.text
        assert header_unlocked.json()["remark"] == "退回后整单资料已解锁"


def test_clone_can_explicitly_preserve_legacy_whole_quote_workflow(monkeypatch):
    with make_client(monkeypatch) as client:
        owner = login(
            client,
            "iq_whole_clone_owner",
            "sales_customer_supervisor",
            "sales-business",
        )
        created = client.post(
            "/api/internal-quotes",
            json=whole_review_payload(
                "WHOLE-CLONE-SOURCE",
                owner["id"],
                owner["display_name"],
            ),
        )
        assert created.status_code == 201, created.text

        cloned = client.post(
            f"/api/internal-quotes/{created.json()['id']}/clone",
            json={
                "quote_no": "IQ-TEST-WHOLE-CLONE-TARGET",
                "workflow_mode": "whole_quote_review",
                "version_label": "V2",
                "business_owner_id": owner["id"],
                "business_owner_name": owner["display_name"],
            },
        )
        assert cloned.status_code == 201, cloned.text
        assert cloned.json()["module_version"] == "v3"


def test_multi_product_batch_is_listed_once_and_reviewed_in_one_transaction(monkeypatch):
    with make_client(monkeypatch) as client:
        reviewer_username = "iq_batch_selected_reviewer"
        ensure_user(
            reviewer_username,
            "sales_customer_supervisor",
            "sales-business",
        )
        login(
            client,
            "iq_batch_submitter",
            "sales_customer_owner",
            "sales-business",
        )
        payload = whole_review_payload(
            "WHOLE-BATCH",
            f"user-{reviewer_username}",
            reviewer_username,
        )
        payload.update(
            {
                "quote_type": "series",
                "products": [
                    {"product_name": "系列基准款", "qty": 5000, "region_code": ""},
                    {"product_name": "系列第二款", "qty": 5000, "region_code": ""},
                ],
            }
        )
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        root = created.json()
        assert root["batch_size"] == 2
        assert root["batch_position"] == 1

        products_response = client.get(f"/api/internal-quotes/{root['id']}/batch-products")
        assert products_response.status_code == 200, products_response.text
        products = products_response.json()
        assert [item["product_name"] for item in products] == ["系列基准款", "系列第二款"]
        assert [item["is_baseline"] for item in products] == [True, False]
        child_id = products[1]["quote_id"]

        list_response = client.get("/api/internal-quotes?factory_id=huaxing")
        assert list_response.status_code == 200, list_response.text
        assert sum(item["batch_id"] == root["batch_id"] for item in list_response.json()) == 1

        mark_whole_quote_ready(root["id"])
        mark_whole_quote_ready(child_id)
        submitted = client.post(
            f"/api/internal-quotes/{child_id}/final-submit",
            json={"revision": 1},
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["quote"]["status"] == "final_reviewing"
        assert client.get(f"/api/internal-quotes/{root['id']}").json()["status"] == "final_reviewing"

        logout(client)
        login(
            client,
            reviewer_username,
            "sales_customer_supervisor",
            "sales-business",
        )
        approved = client.post(
            f"/api/internal-quotes/{child_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "整批确认通过"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["quote"]["status"] == "fully_approved"
        assert client.get(f"/api/internal-quotes/{root['id']}").json()["status"] == "fully_approved"


def test_batch_baseline_copy_keeps_target_identity_and_then_diverges_independently(monkeypatch):
    with make_client(monkeypatch) as client:
        owner = login(
            client,
            "iq_batch_copy_owner",
            "sales_customer_supervisor",
            "sales-business",
        )
        payload = whole_review_payload(
            "WHOLE-BATCH-COPY",
            owner["id"],
            owner["display_name"],
        )
        payload.update(
            {
                "quote_type": "series",
                "products": [
                    {"product_name": "基准产品", "qty": 5000, "region_code": ""},
                    {"product_name": "目标产品", "qty": 3000, "region_code": ""},
                ],
            }
        )
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        root = created.json()
        products = client.get(f"/api/internal-quotes/{root['id']}/batch-products").json()
        target_id = products[1]["quote_id"]

        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            baseline = db.get(quote_models.InternalQuote, root["id"])
            baseline.remark = "从基准款复制的公共资料"
            sales = db.query(quote_models.InternalQuoteSection).filter_by(
                quote_id=root["id"],
                department="sales",
            ).one()
            sales.payload_json = json.dumps(
                {
                    "packaging_materials": [{
                        "item": "基准彩盒",
                        "category": "color_box_inner_card",
                        "quantity": 1,
                        "unit_price_rmb": 1,
                        "unit_price_source_currency": "RMB",
                        "loss_rate": 1,
                        "tax_rate_percent": 0,
                    }]
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            db.commit()

        copied = client.post(
            f"/api/internal-quotes/{root['id']}/batch-products/{target_id}/copy-baseline",
            json={"revision": 1},
        )
        assert copied.status_code == 200, copied.text
        copied_body = copied.json()
        assert copied_body["product_name"] == "目标产品"
        assert copied_body["qty"] == 5000
        assert copied_body["remark"] == "从基准款复制的公共资料"
        assert copied_body["cloned_from_quote_id"] == root["id"]
        assert copied_body["header_revision"] == 2
        copied_sales = next(
            section for section in copied_body["sections"] if section["department"] == "sales"
        )
        assert copied_sales["payload"]["packaging_materials"][0]["item"] == "基准彩盒"

        copied_products = client.get(f"/api/internal-quotes/{target_id}/batch-products").json()
        assert copied_products[1]["differs_from_baseline"] is False
        assert copied_products[1]["different_header_fields"] == []
        assert copied_products[1]["different_sections"] == []

        target_payload = copied_sales["payload"]
        target_payload["packaging_materials"][0]["item"] = "目标款独立彩盒"
        changed = client.put(
            f"/api/internal-quotes/{target_id}/sections/sales",
            json={"revision": copied_sales["revision"], "payload": target_payload},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["payload"]["packaging_materials"][0]["item"] == "目标款独立彩盒"
        baseline_after = client.get(f"/api/internal-quotes/{root['id']}").json()
        baseline_sales = next(
            section for section in baseline_after["sections"] if section["department"] == "sales"
        )
        assert baseline_sales["payload"]["packaging_materials"][0]["item"] == "基准彩盒"
        diverged_products = client.get(f"/api/internal-quotes/{target_id}/batch-products").json()
        assert diverged_products[1]["differs_from_baseline"] is True
        assert diverged_products[1]["different_header_fields"] == []
        assert diverged_products[1]["different_sections"] == ["sales"]
        assert any(
            "包装材料" in detail and "名称" in detail
            for detail in diverged_products[1]["different_section_details"]["sales"]
        )


def test_batch_baseline_copy_does_not_cross_copy_indonesia_freight(monkeypatch):
    with make_client(monkeypatch) as client:
        owner = login(
            client,
            "iq_region_copy_owner",
            "sales_customer_supervisor",
            "sales-business",
        )
        payload = whole_review_payload(
            "WHOLE-REGION-COPY",
            owner["id"],
            owner["display_name"],
        )
        payload.update(
            {
                "quote_type": "multi_region",
                "products": [
                    {"product_name": "复制基准—大陆价", "qty": 5000, "region_code": "mainland"},
                    {"product_name": "复制目标—印尼价", "qty": 5000, "region_code": "indonesia"},
                ],
            }
        )
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        root = created.json()
        products = client.get(f"/api/internal-quotes/{root['id']}/batch-products").json()
        target_id = products[1]["quote_id"]

        root_sales = next(section for section in root["sections"] if section["department"] == "sales")
        saved_root = client.put(
            f"/api/internal-quotes/{root['id']}/sections/sales",
            json={
                "revision": root_sales["revision"],
                "payload": {"indonesia_freight_hkd": 99, "additional_tax_hkd": 2},
            },
        )
        assert saved_root.status_code == 200, saved_root.text

        target = client.get(f"/api/internal-quotes/{target_id}").json()
        target_sales = next(section for section in target["sections"] if section["department"] == "sales")
        saved_target = client.put(
            f"/api/internal-quotes/{target_id}/sections/sales",
            json={
                "revision": target_sales["revision"],
                "payload": {"indonesia_freight_hkd": 3.25},
            },
        )
        assert saved_target.status_code == 200, saved_target.text

        refreshed_target = client.get(f"/api/internal-quotes/{target_id}").json()
        copied = client.post(
            f"/api/internal-quotes/{root['id']}/batch-products/{target_id}/copy-baseline",
            json={"revision": refreshed_target["header_revision"]},
        )
        assert copied.status_code == 200, copied.text
        copied_sales = next(
            section for section in copied.json()["sections"] if section["department"] == "sales"
        )
        assert copied_sales["payload"]["indonesia_freight_hkd"] == 3.25
        assert copied_sales["payload"]["additional_tax_hkd"] == 2

        summary = client.get(f"/api/internal-quotes/{target_id}/summary")
        assert summary.status_code == 200, summary.text
        assert summary.json()["rr2_cost_summary"]["indonesia_freight_hkd"] == "3.2500"
