from test_internal_quote_api import ALL_SECTION_CODES, create_payload, login, make_client
from test_internal_quote_p3_api import workbook_bytes


def test_uv_import_save_reload_and_summary_use_authoritative_cost(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "painting_uv_owner", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(
            suffix="UV", participating_sections=ALL_SECTION_CODES))
        assert created.status_code == 201, created.text
        base = f"/api/internal-quotes/{created.json()['id']}"
        source = workbook_bytes([
            ["名称", "位置", "UV", "UV单价", "散枪", "散枪单价", "总报价"],
            ["外壳", "正面", 2, .52, 3, .08, 999],
        ])
        preview = client.post(base + "/imports/painting/preview", files={"file": ("UV.xlsx", source)})
        assert preview.status_code == 201, preview.text
        batch = preview.json()
        assert batch["payload_fragment"]["rows"][0]["operations"]["uv"]["quantity"] == "2.0000"
        confirmed = client.post(base + f"/imports/{batch['batch_id']}/confirm",
                                json={"revision": batch["target_revision"], "mode": "replace"})
        assert confirmed.status_code == 200, confirmed.text
        section = confirmed.json()["section"]
        assert section["calculation"]["totals"]["total_hkd"] == "1.2800"
        section["payload"]["rows"][0]["operations"]["uv"]["quantity"] = 3
        saved = client.put(base + "/sections/painting",
                           json={"revision": section["revision"], "payload": section["payload"]})
        assert saved.status_code == 200, saved.text
        assert saved.json()["calculation"]["totals"]["total_hkd"] == "1.8000"
        detail = client.get(base).json()
        reloaded = next(row for row in detail["sections"] if row["department"] == "painting")
        assert reloaded["payload"]["rows"][0]["operations"]["uv"]["quantity"] == 3
        assert reloaded["calculation"] == saved.json()["calculation"]
        summary = client.get(base + "/summary")
        assert summary.status_code == 200, summary.text
        # The summary must split the full painting cost, including UV, by existing labor/material rules.
        costs = {row["key"]: row["value"] for row in summary.json()["rr2_cost_summary"]["t3"]}
        assert costs["painting_labor"] == "1.2600"
        assert costs["paint_material"] == "0.5400"
