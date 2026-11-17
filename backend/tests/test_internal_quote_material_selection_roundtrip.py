from copy import deepcopy
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_alternatives import fill


@pytest.mark.parametrize("factory,customer", [("huaxing", "普通测试客"), ("huakang-b", "JustPlay")])
@pytest.mark.parametrize("material,alias,grade", [
    ("C-PP", "透明PP", "NEW-2026"), ("C-ABS", "透明ABS", "NEW-2026"),
    ("导电PP", "导电pp", "导电"), ("导电PP", "1#PP", "7032 E3"),
])
def test_added_material_survives_save_refresh_repeated_save_and_excel(monkeypatch, factory, customer, material, alias, grade):
    with make_client(monkeypatch) as client:
        login(client, "material-roundtrip-owner", "admin", "*", "*")
        body = create_payload(suffix="RESIN-ROUNDTRIP", participating_sections=["engineering", "molding", "assembly", "sales"])
        body.update(factory_id=factory, workshop_code=f"{factory}-workshop", customer=customer, workflow_mode="direct_output")
        if customer == "JustPlay":
            body["pricing_components"] = ["主体"]
        response = client.post("/api/internal-quotes", json=body)
        assert response.status_code == 201, response.text
        quote = fill(client, response.json())
        base = f"/api/internal-quotes/{quote['id']}"

        def current():
            response = client.get(base)
            assert response.status_code == 200, response.text
            return response.json()

        def section(code):
            return next(s for s in current()["sections"] if s["department"] == code)

        def save(code, payload):
            previous = section(code)
            response = client.put(base + f"/sections/{code}", json={"revision": previous["revision"], "payload": payload})
            assert response.status_code == 200, response.text
            return response.json()

        if customer == "JustPlay":
            save("sales", {**section("sales")["payload"], "pricing_mode": "component",
                "pricing_components": [{"id": "component-01", "name": "主体", "markup_x": 1.2}],
                "color_box_size_in": {"length": 8.25, "width": 4, "height": 14.75}})
        engineering = {"molds": [{"mold_id": "resin-mold", "mold_no": "3", "item": "船身左",
            "material_type": material, "net_weight_g": 75, "quantity": 2, "target_output": 14142.8571,
            "machine_code": "18A", "pricing_component_id": "component-01"}]}
        save("engineering", engineering)
        before = client.get(base + "/reference-snapshot").json()["snapshot"]
        prices = [{"material": key.split("|", 1)[0], "grade": key.split("|", 1)[1], "price_hkd_lb": value}
                  for key, value in before["material_prices"].items()]
        # Also exercise switching from the quote-only entry to an existing baseline grade.
        existing_grade = grade == "7032 E3"
        prices.append({"material": "导电pp" if existing_grade else alias,
                       "grade": "导电" if existing_grade else grade, "price_hkd_lb": "8.20"})
        expected_price = before["material_prices"][f"{alias}|{grade}"] if existing_grade else "8.20"
        response = client.put(base + "/reference-snapshot/materials", json={
            "revision": current()["header_revision"], "material_prices": prices})
        assert response.status_code == 200, response.text
        payload = deepcopy(section("molding")["payload"])
        payload["injection_lines"][0].update(material=alias, grade=grade, quantity=3)
        if existing_grade:
            payload["injection_lines"][0]["material_choice_for"] = ["", "导电PP"]
        if material == "导电PP" and not existing_grade:
            # The very first write is the whole-product form, including a
            # historical draft that has no client-supplied selection marker.
            response = client.put(base + "/sections/save-all", json={"sections": [
                {"section_code": s["department"], "revision": s["revision"],
                 "payload": payload if s["department"] == "molding" else s["payload"]}
                for s in current()["sections"] if s["is_required"]]})
            assert response.status_code == 200, response.text
            selected = section("molding")
            assert selected["payload"]["injection_lines"][0]["material_choice_for"] == ["", "导电PP"]
        else:
            selected = save("molding", payload)
        assert selected["calculation_status"] == "valid", selected
        assert selected["payload"]["injection_lines"][0]["grade"] == grade
        # Exercise the whole-product transaction and then the department save,
        # matching the sequence that previously cleared the selected grade.
        quote = current()
        response = client.put(base + "/sections/save-all", json={"sections": [{
            "section_code": s["department"], "revision": s["revision"], "payload": s["payload"],
        } for s in quote["sections"] if s["is_required"]]})
        assert response.status_code == 200, response.text
        refreshed = section("molding")
        repeated = save("molding", refreshed["payload"])
        row = repeated["payload"]["injection_lines"][0]
        assert (row["material"], row["grade"]) == (alias, grade)
        assert (row["target_output"], row["quantity"], row["sets"], row["net_weight_g"]) == (14142.8571, 3, 2, 75)
        assert repeated["calculation_status"] == "valid"
        assert repeated["calculation"]["totals"] == selected["calculation"]["totals"]
        line = next(line for line in repeated["calculation"]["line_breakdown"] if line["kind"] == "injection")
        assert Decimal(line["material_price_hkd_lb"]) == Decimal(expected_price)
        assert "grade" not in row["engineering_synced_fields"]
        response = client.get(base + "/summary")
        assert response.status_code == 200, response.text
        quote = current()
        assert all(s["calculation_status"] == "valid" for s in quote["sections"] if s["is_required"]), quote["sections"]
        issued = client.post(base + "/direct-issue", json={"revision": quote["header_revision"]})
        assert issued.status_code == 200, issued.text
        raw = client.get(base + f"/exports/{issued.json()['id']}/download")
        assert raw.status_code == 200
        workbook = load_workbook(BytesIO(raw.content))
        try:
            values = [str(cell.value) for ws in workbook for row in ws for cell in row if cell.value is not None]
            assert any(grade in value for value in values)
            sheet = workbook.worksheets[0]
            mold_row = next(row for row in sheet.iter_rows() if row[2].value == "船身左")
            assert mold_row[3].value == alias
            assert mold_row[5].value is not None and mold_row[9].value is not None
            assert not any("牌号待填写" in value or "未匹配材料价" in value for value in values)
        finally:
            workbook.close()
