"""An import may preview a local draft and atomically merge only its owned region."""
from copy import deepcopy
from io import BytesIO
import json

from openpyxl import Workbook
import pytest

from test_internal_quote_api import login, make_client
from test_internal_quote_alternatives import create, fill
from test_internal_quote_incomplete_drafts import detail


def mold_file():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数"])
    sheet.append(["M-NEW", "模拟新模具", "ABS", 20, 1, 1000, "4A", 3000])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def preview(client, quote_id, draft, revision):
    return client.post(f"/api/internal-quotes/{quote_id}/imports/mold/preview", data={
        "draft_payload": json.dumps(draft, ensure_ascii=False), "draft_revision": str(revision),
    }, files={"file": ("虚构模具.xlsx", mold_file(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


@pytest.mark.parametrize("invalid_auxiliary", [False, True])
def test_draft_import_preview_is_readonly_and_confirmation_keeps_other_inputs(monkeypatch, invalid_auxiliary):
    with make_client(monkeypatch) as client:
        login(client, "draft-import-owner", "admin", "*", "*")
        quote = fill(client, create(client, suffix="DRAFT-IMPORT"))
        quote_id = quote["id"]
        before, sections = detail(client, quote_id)
        engineering = sections["engineering"]
        draft = deepcopy(engineering["payload"])
        draft["materials"] = [
            {"item": "本地未保存五金", "category": "hardware", "quantity": 3, "unit_price_rmb": 0.2},
            {"item": "本地未保存辅助", "category": "auxiliary", "quantity": 2,
             "unit_price_rmb": "待补" if invalid_auxiliary else 0.3},
        ]
        draft["molds"] = [{"mold_no": "M-OLD", "item": "应被替换的草稿模具", "quantity": 1, "cost_rmb": 2000}]
        draft["remark"] = "保留未保存的工程备注"
        response = preview(client, quote_id, draft, engineering["revision"])
        assert response.status_code == 201, response.text
        batch = response.json()
        current, current_sections = detail(client, quote_id)
        assert current_sections["engineering"] == engineering
        assert current["header_revision"] == before["header_revision"]
        assert batch["diff_summary"]["existing_rows"] == 1
        assert batch["payload_fragment"]["molds"][0]["mold_no"] == "M-NEW"
        confirmed = client.post(f"/api/internal-quotes/{quote_id}/imports/{batch['batch_id']}/confirm", json={
            "revision": engineering["revision"], "mode": "replace"})
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()
        saved = result["section"]
        assert saved["revision"] == engineering["revision"] + 1
        assert saved["payload"]["materials"] == draft["materials"]
        assert saved["payload"]["remark"] == draft["remark"]
        assert [row["mold_no"] for row in saved["payload"]["molds"]] == ["M-NEW"]
        assert result["batch"]["status"] == "confirmed"
        assert saved["calculation_status"] == ("blocked" if invalid_auxiliary else "valid")
        if invalid_auxiliary:
            assert saved["calculation"]["totals"] == {}
            assert saved["calculation"]["line_breakdown"] == []
            assert saved["calculation"]["warnings"][0]["code"] == "invalid_input"
            current, _ = detail(client, quote_id)
            issued = client.post(f"/api/internal-quotes/{quote_id}/direct-issue", json={"revision": current["header_revision"]})
            assert issued.status_code == 409, issued.text
            assert "工程" in issued.text
        else:
            assert saved["calculation"]["totals"]["mold_total_rmb"] == "1000.0000"
        assert detail(client, quote_id)[1]["engineering"] == saved
        repeated = client.post(f"/api/internal-quotes/{quote_id}/imports/{batch['batch_id']}/confirm", json={"revision": saved["revision"]})
        assert repeated.status_code == 409, repeated.text
        assert detail(client, quote_id)[1]["engineering"] == saved


def test_draft_import_revision_is_bound_at_preview_and_cannot_be_rebased_at_confirm(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "draft-import-lock-owner", "admin", "*", "*")
        quote = fill(client, create(client, suffix="DRAFT-IMPORT-LOCK"))
        quote_id = quote["id"]
        _, sections = detail(client, quote_id)
        engineering = sections["engineering"]
        draft = deepcopy(engineering["payload"])
        draft["materials"][0]["item"] = "旧页面本地未保存五金"
        stale = preview(client, quote_id, draft, engineering["revision"] - 1)
        assert stale.status_code == 409, stale.text
        assert "current_revision" in stale.text
        assert detail(client, quote_id)[1]["engineering"] == engineering
        response = preview(client, quote_id, draft, engineering["revision"])
        assert response.status_code == 201, response.text
        batch = response.json()
        other_edit = deepcopy(engineering["payload"])
        other_edit["materials"][0]["item"] = "其他页面刚保存的五金"
        changed = client.put(f"/api/internal-quotes/{quote_id}/sections/engineering", json={
            "revision": engineering["revision"], "payload": other_edit})
        assert changed.status_code == 200, changed.text
        current = changed.json()
        attachments = client.get(f"/api/internal-quotes/{quote_id}/attachments").json()
        for revision in (engineering["revision"], current["revision"]):
            refused = client.post(f"/api/internal-quotes/{quote_id}/imports/{batch['batch_id']}/confirm", json={"revision": revision})
            assert refused.status_code == 409, refused.text
            assert detail(client, quote_id)[1]["engineering"] == current
        assert client.get(f"/api/internal-quotes/{quote_id}/attachments").json() == attachments
