import importlib
from io import BytesIO

import pytest
from PIL import Image

from test_internal_quote_api import ALL_SECTION_CODES, create_payload, login, logout, make_client
from test_internal_quote_p3_api import workbook_bytes


def create_justplay(client, suffix="COMPONENT"):
    payload = create_payload(suffix=suffix, participating_sections=ALL_SECTION_CODES)
    payload.update(factory_id="huakang-b", workshop_code="huakang-b-workshop", customer="JustPlay",
                   pricing_components=["主体", "电话", "镜子"])
    response = client.post("/api/internal-quotes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def section(quote, code):
    return next(s for s in quote["sections"] if s["department"] == code)


@pytest.mark.parametrize("import_type", ["mold", "painting"])
def test_map_once_assign_multiple_components_skip_and_reassign(monkeypatch, import_type):
    with make_client(monkeypatch) as client:
        login(client, "jp_mapper", "sales_customer_owner", "sales-business", "huakang-b")
        quote = create_justplay(client)
        quote_url = f"/api/internal-quotes/{quote['id']}"
        if import_type == "mold":
            source = workbook_bytes([["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"],
                                     ["M1", "电话壳", "ABS", 20, 1, 7000, "4A", 5000],
                                     ["M2", "镜框", "ABS", 10, 1, 5000, "4A", 5000],
                                     ["M3", "不采用模", "PP", 10, 1, 1000, "4A", 5000]])
            code, field = "engineering", "molds"
        else:
            source = workbook_bytes([["名称", "位置", "散枪", "散枪单价"],
                                     ["电话壳", "正面", 1, 0.1], ["镜框", "边框", 1, 0.2], ["不采用", "反面", 1, 0.3]])
            code, field = "painting", "rows"
        preview = client.post(quote_url + f"/imports/{import_type}/preview", files={"file": ("一次映射.xlsx", source)})
        assert preview.status_code == 201, preview.text
        preview = preview.json()
        assert len(preview["assignment_rows"]) == 3
        assert len(preview["assignment_components"]) == 3
        confirm_url = quote_url + f"/imports/{preview['batch_id']}/confirm"
        revision = preview["target_revision"]
        assert client.post(confirm_url, json={"revision": revision}).status_code == 400
        assignments = {f"{field}:0": "component-02", f"{field}:1": "component-03", f"{field}:2": "__skip__"}
        invalid = {**assignments, f"{field}:1": "foreign-component"}
        assert client.post(confirm_url, json={"revision": revision, "component_assignments": invalid}).status_code == 400
        response = client.post(confirm_url, json={"revision": revision, "component_assignments": assignments})
        assert response.status_code == 200, response.text
        assert client.post(confirm_url, json={"revision": revision, "component_assignments": assignments}).status_code == 409
        detail = client.get(quote_url).json()
        saved = section(detail, code)
        rows = saved["payload"][field]
        assert [r["pricing_component_id"] for r in rows] == ["component-02", "component-03"]
        assert len(rows) == 2
        rows[0]["pricing_component_id"] = "component-03"
        response = client.put(quote_url + f"/sections/{code}", json={"revision": saved["revision"], "payload": saved["payload"]})
        assert response.status_code == 200, response.text
        updated = client.get(quote_url).json()
        assert section(updated, code)["payload"][field][0]["pricing_component_id"] == "component-03"
        if import_type == "mold":
            molding_rows = section(updated, "molding")["payload"]["injection_lines"]
            assert len(molding_rows) == 2
            assert all(r["pricing_component_id"] == "component-03" for r in molding_rows)
            assert sum(float(r["cost_rmb"]) for r in section(updated, code)["payload"][field]) == 12000


def test_component_images_isolated_versioned_and_locked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "jp_images", "sales_customer_owner", "sales-business", "huakang-b")
        quote = create_justplay(client)
        base = f"/api/internal-quotes/{quote['id']}"
        image = BytesIO()
        Image.new("RGB", (20, 30), "red").save(image, format="PNG")
        content = image.getvalue()
        def upload(component, revision, data=content):
            return client.post(base + f"/components/{component}/image", data={"revision": revision}, files={"file": ("分项.png", data, "image/png")})
        revision = quote["header_revision"]
        assert upload("component-02", revision, b"not an image").status_code == 400
        assert upload("missing", revision).status_code == 400
        first = upload("component-02", revision)
        assert first.status_code == 200, first.text
        assert first.json()["pricing_component_id"] == "component-02"
        assert upload("component-03", revision).status_code == 409
        second = upload("component-03", revision + 1)
        assert second.status_code == 200, second.text
        replacement = upload("component-02", revision + 2)
        assert replacement.status_code == 200, replacement.text
        images = client.get(base + "/attachments").json()
        assert {a["id"] for a in images} == {second.json()["id"], replacement.json()["id"]}
        assert client.get(base + f"/attachments/{first.json()['id']}/preview").status_code == 404
        other_quote = create_justplay(client, "OTHER")
        assert client.get(f"/api/internal-quotes/{other_quote['id']}/attachments/{replacement.json()['id']}/preview").status_code == 404
        logout(client)
        login(client, "jp_foreign", "sales_customer_owner", "sales-business", "huaxing")
        assert upload("component-02", revision + 3).status_code == 403
        logout(client)
        login(client, "jp_images", "sales_customer_owner", "sales-business", "huakang-b")
        deleted = client.delete(base + "/components/component-02/image", params={"revision": revision + 3})
        assert deleted.status_code == 200, deleted.text
        assert [a["pricing_component_id"] for a in client.get(base + "/attachments").json()] == ["component-03"]
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            stored = db.get(models.InternalQuote, quote["id"])
            stored.status = "final_reviewing"
            stored.final_release_status = "pending"
            db.commit()
        assert upload("component-02", revision + 4).status_code == 409


def test_baseline_copy_never_copies_images_or_reuses_them_for_changed_components(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "jp_copy_images", "sales_customer_owner", "sales-business", "huakang-b")
        payload = create_payload(suffix="COPY-IMAGES")
        payload.update(factory_id="huakang-b", workshop_code="huakang-b-workshop", customer="JustPlay", quote_type="series",
                       products=[{"product_name": "A款", "qty": 5000, "pricing_components": ["主体", "电话"]},
                                 {"product_name": "B款", "qty": 5000, "pricing_components": ["主体", "镜子"]}])
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        root = created.json()
        base = f"/api/internal-quotes/{root['id']}"
        products = client.get(base + "/batch-products").json()
        target_id = next(p["quote_id"] for p in products if p["quote_id"] != root["id"])
        image = BytesIO()
        Image.new("RGB", (10, 10), "blue").save(image, format="PNG")
        retained_id = ""
        for quote_id, component, revision in [(root["id"], "component-02", 1), (target_id, "component-01", 1), (target_id, "component-02", 2)]:
            result = client.post(f"/api/internal-quotes/{quote_id}/components/{component}/image",
                                 data={"revision": revision}, files={"file": ("图.png", image.getvalue())})
            assert result.status_code == 200, result.text
            if quote_id == target_id and component == "component-01":
                retained_id = result.json()["id"]
        copied = client.post(base + f"/batch-products/{target_id}/copy-baseline", json={"revision": 3})
        assert copied.status_code == 200, copied.text
        images = client.get(f"/api/internal-quotes/{target_id}/attachments").json()
        assert [(a["id"], a["pricing_component_id"]) for a in images] == [(retained_id, "component-01")]
