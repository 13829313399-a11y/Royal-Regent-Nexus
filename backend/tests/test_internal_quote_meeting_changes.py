import base64
import json
from io import BytesIO

from openpyxl import load_workbook
from PIL import Image

from test_internal_quote_api import make_client, login, create_payload, logout
from test_internal_quote_alternatives import create, fill, fork
from test_internal_quote_import import workbook_bytes


def section(client, root, code="engineering"):
    return next(s for s in client.get(root).json()["sections"] if s["department"] == code)


def preview(client, root, kind, name, item, price, replacement=None):
    content = workbook_bytes([["零件名称", "规格", "用量", "单价RMB", "备注"], [item, "规格A", 2, price, "来源"]])
    response = client.post(root + f"/imports/{kind}/preview", data={"replace_attachment_id": replacement} if replacement else {},
                           files={"file": (name, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, root, draft, **overrides):
    return client.post(root + f"/imports/{draft['batch_id']}/confirm", json={"revision": draft["target_revision"], **overrides})


def test_auxiliary_template_and_atomic_selected_source_replacement(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "meeting-owner", "admin", "*", "*")
        quote = fill(client, create(client, "REPLACE")); root = f"/api/internal-quotes/{quote['id']}"
        hardware = client.get(root + "/imports/hardware/template")
        auxiliary = client.get(root + "/imports/auxiliary/template")
        assert auxiliary.status_code == 200 and auxiliary.content == hardware.content
        first = preview(client, root, "auxiliary", "旧辅料.xlsx", "旧胶水", 3)
        assert first["payload_fragment"]["materials"][0]["category"] == "auxiliary"
        assert confirm(client, root, first).status_code == 200
        current = section(client, root)
        current["payload"]["materials"].append({"item": "手动辅料", "category": "auxiliary", "quantity": 1, "unit_price_rmb": 2})
        assert client.put(root + "/sections/engineering", json={"revision": current["revision"], "payload": current["payload"]}).status_code == 200
        original = next(a for a in client.get(root + "/attachments").json() if a["is_import_source"])
        invalid = section(client, root)
        invalid["payload"]["molds"] = [{"item": "无效模具", "cost_rmb": -1}]
        content = workbook_bytes([["零件名称", "规格", "用量", "单价RMB"], ["不能写入", "", 1, 1]])
        late_failure = client.post(root + "/imports/auxiliary/preview", data={"replace_attachment_id": original["id"],
            "draft_revision": invalid["revision"], "draft_payload": json.dumps(invalid["payload"])},
            files={"file": ("无效更换.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert late_failure.status_code == 201, late_failure.text
        assert confirm(client, root, late_failure.json()).status_code == 400
        assert [a["id"] for a in client.get(root + "/attachments").json()] == [original["id"]]
        assert section(client, root)["payload"]["molds"] == []
        draft = preview(client, root, "auxiliary", "新辅料.xlsx", "新胶水", 1, original["id"])
        assert draft["diff_summary"]["replaced_file_name"] == "旧辅料.xlsx"
        assert any(r["item"] == "旧胶水" for r in section(client, root)["payload"]["materials"])
        # Wrong revision must leave both old rows and source bytes untouched.
        assert confirm(client, root, draft, revision=draft["target_revision"] + 1).status_code == 409
        assert any(a["id"] == original["id"] for a in client.get(root + "/attachments").json())
        response = confirm(client, root, draft)
        assert response.status_code == 200, response.text
        rows = section(client, root)["payload"]["materials"]
        assert {r["item"] for r in rows} == {"螺丝", "手动辅料", "新胶水"}
        assert next(r for r in rows if r["item"] == "新胶水")["unit_price_rmb"] == "1.0000"
        attachments = client.get(root + "/attachments").json()
        assert all(a["id"] != original["id"] for a in attachments)
        assert [a["file_name"] for a in attachments if a["is_import_source"]] == ["新辅料.xlsx"]
        assert confirm(client, root, draft).status_code == 409
        layout = client.get(root + "/output-layout").json()
        assert layout["import_sources"][0]["file_name"] == "新辅料.xlsx"
        assert layout["quote_price_hkd"] is not None


def png():
    buffer = BytesIO(); Image.new("RGB", (80, 40), "green").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_price_notes_preview_save_export_copy_and_image_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "note-owner", "admin", "*", "*")
        quote = fill(client, create(client, "NOTES")); root = f"/api/internal-quotes/{quote['id']}"
        layout = client.get(root + "/output-layout").json()
        field = next(g for g in layout["groups"] if g["label"] == "螺丝")["fields"][1]
        body = {"base_token": layout["base_token"], "edits": [{"field_id": field["id"], "value": "0.3",
                "annotation": {"text": "供应商电话确认降价，报价单待更新", "new_images": [png()]}}]}
        response = client.post(root + "/output-layout/preview", json=body)
        assert response.status_code == 200, response.text
        assert client.get(root + "/attachments").json() == []
        assert "price_annotations" not in section(client, root)["payload"]["materials"][0]
        assert client.put(root + "/output-layout", json=body).status_code == 200
        row = section(client, root)["payload"]["materials"][0]
        note = row["price_annotations"]["unit_price_rmb"]
        assert len(note["image_attachment_ids"]) == 1 and note["price_at_note"] == "0.3"
        import app.services.internal_quote_output_layout as layout_service
        with monkeypatch.context() as restricted:
            restricted.setattr(layout_service, "_can_access_attachment_department", lambda *args: False)
            hidden = client.get(root + "/output-layout").json()
            assert not next(s for s in hidden["sheets"] if s["name"] == "调价说明").get("images")
        current = client.get(root).json()
        cloned = fork(client, current)
        cloned_note = next(s for s in cloned["sections"] if s["department"] == "engineering")["payload"]["materials"][0]["price_annotations"]["unit_price_rmb"]
        assert cloned_note["image_attachment_ids"] != note["image_attachment_ids"]
        # Foreign-quote image references must be rejected, even from an admin.
        fresh = client.get(root + "/output-layout").json()
        bad = {"base_token": fresh["base_token"], "edits": [{"field_id": field["id"], "value": "0.2",
               "annotation": {"text": "错误截图", "image_attachment_ids": cloned_note["image_attachment_ids"]}}]}
        assert client.put(root + "/output-layout", json=bad).status_code == 400
        assert section(client, root)["payload"]["materials"][0]["unit_price_rmb"] == "0.3"
        # Frozen output must retain the actual comments and embedded screenshots.
        current = client.get(root).json()
        issued = client.post(root + "/direct-issue", json={"revision": current["header_revision"]})
        assert issued.status_code == 200, issued.text
        content = client.get(root + f"/exports/{issued.json()['id']}/download").content
        book = load_workbook(BytesIO(content))
        assert book["调价说明"].sheet_state == "visible" and len(book["调价说明"]._images) == 1
        assert book["调价说明"]["A2"].value == "螺丝"
        comments = [c.comment.text for row in book["报价明细"] for c in row if c.comment]
        assert any("供应商电话确认降价" in text for text in comments)
        book.close()
        assert client.put(root + "/output-layout", json=body).status_code == 409


def test_engineering_export_individual_electronics_and_revision_guard(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "selection-owner", "admin", "*", "*")
        payload = create_payload(suffix="SELECT", participating_sections=["engineering", "assembly", "sales", "electronic"])
        payload["workflow_mode"] = "direct_output"
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        quote = fill(client, created.json()); root = f"/api/internal-quotes/{quote['id']}"
        electronic = section(client, root, "electronic")
        response = client.put(root + "/sections/electronic", json={"revision": electronic["revision"], "payload": {
            "quote_mode": "quick", "quick_quotes": [{"item": "电子A", "unit_price_rmb": 1}, {"item": "电子B", "unit_price_rmb": 2}]}})
        assert response.status_code == 200, response.text
        assert response.json()["calculation_status"] == "valid", response.text
        current = client.get(root).json()
        issued = client.post(root + "/direct-issue", json={"revision": current["header_revision"]})
        assert issued.status_code == 200, issued.text
        options = client.get(root + "/engineering-data/options").json()
        before_export = client.get(root + "/summary").json()["factory_price_hkd"]
        assert [item["name"] for item in options["items"]] == ["电子A", "电子B"]
        selection = {k: options[k] for k in ("header_revision", "electronic_revision")}
        bad = client.post(root + "/engineering-data/export", json={**selection, "header_revision": selection["header_revision"] - 1, "electronic_selection": ["1"]})
        assert bad.status_code == 409
        assert client.post(root + "/engineering-data/export", json={**selection, "electronic_selection": ["9"]}).status_code == 400
        for ids in (["1"], [], ["0", "1"]):
            response = client.post(root + "/engineering-data/export", json={**selection, "electronic_selection": ids})
            assert response.status_code == 200, response.text
            book = load_workbook(BytesIO(response.content))
            strings = {c.value for row in book["外购清单"] for c in row if isinstance(c.value, str)}
            assert ("电子A" in strings) == ("0" in ids)
            assert ("电子B" in strings) == ("1" in ids)
            assert "螺丝" in strings
            book.close()
        after = client.get(root).json()
        assert client.get(root + "/summary").json()["factory_price_hkd"] == before_export
        assert section(client, root, "electronic")["revision"] == options["electronic_revision"]
