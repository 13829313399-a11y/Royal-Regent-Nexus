from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.services.internal_quote import _rr2_cost_summary
from app.services.internal_quote_calculator import CalculationInputError, calculate_section
from app.services.internal_quote_excel import build_internal_quote_workbook
from app.services.internal_quote_workbook_view import WorkbookValues
from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_excel_formula_links import _section


CONTEXT = {"factory_id": "huaxing", "customer": "BuzzBee"}
SNAPSHOT = {"fx": {"rmb_hkd": ".84", "hkd_usd": "7.8", "rmb_usd": "6.6"},
            "material_prices": {"ABS|其他": "8.5", "ABS|750SW": "7.2"}}
FORMULA = {"material": "ABS", "grade": "750SW", "weight_g": 48, "labor_rmb": ".64",
           "price_hkd_lb": 999}
ROW = {"category": "auxiliary", "auxiliary_category": "其他外购", "item": "ABS拉管",
       "quantity": 12, "unit_price_hkd": 999, "unit_price_source_currency": "HKD", "resin_processing_formula": FORMULA}


def calculate(row, context=CONTEXT):
    return calculate_section("engineering", {"materials": [row]}, SNAPSHOT, "BUZZBEE", context=context)


@pytest.mark.parametrize("row,context,error", [
    (ROW, {**CONTEXT, "customer": "Other"}, "仅适用于"),
    (ROW, {**CONTEXT, "factory_id": "huadeng"}, "仅适用于"),
    ({**ROW, "auxiliary_category": "吸塑"}, CONTEXT, "仅适用于"),
    ({**ROW, "category": "hardware"}, CONTEXT, "仅适用于"),
    ({**ROW, "resin_processing_formula": {**FORMULA, "grade": "unknown"}}, CONTEXT, "冻结价目"),
    ({**ROW, "resin_processing_formula": {**FORMULA, "weight_g": 0}}, CONTEXT, "单条重量"),
    ({**ROW, "resin_processing_formula": {**FORMULA, "labor_rmb": ""}}, CONTEXT, "啤工"),
    ({**ROW, "resin_processing_formula": {**FORMULA, "labor_rmb": -1}}, CONTEXT, "啤工"),
])
def test_formula_validates_scope_and_operands(row, context, error):
    with pytest.raises(CalculationInputError, match=error):
        calculate(row, context)


def test_zero_processing_and_manual_rows():
    line = calculate({**ROW, "resin_processing_formula": {**FORMULA, "labor_rmb": 0}})["line_breakdown"][0]
    assert line["base_unit_price_hkd"] == "0.7612"
    manual = {k: v for k, v in ROW.items() if k != "resin_processing_formula"}
    assert calculate(manual)["line_breakdown"][0]["amount_hkd"] == "11988.0000"


def test_api_preview_save_reload_and_update_material_price(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "bb_fx_engineering", "admin", "*", "*")
        header = {**create_payload(suffix="BB-FX", participating_sections=["engineering", "assembly", "sales"]), **CONTEXT}
        created = client.post("/api/internal-quotes", json=header)
        assert created.status_code == 201, created.text
        path = "/api/internal-quotes/" + created.json()["id"]
        draft = {"revision": 1, "payload": {"materials": [ROW]}}
        preview = client.post(path + "/cost-preview", json={"drafts": [{"section_code": "engineering", **draft}]})
        assert preview.status_code == 200, preview.text
        saved = client.put(path + "/sections/engineering", json=draft)
        assert saved.status_code == 200, saved.text
        reloaded = client.get(path).json()
        engineering = next(s for s in reloaded["sections"] if s["department"] == "engineering")
        line = engineering["calculation"]["line_breakdown"][0]
        assert line == preview.json()["calculations"]["engineering"]["line_breakdown"][0]
        assert engineering["payload"]["materials"][0]["unit_price_hkd"] == pytest.approx(float(line["base_unit_price_hkd"]), abs=.00005)
        updated = client.put(path + "/reference-snapshot/materials", json={"revision": reloaded["header_revision"],
                             "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "9.9"}]})
        assert updated.status_code == 200, updated.text
        refreshed = next(s for s in updated.json()["sections"] if s["department"] == "engineering")
        assert refreshed["payload"]["materials"][0]["resin_processing_formula"]["price_hkd_lb"] == 9.9
        assert refreshed["calculation"]["line_breakdown"][0]["amount_hkd"] != line["amount_hkd"]


@pytest.mark.parametrize("loss,expected,extra_grades", [(1, "18.2777", 0), (1.05, "19.1915", 20)])
def test_saved_workbook_keeps_live_material_and_processing_formula(loss, expected, extra_grades):
    prices = {f"PP|grade-{i}": "5" for i in range(extra_grades)}
    snapshot = {**SNAPSHOT, "material_prices": {**prices, **SNAPSHOT["material_prices"]}}
    material = {**ROW, "loss_rate": loss, "tax_rate_percent": 13}
    manual = {"item": "普通外购", "category": "auxiliary", "auxiliary_category": "其他外购",
              "quantity": 1, "unit_price_rmb": ".84", "tax_rate_percent": 13}
    payload = {"materials": [manual, material]}
    calculation = calculate_section("engineering", payload, snapshot, "BUZZBEE", context=CONTEXT)
    line = calculation["line_breakdown"][1]
    assert line["resin_processing_formula"]["price_hkd_lb"] == "7.2"
    assert line["base_unit_price_hkd"] == "1.5231"
    assert line["amount_hkd"] == expected
    section = _section("engineering", payload=payload, calculation=calculation)
    section.is_required = True
    section.department_name, section.status, section.revision = "工程", "draft", 1
    section.reviewed_by, section.reviewed_at, section.dependency_status = "", "", "current"
    total = Decimal(calculation["totals"]["total_hkd"])
    context = {"engineering_hkd": total, "auxiliary_hkd": total, "factory_price_hkd": total}
    summary = _rr2_cost_summary([section], context, snapshot, factory_id="huaxing")
    quote = SimpleNamespace(**CONTEXT, product_name="ABS 拉管", quote_no="BB", region_code="mainland",
                            remark="", header_revision=1, reference_snapshot_id="BB", formula_version="test", version_label="A")
    data = build_internal_quote_workbook(quote, [section], {}, snapshot, summary, context)
    book = load_workbook(BytesIO(data))
    try:
        sheet = book["报价明细"]
        detail = next(cell for cell in sheet["D"] if cell.data_type == "f" and "'外购计价'!" in cell.value)
        inputs = book["外购计价"]
        assert inputs.sheet_state == "visible"
        adopted_cell = f"$C${extra_grades + 5}"
        if extra_grades:
            assert inputs["D2"].value == f"='采用价目表'!{adopted_cell}"
        else:
            assert inputs["D2"].value == "='报价明细'!E2"
            assert sheet["E2"].value == f"='采用价目表'!{adopted_cell}"
        assert [inputs.cell(2, column).value for column in range(5, 9)] == [48, .64, 12, loss]
        assert "/454*" in detail.value and "/$L$4" in detail.value

        def amount():
            return WorkbookValues(book).cell(sheet.title, detail.coordinate)

        assert round(amount(), 4) == float(expected)
        assert WorkbookValues(book).cell(inputs.title, "I2") == pytest.approx(7.2 / 454 * 48 + .64 / .84)
        book["采用价目表"][adopted_cell] = 9.4
        sheet["L4"] = .8
        inputs["G2"] = 2
        assert amount() == pytest.approx((9.4 / 454 * 48 + .64 / .8) * 2 * loss)
    finally:
        book.close()
