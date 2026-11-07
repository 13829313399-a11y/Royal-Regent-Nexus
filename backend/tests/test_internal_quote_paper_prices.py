from copy import deepcopy
from io import BytesIO
import json
import pytest
from openpyxl import load_workbook
from app.services.internal_quote_calculator import CalculationInputError
from app.services.internal_quote_amount_adjustments import adjustment_catalog
from test_internal_quote_api import make_client, login
from test_internal_quote_alternatives import create, fill, fork

PAPERS = [{"key": "ab", "name": "A=B", "price_factor_hkd": "2.60", "remark": "合成测试价"},
          {"key": "bbb", "name": "B3B", "price_factor_hkd": "1.94", "remark": "合成测试价"},
          {"key": "a535", "name": "A535B", "price_factor_hkd": "3.20", "remark": "合成测试价"}]
SNAPSHOT = {"paper_prices": PAPERS, "paper_price_factor": "2.75"}
PAYLOAD = {"paper_price_factor": 2.75, "inner_paper_price_factor": 2.5, "flat_card_price_factor": 1.5,
 "cartons": [{"item": "主箱", "length_in": 9, "width_in": 4.75, "height_in": 15.75, "qty_per_carton": 6,
 "paper_material_key": "ab", "flat_cards": [{"name": "平卡", "length_in": 8, "width_in": 4, "quantity": 2, "paper_material_key": "a535"}]},
 {"item": "内箱", "length_in": 8, "width_in": 4, "height_in": 7, "qty_per_carton": 3, "paper_material_key": "bbb"}]}

def packaging(payload, snapshot=SNAPSHOT):
    from app.services.internal_quote_calculator import _sales_packaging
    result = {"line_breakdown": [], "warnings": []}
    total, _ = _sales_packaging(payload, snapshot, result)
    return total, result


def test_individual_paper_factors_preserve_inputs_and_legacy_costs():
    before = deepcopy(PAYLOAD)
    total, detail = packaging(PAYLOAD)
    expected = ((9+4.75+2)*(4.75+15.75+1)*2*2.6/1000 + 8*4*2*3.2/1000)/6 + (8+4+2)*(4+7+1)*2*1.94/1000/3
    assert float(total) == pytest.approx(expected)
    assert detail["line_breakdown"][0]["paper_material"] == "A=B"
    assert detail["line_breakdown"][0]["flat_paper_details"][0]["paper_price_factor"] == "3.2000"
    assert PAYLOAD == before
    legacy = deepcopy(PAYLOAD)
    for c in legacy["cartons"]:
        c.pop("paper_material_key")
        for flat in c.get("flat_cards", []): flat.pop("paper_material_key")
    assert packaging(legacy)[0] == packaging(legacy, {})[0]


def test_unknown_paper_blocks_instead_of_falling_back_to_legacy():
    payload = deepcopy(PAYLOAD); payload["cartons"][0]["paper_material_key"] = "deleted"
    with pytest.raises(CalculationInputError, match="未匹配本报价价目表"):
        packaging(payload)


def test_material_change_at_equal_price_requires_adjustment_confirmation():
    payload = deepcopy(PAYLOAD); snapshot = deepcopy(SNAPSHOT)
    snapshot["paper_prices"].append({**PAPERS[0], "key": "other", "name": "另一纸材"})
    spec = adjustment_catalog("sales", payload, snapshot)[("cartons", 0)]
    row = payload["cartons"][0]
    row["quote_amount_adjustment"] = {"mode": "per_piece", "amount_hkd": ".2", "basis_hash": spec["basis_hash"]}
    row["price_annotations"] = {"quote_amount_adjustment": {"text": "供应商确认"}}
    assert adjustment_catalog("sales", payload, snapshot)[("cartons", 0)]["status"] == "adopted"
    row["paper_material_key"] = "other"
    assert adjustment_catalog("sales", payload, snapshot)[("cartons", 0)]["status"] == "pending"


def test_paper_catalog_is_frozen_copied_and_exported_consistently(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "paper-owner", "admin", "*", "*")
        quote = fill(client, create(client, "PAPER")); qid = quote["id"]
        before = client.get(f"/api/internal-quotes/{qid}/reference-snapshot").json()
        materials = [{"material": k.split("|", 1)[0], "grade": k.split("|", 1)[1], "price_hkd_lb": v} for k,v in before["snapshot"]["material_prices"].items()]
        response = client.put(f"/api/internal-quotes/{qid}/reference-snapshot/materials", json={"revision": quote["header_revision"], "material_prices": materials, "paper_prices": PAPERS})
        assert response.status_code == 200, response.text
        quote = response.json()
        current = client.get(f"/api/internal-quotes/{qid}/reference-snapshot").json()
        assert current["snapshot"]["paper_prices"] == PAPERS
        assert current["snapshot"]["material_prices"] == before["snapshot"]["material_prices"]
        assert current["id"] != before["id"]
        sales = next(s for s in quote["sections"] if s["department"] == "sales")
        payload = {**sales["payload"], **deepcopy(PAYLOAD)}
        saved = client.put(f"/api/internal-quotes/{qid}/sections/sales", json={"revision": sales["revision"], "payload": payload})
        assert saved.status_code == 200 and saved.json()["calculation_status"] == "valid", saved.text
        quote = client.get(f"/api/internal-quotes/{qid}").json()
        layout = client.get(f"/api/internal-quotes/{qid}/output-layout")
        assert layout.status_code == 200, layout.text
        assert layout.json()["quote_price_hkd"] is not None
        copied = fork(client, quote)
        copied_ref = client.get(f"/api/internal-quotes/{copied['id']}/reference-snapshot").json()
        assert copied_ref["snapshot"]["paper_prices"] == PAPERS
        assert next(s for s in copied["sections"] if s["department"] == "sales")["payload"]["cartons"] == payload["cartons"]
        # Removing a selected catalog entry must retain the input and block totals, not silently revert to the old factor.
        deleted = client.put(f"/api/internal-quotes/{copied['id']}/reference-snapshot/materials", json={"revision": copied["header_revision"], "material_prices": materials, "paper_prices": []})
        assert deleted.status_code == 200, deleted.text
        copied_sales = next(s for s in deleted.json()["sections"] if s["department"] == "sales")
        assert copied_sales["calculation_status"] == "blocked"
        assert copied_sales["payload"]["cartons"] == payload["cartons"]
        incomplete = client.get(f"/api/internal-quotes/{copied['id']}/output-layout")
        assert incomplete.status_code == 200 and incomplete.json()["quote_price_hkd"] is None, incomplete.text
        issued = client.post(f"/api/internal-quotes/{qid}/direct-issue", json={"revision": quote["header_revision"]})
        assert issued.status_code == 200, issued.text
        content = client.get(f"/api/internal-quotes/{qid}/exports/{issued.json()['id']}/download").content
        book = load_workbook(BytesIO(content))
        try:
            assert book["采用价目表"].sheet_state == "visible"
            assert any(c.value == "A=B" for row in book["采用价目表"] for c in row)
            formulas = [c.value for row in book["报价明细"] for c in row if c.data_type == "f"]
            assert any("*2.60*2/1000" in f for f in formulas)
            assert any("*1.94*2/1000" in f for f in formulas)
            assert any("*3.20/1000" in f for f in formulas)
        finally: book.close()
        frozen = client.get(f"/api/internal-quotes/{qid}").json()
        blocked = client.put(f"/api/internal-quotes/{qid}/reference-snapshot/materials", json={"revision": frozen["header_revision"], "material_prices": materials, "paper_prices": []})
        assert blocked.status_code == 409
        assert client.get(f"/api/internal-quotes/{qid}/exports/{issued.json()['id']}/download").content == content


def test_paper_catalog_baseline_freezing_scope_and_omitted_updates(monkeypatch):
    from test_internal_quote_api import logout
    with make_client(monkeypatch) as client:
        login(client, "paper-admin", "admin", "*", "*")
        old = create(client, "PAPER-OLD")
        url = "/api/internal-quotes/pricing-baseline?factory_id=huaxing&workshop_code=huaxing-workshop"
        baseline = client.get(url).json()
        payload = {key: baseline[key] for key in ("revision", "workshop_name", "material_prices", "machine_prices", "freight_routes")}
        saved = client.put(url, json={**payload, "paper_prices": PAPERS})
        assert saved.status_code == 200, saved.text
        payload["revision"] = saved.json()["revision"]
        omitted = client.put(url, json=payload)
        assert omitted.status_code == 200 and omitted.json()["paper_prices"] == PAPERS
        new = create(client, "PAPER-NEW")
        assert client.get(f"/api/internal-quotes/{new['id']}/reference-snapshot").json()["snapshot"]["paper_prices"] == PAPERS
        assert client.get(f"/api/internal-quotes/{old['id']}/reference-snapshot").json()["snapshot"].get("paper_prices", []) == []
        other = client.get("/api/internal-quotes/pricing-baseline?factory_id=huakang-b&workshop_code=huakang-b-workshop")
        assert other.status_code == 200 and other.json()["paper_prices"] == []
        payload["revision"] = omitted.json()["revision"]
        logout(client); login(client, "paper-reader", "sales_customer_owner", "sales-business")
        forbidden = client.put(url, json={**payload, "paper_prices": []})
        assert forbidden.status_code == 403
        assert client.get(url).json()["paper_prices"] == PAPERS


def test_paper_schema_rejects_ambiguous_or_nonpositive_prices():
    from app.schemas.internal_quote import InternalQuoteReferenceMaterialsUpdateRequest
    from pydantic import ValidationError
    for papers in ([PAPERS[0], PAPERS[0]], [{**PAPERS[0], "price_factor_hkd": "0"}], [{**PAPERS[0], "name": " "}], [{**PAPERS[0], "price_factor_hkd": "NaN"}]):
        with pytest.raises(ValidationError):
            InternalQuoteReferenceMaterialsUpdateRequest(revision=1, material_prices=[], paper_prices=papers)


def test_paper_migration_preserves_existing_data_and_prevents_loss():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text
    path = Path(__file__).parents[1] / "alembic/versions/20261107_0193_quote_paper_prices.py"
    spec = importlib.util.spec_from_file_location("paper_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE internal_quote_pricing_baselines (id TEXT PRIMARY KEY, factory_id TEXT, material_prices_json TEXT)"))
        connection.execute(text("INSERT INTO internal_quote_pricing_baselines VALUES ('old', 'huakang-b', 'preserved')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(text("SELECT * FROM internal_quote_pricing_baselines")).fetchall() == [("old", "huakang-b", "preserved", "[]")]
        migration.downgrade()
        assert "paper_prices_json" not in {c["name"] for c in inspect(connection).get_columns("internal_quote_pricing_baselines")}
        migration.upgrade()
        connection.execute(text("UPDATE internal_quote_pricing_baselines SET paper_prices_json=:papers"), {"papers": json.dumps(PAPERS)})
        with pytest.raises(RuntimeError, match="禁止删除"):
            migration.downgrade()
        assert json.loads(connection.execute(text("SELECT paper_prices_json FROM internal_quote_pricing_baselines")).scalar_one()) == PAPERS
        assert connection.execute(text("SELECT id,factory_id,material_prices_json FROM internal_quote_pricing_baselines")).fetchall() == [("old", "huakang-b", "preserved")]
    engine.dispose()


@pytest.mark.parametrize("component", [False, True])
@pytest.mark.parametrize("unit", ["inch", "cm"])
def test_selected_paper_excel_values_match_authoritative_cost(component, unit):
    from types import SimpleNamespace
    from openpyxl import Workbook
    from app.services.internal_quote_calculator import calculate_section
    from app.services.internal_quote_excel import _build_summary_sheet
    from app.services.internal_quote_workbook_view import WorkbookValues
    from test_internal_quote_excel_formula_links import _section, _find_row
    snapshot = {**deepcopy(SNAPSHOT), "fx": {"rmb_hkd": ".85", "hkd_usd": "7.8"}}
    payload = {**deepcopy(PAYLOAD), "testing_fee_enabled": False, "freight_calc": {"enabled": False}}
    for c in payload["cartons"]: c["size_unit"] = unit
    if component:
        payload.update(pricing_mode="component", pdq_size_in={"length": 8.25, "width": 4, "height": 14.75})
    calculation = calculate_section("sales", payload, snapshot, "paper-test")
    assert calculation["status"] == "valid"
    entries = [{"section": "sales", "is_global": True, "label": row["item"], "amount_hkd": row.get("per_piece_hkd", row.get("amount_hkd")), **row} for row in calculation["line_breakdown"]]
    shipping = {"markup": "1.2", "misc_ratio": ".02", "rows": []}
    if component:
        shipping.update(pricing_mode="component", pricing_groups=[{"id": "main", "name": "主体", "markup": "1.15", "cost_hkd": "0"}], pricing_entries=entries,
                        global_pricing={"entries": entries, "markup": "1.25", "cost_hkd": calculation["totals"]["total_hkd"]})
    book = Workbook()
    try:
        _build_summary_sheet(book, SimpleNamespace(product_name="纸材验证", quote_no="PAPER", customer="JustPlay" if component else "普通客", region_code="mainland", remark=""),
                             [_section("sales", payload=payload, calculation=calculation)], snapshot,
                             {"shipping_pricing": shipping, "t1": [], "t2": [], "t3": [], "t4": []}, {"factory_price_hkd": calculation["totals"]["total_hkd"], "carton_hkd": calculation["totals"]["carton_hkd"]}, [])
        sheet = book["报价明细"]; values = WorkbookValues(book)
        assert sheet["N5"].value == "主箱默认系数"
        total_row = _find_row(sheet, 14, "合计")
        assert values.cell(sheet.title, f"O{total_row}") == pytest.approx(float(calculation["totals"]["carton_hkd"]), abs=.00005)
    finally: book.close()


def test_paper_startup_guard_only_reads_and_requires_migration(monkeypatch):
    import importlib
    from sqlalchemy import create_engine, text
    db = importlib.import_module("app.db")
    engine = create_engine("sqlite://")
    monkeypatch.setattr(db, "engine", engine)
    db.ensure_internal_quote_paper_schema_ready()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE internal_quote_pricing_baselines (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO internal_quote_pricing_baselines VALUES ('original')"))
    with pytest.raises(RuntimeError, match="20261107_0193"):
        db.ensure_internal_quote_paper_schema_ready()
    with engine.begin() as connection:
        assert connection.execute(text("SELECT * FROM internal_quote_pricing_baselines")).fetchall() == [("original",)]
        connection.execute(text("ALTER TABLE internal_quote_pricing_baselines ADD COLUMN paper_prices_json TEXT NOT NULL DEFAULT '[]'"))
    db.ensure_internal_quote_paper_schema_ready()
    engine.dispose()
