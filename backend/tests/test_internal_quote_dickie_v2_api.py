"""Real isolated save/approval/export path. Optional output is an explicitly marked demo."""
import json
import os
import random
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageDraw

from test_internal_quote_api import create_payload, ensure_user, login, logout, make_client


def test_dickie_v2_whole_quote_release_and_sample(monkeypatch):
    rng = random.Random(20260921)
    bilingual = lambda zh, en: {"zh": zh, "en": en}
    offer = lambda key, moq, zh, en, adjustments: {
        "id": key, "included": True, "label": bilingual(zh, en), "moq": moq, "moq_text": f"{moq:,} pcs",
        "remark": bilingual("", ""), "route_40": "hk40", "route_20": "hk20", "route_lcl": "hk5t",
        "price_source": "calculated", "confirmed_40": "", "confirmed_20": "", "confirmed_lcl": "", "confirmed_reference": "", "adjustments": adjustments,
    }
    mapping = {
        "version": "dickie-v2", "company": "hk", "client_name": "Dickie — DEMO", "attention": "Demo Buyer", "from_name": "Demo Sales",
        "quote_date": "2026-09-21", "revision": "DEMO-A", "quotation_kind": "estimate", "item_number": "DEMO-260921",
        "item_name": bilingual("演示款惯性城市巴士", "DEMO Friction City Bus"), "item_note": bilingual("随机演示数据", "Random demonstration data"),
        "inner_pack": 1, "dimension_source": "color_box", "dimension_unit": "cm", "customer_carton_enabled": False,
        "customer_carton_cm": {"length": 0, "width": 0, "height": 0},
        "remarks": [bilingual("本文件为随机数据演示，仅供核对系统输出，不作正式报价。", "Random-data demonstration for checking system output only; not a commercial quotation."),
                    bilingual("惯性驱动，不含电池；彩盒包装。", "Friction drive, no batteries; color box packaging.")],
        "offers": [offer("normal5", 5000, "中国正常价", "China normal price", []),
                   offer("normal10", 10000, "中国正常价", "China normal price", []),
                   offer("season10", 10000, "中国淡季价（减8%）", "China low-season price (-8%)", [{"label": "演示淡季折扣", "percent": -8, "amount_hkd": 0}])],
        "include_molds": True, "first_shot": bilingual("确认后45天", "45 days after confirmation"), "finish": bilingual("确认后75天", "75 days after confirmation"),
        "lead_time_basis": bilingual("确认最终图纸并收到模具定金后起算。", "From final drawing approval and receipt of tooling deposit."),
    }
    molds = []
    for index, (zh, en, resin, size) in enumerate([("车身", "Body", "ABS", "30*35*30"), ("底盘", "Chassis", "ABS", "25*30*25"), ("车轮", "Wheels", "PP", "20*25*20")]):
        cost = rng.randrange(140, 280) * 100
        molds.append({"item": zh, "mold_no": f"M0{index+1}", "chinese_name": zh, "material_type": resin, "material": resin,
                      "mold_size": size, "mold_base_material": "P20", "cavity": "2" if index < 2 else "8", "quantity": 1, "cost_rmb": cost,
                      "dickie_export": {"included": True, "customer_mold_no": "", "parts_en": en, "group": bilingual("城市巴士", "City Bus"), "shared_products": bilingual("", ""), "size_unit": "cm",
                                        "customer_price_hkd": round(cost / .85 * 1.18 / 100) * 100, "remark": bilingual("演示模具", "Demo tooling")}})
    payloads = {
        "engineering": {"materials": [
            {"item": "螺丝", "category": "hardware", "specification": "2.0*6mm", "quantity": 6, "unit_price_rmb": round(rng.uniform(.025, .045), 3)},
            {"item": "车轴", "category": "hardware", "specification": "2.0*65mm", "quantity": 2, "unit_price_rmb": round(rng.uniform(.15, .25), 3)},
            {"item": "惯性牙箱", "category": "auxiliary", "auxiliary_category": "其他外购", "quantity": 1, "unit_price_rmb": round(rng.uniform(1.2, 1.8), 2)},
        ], "molds": molds, "mold_allocation_enabled": False, "amortization_qty": 10000, "customer_mold_subsidy_usd": 0},
        "molding": {"injection_lines": [
            {"item": m["chinese_name"], "material": m["material_type"], "grade": "750SW" if m["material_type"] == "ABS" else "M800E", "net_weight_g": rng.randrange(30, 70), "loss_rate_percent": 3,
             "machine_code": "4A-6A", "sets": 2, "target_output": rng.randrange(35, 50)*100, "quantity": 1}
            for m in molds], "blow_lines": []},
        "painting": {"rows": [{"name": "车身", "operations": {"spray": {"quantity": 3, "unit_price_hkd": .085}, "tampo": {"quantity": 2, "unit_price_hkd": .045}}}]},
        "assembly": {"labor_base_hkd": 310, "groups": [{"name": "巴士装配", "category": "assembly", "processes": [{"name": "装配检测", "persons": 4, "teams": 1, "production_qty": 4000}]},
                                                                       {"name": "包装", "category": "packaging", "processes": [{"name": "入盒封箱", "persons": 2, "teams": 1, "production_qty": 5000}]}]},
        "sales": {"product_size_in": {"length": 8, "width": 3, "height": 3.5}, "color_box_size_in": {"length": 9, "width": 4, "height": 4.25},
                  "cartons": [{"item": "主纸箱", "length_in": 18.75, "width_in": 13, "height_in": 9.25, "qty_per_carton": 12}], "paper_price_factor": 2.75,
                  "packaging_materials": [{"item": "印刷彩盒", "category": "color_box_inner_card", "quantity": 1, "unit_price_rmb": round(rng.uniform(.7, 1), 2)},
                                          {"item": "说明书", "category": "leaflet_manual", "quantity": 1, "unit_price_rmb": .08}],
                  "testing_fee_enabled": False, "freight_calc": {"enabled": True, "freight_enabled": True, "lifting_enabled": False, "selected_route_keys": ["hk40", "hk20", "hk5t"]},
                  "shipping": {"markup_tiers": [{"moq": 5000, "markup_x": 1.18, "include_in_output": True}, {"moq": 10000, "markup_x": 1.15, "include_in_output": True}], "selected_markup_moq": 5000, "misc_ratio": .02, "freight_pct": .48, "lifting_pct": 0},
                  "customer_quote_fields": {"dickie": {"mapping": mapping}}},
    }
    with make_client(monkeypatch) as client:
        ensure_user("demo_dickie_reviewer", "sales_customer_supervisor", "sales-business", "huaxing")
        login(client, "demo_dickie_creator", "admin", "*", "*")
        baseline = client.get("/api/internal-quotes/pricing-baseline", params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"}).json()
        saved_baseline = client.put("/api/internal-quotes/pricing-baseline", params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"}, json={
            "revision": baseline["revision"], "workshop_name": "华兴", "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "5.8"}, {"material": "PP", "grade": "M800E", "price_hkd_lb": "4.8"}],
            "machine_prices": [{"machine_range": "4A-6A", "machine": "80T", "shift_price_hkd": "940"}], "freight_routes": baseline["freight_routes"],
        })
        assert saved_baseline.status_code == 200, saved_baseline.text
        request = create_payload(suffix="DICKIE-DEMO", participating_sections=list(payloads))
        request.update(customer="Dickie", product_name="演示数据-惯性城市巴士", quote_no="DEMO-DICKIE-260921", remark="随机演示数据，仅供检查输出，不作正式报价。", target_date="2026-10-31",
                       business_owner_id="user-demo_dickie_reviewer", business_owner_name="demo_dickie_reviewer", workflow_mode="whole_quote_review")
        created = client.post("/api/internal-quotes", json=request)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        picture = Image.new("RGB", (600, 280), "white")
        draw = ImageDraw.Draw(picture)
        draw.rounded_rectangle((30, 45, 570, 215), radius=20, fill="#2475ad")
        for x in range(60, 490, 85):
            draw.rectangle((x, 65, x+65, 130), fill="#d5ecf7")
        draw.rectangle((500, 65, 550, 190), fill="#d5ecf7")
        for x in (135, 460):
            draw.ellipse((x-38, 183, x+38, 259), fill="#26333e")
            draw.ellipse((x-17, 204, x+17, 238), fill="#c4ccd4")
        draw.text((235, 162), "DEMO BUS", fill="white", font_size=24)
        image_bytes = BytesIO()
        picture.save(image_bytes, format="PNG")
        uploaded = client.post(f"/api/internal-quotes/{quote_id}/product-image", files={"file": ("demo-bus.png", image_bytes.getvalue(), "image/png")})
        assert uploaded.status_code == 201, uploaded.text
        for code in ["engineering", "molding", "assembly", "painting", "sales"]:
            current = client.get(f"/api/internal-quotes/{quote_id}").json()
            section = next(s for s in current["sections"] if s["department"] == code)
            saved = client.put(f"/api/internal-quotes/{quote_id}/sections/{code}", json={"revision": section["revision"], "payload": payloads[code], "reason": "随机演示录入"})
            assert saved.status_code == 200, saved.text
            assert saved.json()["calculation_status"] == "valid", saved.text
        current = client.get(f"/api/internal-quotes/{quote_id}").json()
        submitted = client.post(f"/api/internal-quotes/{quote_id}/final-submit", json={"revision": current["header_revision"]})
        assert submitted.status_code == 200, submitted.text
        logout(client)
        login(client, "demo_dickie_reviewer", "sales_customer_supervisor", "sales-business", "huaxing")
        approved = client.post(f"/api/internal-quotes/{quote_id}/final-review", json={"revision": submitted.json()["quote"]["header_revision"], "decision": "approve", "reason": "隔离测试环境演示审核，非正式业务放行"})
        assert approved.status_code == 200, approved.text
        exported = client.post(f"/api/internal-quotes/{quote_id}/exports")
        assert exported.status_code == 201, exported.text
        pool = client.get("/api/customer-price/internal-quote-artifacts", params={"factory_id": "huaxing", "status": "available"})
        assert pool.status_code == 200, pool.text
        released = next(row for row in pool.json() if row["quote_id"] == quote_id)
        assert released["customer"] == "Dickie"
        download = client.get(f"/api/customer-price/internal-quote-artifacts/{released['id']}/download")
        assert download.status_code == 200
        workbook = load_workbook(BytesIO(download.content), data_only=True)
        mapping_rows = [r for r in workbook["结构化数据"].values if r[0] == "customer_mapping"]
        handoff = json.loads("".join(r[10] for r in mapping_rows))
        assert len(handoff["prices"]) == 6
        assert all(float(row["price_hkd"]) > 0 and float(row["lift_hkd"]) == 0 for row in handoff["prices"])
        assert handoff["customer"] == "Dickie"
        consumed = client.post(f"/api/customer-price/internal-quote-artifacts/{released['id']}/consume", json={"consumer_reference": f"customer-price-ui:{released['id']}"})
        assert consumed.status_code == 200, consumed.text
        assert consumed.json()["status"] == "consumed"
        if directory := os.getenv("DICKIE_V2_SAMPLE_DIR"):
            output = Path(directory)
            output.mkdir(parents=True, exist_ok=True)
            (output / "Dickie-演示内部报价.xlsx").write_bytes(download.content)
            (output / "sample-prices.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "sample-handoff.json").write_text(json.dumps(released, ensure_ascii=False, indent=2), encoding="utf-8")
