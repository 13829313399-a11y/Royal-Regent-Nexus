"""Imported mold totals initialize one editable production fee with source ownership."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
import importlib
import json
from types import SimpleNamespace

from openpyxl import Workbook
import pytest

from test_internal_quote_api import login, make_client
from test_internal_quote_alternatives import create
from test_internal_quote_calculator import SNAPSHOT
from test_internal_quote_incomplete_drafts import detail


def service():
    return importlib.import_module("app.services.internal_quote_artifacts")


def fragment(batch="batch-a", prices=("100", "200")):
    return {"molds": [
        {"item": f"模拟模具{index}", "mold_no": f"M{index}", "cost_rmb": price,
         "quantity": index + 2, "parts": [{"name": "上"}, {"name": "下"}], "import_batch_id": batch}
        for index, price in enumerate(prices)
    ], "amortization_qty": "1000"}


def merge(payload, batch="batch-a", prices=("100", "200")):
    return service()._merge_import_payload("mold", payload, fragment(batch, prices), "replace")


def batch_record(batch_id, revision=2):
    return SimpleNamespace(id=batch_id, import_type="mold", confirmed_revision=revision,
                           preview_json=json.dumps({"payload_fragment": fragment(batch_id)}))


def calculate(payload):
    calculator = importlib.import_module("app.services.internal_quote_calculator")
    return calculator.calculate_section("engineering", payload, SNAPSHOT, "test-mold-fee-ref")


def automatic_fee(payload):
    rows = [row for row in payload["production_mold_costs"] if "mold_import_default_rmb" in row]
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("existing", [None, [], [{"item": "模具费用", "cost_rmb": "999"}],
                                            [{"item": "超声模费用", "cost_rmb": "50"}]])
def test_mold_import_initializes_one_fee_and_preserves_decimal_precision(existing):
    original = {} if existing is None else {"production_mold_costs": existing}
    before = deepcopy(original)
    result = merge(original, prices=("0.1", "0.2"))
    assert original == before
    fee = automatic_fee(result)
    assert Decimal(fee["cost_rmb"]) == Decimal("0.3")
    assert isinstance(fee["mold_import_default_rmb"], str)
    assert Decimal(fee["mold_import_default_rmb"]) == Decimal("0.3")
    assert fee["import_batch_id"] == "batch-a"
    assert len([row for row in result["production_mold_costs"] if row["item"] == "模具费用"]) == 1
    if existing and existing[0]["item"] == "超声模费用":
        assert existing[0] in result["production_mold_costs"]


@pytest.mark.parametrize("enabled", [True, False])
def test_import_total_does_not_multiply_sets_or_parts_and_preserves_other_fees(enabled):
    others = [{"item": "超声模费用", "cost_rmb": "50"}, {"item": "喷油模具", "cost_rmb": "60"},
              {"item": "其他费用", "cost_rmb": "10", "remark": "手工费用"}]
    original = {"production_mold_costs": [{"item": "模具费用", "cost_rmb": "0"}, *others],
                "mold_allocation_enabled": enabled, "mold_fx_rmb_usd": "7.75", "customer_mold_subsidy_usd": "0"}
    result = merge(original)
    assert result["production_mold_costs"][1:] == others
    assert result["mold_allocation_enabled"] is enabled
    assert result["mold_fx_rmb_usd"] == "7.75"
    assert result["customer_mold_subsidy_usd"] == "0"
    fee = automatic_fee(result)
    assert Decimal(fee["cost_rmb"]) == 300
    calculated = calculate(result)
    assert calculated["status"] == "valid"
    assert calculated["totals"]["mold_quote_total_rmb"] == "300.0000"
    assert calculated["totals"]["mold_total_rmb"] == ("420.0000" if enabled else "0.0000")
    assert calculated["totals"]["mold_share_rmb"] == ("0.4200" if enabled else "0.0000")
    assert all(row["reference_only"] for row in calculated["line_breakdown"] if row["kind"] == "mold_quote")


def test_reimport_updates_renamed_owned_fee_before_matching_manual_labels():
    original = merge({})
    fee = automatic_fee(original)
    fee.update(item="修改过名称的主模费", cost_rmb="350")
    manual = {"item": "模具费用", "cost_rmb": "25", "remark": "独立手工附加费"}
    original["production_mold_costs"].append(manual)
    result = merge(original, "batch-b", ("400",))
    current = automatic_fee(result)
    assert current["item"] == fee["item"]
    assert Decimal(current["cost_rmb"]) == Decimal(current["mold_import_default_rmb"]) == 400
    assert current["import_batch_id"] == "batch-b"
    assert len(result["production_mold_costs"]) == len(original["production_mold_costs"])
    assert manual in result["production_mold_costs"]
    assert fee["cost_rmb"] == "350"


@pytest.mark.parametrize("amount,expected", [(300, "0"), ("300.0000", "0"), ("350", "350"), ("0", "0")])
@pytest.mark.parametrize("renamed", [False, True])
def test_source_delete_clears_only_unchanged_default_and_detaches_manual_overrides(amount, expected, renamed):
    payload = merge({"production_mold_costs": [{"item": "超声模费用", "cost_rmb": "50"}]})
    fee = automatic_fee(payload)
    fee.update(item="已改名的模具费用" if renamed else "模具费用", cost_rmb=amount)
    before = deepcopy(payload)
    result, images = service()._clear_import_generated_payload(payload, [batch_record("batch-a")])
    assert payload == before
    assert not images
    assert result["molds"] == []
    retained = next(row for row in result["production_mold_costs"] if row["item"] == fee["item"])
    assert Decimal(str(retained["cost_rmb"])) == Decimal(str(amount) if renamed else expected)
    assert "mold_import_default_rmb" not in retained
    assert "import_batch_id" not in retained
    assert {"item": "超声模费用", "cost_rmb": "50"} in result["production_mold_costs"]


def test_deleting_old_source_cannot_clear_new_source_fee_or_unowned_manual_fee():
    payload = merge(merge({}), "batch-b", ("400",))
    unowned = {"item": "模具费用", "cost_rmb": "400"}
    payload["production_mold_costs"].append(unowned)
    old, current = batch_record("batch-a", 2), batch_record("batch-b", 3)
    cleared, _ = service()._clear_import_generated_payload(payload, [old], all_batches=[old, current])
    assert cleared == payload
    cleared, _ = service()._clear_import_generated_payload(payload, [current], all_batches=[old, current])
    assert unowned in cleared["production_mold_costs"]
    assert len([row for row in cleared["production_mold_costs"] if Decimal(str(row["cost_rmb"])) == 400]) == 1


def test_legacy_without_production_fee_list_retains_same_cost_after_import():
    legacy = fragment()
    before = calculate(legacy)
    after = calculate(merge(legacy))
    assert before["status"] == after["status"] == "valid"
    assert before["totals"] == after["totals"]


def test_zero_price_reimport_replaces_previous_default_instead_of_retaining_old_charge():
    result = merge(merge({}), "batch-zero", ("0", "0"))
    fee = automatic_fee(result)
    assert Decimal(fee["cost_rmb"]) == Decimal(fee["mold_import_default_rmb"]) == 0
    assert fee["import_batch_id"] == "batch-zero"
    assert calculate(result)["totals"]["mold_total_rmb"] == "0.0000"


def mold_workbook(prices):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"])
    for index, price in enumerate(prices):
        sheet.append([f"M{index}", f"虚构模具{index}", "ABS", 20, index + 2, price, "4A", 3000])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_api_mold_fee_import_edit_reimport_and_source_delete_lifecycle(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "mold-fee-owner", "admin", "*", "*")
        quote = create(client, suffix="MOLD-FEE")
        quote_id = quote["id"]
        base = f"/api/internal-quotes/{quote_id}"
        draft = {"production_mold_costs": [{"item": "模具费用", "cost_rmb": 0},
            {"item": "超声模费用", "cost_rmb": 50}, {"item": "喷油模具", "cost_rmb": 60},
            {"item": "其他费用", "cost_rmb": 10}]}

        def import_file(prices, name, payload):
            current = detail(client, quote_id)[1]["engineering"]
            response = client.post(base + "/imports/mold/preview", data={
                "draft_payload": json.dumps(payload, ensure_ascii=False), "draft_revision": current["revision"],
            }, files={"file": (name, mold_workbook(prices), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            assert response.status_code == 201, response.text
            preview = response.json()
            confirmed = client.post(base + f"/imports/{preview['batch_id']}/confirm", json={"revision": current["revision"]})
            assert confirmed.status_code == 200, confirmed.text
            source = next(row for row in client.get(base + "/attachments?department=engineering").json() if row["import_batch_id"] == preview["batch_id"])
            return confirmed.json()["section"], source

        saved, source_a = import_file([100, 200], "模拟工模A.xlsx", draft)
        assert saved["calculation"]["totals"]["mold_total_rmb"] == "420.0000"
        edited = deepcopy(saved["payload"])
        automatic_fee(edited)["cost_rmb"] = 350
        response = client.put(base + "/sections/engineering", json={"revision": saved["revision"], "payload": edited})
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed["calculation"]["totals"]["mold_total_rmb"] == "470.0000"
        assert automatic_fee(detail(client, quote_id)[1]["engineering"]["payload"])["cost_rmb"] == 350
        current, source_b = import_file([400], "模拟工模B.xlsx", changed["payload"])
        assert len(current["payload"]["production_mold_costs"]) == 4
        assert current["calculation"]["totals"]["mold_total_rmb"] == "520.0000"
        deleted = client.delete(base + f"/attachments/{source_a['id']}", params={"revision": current["revision"]})
        assert deleted.status_code == 204, deleted.text
        after_a = detail(client, quote_id)[1]["engineering"]
        assert after_a["payload"] == current["payload"]
        stale = client.delete(base + f"/attachments/{source_b['id']}", params={"revision": current["revision"]})
        assert stale.status_code == 409, stale.text
        assert detail(client, quote_id)[1]["engineering"] == after_a
        deleted = client.delete(base + f"/attachments/{source_b['id']}", params={"revision": after_a["revision"]})
        assert deleted.status_code == 204, deleted.text
        cleared = detail(client, quote_id)[1]["engineering"]
        assert cleared["payload"]["molds"] == []
        assert cleared["calculation"]["totals"]["mold_total_rmb"] == "120.0000"
        assert all("mold_import_default_rmb" not in row and "import_batch_id" not in row for row in cleared["payload"]["production_mold_costs"])
        current, source_c = import_file([500], "模拟工模C.xlsx", cleared["payload"])
        edited = deepcopy(current["payload"])
        automatic_fee(edited)["cost_rmb"] = 600
        response = client.put(base + "/sections/engineering", json={"revision": current["revision"], "payload": edited})
        assert response.status_code == 200, response.text
        deleted = client.delete(base + f"/attachments/{source_c['id']}", params={"revision": response.json()["revision"]})
        assert deleted.status_code == 204, deleted.text
        manual = detail(client, quote_id)[1]["engineering"]
        assert manual["calculation"]["totals"]["mold_total_rmb"] == "720.0000"
        assert all("mold_import_default_rmb" not in row and "import_batch_id" not in row for row in manual["payload"]["production_mold_costs"])
