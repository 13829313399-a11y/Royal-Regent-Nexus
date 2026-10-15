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
        preserved = client.get(f"/api/internal-quotes/{legacy['id']}").json()
        # Deletion eligibility changes when a descendant exists; stored history does not.
        assert {key: value for key, value in preserved.items() if key not in {"delete_block_reason", "document_version_count"}} == {key: value for key, value in legacy.items() if key not in {"delete_block_reason", "document_version_count"}}
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


def test_selective_copy_preserves_unselected_departments_pending_and_issued_history(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "selective-owner", "admin", "*", "*")
        source = fill(client, create(client, "SELECTIVE"))
        picture = BytesIO()
        Image.new("RGB", (4, 4), "blue").save(picture, format="PNG")
        for code in ("engineering", "sales"):
            response = client.post(f"/api/internal-quotes/{source['id']}/attachments", data={"department": code}, files={"file": (f"{code}.png", picture.getvalue(), "image/png")})
            assert response.status_code == 201, response.text
        source = client.get(f"/api/internal-quotes/{source['id']}").json()
        issued = client.post(f"/api/internal-quotes/{source['id']}/direct-issue", json={"revision": source["header_revision"]})
        assert issued.status_code == 200, issued.text
        record = issued.json()
        frozen = client.get(f"/api/internal-quotes/{source['id']}").json()
        raw = client.get(f"/api/internal-quotes/{source['id']}/exports/{record['id']}/download").content
        for selected in (["engineering"], ["engineering", "assembly"]):
            family = client.get(f"/api/internal-quotes/{source['id']}/alternatives").json()
            response = client.post(f"/api/internal-quotes/{source['id']}/alternatives", json={"revision": frozen["header_revision"], "family_revision": family["revision"], "kind": "scenario", "name": "/".join(selected), "change_note": "选择部门", "copy_departments": selected})
            assert response.status_code == 200, response.text
            target = response.json()
            assert [r["department"] for r in target["sections"] if r["is_required"]] == [r["department"] for r in frozen["sections"] if r["is_required"]]
            for section in target["sections"]:
                if section["department"] in selected:
                    assert section["payload"] == next(r for r in frozen["sections"] if r["department"] == section["department"])["payload"]
                    assert section["filled_at"] and section["calculation_status"] == "valid"
                elif section["is_required"]:
                    assert section["payload"] == {}
                    assert not section["filled_at"] and section["calculation_status"] == "pending"
            docs = client.get(f"/api/internal-quotes/{target['id']}/attachments").json()
            assert [doc["department"] for doc in docs] == ["engineering"]
            blocked = client.post(f"/api/internal-quotes/{target['id']}/direct-issue", json={"revision": target["header_revision"]})
            assert blocked.status_code == 409
        preserved = client.get(f"/api/internal-quotes/{source['id']}").json()
        assert preserved["sections"] == frozen["sections"]
        assert client.get(f"/api/internal-quotes/{source['id']}/exports/{record['id']}/download").content == raw


def test_selective_copy_rejects_invalid_department_sets_without_creating_versions(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "selective-invalid", "admin", "*", "*")
        source = create(client, "SELECTIVE-INVALID")
        for selected, status in (([], 422), (["engineering", "engineering"], 422), (["unknown"], 422), (["painting"], 400)):
            response = client.post(f"/api/internal-quotes/{source['id']}/alternatives", json={"revision": source["header_revision"], "family_revision": 0, "kind": "scenario", "name": "不应创建", "change_note": "无效选择", "copy_departments": selected})
            assert response.status_code == status, response.text
            assert client.get(f"/api/internal-quotes/{source['id']}/alternatives").json()["revision"] == 0


def test_engineering_only_copy_does_not_auto_fill_molding(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "selective-engineering", "admin", "*", "*")
        payload = create_payload(suffix="SELECTIVE-MOLD", participating_sections=["engineering", "molding", "assembly", "sales"])
        payload["workflow_mode"] = "direct_output"
        response = client.post("/api/internal-quotes", json=payload)
        assert response.status_code == 201, response.text
        source = response.json()
        engineering = next(s for s in source["sections"] if s["department"] == "engineering")
        saved = client.put(f"/api/internal-quotes/{source['id']}/sections/engineering", json={"revision": engineering["revision"], "payload": {"materials": [], "molds": [{"mold_id": "m1", "item": "外壳", "net_weight_g": 50, "quantity": 1, "cavity": "2"}]}, "reason": "工程模具"})
        assert saved.status_code == 200, saved.text
        source = client.get(f"/api/internal-quotes/{source['id']}").json()
        response = client.post(f"/api/internal-quotes/{source['id']}/alternatives", json={"revision": source["header_revision"], "family_revision": 0, "kind": "scenario", "name": "仅工程", "change_note": "啤机待填写", "copy_departments": ["engineering"]})
        assert response.status_code == 200, response.text
        target = response.json()
        for _ in range(2):
            target = client.get(f"/api/internal-quotes/{target['id']}").json()
            molding = next(s for s in target["sections"] if s["department"] == "molding")
            assert molding["payload"] == {"engineering_prefill_paused": True}
            assert not molding["filled_at"] and molding["calculation_status"] == "pending"


def test_molding_only_copy_retains_rows_and_requires_missing_engineering_resolution(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "selective-molding", "admin", "*", "*")
        created = client.post("/api/internal-quotes", json={**create_payload(suffix="ONLY-MOLD", participating_sections=["engineering", "molding", "assembly", "sales"]), "workflow_mode": "direct_output"})
        assert created.status_code == 201, created.text
        source = created.json()
        for code, payload in (("engineering", {"molds": [{"mold_id": "m1", "item": "外壳", "net_weight_g": 50, "quantity": 1, "cavity": "2"}]}), ("molding", {"injection_lines": [{"line_id": "injection:m1", "engineering_mold_id": "m1", "engineering_source_key": "mold-id:m1", "engineering_synced_fields": ["item"], "item": "外壳", "material": "ABS", "grade": "750SW", "net_weight_g": 50, "sets": 1, "quantity": 1, "target_output": 2000, "machine_code": "18A"}]})):
            current = client.get(f"/api/internal-quotes/{source['id']}").json()
            section = next(row for row in current["sections"] if row["department"] == code)
            saved = client.put(f"/api/internal-quotes/{source['id']}/sections/{code}", json={"revision": section["revision"], "payload": payload, "reason": "填写来源"})
            assert saved.status_code == 200, saved.text
        source = client.get(f"/api/internal-quotes/{source['id']}").json()
        copied = client.post(f"/api/internal-quotes/{source['id']}/alternatives", json={"revision": source["header_revision"], "family_revision": 0, "kind": "scenario", "name": "仅啤机", "change_note": "工程重新填写", "copy_departments": ["molding"]})
        assert copied.status_code == 200, copied.text
        target = copied.json()
        molding = next(s for s in target["sections"] if s["department"] == "molding")
        line = molding["payload"]["injection_lines"][0]
        assert line["engineering_mold_id"] == "m1" and line["engineering_source_missing"] is True
        assert not line.get("engineering_sync_disabled")
        assert molding["dependency_status"] == "stale"
        assert next(s for s in target["sections"] if s["department"] == "engineering")["payload"] == {}


def test_selective_copy_keeps_product_components_and_referenced_images_without_sales_costs(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "selective-components", "admin", "*", "*")
        source = create(client, "COMPONENT-COPY")
        base = f"/api/internal-quotes/{source['id']}"
        picture = BytesIO()
        Image.new("RGB", (4, 4), "green").save(picture, format="PNG")
        image = client.post(base + "/attachments", data={"department": "sales"}, files={"file": ("referenced.png", picture.getvalue(), "image/png")})
        assert image.status_code == 201, image.text
        for code, payload in (("sales", {"pricing_mode": "component", "pricing_components": [{"id": "body", "name": "主件", "markup_x": 1.8}], "packaging_materials": [{"item": "彩盒", "quantity": 1, "unit_price_rmb": 5}]}), ("engineering", {"materials": [{"item": "螺丝", "category": "hardware", "quantity": 1, "unit_price_rmb": 1, "pricing_component_id": "body"}], "molds": [{"mold_id": "m1", "item": "外壳", "image_attachment_ids": [image.json()["id"]]}]})):
            quote = client.get(base).json()
            section = next(row for row in quote["sections"] if row["department"] == code)
            saved = client.put(base + f"/sections/{code}", json={"revision": section["revision"], "payload": payload, "reason": "测试组件与图片"})
            assert saved.status_code == 200, saved.text
        source = client.get(base).json()
        response = client.post(base + "/alternatives", json={"revision": source["header_revision"], "family_revision": 0, "kind": "scenario", "name": "组件工程", "change_note": "仅复制工程", "copy_departments": ["engineering"]})
        assert response.status_code == 200, response.text
        target = response.json()
        sales = next(row for row in target["sections"] if row["department"] == "sales")
        assert sales["payload"] == {"pricing_mode": "component", "pricing_components": [{"id": "body", "name": "主件"}]}
        assert not sales["filled_at"] and sales["calculation_status"] == "pending"
        engineering = next(row for row in target["sections"] if row["department"] == "engineering")
        images = engineering["payload"]["molds"][0]["image_attachment_ids"]
        assert len(images) == 1 and images[0] != image.json()["id"]
        attachments = client.get(f"/api/internal-quotes/{target['id']}/attachments").json()
        assert images == [row["id"] for row in attachments]
