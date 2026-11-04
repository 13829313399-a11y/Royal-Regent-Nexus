from copy import deepcopy
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook
from app.services.internal_quote_amount_adjustments import KEY, adjustment_catalog, retain_replaced_adjustments
from app.services.internal_quote_calculator import calculate_section
from test_internal_quote_calculator import SNAPSHOT

def default_reference_snapshot():
    return deepcopy(SNAPSHOT)


def adopt(code, payload, path, amount, mode="per_piece"):
    spec = adjustment_catalog(code, payload, default_reference_snapshot())[tuple(path)]
    row = payload
    for key in path:
        row = row[key]
    row[KEY] = {"amount_hkd": str(amount), "mode": mode, "basis_hash": spec["basis_hash"]}
    row.setdefault("price_annotations", {})[KEY] = {"text": "供应商口头确认优惠", "image_attachment_ids": []}


def assembly():
    return {"labor_base_hkd": 260, "standard_work_hours": 11, "groups": [
        {"name": "组装", "category": "assembly", "teams": 1, "production_qty": 3000,
         "processes": [{"name": "装壳", "persons": 10}, {"name": "打螺丝", "persons": 4}]},
        {"name": "包装", "category": "packaging", "teams": 1, "production_qty": 3000, "total_persons": 6, "processes": []}]}


def calc(code, payload):
    return calculate_section(code, payload, default_reference_snapshot(), "ref")


def test_assembly_adopted_cost_preserves_basis_zero_and_pending():
    payload = assembly()
    original = deepcopy(payload)
    adopt("assembly", payload, ["groups", 0], "1.1")
    adopt("assembly", payload, ["groups", 1], "0")
    result = calc("assembly", payload)
    assert result["status"] == "valid"
    assert result["totals"]["total_hkd"] == "1.1000"
    assert result["group_summaries"][0]["original_amount_hkd_pcs"] == "1.2133"
    assert payload["groups"][0]["processes"] == original["groups"][0]["processes"]
    payload["groups"][0]["name"] = "改名不改价"
    assert calc("assembly", payload)["status"] == "valid"
    payload["groups"][0]["production_qty"] = 4000
    result = calc("assembly", payload)
    assert result["status"] == "blocked"
    assert result["totals"]["assembly_hkd"] == "0.9100"
    adopt("assembly", payload, ["groups", 0], "1.1")
    assert calc("assembly", payload)["status"] == "valid"
    del payload["groups"][0][KEY]
    assert calc("assembly", payload)["totals"]["total_hkd"] == "0.9100"


def test_carton_and_flat_modes_include_quantity_once_and_stale_on_specs():
    payload = {"cartons": [{"item": "外箱", "length_in": 18, "width_in": 12, "height_in": 10,
                           "qty_per_carton": 12, "flat_cards": [{"name": "平卡", "length_in": 10, "width_in": 5, "quantity": 2}]}]}
    adopt("sales", payload, ["cartons", 0], 6, "per_carton")
    adopt("sales", payload, ["cartons", 0, "flat_cards", 0], ".1")
    result = calc("sales", payload)
    assert result["status"] == "valid"
    carton = next(line for line in result["line_breakdown"] if line["kind"] == "carton")
    assert Decimal(carton["per_piece_hkd"]) == Decimal(".6")
    adopt("sales", payload, ["cartons", 0], ".5")
    assert calc("sales", payload)["totals"]["carton_hkd"] == "0.6000"
    payload["cartons"][0]["qty_per_carton"] = 24
    assert calc("sales", payload)["status"] == "blocked"


def test_import_retains_adjustments_for_explicit_review_without_reapplying():
    old = assembly()
    adopt("assembly", old, ["groups", 0], 1)
    new = assembly()
    new["groups"][0]["import_batch_id"] = "new-sheet"
    result = retain_replaced_adjustments(old, new)
    assert result["groups"][0][KEY]["requires_confirmation"]
    assert calc("assembly", result)["status"] == "blocked"
    removed = retain_replaced_adjustments(old, {"groups": []})
    assert removed["removed_amount_adjustments"][0]["adjustment"]["amount_hkd"] == "1"


@pytest.mark.parametrize("component", [False, True])
@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("assembly_amount", ["1.1", "0"])
def test_adopted_amounts_match_visible_excel_for_ordinary_and_justplay(component, count, assembly_amount):
    from types import SimpleNamespace
    from openpyxl import Workbook
    from app.services.internal_quote import _rr2_cost_summary
    from app.services.internal_quote_excel import _build_summary_sheet
    from app.services.internal_quote_workbook_view import WorkbookValues
    from app.services.internal_quote_output_fields import _bind_aggregate_cells, source_groups
    from test_internal_quote_excel_formula_links import _section, _find_row
    payload = {"cartons": [{"item": "外箱", "size_unit": "cm", "length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 12,
                            "flat_cards": [{"name": "平卡", "length_in": 10, "width_in": 4, "quantity": 2}]},
                           {"item": "内箱", "length_in": 5, "width_in": 4, "height_in": 3, "qty_per_carton": 6}][:count],
               "color_box_size_in": {"length": 17.25, "width": 11.25, "height": 9},
               "shipping": {"markup_x": "1.2", "misc_ratio": ".02", "packaging_markup_x": "1.3"},
               "testing_fee_enabled": False, "freight_calc": {"enabled": False, "freight_enabled": False, "lifting_enabled": False}}
    if component:
        payload.update(pricing_mode="component", pricing_components=[{"id": "main", "name": "主体", "markup_x": "1.2"}])
    adopt("sales", payload, ["cartons", 0], "6", "per_carton")
    adopt("sales", payload, ["cartons", 0, "flat_cards", 0], ".1")
    if count == 2:
        adopt("sales", payload, ["cartons", 1], ".2")
    labor = assembly()
    adopt("assembly", labor, ["groups", 0], assembly_amount)
    adopt("assembly", labor, ["groups", 1], ".3")
    sales_calc, labor_calc = calc("sales", payload), calc("assembly", labor)
    sections = [_section("sales", payload=payload, calculation=sales_calc), _section("assembly", payload=labor, calculation=labor_calc)]
    for section in sections:
        section.is_required = True
        section.department_name = section.department
    total = Decimal(sales_calc["totals"]["total_hkd"]) + Decimal(labor_calc["totals"]["total_hkd"])
    context = {"factory_price_hkd": total, "carton_hkd": Decimal(sales_calc["totals"]["carton_hkd"]), "assembly_hkd": Decimal(labor_calc["totals"]["total_hkd"])}
    summary = _rr2_cost_summary(sections, context, SNAPSHOT, factory_id="huakang-b" if component else "huaxing")
    book = Workbook()
    _build_summary_sheet(book, SimpleNamespace(product_name="调价验证", quote_no="ADOPTED", customer="JustPlay" if component else "普通客", region_code="mainland", remark=""), sections, SNAPSHOT, summary, context, [])
    sheet = book["报价明细"]
    values = WorkbookValues(book)
    total_row = _find_row(sheet, 14, "合计")
    assert values.cell(sheet.title, f"O{total_row}") == pytest.approx(.6 + (.2 if count == 2 else 0), abs=.00005)
    _bind_aggregate_cells(book, source_groups(sections, snapshot=SNAPSHOT))
    for index, expected in enumerate([float(assembly_amount), .3]):
        bindings = [address for address, binding in sheet._quote_bindings.items() if binding.get("group") == f"assembly:groups/{index}" and binding["kind"] == "price"]
        assert bindings, (component, index, sheet._quote_bindings)
        assert sum(values.cell(sheet.title, address) for address in bindings) == pytest.approx(expected, abs=.00005)
    for row in sheet:
        for cell in row:
            if cell.data_type == "f":
                values.cell(sheet.title, cell.coordinate)
    book.close()


def test_output_adjustment_preview_save_restore_and_export(monkeypatch):
    from test_internal_quote_api import make_client, login
    from test_internal_quote_alternatives import create, fill
    with make_client(monkeypatch) as client:
        login(client, "amount-owner", "admin", "*", "*")
        quote = fill(client, create(client, "AMOUNT"))
        root = f"/api/internal-quotes/{quote['id']}"
        initial = client.get(root + "/output-layout")
        assert initial.status_code == 200, initial.text
        layout = initial.json()
        assert layout["formula_errors"] == []
        fields = [f for g in layout["groups"] for f in g["fields"] if f.get("adjustment")]
        fields.sort(key=lambda f: f["id"])
        assert len(fields) == 2
        edits = [{"field_id": f["id"], "value": "0.1", "adjustment_mode": "per_piece",
                  "annotation": {"text": "供应商口头确认", "image_attachment_ids": [], "new_images": []}} for f in fields]
        import base64
        from PIL import Image
        picture = BytesIO()
        Image.new("RGB", (4, 4), "blue").save(picture, format="PNG")
        edits[0]["annotation"]["new_images"] = [base64.b64encode(picture.getvalue()).decode()]
        body = {"base_token": layout["base_token"], "edits": edits}
        invalid = deepcopy(body)
        invalid["edits"][0]["annotation"]["text"] = ""
        assert client.put(root + "/output-layout", json=invalid).status_code == 400
        preview = client.post(root + "/output-layout/preview", json=body)
        assert preview.status_code == 200, preview.text
        assert preview.json()["formula_errors"] == []
        before = client.get(root).json()
        assert client.get(root + "/attachments").json() == []
        assert not next(s for s in before["sections"] if s["department"] == "assembly")["payload"]["groups"][0].get(KEY)
        saved = client.put(root + "/output-layout", json=body)
        assert saved.status_code == 200, saved.text
        fresh = client.get(root + "/output-layout").json()
        assert fresh["quote_price_hkd"] == preview.json()["quote_price_hkd"]
        assert client.put(root + "/output-layout", json=body).status_code == 409
        assert len(client.get(root + "/attachments").json()) == 1
        assembly_section = next(s for s in client.get(root).json()["sections"] if s["department"] == "assembly")
        assembly_section["payload"]["groups"][0]["production_qty"] = 4000
        changed = client.put(root + "/sections/assembly", json={"revision": assembly_section["revision"], "payload": assembly_section["payload"]})
        assert changed.status_code == 200, changed.text
        assert changed.json()["calculation_status"] == "blocked"
        pending = client.get(root + "/output-layout").json()
        pending_field = next(f for g in pending["groups"] if g["section"] == "assembly" for f in g["fields"] if f.get("adjustment"))
        assert pending_field["adjustment"]["status"] == "pending"
        assert pending["quote_price_hkd"] is None
        reconfirm = {"base_token": pending["base_token"], "edits": [{"field_id": pending_field["id"], "value": "0.1", "adjustment_mode": "per_piece"}]}
        reconfirmed = client.put(root + "/output-layout", json=reconfirm)
        assert reconfirmed.status_code == 200, reconfirmed.text
        restore = {"base_token": client.get(root + "/output-layout").json()["base_token"], "edits": [{"field_id": pending_field["id"], "value": None, "adjustment_mode": "formula"}]}
        restored = client.put(root + "/output-layout", json=restore)
        assert restored.status_code == 200, restored.text
        restored_section = next(s for s in client.get(root).json()["sections"] if s["department"] == "assembly")
        assert KEY not in restored_section["payload"]["groups"][0]
        assert len(restored_section["payload"]["groups"][0]["quote_amount_history"]) == 3
        assert Decimal(restored_section["calculation"]["totals"]["total_hkd"]) == Decimal(".155")
        # Adopt again with the same protected image; keep all three earlier actions.
        latest = client.get(root + "/output-layout").json()
        reconfirm["base_token"] = latest["base_token"]
        reconfirm["edits"][0]["annotation"] = {"text": "重新确认", "image_attachment_ids": [client.get(root + "/attachments").json()[0]["id"]]}
        assert client.put(root + "/output-layout", json=reconfirm).status_code == 200
        current = client.get(root).json()
        issued = client.post(root + "/direct-issue", json={"revision": current["header_revision"]})
        assert issued.status_code == 200, issued.text
        file = client.get(root + f"/exports/{issued.json()['id']}/download")
        book = load_workbook(BytesIO(file.content))
        assert "调价说明" in book.sheetnames
        assert any(c.comment and "原核算" in c.comment.text for row in book["报价明细"] for c in row)
        assert book["调价说明"].max_row >= 3
        assert len(book["调价说明"]._images) == 1
        assert client.get(root + f"/exports/{issued.json()['id']}/download").content == file.content


def test_selected_source_replacement_keeps_adopted_cost_pending(monkeypatch):
    from test_internal_quote_api import make_client, login
    from test_internal_quote_alternatives import create, fill
    from test_internal_quote_import import workbook_bytes
    with make_client(monkeypatch) as client:
        login(client, "replacement-owner", "admin", "*", "*")
        quote = fill(client, create(client, "AMOUNT-REPLACE"))
        root = f"/api/internal-quotes/{quote['id']}"
        def import_sheet(people, replacement=None):
            content = workbook_bytes([["组装工序名称", "人数", "工具", "备注"], ["装壳", people, "", ""]])
            response = client.post(root + "/imports/assembly/preview", data={"replace_attachment_id": replacement} if replacement else {},
                                   files={"file": (f"装工{people}.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            assert response.status_code == 201, response.text
            data = response.json()
            confirmed = client.post(root + f"/imports/{data['batch_id']}/confirm", json={"revision": data["target_revision"]})
            assert confirmed.status_code == 200, confirmed.text
        import_sheet(14)
        layout = client.get(root + "/output-layout").json()
        field = next(f for g in layout["groups"] if g["section"] == "assembly" for f in g["fields"] if f.get("adjustment"))
        saved = client.put(root + "/output-layout", json={"base_token": layout["base_token"], "edits": [{"field_id": field["id"], "value": "1.1", "adjustment_mode": "per_piece", "annotation": {"text": "议价后确认"}}]})
        assert saved.status_code == 200, saved.text
        source = next(a for a in client.get(root + "/attachments").json() if a["is_import_source"])
        import_sheet(12, source["id"])
        section = next(s for s in client.get(root).json()["sections"] if s["department"] == "assembly")
        assert section["calculation_status"] == "blocked"
        group = section["payload"]["groups"][0]
        assert group[KEY]["amount_hkd"] == "1.1" and group[KEY]["requires_confirmation"]
        assert group["price_annotations"][KEY]["text"] == "议价后确认"
        assert len(group["quote_amount_history"]) == 1
