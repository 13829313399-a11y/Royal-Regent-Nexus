import importlib
import json
from io import BytesIO

import pytest
from PIL import Image

from test_internal_quote_api import create_payload, login, logout, make_client, ALL_SECTION_CODES


def create(client, suffix, *, jp=False, products=None):
    payload = create_payload(suffix=suffix, participating_sections=ALL_SECTION_CODES)
    payload.update(workflow_mode="whole_quote_review")
    if jp:
        payload.update(factory_id="huakang-b", workshop_code="huakang-b-workshop", customer="JustPlay", pricing_components=["主体", "电话", "镜子"])
    if products:
        payload.update(quote_type="series" if len(products) > 1 else "single", products=products)
    response = client.post("/api/internal-quotes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def source_ref(row, component=""):
    return {"quote_id": row["quote_id"], "fingerprint": row["fingerprint"], "component_id": component}


def catalog(client, factory="huakang-b", **params):
    response = client.get("/api/internal-quotes/history-products", params={"factory_id": factory, **params})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def put_source(quote_id, payloads):
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.internal_quote")
    with db_module.SessionLocal() as db:
        for code, payload in payloads.items():
            section = db.get(models.InternalQuoteSection, f"{quote_id}-{code}")
            section.payload_json = json.dumps(payload)
            section.revision += 1
        db.commit()


def parts(quote, code):
    return next(s for s in quote["sections"] if s["department"] == code)["payload"]


def test_ordinary_can_choose_a_nonroot_regional_product_and_append_other_products(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_sales", "sales_customer_owner", "sales-business")
        old = create(client, "REGIONAL", products=[{"product_name": "A大陆", "qty": 100, "region_code": "mainland"},
                                                  {"product_name": "B印尼", "qty": 200, "region_code": "indonesia"}])
        batch = client.get(f"/api/internal-quotes/{old['id']}/batch-products").json()
        bid = batch[1]["quote_id"]
        put_source(bid, {"engineering": {"materials": [{"item": "B五金", "category": "hardware", "quantity": 2, "unit_price_rmb": 1, "import_batch_id": "old-import"}]},
                         "sales": {"indonesia_freight_hkd": 5, "shipping": {"markup_x": 9}}})
        rows = catalog(client, "huaxing", keyword="B印尼", region_code="indonesia")
        assert len(rows) == 1 and rows[0]["quote_id"] == bid
        new = create(client, "NEW", products=[{"product_name": "B新大陆", "qty": 500, "region_code": "mainland", "history_source": source_ref(rows[0])},
                                               {"product_name": "手动F", "qty": 600}])
        copied = parts(new, "engineering")["materials"][0]
        assert copied["item"] == "B五金" and copied["unit_price_rmb"] == 1
        assert "import_batch_id" not in copied
        assert "shipping" not in parts(new, "sales") and "indonesia_freight_hkd" not in parts(new, "sales")
        assert new["qty"] == 500 and new["customer"] == old["customer"]
        assert new["cloned_from_quote_id"] == bid and new["history_sources"][0]["region_code"] == "indonesia"
        assert new["final_release_status"] == "" and all(s["status"] == "draft" for s in new["sections"])
        assert next(s for s in new["sections"] if s["department"] == "engineering")["calculation_status"] == "valid"
        assert parts(client.get(f"/api/internal-quotes/{bid}").json(), "engineering")["materials"][0]["import_batch_id"] == "old-import"


def test_justplay_whole_copy_replace_and_cross_product_recombine_images_and_mold_links(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_jp", "sales_customer_owner", "sales-business", "huakang-b")
        a, b = create(client, "A", jp=True), create(client, "B", jp=True)
        for quote, cost in [(a, 1), (b, 3)]:
            put_source(quote["id"], {
                "sales": {**parts(quote, "sales"), "justplay_packaging": {
                    "adhesive_extra_hkd": .1, "paper_pallet_extra_hkd": .2,
                    "pallet_length_mm": 800 + 500 * cost, "pallet_width_mm": 1200, "pallet_height_mm": 1400}},
                "engineering": {"materials": [{"item": f"电话电池{cost}", "category": "auxiliary", "auxiliary_category": "电池", "quantity": 1, "unit_price_hkd": cost, "pricing_component_id": "component-02"},
                                              {"item": "共享包装", "category": "packaging", "quantity": 1, "unit_price_hkd": 7}],
                                "molds": [{"item": f"电话壳{cost}", "mold_no": "M1", "quantity": 1, "cost_rmb": 100, "pricing_component_id": "component-02"}]},
                "molding": {"injection_lines": [{"item": f"电话壳{cost}", "mold_no": "M1", "engineering_source_key": "mold-no:M1#1", "net_weight_g": 10, "quantity": 1, "target_output": 1000, "machine_code": "4A-6A", "material": "ABS", "grade": "750SW", "pricing_component_id": "component-02"}]},
                "hair": {"lines": [{"name": f"电话头发{cost}", "craft": "植发", "unit": "PCS", "weight_g": 10, "unit_price_hkd": cost, "pricing_component_id": "component-02"},
                                     {"name": "镜子头发", "craft": "植发", "unit": "PCS", "weight_g": 10, "unit_price_hkd": 8, "pricing_component_id": "component-03"}]},
                "electronic": {"pricing_currency": "RMB", "components": [{"item": "IC", "quantity": 1, "unit_price_rmb": cost, "pricing_component_id": "component-02"},
                                                                           {"item": "PCB", "quantity": 1, "unit_price_rmb": cost, "pricing_component_id": "component-03"}], "labor_rmb": 2},
                "assembly": {"groups": [{"name": "包装人工", "category": "packaging", "total_persons": 1, "production_qty": 1000, "teams": 1, "processes": []}]},
            })
            image = BytesIO(); Image.new("RGB", (10, 15), "red" if cost == 1 else "blue").save(image, "PNG")
            uploaded = client.post(f"/api/internal-quotes/{quote['id']}/components/component-02/image", data={"revision": 1}, files={"file": (f"phone{cost}.png", image.getvalue(), "image/png")})
            assert uploaded.status_code == 200, uploaded.text
        rows = {r["quote_id"]: r for r in catalog(client)}
        ar, br = rows[a["id"]], rows[b["id"]]
        # Complete A, but substitute its phone with B's phone; plus an independent mixed product.
        new = create(client, "MIX", jp=True, products=[
            {"product_name": "完整A换电话", "qty": 500, "pricing_components": ["主体", "B电话", "镜子"], "history_source": source_ref(ar),
             "component_sources": [source_ref(ar, "component-01"), source_ref(br, "component-02"), source_ref(ar, "component-03")]},
            {"product_name": "组合X", "qty": 1000, "pricing_components": ["A电话主体", "B电话配件"],
             "component_sources": [source_ref(ar, "component-02"), source_ref(br, "component-02")]},
        ])
        assert [r["name"] for r in parts(new, "hair")["lines"]] == ["电话头发3", "镜子头发"]
        assert parts(new, "sales")["justplay_packaging"] == {
            "adhesive_extra_hkd": .1, "paper_pallet_extra_hkd": .2,
            "pallet_length_mm": 1300, "pallet_width_mm": 1200, "pallet_height_mm": 1400}
        assert any(r["item"] == "共享包装" for r in parts(new, "engineering")["materials"])
        batch = client.get(f"/api/internal-quotes/{new['id']}/batch-products").json()
        x = client.get(f"/api/internal-quotes/{batch[1]['quote_id']}").json()
        assert parts(x, "sales")["justplay_packaging"]["pallet_length_mm"] == 1000  # Components do not duplicate shared packaging.
        assert [r["pricing_component_id"] for r in parts(x, "hair")["lines"]] == ["component-01", "component-02"]
        assert all(r["item"] != "共享包装" for r in parts(x, "engineering")["materials"])
        assert parts(x, "assembly")["groups"] == []
        assert float(parts(x, "electronic")["labor_rmb"]) == 2  # Half of each source's shared labor.
        assert [r["engineering_source_key"] for r in parts(x, "molding")["injection_lines"]] == ["mold-no:M1#1", "mold-no:M1#2"]
        attachments = client.get(f"/api/internal-quotes/{x['id']}/attachments").json()
        assert {(r["department"], r["file_name"]) for r in attachments} == {("component-image:component-01", "phone1.png"), ("component-image:component-02", "phone3.png")}
        assert len(x["history_sources"]) == 2
        assert parts(client.get(f"/api/internal-quotes/{a['id']}").json(), "hair")["lines"][0]["unit_price_hkd"] == 1


def test_stale_sources_foreign_factory_and_invalid_components_are_rejected_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_guard", "sales_customer_owner", "sales-business", "huakang-b")
        old = create(client, "GUARD", jp=True)
        row = catalog(client)[0]
        payload = create_payload(suffix="NO-PARTIAL")
        payload.update(factory_id="huakang-b", customer="JustPlay", pricing_components=["主体"], quote_type="series", products=[
            {"product_name": "手动", "qty": 1, "pricing_components": ["主体"]},
            {"product_name": "坏来源", "qty": 1, "pricing_components": ["主体"], "component_sources": [source_ref(row, "missing")]},
        ])
        assert client.post("/api/internal-quotes", json=payload).status_code == 400
        payload["products"][1]["component_sources"] = [source_ref(row, "component-01")]
        put_source(old["id"], {"hair": {"lines": []}})
        assert client.post("/api/internal-quotes", json=payload).status_code == 409
        assert not catalog(client, keyword="NO-PARTIAL")
        logout(client)
        login(client, "history_foreign", "sales_customer_owner", "sales-business", "huaxing")
        assert client.get("/api/internal-quotes/history-products", params={"factory_id": "huakang-b"}).status_code == 403
        payload = create_payload(suffix="FOREIGN")
        payload["products"] = [{"product_name": "越厂", "qty": 1, "history_source": source_ref(row)}]
        assert client.post("/api/internal-quotes", json=payload).status_code == 404


def test_source_price_conflicts_require_explicit_current_reference_choice(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_prices", "sales_customer_owner", "sales-business", "huakang-b")
        a, b = create(client, "PRICE-A", jp=True), create(client, "PRICE-B", jp=True)
        db_module = importlib.import_module("app.db"); models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            for q, price in [(a, "11"), (b, "22")]:
                ref = db.get(models.InternalQuoteReferenceSet, q["reference_snapshot_id"])
                data = json.loads(ref.snapshot_json); data["material_prices"]["ABS|750SW"] = price
                ref.snapshot_json = json.dumps(data)
            db.commit()
        rows = {r["quote_id"]: r for r in catalog(client)}
        payload = create_payload(suffix="PRICE-NEW")
        payload.update(factory_id="huakang-b", customer="JustPlay", quote_type="series", products=[
            {"product_name": "PRICE-NEW手动首款", "qty": 1, "pricing_components": ["主体"]},
            {"product_name": "组款", "qty": 1, "pricing_components": ["主体", "附件"],
            "component_sources": [source_ref(rows[a["id"]], "component-01"), source_ref(rows[b["id"]], "component-02")]}])
        result = client.post("/api/internal-quotes", json=payload)
        assert result.status_code == 409 and "参考价存在冲突" in result.text
        assert not catalog(client, keyword="PRICE-NEW")
        payload["products"][1]["history_reference_mode"] = "current"
        result = client.post("/api/internal-quotes", json=payload)
        assert result.status_code == 201, result.text


def test_legacy_justplay_and_embedded_images_become_independent_component_copies(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_legacy", "sales_customer_owner", "sales-business", "huakang-b")
        old = create(client, "LEGACY", jp=True)
        put_source(old["id"], {"sales": {}, "engineering": {"molds": [
            {"item": "旧版模具", "mold_no": "LEG", "cost_rmb": 100, "image_attachment_ids": ["old-embedded"], "import_batch_id": "old-batch"}]}})
        db_module = importlib.import_module("app.db"); models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            for aid, dept in [("old-image", "product-image"), ("old-embedded", "engineering")]:
                db.add(models.InternalQuoteAttachment(id=aid, quote_id=old["id"], factory_id="huakang-b", department=dept,
                    file_name=f"{aid}.png", content_type="image/png", size_bytes=3, sha256="abc", content=b"img",
                    uploaded_by="history_legacy", uploaded_by_name="历史", uploaded_at="2026-09-01"))
            db.commit()
        row = catalog(client)[0]
        assert row["components"] == [{"id": "__legacy_main__", "name": "主体（旧版整款）"}]
        new = create(client, "LEGACY-NEW", jp=True, products=[{"product_name": "新款", "qty": 100, "pricing_components": ["主体"],
            "history_source": source_ref(row), "component_sources": [source_ref(row, "__legacy_main__")]}])
        attachments = client.get(f"/api/internal-quotes/{new['id']}/attachments").json()
        assert {a["department"] for a in attachments} == {"engineering", "component-image:component-01"}
        assert not {a["id"] for a in attachments} & {"old-image", "old-embedded"}
        mold = parts(new, "engineering")["molds"][0]
        assert mold["image_attachment_ids"] == [next(a["id"] for a in attachments if a["department"] == "engineering")]
        assert "import_batch_id" not in mold
        assert mold["pricing_component_id"] == "component-01"
        assert new["history_sources"][0]["reference_price_mode"] == "source"
        assert len(client.get(f"/api/internal-quotes/{old['id']}/attachments").json()) == 2


def test_history_reference_prices_preserve_source_materials_but_use_new_fx(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_frozen", "sales_customer_owner", "sales-business")
        old = create(client, "FROZEN")
        db_module = importlib.import_module("app.db"); models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            reference = db.get(models.InternalQuoteReferenceSet, old["reference_snapshot_id"])
            data = json.loads(reference.snapshot_json)
            data["material_prices"]["ABS|750SW"] = "19.75"
            data["fx"]["rmb_hkd"] = "0.5"
            reference.snapshot_json = json.dumps(data)
            db.commit()
        row = catalog(client, "huaxing")[0]
        new = create(client, "FROZEN-NEW", products=[{"product_name": "新产品", "qty": 100, "history_source": source_ref(row)}])
        with db_module.SessionLocal() as db:
            current = json.loads(db.get(models.InternalQuoteReferenceSet, new["reference_snapshot_id"]).snapshot_json)
            assert current["material_prices"]["ABS|750SW"] == "19.75"
            assert current["fx"]["rmb_hkd"] != "0.5"


def test_mixed_quick_and_detail_sources_keep_costs_and_paint_tax_split(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_quick", "sales_customer_owner", "sales-business", "huakang-b")
        a, b = create(client, "QUICK", jp=True), create(client, "DETAIL", jp=True)
        put_source(a["id"], {
            "painting": {"quote_mode": "quick", "quick_quote": {"spray_labor_hkd": 2, "paint_hkd": 3, "pricing_component_id": "component-02"}},
            "sewing": {"quote_mode": "quick", "quick_quotes": [{"doll_name": "车衣", "unit_price_hkd": 5, "pricing_component_id": "component-02"}]},
            "electronic": {"quote_mode": "quick", "quick_quotes": [{"item": "IC", "unit_price_rmb": 4, "pricing_component_id": "component-02"}]},
        })
        put_source(b["id"], {"painting": {"rows": [{"name": "明细喷油", "pricing_component_id": "component-02", "operations": {"spray": {"quantity": 1, "unit_price_hkd": 10}}}]}})
        rows = {r["quote_id"]: r for r in catalog(client)}
        new = create(client, "QUICK-MIX", jp=True, products=[{"product_name": "混合款", "qty": 100, "pricing_components": ["快捷配件", "明细配件"],
            "component_sources": [source_ref(rows[a["id"]], "component-02"), source_ref(rows[b["id"]], "component-02")]}])
        painting = next(s for s in new["sections"] if s["department"] == "painting")["calculation"]
        assert float(painting["totals"]["total_hkd"]) == pytest.approx(15.39)
        assert float(painting["totals"]["painting_labor_hkd"]) == 9
        assert float(painting["totals"]["paint_material_hkd"]) == pytest.approx(6.39)
        assert parts(new, "painting")["rows"][0]["cost_allocation"] == "direct"
        sewing = next(s for s in new["sections"] if s["department"] == "sewing")["calculation"]
        assert float(sewing["totals"]["total_hkd"]) == 5
        assert parts(new, "electronic")["components"][0]["quantity"] == 1
        assert parts(new, "electronic")["components"][0]["unit_price_rmb"] == 4
        excel = importlib.import_module("app.services.internal_quote_excel")
        assert excel._pricing_entry_tax_tag({"section": "painting", "kind": "painting_quick_labor"}) == ""
        assert excel._pricing_entry_tax_tag({"section": "painting", "kind": "painting_quick_paint"}) == "¥13%"


def test_partial_component_copy_only_enables_departments_with_selected_content(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "history_partial_dept", "sales_customer_owner", "sales-business", "huakang-b")
        old = create(client, "DEPTS", jp=True)
        put_source(old["id"], {
            "hair": {"lines": [{"name": "电话头发", "craft": "植发", "unit": "PCS", "weight_g": 10, "unit_price_hkd": 1, "pricing_component_id": "component-02"}]},
            "painting": {"rows": [{"name": "镜子喷油", "pricing_component_id": "component-03", "operations": {"spray": {"quantity": 1, "unit_price_hkd": 2}}}]},
        })
        row = catalog(client)[0]
        assert row["component_sections"]["component-02"] == ["hair"]
        payload = create_payload(suffix="PARTIAL-DEPT")
        payload.update(factory_id="huakang-b", customer="JustPlay", products=[{"product_name": "只有车发", "qty": 100,
            "pricing_components": ["主体"], "component_sources": [source_ref(row, "component-02")]}])
        result = client.post("/api/internal-quotes", json=payload)
        assert result.status_code == 201, result.text
        assert {s["department"] for s in result.json()["sections"] if s["is_required"]} == {"engineering", "assembly", "sales", "hair"}
