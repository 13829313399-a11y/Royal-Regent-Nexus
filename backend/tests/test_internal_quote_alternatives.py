import importlib
from io import BytesIO

from openpyxl import load_workbook
from PIL import Image
from test_internal_quote_api import make_client, login, logout, create_payload, grant_user_permission


def create(client, suffix="OPTIONS", mode="direct_output"):
    payload = create_payload(suffix=suffix)
    payload["workflow_mode"] = mode
    response = client.post("/api/internal-quotes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def fill(client, quote):
    payloads = {
        "engineering": {"materials": [{"item": "螺丝", "category": "hardware", "quantity": 2, "unit_price_rmb": 0.5}], "molds": []},
        "assembly": {"labor_base_hkd": 310, "groups": [{"name": "装配", "category": "assembly", "processes": [{"name": "组装", "persons": 2, "teams": 1, "production_qty": 5000}]}]},
        "sales": {"packaging_materials": [{"item": "彩盒", "category": "color_box_inner_card", "quantity": 1, "unit_price_rmb": 1}],
                  "cartons": [{"item": "主纸箱", "length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 12}],
                  "testing_fee_enabled": False,
                  "freight_calc": {"enabled": False, "freight_enabled": False, "lifting_enabled": False},
                  "shipping": {"markup_tiers": [{"moq": 5000, "markup_x": 1.2, "include_in_output": True}], "selected_markup_moq": 5000}},
    }
    for code, payload in payloads.items():
        current = client.get(f"/api/internal-quotes/{quote['id']}").json()
        section = next(row for row in current["sections"] if row["department"] == code)
        response = client.put(f"/api/internal-quotes/{quote['id']}/sections/{code}", json={"revision": section["revision"], "payload": payload, "reason": "填写测试资料"})
        assert response.status_code == 200, response.text
        assert response.json()["calculation_status"] == "valid", response.text
    return client.get(f"/api/internal-quotes/{quote['id']}").json()


def fork(client, quote, kind="scenario", name="开窗盒"):
    family = client.get(f"/api/internal-quotes/{quote['id']}/alternatives").json()
    response = client.post(f"/api/internal-quotes/{quote['id']}/alternatives", json={
        "revision": quote["header_revision"], "family_revision": family["revision"],
        "kind": kind, "name": name, "change_note": "客户要求比较另一种包装",
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_independent_options_issue_history_and_selection(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "options-owner", "admin", "*", "*")
        source = fill(client, create(client))
        picture = BytesIO()
        Image.new("RGB", (4, 4), "blue").save(picture, format="PNG")
        uploaded = client.post(f"/api/internal-quotes/{source['id']}/attachments", data={"department": "sales"}, files={"file": ("packing.png", picture.getvalue(), "image/png")})
        assert uploaded.status_code == 201, uploaded.text
        source = client.get(f"/api/internal-quotes/{source['id']}").json()
        target = fork(client, source)
        assert target["module_version"] == "v4"
        assert target["batch_size"] == 1 and target["batch_id"] != source["batch_id"]
        assert target["version_label"] == "B-V1"
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            assert db.get(models.InternalQuoteReferenceSet, target["reference_snapshot_id"]).snapshot_json == db.get(models.InternalQuoteReferenceSet, source["reference_snapshot_id"]).snapshot_json
        source_sales = next(row for row in source["sections"] if row["department"] == "sales")
        target_sales = next(row for row in target["sections"] if row["department"] == "sales")
        assert target_sales["payload"] == source_sales["payload"]
        attachments = client.get(f"/api/internal-quotes/{target['id']}/attachments").json()
        assert any(row["file_name"] == "packing.png" and row["id"] != uploaded.json()["id"] for row in attachments)
        target_sales["payload"]["packaging_materials"][0]["unit_price_rmb"] = 2
        saved = client.put(f"/api/internal-quotes/{target['id']}/sections/sales", json={"revision": target_sales["revision"], "payload": target_sales["payload"], "reason": "改包装"})
        assert saved.status_code == 200, saved.text
        stale_issue = client.post(f"/api/internal-quotes/{target['id']}/direct-issue", json={"revision": target["header_revision"]})
        assert stale_issue.status_code == 409
        unchanged = client.get(f"/api/internal-quotes/{source['id']}").json()
        assert next(row for row in unchanged["sections"] if row["department"] == "sales")["payload"] == source_sales["payload"]
        target = client.get(f"/api/internal-quotes/{target['id']}").json()
        issued = client.post(f"/api/internal-quotes/{target['id']}/direct-issue", json={"revision": target["header_revision"]})
        assert issued.status_code == 200, issued.text
        record = issued.json()
        assert record["release_stage"] == "p4_direct_issued"
        assert "B-V1" in record["file_name"]
        frozen = client.get(f"/api/internal-quotes/{target['id']}").json()
        assert frozen["status"] == "exported" and frozen["final_release_status"] == "issued"
        assert not frozen["final_reviewed_by"]
        assert "rr2_cost_summary" not in frozen["final_submission_manifest"]
        assert all(row["status"] == "sealed" for row in frozen["sections"] if row["is_required"])
        raw = client.get(f"/api/internal-quotes/{target['id']}/exports/{record['id']}/download").content
        workbook = load_workbook(BytesIO(raw), read_only=True)
        assert workbook["审批与版本"]["B4"].value == "P4 直接输出"
        assert workbook["审批与版本"]["B5"].value == "报价版本已冻结，可交接客价转换台"
        workbook.close()
        again = client.post(f"/api/internal-quotes/{target['id']}/direct-issue", json={"revision": target["header_revision"]})
        assert again.status_code == 200 and again.json()["id"] == record["id"]
        blocked = client.put(f"/api/internal-quotes/{target['id']}/sections/sales", json={"revision": saved.json()["revision"] + 1, "payload": target_sales["payload"], "reason": "不应修改已输出版本"})
        assert blocked.status_code == 409
        for endpoint, body in [
            ("reference-snapshot/sync", {"revision": frozen["header_revision"], "reason": "不能改冻结参考价"}),
            ("formula/recalculate", {"revision": frozen["header_revision"], "reason": "不能改冻结公式"}),
        ]:
            response = client.post(f"/api/internal-quotes/{target['id']}/{endpoint}", json=body)
            assert response.status_code == 409
        new_version = fork(client, frozen, "version")
        assert new_version["version_label"] == "B-V2"
        assert client.get(f"/api/internal-quotes/{target['id']}/exports/{record['id']}/download").content == raw
        family = client.get(f"/api/internal-quotes/{source['id']}/alternatives").json()
        archived = client.post(f"/api/internal-quotes/{source['id']}/alternative-archive", json={
            "family_revision": family["revision"], "archived": True, "reason": "原方案不用，仍可管理其他方案采用情况"})
        assert archived.status_code == 200, archived.text
        family = archived.json()
        invalid_target = client.patch(f"/api/internal-quotes/{source['id']}/alternative-selection", json={
            "family_revision": family["revision"], "selected_quote_id": source["id"], "reason": "归档版本本身不能采用"})
        assert invalid_target.status_code == 400
        selected = client.patch(f"/api/internal-quotes/{source['id']}/alternative-selection", json={"family_revision": family["revision"], "selected_quote_id": target["id"], "reason": "客户采用开窗盒"})
        assert selected.status_code == 200, selected.text
        assert selected.json()["selected_quote_id"] == target["id"]
        reported = client.post(f"/api/internal-quotes/{target['id']}/reported", json={"revision": frozen["header_revision"]})
        assert reported.status_code == 200
        assert next(row for row in reported.json()["items"] if row["quote_id"] == target["id"])["reported_at"]
        pool = client.get("/api/customer-price/internal-quote-artifacts", params={"factory_id": "huaxing", "status": "available"})
        assert pool.status_code == 200, pool.text
        assert any(row["quote_id"] == target["id"] for row in pool.json())
        comparison = client.get(f"/api/internal-quotes/{target['id']}/compare/{source['id']}")
        assert comparison.status_code == 200, comparison.text
        assert any(row["path"].startswith("shipping_pricing") for row in comparison.json()["header_changes"])


def test_incomplete_direct_output_and_legacy_copy_preserve_history(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "options-incomplete", "admin", "*", "*")
        empty = create(client)
        response = client.post(f"/api/internal-quotes/{empty['id']}/direct-issue", json={"revision": empty["header_revision"]})
        assert response.status_code == 409
        assert client.get(f"/api/internal-quotes/{empty['id']}/alternatives").json()["revision"] == 0
        legacy = fill(client, create(client, "OLD", "whole_quote_review"))
        new = fork(client, legacy, "version")
        assert new["module_version"] == "v4" and new["version_label"] == "A-V2"
        assert client.get(f"/api/internal-quotes/{legacy['id']}").json() == legacy
        denied = client.post(f"/api/internal-quotes/{new['id']}/final-submit", json={"revision": new["header_revision"]})
        assert denied.status_code == 409


def test_family_conflicts_scope_and_draft_adoption_blocked(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    with make_client(monkeypatch) as client:
        login(client, "options-admin", "admin", "*", "*")
        source = create(client)
        target = fork(client, source)
        stale = client.post(f"/api/internal-quotes/{source['id']}/alternatives", json={"revision": 1, "family_revision": 0, "kind": "version", "change_note": "旧列表"})
        assert stale.status_code == 409
        denied = client.patch(f"/api/internal-quotes/{source['id']}/alternative-selection", json={"family_revision": 1, "selected_quote_id": target["id"], "reason": "尚未输出"})
        assert denied.status_code == 409
        logout(client)
        login(client, "options-other-factory", "sales_customer_supervisor", "sales-business", "huadeng")
        assert client.get(f"/api/internal-quotes/{source['id']}/alternatives").status_code == 403
        assert client.post(f"/api/internal-quotes/{target['id']}/direct-issue", json={"revision": 1}).status_code == 403


def test_batch_archive_cannot_change_issued_sibling_and_defaults_are_direct(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "options-batch", "admin", "*", "*")
        payload = create_payload(suffix="BATCH-OPTIONS")
        payload.pop("workflow_mode")
        payload.update(quote_type="series", products=[{"product_name": "产品 A", "qty": 5000}, {"product_name": "产品 B", "qty": 5000}])
        response = client.post("/api/internal-quotes", json=payload)
        assert response.status_code == 201, response.text
        root = response.json()
        assert root["module_version"] == "v4"
        products = client.get(f"/api/internal-quotes/{root['id']}/batch-products").json()
        sibling = fill(client, client.get(f"/api/internal-quotes/{products[1]['quote_id']}").json())
        issued = client.post(f"/api/internal-quotes/{sibling['id']}/direct-issue", json={"revision": sibling["header_revision"]})
        assert issued.status_code == 200, issued.text
        before = client.get(f"/api/internal-quotes/{sibling['id']}").json()
        archive = client.post(f"/api/internal-quotes/{root['id']}/archive", json={"revision": root["header_revision"], "reason": "整批归档"})
        assert archive.status_code == 409, archive.text
        assert client.get(f"/api/internal-quotes/{sibling['id']}").json() == before
        clone = client.post(f"/api/internal-quotes/{root['id']}/clone", json={
            "quote_no": root["quote_no"], "version_label": "CLONE", "business_owner_id": root["business_owner_id"],
            "business_owner_name": root["business_owner_name"],
        })
        assert clone.status_code == 201, clone.text
        assert clone.json()["module_version"] == "v4"


def test_explicit_clone_denial_cannot_copy_alternatives(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    with make_client(monkeypatch) as client:
        login(client, "options-denied", "sales_customer_owner", "sales-business")
        source = create(client)
        grant_user_permission("options-denied", "internal_quote:clone", "sales-business")
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            override = db.query(models.AuthUserPermissionOverride).filter_by(user_id="user-options-denied").one()
            override.effect = "deny"
            db.commit()
        logout(client)
        login(client, "options-denied", "sales_customer_owner", "sales-business")
        denied = client.post(f"/api/internal-quotes/{source['id']}/alternatives", json={"revision": 1, "family_revision": 0, "kind": "scenario", "name": "禁止复制", "change_note": "不能绕过明确拒绝"})
        assert denied.status_code == 403, denied.text


def test_import_and_attachment_writes_invalidate_stale_issue_and_copy(monkeypatch):
    from test_internal_quote_p3_api import workbook_bytes
    with make_client(monkeypatch) as client:
        login(client, "options-concurrent-import", "admin", "*", "*")
        quote = fill(client, create(client, "CONCURRENT"))
        url = f"/api/internal-quotes/{quote['id']}"

        def verify_stale(previous):
            current = client.get(url).json()
            assert current["header_revision"] > previous["header_revision"]
            issue = client.post(url + "/direct-issue", json={"revision": previous["header_revision"]})
            assert issue.status_code == 409 and "版本" in issue.text, issue.text
            copied = client.post(url + "/alternatives", json={
                "revision": previous["header_revision"], "family_revision": 0,
                "kind": "version", "change_note": "不能复制未核对的数据",
            })
            assert copied.status_code == 409, copied.text
            return current

        picture = BytesIO()
        Image.new("RGB", (4, 4), "green").save(picture, format="PNG")
        for endpoint, data in [("product-image", {}), ("attachments", {"department": "sales"})]:
            uploaded = client.post(url + "/" + endpoint, data=data,
                files={"file": ("concurrent.png", picture.getvalue(), "image/png")})
            assert uploaded.status_code == 201, uploaded.text
            quote = verify_stale(quote)
        sales = next(row for row in quote["sections"] if row["department"] == "sales")
        removed = client.delete(url + f"/attachments/{uploaded.json()['id']}/supporting",
            params={"revision": sales["revision"]})
        assert removed.status_code == 204, removed.text
        quote = verify_stale(quote)

        source = workbook_bytes([
            ["报客价/港币", "报价人", "货号或图片", "做工名称", "总目标数量", "人数"],
            ["车间填写", "车间填写", "车间填写", "车间填写", "车间填写", "车间填写"],
            [None, 8, "组装桶", "测试IC板", 3000, 1],
        ], title="组装")
        preview = client.post(url + "/imports/assembly/preview", files={
            "file": ("装工.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert preview.status_code == 201, preview.text
        assert client.get(url).json()["header_revision"] == quote["header_revision"]
        confirmed = client.post(url + f"/imports/{preview.json()['batch_id']}/confirm",
            json={"revision": preview.json()["target_revision"], "mode": "replace"})
        assert confirmed.status_code == 200, confirmed.text
        quote = verify_stale(quote)
        attachment = next(row for row in client.get(url + "/attachments").json() if row["is_import_source"])
        removed = client.delete(url + f"/attachments/{attachment['id']}",
            params={"revision": confirmed.json()["section"]["revision"]})
        assert removed.status_code == 204, removed.text
        verify_stale(quote)
