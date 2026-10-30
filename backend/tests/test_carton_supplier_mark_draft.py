import io
import json

import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from test_molding_sample_api import make_client
from test_carton_supplier_mark_check import prepare, SCOPE
from test_carton_supplier_portal import revoke_supplier_permission, restore_supplier_permission
from test_carton_mark_api import _pdf_bytes, _workbook_bytes

BASE = "/api/carton-supplier/carton-mark/generate-pdf-draft"


def test_draft_upload_needs_neither_factory_nor_order_but_rechecks_access_and_never_saves(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        from app.services import carton_supplier_mark_draft as draft
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from sqlalchemy import select, func
        calls = []
        def render(original, engine):
            calls.append((original, engine))
            assert original["unbound"] and not original["contract_no"] and not original["order_fields"]
            return _pdf_bytes(), 1, ["仅供审阅"]
        monkeypatch.setattr(draft, "prepare", render)
        monkeypatch.setattr(draft.ai, "status", lambda: {"available": True})
        assert client.get("/api/carton-supplier/carton-mark/pdf-draft-status").json()["available"]
        files = {"excel": ("original.xlsx", _workbook_bytes())}
        response = client.post(BASE, files=files)
        assert response.status_code == 200, response.text
        assert response.content == _pdf_bytes() and response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-carton-pdf-pages"] == "1"
        assert calls[0][1] == "excel_original"
        assert client.post(BASE, data={"factory_id": "huakang-b"}, files=files).status_code == 403
        assert client.post(BASE, data={"engine": "deepseek_zumiez"}, files=files).status_code == 422
        assert client.post(BASE, data={"supplements_json": "[]"}, files=files).status_code == 422
        assert client.post(BASE, data={"excel_asset_id": "excel-source"}, files=files).status_code == 422
        assert len(calls) == 1
        def revoked(original, engine):
            revoke_supplier_permission("carton_supplier:edit")
            return render(original, engine)
        monkeypatch.setattr(draft, "prepare", revoked)
        assert client.post(BASE, files=files).status_code == 403
        assert client.get("/api/carton-supplier/carton-mark/pdf-draft-status").status_code == 403
        restore_supplier_permission("carton_supplier:edit")
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset)) == 1
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate)) == 0


def test_stored_draft_rechecks_factory_visibility_and_source_revision_without_order(monkeypatch):
    with make_client(monkeypatch) as client:
        _, payload, excel = prepare(client)
        from app.services import carton_supplier_mark_draft as draft
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        calls = []
        def render(original, engine):
            calls.append(original)
            assert original["excel_bytes"] == excel
            return _pdf_bytes(), 1, []
        monkeypatch.setattr(draft, "prepare", render)
        body = dict(**SCOPE, excel_asset_id=payload["excel_asset_id"], expected_revision=payload["expected_revision"])
        response = client.post(BASE, data=body)
        assert response.status_code == 200, response.text
        assert client.post(BASE, data={**body, "expected_revision": 99}).status_code == 409
        assert client.post(BASE, data={**body, "excel_asset_id": "foreign"}).status_code == 404
        assert client.post(BASE, data={**body, "factory_id": "huakang-b"}).status_code == 403
        assert len(calls) == 1
        def changed(original, engine):
            with SessionLocal() as db:
                db.get(CartonMarkAsset, "excel-source").revision += 1
                db.commit()
            return render(original, engine)
        monkeypatch.setattr(draft, "prepare", changed)
        assert client.post(BASE, data=body).status_code == 409


def test_native_draft_uses_isolated_office_options_and_removes_working_files(monkeypatch, tmp_path):
    from app.services import carton_supplier_mark_draft as draft
    from app.services.document_tools import office_engine
    monkeypatch.setattr(draft, "root", lambda: tmp_path)
    inputs = []
    workbook_bytes = _workbook_bytes()
    def render(source, output, options, work, cancelled):
        inputs.append(source)
        assert options == {"secure_load": True, "recalculate": False}
        assert source.read_bytes() == workbook_bytes and not cancelled()
        output.write_bytes(_pdf_bytes())
    monkeypatch.setattr(office_engine, "render_office", render)
    original = draft.original("../../original.xlsx", workbook_bytes, "excel_original", False, {})
    content, pages, notes = draft.prepare(original, "excel_original")
    assert len(PdfReader(io.BytesIO(content)).pages) == pages == 1 and notes
    assert all(not source.exists() for source in inputs) and not list(tmp_path.iterdir())
    with pytest.raises(HTTPException):
        draft.original("original.xlsx", _workbook_bytes(), "excel_original", False, {"quantity": "1"})


def test_flexible_http_draft_preserves_all_notes_without_model_receipts_or_business_persistence(monkeypatch):
    from urllib.parse import unquote
    from PIL import Image
    from test_carton_mark_flexible import table_workbook, table_plan
    with make_client(monkeypatch) as client:
        prepare(client)
        from app.services import carton_mark_flexible as flexible
        from app.services import carton_supplier_mark_ai as ai
        from app.services import carton_mark_ai_pilot as pilot
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkTemplate
        from sqlalchemy import select, func
        content=table_workbook();source=flexible.read("unseen.xlsx",content)
        result=table_plan(source);result.pop("notes");result.pop("ignored_cells")
        calls=[]
        monkeypatch.setattr(ai,"configuration",lambda:({},pilot.load_template(),b"reference","private-signature"))
        image=io.BytesIO();Image.new("RGB",(200,100),"black").save(image,format="PNG")
        monkeypatch.setattr(flexible,"crop_reference",lambda *a,**k:image.getvalue())
        def request(entries,*args,**kwargs):
            calls.append(entries)
            return json.dumps(result),{}
        monkeypatch.setattr(pilot,"request_plan",request)
        response=client.post(BASE,data=dict(engine="deepseek_zumiez",ai_consent="true"),
                             files={"excel":("unseen.xlsx",content)})
        assert response.status_code==200,response.text
        assert len(calls)==1 and response.headers["cache-control"]=="private, no-store"
        pages=PdfReader(io.BytesIO(response.content)).pages
        assert "PO-SYNTHETIC-A" in pages[0].extract_text() and "PO-SYNTHETIC-B" not in pages[0].extract_text()
        assert "PO-SYNTHETIC-B" in pages[1].extract_text() and "PO-SYNTHETIC-A" not in pages[1].extract_text()
        text="\n".join(p.extract_text() for p in pages[2:])
        assert all(n.location in text for n in source["notes"])
        warnings=json.loads(unquote(response.headers["x-carton-pdf-warnings"]))
        assert any("备注回执" in w for w in warnings) and any("待核对" in w for w in warnings)
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset))==1
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate))==0


def test_unbound_deepseek_only_uses_current_excel_and_explicit_counts(monkeypatch):
    from app.services import carton_supplier_mark_ai as ai
    from app.services import carton_mark_ai_pilot as pilot
    from test_carton_supplier_mark_ai import original
    src = original(filled=True, unbound=True, contract_no="", item_no="", order_fields={})
    entries, native, identity, fallbacks = ai.current_evidence(src)
    assert not identity and not fallbacks and all(e.kind == "current_excel" for e in entries)
    fields = {key: None if key in {"contract", "item"} else
              dict(source_id=next(e.id for e in entries if native[key] in e.text), value=native[key])
              for key in pilot.FIELDS}
    raw = json.dumps(dict(template_id="zumiez-review-v1", layout_variant="reference", fields=fields))
    _, values, provenance = pilot.validate_plan(raw, entries, pilot.load_template(), native,
                                               identity={}, fallbacks={}, unbound=True)
    assert values["contract"] == values["item"] == "" and provenance["item"]["kind"] == "unbound"
    fields["item"] = dict(source_id=entries[0].id, value=entries[0].text)
    with pytest.raises(pilot.PilotError, match="必须留空"):
        pilot.validate_plan(json.dumps(dict(template_id="zumiez-review-v1", layout_variant="reference", fields=fields)),
                            entries, pilot.load_template(), native, identity={}, unbound=True)
    entries, _, _, fallbacks = ai.current_evidence(original(unbound=True, order_fields={},
        supplements={"quantity": "4 PCS", "carton_total": "5"}))
    assert fallbacks == dict(quantity="4 PCS", carton_total="5")
    assert all(e.kind != "issued_order" for e in entries)
