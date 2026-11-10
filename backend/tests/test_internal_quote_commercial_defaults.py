import importlib
import json
from io import BytesIO

import pytest
from openpyxl import load_workbook

from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_alternatives import fork
from test_internal_quote_document_clone import clone_body


def create(client, suffix, factory="huaxing", customer="普通客户"):
    body = create_payload(suffix=suffix, participating_sections=["sales", "assembly"])
    body.update(workflow_mode="direct_output", factory_id=factory,
                workshop_code=f"{factory}-workshop", customer=customer)
    if factory == "huakang-b" and customer == "JustPlay":
        body["pricing_components"] = ["主体"]
    response = client.post("/api/internal-quotes", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def reference(client, quote):
    response = client.get(f"/api/internal-quotes/{quote['id']}/reference-snapshot")
    assert response.status_code == 200, response.text
    return response.json()["snapshot"]


def assert_terms(snapshot, fx, misc, settlement):
    assert snapshot["fx"]["rmb_hkd"] == fx
    assert snapshot["misc_ratio"] == misc
    assert snapshot["settlement"] == settlement


def save_sales(client, quote):
    section = next(s for s in quote["sections"] if s["department"] == "sales")
    payload = {**section["payload"],
               "packaging_materials": [{"item": "彩盒", "category": "color_box_inner_card", "quantity": 1, "unit_price_rmb": .84}],
               "color_box_size_in": {"length": 5, "width": 4, "height": 3},
               "cartons": [{"item": "主纸箱", "length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 12}],
               "testing_fee_enabled": False,
               "freight_calc": {"enabled": False, "freight_enabled": False, "lifting_enabled": False},
               "shipping": {"markup_x": 1.2, "markup_tiers": [{"moq": 5000, "markup_x": 1.2, "include_in_output": True}], "selected_markup_moq": 5000}}
    response = client.put(f"/api/internal-quotes/{quote['id']}/sections/sales",
                          json={"revision": section["revision"], "payload": payload, "reason": "测试默认参数"})
    assert response.status_code == 200, response.text
    assert response.json()["calculation_status"] == "valid", response.text
    return response.json()


def test_all_factories_and_customers_create_with_new_frozen_terms(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "default-terms", "admin", "*", "*")
        cases = [(factory, "普通客户") for factory in
                 ("huaxing", "huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng")]
        cases.append(("huakang-b", "JustPlay"))
        for index, (factory, customer) in enumerate(cases):
            quote = create(client, f"DEFAULT-{index}", factory, customer)
            snapshot = reference(client, quote)
            assert_terms(snapshot, "0.84", "0.03", "0.97")
            assert snapshot["fx"]["hkd_usd"] == "7.8"
            assert snapshot["fx"]["rmb_usd"] == "7.75"
            sales = save_sales(client, quote)
            material = next(row for row in sales["calculation"]["line_breakdown"]
                            if row["kind"] == "packaging_material" and row["item"] == "彩盒")
            # Inspect this purchased material separately from JustPlay packing extras.
            assert float(material["unit_price_hkd"]) == pytest.approx(1)
            assert float(material["amount_hkd"]) == pytest.approx(1)
            summary = client.get(f"/api/internal-quotes/{quote['id']}/summary").json()
            pricing = summary["rr2_cost_summary"]["shipping_pricing"]
            assert float(pricing["misc_ratio"]) == .03
            assert float(pricing["settlement"]) == .97
            assert_terms(reference(client, quote), "0.84", "0.03", "0.97")


def test_new_defaults_reach_excel_export(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "default-export", "admin", "*", "*")
        quote = create(client, "DEFAULT-EXCEL")
        save_sales(client, quote)
        assembly = next(s for s in quote["sections"] if s["department"] == "assembly")
        filled = client.put(f"/api/internal-quotes/{quote['id']}/sections/assembly", json={
            "revision": assembly["revision"], "payload": {"labor_base_hkd": 310,
            "groups": [{"name": "装配", "category": "assembly", "processes": [
                {"name": "组装", "persons": 1, "teams": 1, "production_qty": 5000}]}]},
            "reason": "完成装配核价"})
        assert filled.status_code == 200, filled.text
        quote = client.get(f"/api/internal-quotes/{quote['id']}").json()
        issued = client.post(f"/api/internal-quotes/{quote['id']}/direct-issue",
                             json={"revision": quote["header_revision"]})
        assert issued.status_code == 200, issued.text
        record = issued.json()
        raw = client.get(f"/api/internal-quotes/{quote['id']}/exports/{record['id']}/download")
        assert raw.status_code == 200
        workbook = load_workbook(BytesIO(raw.content))
        try:
            sheet = workbook["报价明细"]
            assert sheet["L4"].value == .84
            assert sheet["Q6"].value == .03
            assert any(cell.value == "=1-$Q$6" for row in sheet for cell in row)
        finally:
            workbook.close()


def test_existing_custom_and_new_terms_survive_copy_and_price_sync(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "preserve-terms", "admin", "*", "*")
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        calculator = importlib.import_module("app.services.internal_quote_calculator")
        with db_module.SessionLocal() as db:
            assert_terms(calculator.build_reference_snapshot(db), "0.85", "0.02", "0.98")
        for index, terms in enumerate((("0.85", "0.02", "0.98"), ("0.87", "0.035", "0.965"), ("0.84", "0.03", "0.97"))):
            quote = create(client, f"PRESERVE-{index}")
            with db_module.SessionLocal() as db:
                row = db.get(models.InternalQuoteReferenceSet, quote["reference_snapshot_id"])
                snapshot = json.loads(row.snapshot_json)
                snapshot["fx"]["rmb_hkd"], snapshot["misc_ratio"], snapshot["settlement"] = terms
                # Prove price refresh still replaces price tables, not the terms.
                snapshot["material_prices"]["ABS|750SW"] = "123.456"
                row.snapshot_json = json.dumps(snapshot)
                db.commit()
            assert_terms(reference(client, quote), *terms)
            alternative = fork(client, quote)
            assert_terms(reference(client, alternative), *terms)
            current = client.get(f"/api/internal-quotes/{quote['id']}").json()
            copied = client.post(f"/api/internal-quotes/{quote['id']}/clone-document",
                                 json=clone_body([current], f"TERMS-COPY-{index}"))
            assert copied.status_code == 201, copied.text
            assert_terms(reference(client, copied.json()), *terms)
            before = reference(client, current)
            synced = client.post(f"/api/internal-quotes/{quote['id']}/reference-snapshot/sync",
                                 json={"revision": current["header_revision"], "reason": "更新价目表"})
            assert synced.status_code == 200, synced.text
            latest = reference(client, synced.json())
            assert_terms(latest, *terms)
            assert latest["material_prices"]["ABS|750SW"] != "123.456"
            with db_module.SessionLocal() as db:
                original = db.get(models.InternalQuoteReferenceSet, quote["reference_snapshot_id"])
                assert json.loads(original.snapshot_json) == before


def test_legacy_divisor_only_snapshot_is_not_replaced_when_syncing_prices(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "legacy-divisor", "admin", "*", "*")
        quote = create(client, "LEGACY-DIVISOR")
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            row = db.get(models.InternalQuoteReferenceSet, quote["reference_snapshot_id"])
            snapshot = json.loads(row.snapshot_json)
            snapshot.pop("misc_ratio")
            snapshot["settlement"] = "0.965"
            snapshot["fx"]["rmb_hkd"] = "0.85"
            row.snapshot_json = json.dumps(snapshot)
            db.commit()
        synced = client.post(f"/api/internal-quotes/{quote['id']}/reference-snapshot/sync",
                             json={"revision": quote["header_revision"], "reason": "更新材料价"})
        assert synced.status_code == 200, synced.text
        latest = reference(client, synced.json())
        assert "misc_ratio" not in latest
        assert latest["settlement"] == "0.965"
        assert latest["fx"]["rmb_hkd"] == "0.85"
        calculator = importlib.import_module("app.services.internal_quote_calculator")
        misc, settlement = calculator.resolve_sales_misc_and_settlement({}, [], latest)
        assert str(misc) == "0.035"
        assert str(settlement) == "0.965"
