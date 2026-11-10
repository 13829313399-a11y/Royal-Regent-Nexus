import importlib
import json
from io import BytesIO

from openpyxl import load_workbook
from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_alternatives import fill


def test_old_paint_tax_requires_recalculation_and_new_output_uses_final_price(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "factory-tax-owner", "admin", "*", "*")
        body = create_payload(suffix="FACTORY-TAX-RECALC", participating_sections=["engineering", "assembly", "painting", "sales"])
        body["workflow_mode"] = "direct_output"
        response = client.post("/api/internal-quotes", json=body)
        assert response.status_code == 201, response.text
        quote = fill(client, response.json())
        painting = next(s for s in quote["sections"] if s["department"] == "painting")
        response = client.put(f"/api/internal-quotes/{quote['id']}/sections/painting", json={
            "revision": painting["revision"], "payload": {"quote_mode": "quick", "quick_quote": {
                "spray_labor_hkd": .48, "paint_hkd": .2, "paint_tax_rate_percent": 13}}})
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["calculation"]["totals"]["total_hkd"] == "0.6800"
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        calculator = importlib.import_module("app.services.internal_quote_calculator")
        with db_module.SessionLocal() as db:
            header = db.get(models.InternalQuote, quote["id"])
            header.formula_version = "rr2-2026-v14"
            row = db.get(models.InternalQuoteSection, saved["id"])
            calculation = json.loads(row.calculation_json)
            calculation["formula_version"] = "rr2-2026-v14"
            calculation["totals"].update(paint_tax_hkd="0.0260", paint_material_hkd="0.2260", total_hkd="0.7060")
            calculation["line_breakdown"].append({"kind": "painting_quick_paint_tax", "item": "油漆税金 13%", "amount_hkd": "0.0260"})
            row.calculation_json = json.dumps(calculation)
            row.calculation_formula_version = "rr2-2026-v14"
            db.commit()
        current = client.get(f"/api/internal-quotes/{quote['id']}").json()
        blocked = client.post(f"/api/internal-quotes/{quote['id']}/direct-issue", json={"revision": current["header_revision"]})
        assert blocked.status_code == 409, blocked.text
        before_reference = client.get(f"/api/internal-quotes/{quote['id']}/reference-snapshot").json()["snapshot"]
        response = client.post(f"/api/internal-quotes/{quote['id']}/formula/recalculate", json={
            "revision": current["header_revision"], "reason": "取消重复油漆税金并应用厂区减税规则"})
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["formula_version"] == calculator.FORMULA_VERSION
        paint = next(s for s in updated["sections"] if s["department"] == "painting")
        assert paint["payload"] == saved["payload"]
        assert paint["calculation"]["totals"]["total_hkd"] == "0.6800"
        assert not any(line["kind"] == "painting_quick_paint_tax" for line in paint["calculation"]["line_breakdown"])
        assert client.get(f"/api/internal-quotes/{quote['id']}/reference-snapshot").json()["snapshot"] == before_reference
        issued = client.post(f"/api/internal-quotes/{quote['id']}/direct-issue", json={"revision": updated["header_revision"]})
        assert issued.status_code == 200, issued.text
        url = f"/api/internal-quotes/{quote['id']}/exports/{issued.json()['id']}/download"
        raw = client.get(url).content
        workbook = load_workbook(BytesIO(raw))
        try:
            sheet = workbook["报价明细"]
            assert not any("油漆税金" in str(cell.value) for row in sheet for cell in row)
            assert not any(cell.value == "搪胶类3%" for row in sheet for cell in row)
        finally:
            workbook.close()
        assert client.get(url).content == raw
