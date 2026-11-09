from copy import deepcopy
from decimal import Decimal
import importlib

import pytest

from test_internal_quote_api import create_payload, login, logout, make_client
from test_internal_quote_alternatives import fill


def prepare(client, customer="普通客", factory="huaxing"):
    login(client, "whole-fx-owner", "admin", "*", "*")
    body = create_payload(suffix="WHOLE-FX", participating_sections=["engineering", "assembly", "sales"])
    body.update(factory_id=factory, workshop_code=f"{factory}-workshop", customer=customer, workflow_mode="direct_output")
    if customer == "JustPlay":
        body["pricing_components"] = ["主体"]
    response = client.post("/api/internal-quotes", json=body)
    assert response.status_code == 201, response.text
    quote = fill(client, response.json())
    root = f"/api/internal-quotes/{quote['id']}"
    drafts = [{"section_code": s["department"], "revision": s["revision"], "payload": deepcopy(s["payload"])} for s in quote["sections"] if s["is_required"]]
    for d in drafts:
        if d["section_code"] == "engineering":
            d["payload"]["materials"][0]["unit_price_rmb"] = 2
        if d["section_code"] == "sales":
            d["payload"]["shipping"].update(misc_ratio=.03, settlement_divisor=.97)
            if customer == "JustPlay":
                d["payload"].update(pricing_mode="component", pricing_components=[{"id": "component-01", "name": "主体", "markup_x": 1.15}], color_box_size_in={"length": 8.25, "width": 4, "height": 14.75})
    return root, quote, {"sections": drafts, "reference_fx": {"revision": quote["header_revision"], "rmb_hkd": "0.90", "hkd_usd": "7.90"}}


@pytest.mark.parametrize("factory,customer", [("huaxing", "普通客"), ("huakang-b", "JustPlay")])
def test_whole_save_includes_fx_and_edits_and_can_be_saved_again(monkeypatch, factory, customer):
    with make_client(monkeypatch) as client:
        root, before, payload = prepare(client, customer, factory)
        saved = client.put(root + "/sections/save-all", json=payload)
        assert saved.status_code == 200, saved.text
        after = saved.json()["quote"]
        reference = client.get(root + "/reference-snapshot").json()["snapshot"]
        assert Decimal(reference["fx"]["rmb_hkd"]) == Decimal(".90")
        assert Decimal(reference["fx"]["hkd_usd"]) == Decimal("7.90")
        assert after["reference_snapshot_id"] != before["reference_snapshot_id"]
        rows = {s["department"]: s for s in saved.json()["sections"]}
        assert rows["engineering"]["payload"]["materials"][0]["unit_price_rmb"] == 2
        assert rows["engineering"]["calculation"]["totals"]["hardware_hkd"] == "4.4444"
        assert rows["sales"]["payload"]["shipping"]["misc_ratio"] == .03
        assert rows["assembly"]["payload"] == next(s["payload"] for s in before["sections"] if s["department"] == "assembly")
        assert all(s["calculation_status"] == "valid" for s in rows.values()), rows
        assert all(s["calculation_reference_snapshot_id"] == after["reference_snapshot_id"] for s in rows.values())
        totals = {code: s["calculation"]["totals"] for code, s in rows.items()}
        repeated = client.put(root + "/sections/save-all", json={"sections": [{"section_code": s["department"], "revision": s["revision"], "payload": s["payload"]} for s in rows.values()]})
        assert repeated.status_code == 200, repeated.text
        assert {s["department"]: s["calculation"]["totals"] for s in repeated.json()["sections"]} == totals
        # The separate FX button remains compatible with a subsequent whole save.
        fx_saved = client.put(root + "/reference-snapshot/fx", json={"revision": repeated.json()["quote"]["header_revision"], "rmb_hkd": "0.88", "hkd_usd": "7.80"})
        assert fx_saved.status_code == 200, fx_saved.text
        active = [s for s in fx_saved.json()["sections"] if s["is_required"]]
        after_fx = client.put(root + "/sections/save-all", json={"sections": [{"section_code": s["department"], "revision": s["revision"], "payload": s["payload"]} for s in active]})
        assert after_fx.status_code == 200, after_fx.text
        engineering = next(s for s in after_fx.json()["sections"] if s["department"] == "engineering")
        assert engineering["calculation"]["totals"]["hardware_hkd"] == "4.5455"
        issued = client.post(root + "/direct-issue", json={"revision": after_fx.json()["quote"]["header_revision"]})
        assert issued.status_code == 200, issued.text


@pytest.mark.parametrize("failure", ["header", "section", "invalid_fx", "permission", "rollback"])
def test_fx_and_departments_remain_unchanged_on_failure(monkeypatch, failure):
    with make_client(monkeypatch) as client:
        root, before, payload = prepare(client)
        if failure == "header":
            payload["reference_fx"]["revision"] += 10
        elif failure == "section":
            payload["sections"][-1]["revision"] += 10
        elif failure == "invalid_fx":
            payload["reference_fx"]["rmb_hkd"] = "0"
        elif failure == "permission":
            response = client.post(root + "/participation", json={"revision": before["header_revision"], "add_sections": ["molding"]})
            assert response.status_code == 200, response.text
            before = client.get(root).json()
            molding = next(s for s in before["sections"] if s["department"] == "molding")
            payload["reference_fx"]["revision"] = before["header_revision"]
            payload["sections"] = [{"section_code": "molding", "revision": molding["revision"], "payload": molding["payload"]}]
            logout(client)
            login(client, "whole-fx-molding", "molding_clerk", "molding")
        elif failure == "rollback":
            service = importlib.import_module("app.services.internal_quote")
            original = service._replace_quote_reference_set
            def fail_after_reference(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError("simulated transaction failure")
            monkeypatch.setattr(service, "_replace_quote_reference_set", fail_after_reference)
        if failure == "rollback":
            with pytest.raises(RuntimeError, match="simulated transaction failure"):
                client.put(root + "/sections/save-all", json=payload)
        else:
            response = client.put(root + "/sections/save-all", json=payload)
            assert response.status_code == {"header": 409, "section": 409, "invalid_fx": 422, "permission": 403}[failure], response.text
        after = client.get(root).json()
        for key in ["header_revision", "reference_snapshot_id", "sections"]:
            assert after[key] == before[key]
