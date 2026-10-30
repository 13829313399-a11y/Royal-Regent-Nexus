import importlib
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image

from test_internal_quote_api import make_client, login, logout, create_payload
from test_internal_quote_alternatives import fork


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def current(client, identity):
    return checked(client.get(f"/api/internal-quotes/{identity}"))


def section(quote, code):
    return next(row for row in quote["sections"] if row["department"] == code)


def batch(client, suffix="PACK", factory="huakang-b"):
    data = create_payload(suffix=suffix)
    data.update(factory_id=factory, workshop_code=f"{factory}-workshop", customer="JustPlay",
                workflow_mode="direct_output", quote_type="series", products=[
                    {"product_name": name, "qty": qty, "pricing_components": ["主体", accessory]}
                    for name, qty, accessory in [("A款", 5000, "电话"), ("B款", 6000, "西瓜西柚"), ("C款", 7000, "镜子")]])
    root = checked(client.post("/api/internal-quotes", json=data), 201)
    return [row["quote_id"] for row in checked(client.get(f"/api/internal-quotes/{root['id']}/batch-products"))]


def fill_product(client, identity, name="来源", rate=310):
    data = {
        "engineering": {"materials": [{"item": name + "螺丝", "category": "hardware", "quantity": 2, "unit_price_rmb": .5}], "molds": []},
        "assembly": {"labor_base_hkd": rate, "groups": [
            {"name": name + "组装", "category": "assembly", "processes": [{"name": "组装", "persons": 2, "teams": 1, "production_qty": 5000}]},
            {"name": name + "包装", "category": "packaging", "processes": [{"name": "装盒", "persons": 1, "teams": 1, "production_qty": 5000}]}]},
    }
    for code, payload in data.items():
        row = section(current(client, identity), code)
        checked(client.put(f"/api/internal-quotes/{identity}/sections/{code}", json={"revision": row["revision"], "payload": payload}))
    row = section(current(client, identity), "sales")
    payload = {**row["payload"], "packaging_materials": [{"item": name + "彩盒", "category": "color_box_inner_card", "quantity": 1, "unit_price_rmb": 2}],
               "color_box_size_in": {"length": 12, "width": 8, "height": 6},
               "product_size_in": {"length": 5, "width": 4, "height": 3},
               "cartons": [{"item": "主纸箱", "length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 12}],
               "justplay_packaging": {"adhesive_extra_hkd": .1, "paper_pallet_extra_hkd": .2, "pallet_length_mm": 1300, "pallet_width_mm": 1200, "pallet_height_mm": 1400},
               "testing_fee_enabled": False, "freight_calc": {"enabled": False, "freight_enabled": False, "lifting_enabled": False},
               "shipping": {"markup_x": 1.2, "packaging_markup_x": 1.3}}
    result = checked(client.put(f"/api/internal-quotes/{identity}/sections/sales", json={"revision": row["revision"], "payload": payload}))
    assert result["calculation_status"] == "valid", result
    return current(client, identity)


def upload_image(client, identity, component=None):
    out = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(out, format="PNG")
    url = f"/api/internal-quotes/{identity}/components/{component}/image" if component else f"/api/internal-quotes/{identity}/product-image"
    return checked(client.post(url, data={"revision": current(client, identity)["header_revision"]},
                               files={"file": ("本款.png", out.getvalue(), "image/png")}), 200 if component else 201)


def request(client, source, targets, assembly=False):
    return {"revision": current(client, source)["header_revision"], "targets": [
        {"quote_id": identity, "revision": current(client, identity)["header_revision"]} for identity in targets],
        "include_assembly": assembly, "reason": "共用包装"}


def preview(client, source, body):
    result = checked(client.post(f"/api/internal-quotes/{source}/packaging-copy/preview", json=body))
    return {**body, "preview_token": result["preview_token"]}


def apply(client, source, body, status=200):
    return checked(client.post(f"/api/internal-quotes/{source}/packaging-copy/apply", json=body), status)


def test_document_groups_scenarios_versions_and_keeps_all_product_slots(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "doc-owner", "admin", "*", "*")
        a, b, c = batch(client)
        alternative = fork(client, current(client, b))
        version = fork(client, alternative, "version")
        for identity in (alternative["id"], version["id"]):
            quote = current(client, identity)
            assert quote["document_quote_id"] == a and quote["product_root_id"] == b
            products = checked(client.get(f"/api/internal-quotes/{identity}/batch-products"))
            assert [row["quote_id"] for row in products] == [a, identity, c]
            assert [row["position"] for row in products] == [1, 2, 3]
            assert all(row["batch_size"] == 3 for row in products)
            assert not products[1]["is_baseline"]
        rows = checked(client.get("/api/internal-quotes", params={"factory_id": "huakang-b"}))
        assert [row["id"] for row in rows] == [a]
        assert rows[0]["document_product_count"] == 3 and rows[0]["document_version_count"] == 5
        page = checked(client.get("/api/internal-quotes", params={"factory_id": "huakang-b", "page": 1, "page_size": 20, "keyword": version["version_label"]}))
        assert page["total"] == 1 and page["items"][0]["id"] == a
        family = checked(client.get(f"/api/internal-quotes/{b}/alternatives"))
        assert len(family["items"]) == 3
        # Saving a child does not write into its parent product/version.
        before = section(current(client, b), "sales")
        child = section(current(client, version["id"]), "sales")
        checked(client.put(f"/api/internal-quotes/{version['id']}/sections/sales", json={"revision": child["revision"], "payload": {**child["payload"], "testing_fee_enabled": False}}))
        assert section(current(client, b), "sales") == before


def test_packaging_copy_preserves_identity_images_costs_and_target_reference(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-owner", "admin", "*", "*")
        a, b, c = batch(client)
        fill_product(client, a)
        fill_product(client, b, "目标", 420)
        for component in (None, "component-01", "component-02"):
            upload_image(client, b, component)
        before = current(client, b)
        pictures = checked(client.get(f"/api/internal-quotes/{b}/attachments"))
        body = request(client, a, [b, c], True)
        confirmed = preview(client, a, body)
        assert current(client, b) == before  # Preview writes nothing.
        apply(client, a, confirmed)
        after = current(client, b)
        for field in ("product_name", "qty", "customer", "reference_snapshot_id", "batch_id", "business_owner_id"):
            assert after[field] == before[field]
        assert checked(client.get(f"/api/internal-quotes/{b}/attachments")) == pictures
        assert section(after, "engineering") == section(before, "engineering")
        sales_before, sales_after = section(before, "sales"), section(after, "sales")
        for field in ("pricing_components", "shipping", "product_size_in"):
            assert sales_after["payload"][field] == sales_before["payload"][field]
        assert sales_after["payload"]["packaging_materials"][0]["item"] == "来源彩盒"
        assert sales_after["payload"]["justplay_packaging"] == section(current(client, a), "sales")["payload"]["justplay_packaging"]
        assert sales_after["calculation_status"] == "valid"
        assembly = section(after, "assembly")["payload"]
        assert assembly["labor_base_hkd"] == 420
        assert [row["name"] for row in assembly["groups"]] == ["目标组装", "来源包装"]
        assert section(current(client, c), "sales")["payload"]["packaging_materials"][0]["item"] == "来源彩盒"


def test_packaging_direction_identifies_saved_empty_source_and_packaging_only_source(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-direction", "admin", "*", "*")
        a, b, c = batch(client)
        fill_product(client, a)
        packaging = {"labor_base_hkd": 260, "standard_work_hours": 11, "groups": [
            {"name": "包装人工", "category": "packaging", "production_qty": 5000, "teams": 1, "total_persons": 20},
            {"name": "混装人工", "category": "packaging", "production_qty": 8000, "teams": 1, "total_persons": 18},
        ]}
        for identity, payload in ((a, packaging), (b, {"labor_base_hkd": 260, "groups": []})):
            row = section(current(client, identity), "assembly")
            checked(client.put(f"/api/internal-quotes/{identity}/sections/assembly", json={"revision": row["revision"], "payload": payload}))
        before = current(client, a)
        failed = checked(client.post(f"/api/internal-quotes/{b}/packaging-copy/preview", json=request(client, b, [a], True)), 409)
        assert "B款" in failed["detail"] and "装配部已保存，但核算未通过" in failed["detail"]
        assert "没有符合字段契约的可计算明细" in failed["detail"]
        rows = checked(client.get(f"/api/internal-quotes/{b}/batch-products"))
        ready, empty = rows[0]["packaging_copy"], rows[1]["packaging_copy"]
        assert ready["packaging_labor_hkd"] == "1.6250" and ready["packaging_group_count"] == 2
        assert ready["source_issue"] == ready["assembly_issue"] == ""
        assert "已保存，但核算未通过" in empty["assembly_issue"]
        assert "尚未保存" in rows[2]["packaging_copy"]["assembly_issue"]
        assert rows[0]["version_label"] == before["version_label"]
        assert current(client, a) == before  # Listing and rejected preview are read-only.
        apply(client, a, preview(client, a, request(client, a, [b, c], True)))
        assert section(current(client, b), "assembly")["calculation_status"] == "valid"


def test_packaging_status_reports_version_archive_and_keeps_receivers_without_costing_eligible(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-archive-status", "admin", "*", "*")
        a, b, _ = batch(client)
        fill_product(client, a)
        family = checked(client.get(f"/api/internal-quotes/{a}/alternatives"))
        checked(client.post(f"/api/internal-quotes/{a}/alternative-archive", json={
            "family_revision": family["revision"], "archived": True, "reason": "仅归档此版用于验证"}))
        rows = checked(client.get(f"/api/internal-quotes/{b}/batch-products"))
        assert rows[0]["archived"] is True
        assert "此方案版本已归档" in rows[0]["packaging_copy"]["source_issue"]
        assert "此方案版本已归档" in rows[0]["packaging_copy"]["target_issue"]
        assert rows[1]["packaging_copy"]["target_issue"] == ""
        assert rows[1]["packaging_copy"]["assembly_target_issue"] == ""
        checked(client.post(f"/api/internal-quotes/{a}/packaging-copy/preview", json=request(client, a, [b], True)), 409)


@pytest.mark.parametrize("whole", [False, True])
def test_save_repairs_stale_quote_formula_header_only_after_all_costs_are_current(monkeypatch, whole):
    with make_client(monkeypatch) as client:
        login(client, "pack-formula-header", "admin", "*", "*")
        a, b, _ = batch(client)
        fill_product(client, a)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        calculator = importlib.import_module("app.services.internal_quote_calculator")
        with db_module.SessionLocal() as db:
            db.get(models.InternalQuote, a).formula_version = "rr2-2026-v7"
            db.commit()
        before = current(client, a)
        assert "按当前公式重算" in checked(client.get(f"/api/internal-quotes/{a}/batch-products"))[0]["packaging_copy"]["source_issue"]
        assert current(client, a)["formula_version"] == "rr2-2026-v7"  # Reads never repair data.
        row = section(before, "sales")
        draft = {"revision": row["revision"], "payload": row["payload"]}
        if whole:
            checked(client.put(f"/api/internal-quotes/{a}/sections/save-all", json={"sections": [{"section_code": "sales", **draft}]}))
        else:
            checked(client.put(f"/api/internal-quotes/{a}/sections/sales", json=draft))
        after = current(client, a)
        assert after["formula_version"] == calculator.FORMULA_VERSION
        assert after["header_revision"] == before["header_revision"] + 1
        assert after["sections"] == before["sections"]
        preview(client, a, request(client, a, [b], True))
        # A second unchanged save is still a no-op, not another header revision.
        checked(client.put(f"/api/internal-quotes/{a}/sections/sales", json=draft))
        assert current(client, a)["header_revision"] == after["header_revision"]


@pytest.mark.parametrize("field,value", [
    ("calculation_formula_version", "rr2-2026-v7"), ("calculation_status", "blocked"),
    ("dependency_status", "stale"), ("filled_at", ""), ("calculation_reference_snapshot_id", "old-reference"),
    ("dependency_hash", "outdated"),
])
def test_saving_one_department_cannot_relabel_another_stale_or_incomplete_cost(monkeypatch, field, value):
    with make_client(monkeypatch) as client:
        login(client, "pack-formula-protection", "admin", "*", "*")
        a, _, _ = batch(client)
        fill_product(client, a)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            db.get(models.InternalQuote, a).formula_version = "rr2-2026-v7"
            setattr(db.get(models.InternalQuoteSection, f"{a}-assembly"), field, value)
            db.commit()
        before = current(client, a)
        sales = section(before, "sales")
        checked(client.put(f"/api/internal-quotes/{a}/sections/sales", json={"revision": sales["revision"], "payload": sales["payload"]}))
        after = current(client, a)
        assert after["formula_version"] == "rr2-2026-v7"
        assert after["header_revision"] == before["header_revision"]
        assert section(after, "assembly") == section(before, "assembly")


def test_section_only_old_formula_is_actionable_and_recalculation_unblocks_copy(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-section-formula", "admin", "*", "*")
        source, target, _ = batch(client)
        fill_product(client, source)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        calculator = importlib.import_module("app.services.internal_quote_calculator")
        with db_module.SessionLocal() as db:
            row = db.get(models.InternalQuoteSection, section(current(client, source), "assembly")["id"])
            row.calculation_formula_version = "rr2-2026-v7"
            db.commit()
        before = current(client, source)
        assert before["formula_version"] == before["current_formula_version"] == calculator.FORMULA_VERSION
        assert before["formula_recalculation_required"] is True
        readiness = checked(client.get(f"/api/internal-quotes/{source}/batch-products"))[0]["packaging_copy"]
        assert readiness["formula_recalculation_required"] is True
        assert "按当前公式重算" in readiness["source_issue"]
        checked(client.post(f"/api/internal-quotes/{source}/packaging-copy/preview", json=request(client, source, [target], True)), 409)
        assert section(current(client, source), "assembly")["calculation_formula_version"] == "rr2-2026-v7"
        frozen = checked(client.get(f"/api/internal-quotes/{source}/reference-snapshot"))["snapshot"]
        checked(client.post(f"/api/internal-quotes/{source}/formula/recalculate", json={
            "revision": before["header_revision"], "reason": "复制包装前更新旧部门公式",
        }))
        after = current(client, source)
        assert after["formula_recalculation_required"] is False
        assert section(after, "assembly")["calculation_formula_version"] == calculator.FORMULA_VERSION
        assert checked(client.get(f"/api/internal-quotes/{source}/reference-snapshot"))["snapshot"] == frozen
        readiness = checked(client.get(f"/api/internal-quotes/{source}/batch-products"))[0]["packaging_copy"]
        assert readiness["formula_recalculation_required"] is False
        assert readiness["source_issue"] == readiness["assembly_issue"] == ""
        apply(client, source, preview(client, source, request(client, source, [target], True)))
        assert section(current(client, target), "sales")["payload"]["packaging_materials"][0]["item"] == "来源彩盒"


def test_packaging_scope_stale_preview_and_atomic_rollback(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-atomic", "admin", "*", "*")
        a, b, c = batch(client)
        fill_product(client, a)
        external = batch(client, "OUTSIDE")[1]
        checked(client.post(f"/api/internal-quotes/{a}/packaging-copy/preview", json=request(client, a, [external])), 400)
        body = preview(client, a, request(client, a, [b, c]))
        # An edit after preview must reject the entire batch before any write.
        fill_product(client, c, "后来修改")
        before_b = current(client, b)
        apply(client, a, body, 409)
        assert current(client, b) == before_b
        body = preview(client, a, request(client, a, [b, c]))
        before_b, before_c = current(client, b), current(client, c)
        service = importlib.import_module("app.services.internal_quote_packaging_copy")
        save = service._save_section_in_transaction
        def fail_second(db, quote, *args, **kwargs):
            if quote.id == c:
                from fastapi import HTTPException
                raise HTTPException(409, "模拟第二款核算失败")
            return save(db, quote, *args, **kwargs)
        monkeypatch.setattr(service, "_save_section_in_transaction", fail_second)
        apply(client, a, body, 409)
        assert current(client, b) == before_b and current(client, c) == before_c
        logout(client)
        login(client, "pack-outsider", "sales_customer_owner", "sales-business", "huaxing")
        checked(client.post(f"/api/internal-quotes/{a}/packaging-copy/preview", json=body), 403)


def test_leaf_draft_deletion_before_and_after_archive_preserves_lineage(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "draft-owner", "admin", "*", "*")
        a, b, c = batch(client)
        parent = fork(client, current(client, b))
        leaf = fork(client, parent, "version")
        checked(client.delete(f"/api/internal-quotes/{parent['id']}", params={"revision": parent["header_revision"]}), 409)
        family = checked(client.get(f"/api/internal-quotes/{b}/alternatives"))
        assert not next(row for row in family["items"] if row["quote_id"] == parent["id"])["can_delete"]
        assert next(row for row in family["items"] if row["quote_id"] == leaf["id"])["can_delete"]
        checked(client.post(f"/api/internal-quotes/{leaf['id']}/alternative-archive", json={"family_revision": family["revision"], "archived": True, "reason": "误建"}))
        checked(client.delete(f"/api/internal-quotes/{leaf['id']}", params={"revision": leaf["header_revision"]}), 204)
        checked(client.get(f"/api/internal-quotes/{leaf['id']}"), 404)
        checked(client.delete(f"/api/internal-quotes/{parent['id']}", params={"revision": parent["header_revision"]}), 204)
        assert len(checked(client.get(f"/api/internal-quotes/{b}/alternatives"))["items"]) == 1
        assert len(checked(client.get(f"/api/internal-quotes/{a}/batch-products"))) == 3
        # The remaining original family and all product slots can now be cleaned.
        checked(client.delete(f"/api/internal-quotes/{a}", params={"revision": current(client, a)["header_revision"]}), 204)
        db_module = importlib.import_module("app.db")
        with db_module.SessionLocal() as db:
            assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


def test_single_product_versions_stay_in_one_document_and_scenario_ids_do_not_collide(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "single-document", "admin", "*", "*")
        payload = create_payload(suffix="SINGLE-DOCUMENT")
        payload["workflow_mode"] = "direct_output"
        root = checked(client.post("/api/internal-quotes", json=payload), 201)
        first = fork(client, root, name="误建方案")
        second = fork(client, current(client, root["id"]), name="保留方案")
        checked(client.delete(f"/api/internal-quotes/{first['id']}", params={"revision": first["header_revision"]}), 204)
        third = fork(client, current(client, root["id"]), name="新方案")
        family = checked(client.get(f"/api/internal-quotes/{third['id']}/alternatives"))
        assert len({row["scenario_id"] for row in family["items"]}) == 3
        assert third["version_label"] == "D-V1" and second["version_label"] == "C-V1"
        rows = checked(client.get("/api/internal-quotes", params={"factory_id": "huaxing"}))
        assert [row["id"] for row in rows] == [root["id"]]
        assert rows[0]["document_product_count"] == 1 and rows[0]["document_version_count"] == 3
        assert checked(client.get(f"/api/internal-quotes/{third['id']}/batch-products"))[0]["quote_id"] == third["id"]


def test_packaging_copy_rejects_issued_target_and_stale_source(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-freeze", "admin", "*", "*")
        a, b, c = batch(client)
        fill_product(client, a)
        fill_product(client, b)
        body = preview(client, a, request(client, a, [c]))
        upload_image(client, a)
        apply(client, a, body, 409)
        source = current(client, a)
        checked(client.post(f"/api/internal-quotes/{b}/direct-issue", json={"revision": current(client, b)["header_revision"]}))
        checked(client.post(f"/api/internal-quotes/{a}/packaging-copy/preview", json=request(client, a, [b])), 409)
        # Issued inputs are a valid source; their bytes and sealed version stay unchanged.
        issued = current(client, b)
        target = preview(client, b, request(client, b, [c]))
        apply(client, b, target)
        assert current(client, b) == issued
        checked(client.delete(f"/api/internal-quotes/{b}", params={"revision": issued["header_revision"]}), 409)


def test_invalid_target_geometry_rejects_copy_without_committing_any_target(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "pack-invalid-geometry", "admin", "*", "*")
        a, b, c = batch(client)
        fill_product(client, a)
        fill_product(client, b)
        row = section(current(client, a), "sales")
        checked(client.put(f"/api/internal-quotes/{a}/sections/sales", json={
            "revision": row["revision"], "payload": {**row["payload"], "justplay_carton": {
                "dimension_source": "product", "length_count": 1, "width_count": 1, "height_count": 1}}}))
        # C has no product dimensions yet. Those product-owned values must not
        # be overwritten merely to make the copied packaging calculate.
        body = preview(client, a, request(client, a, [b, c]))
        before_b, before_c = current(client, b), current(client, c)
        result = apply(client, a, body, 409)
        assert "C款的业务部核算未通过，整批未复制" in result["detail"]
        assert current(client, b) == before_b and current(client, c) == before_c


def test_packaging_merge_keeps_target_multipliers_and_customer_supplements():
    from app.services.internal_quote_packaging_copy import merge_packaging
    before = {"pricing_components": [{"id": "component-02", "name": "西瓜西柚"}],
              "shipping": {"packaging_markup_x": 1.3}, "packaging_materials": [{
                  "item": "彩盒", "category": "color_box_inner_card", "unit_price_rmb": 1,
                  "markup_override": 1.4, "customer_description": "目标", "pricing_component_id": "component-02"}]}
    source = {"packaging_materials": [{"item": "彩盒", "category": "color_box_inner_card", "unit_price_rmb": 2,
                                       "markup_override": 9, "customer_description": "来源", "pricing_component_id": "source-01"}]}
    result = merge_packaging(before, source, "sales")
    assert result["pricing_components"] == before["pricing_components"]
    assert result["shipping"] == before["shipping"]
    row = result["packaging_materials"][0]
    assert row["unit_price_rmb"] == 2 and row["markup_override"] == 1.4 and row["customer_description"] == "目标"
    assert "pricing_component_id" not in row
    assert before["packaging_materials"][0]["unit_price_rmb"] == 1
