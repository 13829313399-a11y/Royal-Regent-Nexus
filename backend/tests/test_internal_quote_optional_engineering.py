"""Engineering participation is optional; selected departments still gate output."""
from copy import deepcopy
from io import BytesIO

import pytest
from openpyxl import load_workbook

from test_internal_quote_api import create_payload, login, logout, make_client
from test_internal_quote_alternatives import fork
from test_internal_quote_document_clone import clone_body
from test_internal_quote_linkage_completeness import ROW


def create(client, *, engineering=False, factory="huaxing", customer="测试客户", molding=False):
    codes = ["assembly", "slush", "sales"] + (["engineering"] if engineering else []) + (["molding"] if molding else [])
    payload = create_payload(suffix="OPTIONAL-ENGINEERING", participating_sections=codes)
    payload.update(workflow_mode="direct_output", factory_id=factory, customer=customer)
    if customer == "JustPlay":
        payload["pricing_components"] = ["主体"]
    response = client.post("/api/internal-quotes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def save(client, root, code, payload):
    section = next(s for s in client.get(root).json()["sections"] if s["department"] == code)
    response = client.put(root + f"/sections/{code}", json={"revision": section["revision"], "payload": payload})
    assert response.status_code == 200, response.text
    return response.json()


def fill_without_engineering(client, quote):
    root = f"/api/internal-quotes/{quote['id']}"
    sales = deepcopy(next(s for s in quote["sections"] if s["department"] == "sales")["payload"])
    component_id = next(iter(sales.get("pricing_components", [])), {}).get("id", "")
    save(client, root, "assembly", {"labor_base_hkd": 310, "groups": [{"name": "组装", "category": "assembly",
        "pricing_component_id": component_id, "processes": [{"name": "组装", "persons": 2, "teams": 1, "production_qty": 5000}]}]})
    save(client, root, "slush", {"lines": [{"product_code": "RC-01", "item": "软胶件", "material": "PVC", "weight_g": 35,
        "daily_output_24h": 8000, "quantity": 2, "unit_price_hkd": 3.6, "pricing_component_id": component_id}]})
    sales.update(packaging_materials=[{"item": "彩盒", "category": "color_box_inner_card", "quantity": 1, "unit_price_rmb": 1}],
        color_box_size_in={"length": 5, "width": 4, "height": 3},
        cartons=[{"item": "主纸箱", "length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 12}],
        testing_fee_enabled=False, freight_calc={"enabled": False, "freight_enabled": False, "lifting_enabled": False},
        shipping={"markup_tiers": [{"moq": 5000, "markup_x": 1.2, "include_in_output": True}], "selected_markup_moq": 5000})
    save(client, root, "sales", sales)
    return client.get(root).json()


@pytest.mark.parametrize("factory,customer", [("huaxing", "测试客户"), ("huakang-d", "测试客户"), ("huakang-b", "JustPlay")])
def test_slush_quote_without_engineering_can_copy_and_issue(monkeypatch, factory, customer):
    with make_client(monkeypatch) as client:
        login(client, "optional-engineering-owner", "admin", "*", "*")
        quote = fill_without_engineering(client, create(client, factory=factory, customer=customer))
        assert quote["readiness"]["state"] == "ready", quote["readiness"]
        assert quote["readiness"]["required_sections"] == 3
        engineering = next(s for s in quote["sections"] if s["department"] == "engineering")
        assert not engineering["is_required"] and not engineering["filled_at"]
        copied = fork(client, quote, "version")
        response = client.post(f"/api/internal-quotes/{quote['id']}/clone-document", json=clone_body([quote]))
        assert response.status_code == 201, response.text
        for current in (quote, copied, response.json()):
            assert not next(s for s in current["sections"] if s["department"] == "engineering")["is_required"]
            root = f"/api/internal-quotes/{current['id']}"
            summary = client.get(root + "/summary")
            assert summary.status_code == 200, summary.text
            assert summary.json()["pricing_complete"]
            issued = client.post(root + "/direct-issue", json={"revision": current["header_revision"]})
            assert issued.status_code == 200, issued.text
            raw = client.get(root + f"/exports/{issued.json()['id']}/download")
            assert raw.status_code == 200
            workbook = load_workbook(BytesIO(raw.content), read_only=True)
            assert workbook["审批与版本"]["B4"].value == "P4 直接输出"
            workbook.close()


def test_selected_engineering_blocks_until_removed_and_can_be_added_back(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "engineering-participation-owner", "admin", "*", "*")
        quote = fill_without_engineering(client, create(client, engineering=True))
        root = f"/api/internal-quotes/{quote['id']}"
        assert any(b["section_code"] == "engineering" for b in quote["readiness"]["blockers"])
        assert client.post(root + "/direct-issue", json={"revision": quote["header_revision"]}).status_code == 409
        for code in ("sales", "assembly"):
            assert client.post(root + "/participation/remove", json={"revision": quote["header_revision"], "remove_sections": [code]}).status_code == 422
        removed = client.post(root + "/participation/remove", json={"revision": quote["header_revision"], "remove_sections": ["engineering"]})
        assert removed.status_code == 200, removed.text
        assert removed.json()["readiness"]["state"] == "ready"
        stale = client.post(root + "/participation", json={"revision": quote["header_revision"], "add_sections": ["engineering"]})
        assert stale.status_code == 409
        added = client.post(root + "/participation", json={"revision": removed.json()["header_revision"], "add_sections": ["engineering"]})
        assert added.status_code == 200, added.text
        assert any(b["section_code"] == "engineering" for b in added.json()["readiness"]["blockers"])
        logout(client)
        login(client, "engineering-participation-molding", "molding_clerk", "molding")
        denied = client.post(root + "/participation/remove", json={"revision": added.json()["header_revision"], "remove_sections": ["engineering"]})
        assert denied.status_code == 403


def test_removing_engineering_invalidates_linked_molding_but_keeps_manual_rows(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "engineering-removal-molding", "admin", "*", "*")
        quote = create(client, engineering=True, molding=True)
        root = f"/api/internal-quotes/{quote['id']}"
        save(client, root, "engineering", {"molds": [{"mold_id": "m1", "mold_no": "M1", "item": "外壳", "cost_rmb": 10, "quantity": 1, "net_weight_g": 100}]})
        saved = save(client, root, "molding", {"injection_lines": [deepcopy(ROW), {**ROW, "mold_no": "MANUAL", "item": "手动胶件", "engineering_sync_disabled": True}]})
        quote = client.get(root).json()
        removed = client.post(root + "/participation/remove", json={"revision": quote["header_revision"], "remove_sections": ["engineering"]})
        assert removed.status_code == 200, removed.text
        molding = next(s for s in removed.json()["sections"] if s["department"] == "molding")
        assert molding["calculation_status"] == "stale"
        linked, manual = molding["payload"]["injection_lines"]
        assert linked["engineering_source_missing"]
        assert not manual.get("engineering_source_missing")
        # A stale editor cannot clear the missing-source marker by resaving its old payload.
        resaved = save(client, root, "molding", saved["payload"])
        assert resaved["calculation_status"] == "blocked"
        assert resaved["payload"]["injection_lines"][0]["engineering_source_missing"]
