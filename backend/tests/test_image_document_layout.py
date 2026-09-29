import re
from pathlib import Path

import numpy as np
import pdfplumber
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.document_tools.image_translation import append_preserved_pdf
from app.services.document_tools.image_text_regions import native_regions
from app.services.document_tools.image_terminology import translate_image_texts
from app.services.document_tools.document_ir import ToolError


def native_pdf(path):
    writer=PdfWriter();page=writer.add_blank_page(400,200)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    data=DecodedStreamObject();data.set_data(b'BT /F1 14 Tf 20 130 Td (Quantity 00123 Length 0.05mm) Tj ET BT /F1 14 Tf 20 40 Td (________________) Tj ET 10 50 m 390 50 l S')
    page[NameObject('/Contents')]=writer._add_object(data);writer.write(path)


def test_native_word_boundaries_separate_numbers_before_translation(tmp_path):
    source=tmp_path/'native.pdf';native_pdf(source)
    with pdfplumber.open(source) as pdf:
        regions=native_regions(pdf.pages[0],2)
    assert [r['sourceText'] for r in regions if not r['protected']]==['Quantity','Length']
    assert [r['sourceText'] for r in regions if r['protected']]==['00123','0.05mm']
    for r in regions:
        assert 0<=r['box']['x']<800 and 0<=r['box']['y']<400


def test_pdf_overlay_preserves_original_objects_digits_and_visuals(tmp_path):
    import pypdfium2 as pdfium
    source=tmp_path/'native.pdf';native_pdf(source)
    with pdfium.PdfDocument(source) as doc:
        bitmap=doc[0].render(scale=2); original=bitmap.to_pil().convert('RGB');bitmap.close()
    result=original.copy();ImageDraw.Draw(result).rectangle((40,110,140,140),fill='red')
    before=tmp_path/'before.png';after=tmp_path/'after.png';original.save(before);result.save(after)
    writer=PdfWriter();append_preserved_pdf(writer,PdfReader(source).pages[0],before,after,400,200)
    target=tmp_path/'result.pdf';writer.write(target)
    parsed=PdfReader(target)
    assert parsed.pages[0].extract_text().strip()==PdfReader(source).pages[0].extract_text().strip()
    assert b'10 50 m' in parsed.pages[0].get_contents().get_data()
    with pdfium.PdfDocument(target) as doc:
        bitmap=doc[0].render(scale=2); actual=np.asarray(bitmap.to_pil().convert('RGB'));bitmap.close()
    expected=np.asarray(result)
    assert np.max(np.abs(actual.astype(int)-expected.astype(int)))<=1


def test_bad_translation_is_isolated_without_changing_numbers():
    def translate(texts,direction):
        if 'unknown' in texts: raise ToolError('TRANSLATION_NUMBERS_CHANGED','bad output')
        return ['安全文字']*len(texts)
    assert translate_image_texts(['Hair','good','unknown'],'en_to_zh',translate)==['头发','安全文字','unknown']


def test_online_provider_errors_are_not_silently_hidden():
    import pytest
    def translate(*args):raise ToolError('TRANSLATION_NETWORK','unavailable')
    with pytest.raises(ToolError,match='unavailable'):
        translate_image_texts(['unknown'],'en_to_zh',translate)


def test_translation_wait_does_not_block_child_cancellation(tmp_path,monkeypatch):
    import threading,time,subprocess,pytest
    from app.core.config import settings
    from app.services.document_tools import image_translation as engine
    worker=tmp_path/'slow.mjs'
    worker.write_text("process.stdout.write(JSON.stringify({event:'translate',texts:['pending']})+'\\n');setInterval(()=>{},1000)",encoding='utf-8')
    monkeypatch.setattr(settings,'image_translation_runner',str(worker))
    started=threading.Event(); release=threading.Event(); finished=threading.Event(); processes=[]
    def translator(*args):
        started.set();release.wait(3);finished.set();return ['译文']
    monkeypatch.setattr(engine,'make_translator',lambda *args:translator)
    original=subprocess.Popen
    def spawn(*args,**kwargs):
        p=original(*args,**kwargs);processes.append(p);return p
    monkeypatch.setattr(engine.subprocess,'Popen',spawn)
    try:
        before=time.monotonic()
        with pytest.raises(ToolError) as error:
            engine.run_node([],{},tmp_path,lambda *a:None,started.is_set)
        assert error.value.code=='CANCELLED'
        assert time.monotonic()-before<2 and not finished.is_set()
        assert processes[0].poll() is not None
    finally:
        release.set();finished.wait(3)
