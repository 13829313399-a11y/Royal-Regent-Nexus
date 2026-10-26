import base64
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest
from PIL import Image
from assistant_ocr_fixtures import image_bytes, scanned_pdf
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate
from test_assistant_v3_office_api import ready


@pytest.mark.parametrize('extension,factory', [('.png',image_bytes),('.pdf',scanned_pdf)])
def test_real_bounded_ocr_without_network(tmp_path, extension, factory):
    worker=Path(__file__).resolve().parents[1]/'app/services/assistant/document_worker.py'
    wrapper=tmp_path/'offline_worker.py'
    wrapper.write_text("import sys,runpy\ndef deny(event,args):\n if event in ('socket.connect','socket.getaddrinfo'): raise RuntimeError('network forbidden')\nsys.addaudithook(deny)\nsys.path.insert(0,sys.argv[1])\nsys.argv=sys.argv[2:]\nrunpy.run_path(sys.argv[0],run_name='__main__')\n")
    source=tmp_path/('scan'+extension); source.write_bytes(factory())
    target=tmp_path/'result.json'
    with (tmp_path/'stderr.log').open('w') as log:
        child=subprocess.Popen([sys.executable,str(wrapper),str(worker.parent),str(worker),str(source),str(target),extension,'100','200000','20','512'],stdin=subprocess.PIPE,stdout=log,stderr=log)
        try:
            assert child.wait(timeout=25)==0
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=3)
            child.stdin.close()
    result=json.loads(target.read_text(encoding='utf-8'))
    assert not result.get('error'), result
    page=2 if extension=='.pdf' else 1
    parts=[p for p in result['segments'] if p['locator'].get('page')==page]
    assert parts and any('Quantity' in p['text'] for p in parts)
    assert all(p['metadata']['uncertain'] for p in parts)
    assert all(p['metadata']['engine'].startswith('RapidOCR/') for p in parts)
    preview=Image.open(BytesIO(base64.b64decode(result['previews'][str(page)])))
    assert preview.size==(1200,800)
    for part in parts:
        box=part['locator']['bbox']
        assert 0<=box['x']<1 and 0<=box['y']<1 and box['width']>0 and box['height']>0
        assert box['x']+box['width']<=1 and box['y']+box['height']<=1
        assert 0<=part['metadata']['signal_score']<=1
    number=next(p for p in parts if 'Quantity' in p['text'])
    assert .12 < number['locator']['bbox']['y'] < .5
    assert '?' in number['text'], 'Ambiguous source text must not become a confirmed 400'
    assert 'ambiguous_characters' in number['metadata']['uncertainty_reasons']


def test_image_rejection_before_engine_and_missing_local_models(monkeypatch):
    from app.services.assistant import document_ocr as ocr
    with pytest.raises(ocr.OcrError,match='image_signature'):
        ocr.image_document(b'not an image','.png')
    with pytest.raises(ocr.OcrError,match='image_signature'):
        ocr.image_document(image_bytes('JPEG'),'.png')
    monkeypatch.setattr(ocr,'MAX_IMAGE_PIXELS',10)
    with pytest.raises(ocr.OcrError,match='image_pixel_limit'):
        ocr.image_document(image_bytes(),'.png')
    monkeypatch.setattr(ocr,'find_spec',lambda _:None)
    with pytest.raises(ocr.OcrError,match='ocr_unavailable'):
        ocr.LocalOcr({}).initialize()


def test_image_orientation_and_transparency_match_visible_paper():
    from app.services.assistant.document_ocr import image_document
    source=Image.new('RGBA',(30,20),(0,0,0,0)); source.putpixel((10,10),(0,0,0,255))
    stream=BytesIO(); source.save(stream,format='PNG')
    picture=image_document(stream.getvalue(),'.png')
    assert picture.getpixel((0,0))==(255,255,255) and picture.getpixel((10,10))==(0,0,0)
    source=Image.new('RGB',(30,20),'white'); exif=Image.Exif(); exif[274]=6
    stream=BytesIO();source.save(stream,format='JPEG',exif=exif)
    assert image_document(stream.getvalue(),'.jpg').size==(20,30)


def test_ocr_caps_and_low_signal_metadata_are_explicit(monkeypatch):
    from app.services.assistant import document_ocr as ocr
    from types import SimpleNamespace
    reader=ocr.LocalOcr({}); reader.identity='synthetic-contract-test'
    reader.engine=lambda _:SimpleNamespace(txts=['4?0'],scores=[.42],boxes=[[[1,1],[9,1],[9,9],[1,9]]])
    segments=[]
    reader.recognize(Image.new('RGB',(10,10),'white'),2,lambda t,l,m:segments.append((t,l,m)))
    assert segments[0][2]['uncertain'] and 'low_signal' in segments[0][2]['uncertainty_reasons']
    reader.pages=ocr.MAX_OCR_PAGES
    with pytest.raises(ocr.OcrError,match='ocr_page_limit'):
        reader.recognize(Image.new('RGB',(10,10),'white'),21,lambda *args:None)
    reader.pages=0
    monkeypatch.setattr(ocr,'MAX_PREVIEW_BYTES',1)
    with pytest.raises(ocr.OcrError,match='ocr_preview_limit'):
        reader.recognize(Image.new('RGB',(10,10),'white'),1,lambda *args:None)


def test_ocr_private_preview_export_and_delete(env):
    client,dbm,calls,_=env
    migrate(dbm); sid=session(client)
    result=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('scan.pdf',scanned_pdf(),'application/pdf')})
    assert result.status_code==200,result.text
    ident=result.json()['id']; info=ready(client,ident)
    assert info['parse_status']=='ready',info
    path=f'/api/assistant/files/{ident}/pages/2'
    response=client.get(path)
    assert response.status_code==200 and response.content.startswith(b'\x89PNG')
    assert response.headers['cache-control']=='private, no-store'
    assert client.get(f'/api/assistant/files/{ident}/pages/501').status_code==404
    client.cookies.set('rr_session','bob')
    assert client.get(path).status_code==404
    client.cookies.set('rr_session','alice')
    assert not calls
    run=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,document_ids=[ident],intent='analyze_files') | {'text':'读取第2页，保留模糊字符并说明未知项。'})
    assert 'event: run.completed' in run.text,run.text
    upstream=json.dumps(calls[-1],ensure_ascii=False)
    assert 'signal_score不是正确率' in upstream and 'ambiguous_characters' in upstream
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    evidence=next(p for p in answer['content_parts'] if p['type']=='evidence')
    assert any(s.get('ocr',{}).get('uncertain') for s in evidence['sources'])
    exported=client.get(f"/api/assistant/runs/{answer['run_id']}/export").text
    assert '识别评分不是正确率' in exported
    from app.services.assistant import files
    with dbm.SessionLocal() as db:
        row=db.get(files.Document,ident); preview=files.preview_path(row.storage_key,2)
    assert preview.is_file()
    assert client.delete(f'/api/assistant/files/{ident}').status_code==204
    assert client.get(path).status_code==410 and not preview.exists()


def test_failed_image_releases_queue_and_preserves_next_parse(env):
    client,dbm,calls,_=env
    migrate(dbm);sid=session(client);url=f'/api/assistant/sessions/{sid}/files'
    assert client.post(url,files={'file':('x.png',image_bytes(),'text/plain')}).status_code==422
    result=client.post(url,files={'file':('x.png',b'not png','image/png')})
    info=ready(client,result.json()['id'])
    assert info['parse_status']=='failed' and info['error_code']=='image_signature'
    good=client.post(url,files={'file':('x.txt',b'next file')})
    assert ready(client,good.json()['id'])['parse_status']=='ready'
    assert not calls
