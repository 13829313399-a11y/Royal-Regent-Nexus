import io
import json

from PIL import Image
from pypdf import PdfReader

from test_molding_sample_api import make_client
from test_carton_supplier_mark_check import prepare
from test_carton_mark_flexible import table_workbook,table_plan
from test_carton_mark_workbench import multi_sheet_notes_workbook
from test_carton_supplier_portal import revoke_supplier_permission


def test_read_review_render_rechecks_source_permission_and_does_not_persist_or_recall_provider(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        from app.services import carton_mark_flexible as flow
        from app.services import carton_mark_workbench as workbench
        from app.services import carton_supplier_mark_ai as ai
        from app.services import carton_mark_ai_pilot as pilot
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset,CartonMarkTemplate
        from sqlalchemy import select,func
        content=table_workbook();source=flow.read('source.xlsx',content);calls=[]
        monkeypatch.setattr(ai,'configuration',lambda:({},pilot.load_template(),b'reference','signature'))
        monkeypatch.setattr(workbench.carton_mark_images,'collect',lambda *a,**k:([],[],[]))
        image=io.BytesIO();Image.new('RGB',(200,100),'black').save(image,format='PNG')
        monkeypatch.setattr(flow,'crop_reference',lambda *a,**k:image.getvalue())
        def provider(*a,**k):calls.append(a);return json.dumps(table_plan(source)),{}
        monkeypatch.setattr(pilot,'request_plan',provider)
        files={'excel':('source.xlsx',content)};base='/api/carton-supplier/carton-mark/'
        inspection=client.post(base+'inspect-pdf-draft',files=files)
        assert inspection.status_code==200 and len(inspection.json()['worksheets'])==2
        assert not calls
        assert client.post(base+'read-pdf-draft',files=files).status_code==422
        assert client.post(base+'read-pdf-draft',data={'ai_consent':'true','worksheets_json':'["missing"]'},files=files).status_code==422
        response=client.post(base+'read-pdf-draft',data={'ai_consent':'true'},files=files)
        assert response.status_code==200,response.text
        assert response.headers['cache-control']=='private, no-store'
        read=response.json();assert read['mode']=='ai' and len(calls)==1
        data=dict(review_payload=read['payload'],review_signature=read['signature'])
        rendered=client.post(base+'render-reviewed-draft',data=data,files=files)
        assert rendered.status_code==200,rendered.text
        pages=PdfReader(io.BytesIO(rendered.content)).pages
        assert 'PO-SYNTHETIC-A' in pages[0].extract_text() and 'PO-SYNTHETIC-B' in pages[1].extract_text()
        assert client.post(base+'render-reviewed-draft',data={**data,'review_signature':'bad'},files=files).status_code==409
        assert client.post(base+'render-reviewed-draft',data=data,files={'excel':('source.xlsx',content+b'changed')}).status_code==409
        again=client.post(base+'render-reviewed-draft',data={**data,'paper':'A3','orientation':'portrait'},files=files)
        assert again.status_code==200 and len(calls)==1
        clean=client.post(base+'render-reviewed-draft',data={**data,'include_sources':'false'},files=files)
        assert clean.status_code==200 and len(calls)==1
        clean_pages=PdfReader(io.BytesIO(clean.content)).pages
        assert len(clean_pages)==2 and '制版备注与来源' not in '\n'.join(p.extract_text() for p in clean_pages)
        revoke_supplier_permission('carton_supplier:edit')
        assert client.post(base+'render-reviewed-draft',data=data,files=files).status_code==403
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset))==1
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate))==0


def test_multi_sheet_note_review_transport_preserves_all_sources_and_reuses_one_read(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        from app.services import carton_mark_workbench as workbench,carton_supplier_mark_ai as ai,carton_mark_ai_pilot as pilot
        monkeypatch.setattr(ai,'configuration',lambda:({},pilot.load_template(),b'reference','signature'))
        monkeypatch.setattr(workbench.carton_mark_images,'collect',lambda *a,**k:([],[],[]))
        calls=[]
        def provider(*a,**k):calls.append(a);return '{}',{}
        monkeypatch.setattr(pilot,'request_plan',provider)
        files={'excel':('multiple-ports.xlsx',multi_sheet_notes_workbook())};base='/api/carton-supplier/carton-mark/'
        response=client.post(base+'read-pdf-draft',data={'ai_consent':'true'},files=files)
        assert response.status_code==200,response.text
        read=response.json();assert len(read['notes'])==176 and read['mode']=='needs_mapping'
        reviewed=json.dumps([n['id'] for n in read['notes']],indent=40)
        assert len(reviewed)>5000  # The previous form-size limit must not reject the review.
        data=dict(review_payload=read['payload'],review_signature=read['signature'],reviewed_notes_json=reviewed)
        for _ in range(2):
            result=client.post(base+'render-reviewed-draft',data=data,files=files)
            assert result.status_code==200,result.text
            text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(result.content)).pages)
            assert all(n['location'] in text for n in read['notes'])
            assert text.count('页面已明确核对')==176
        assert len(calls)==1
