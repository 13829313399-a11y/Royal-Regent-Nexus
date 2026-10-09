import re
import math
from pathlib import Path

import numpy as np
import pdfplumber
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.document_tools.image_translation import append_preserved_pdf
from app.services.document_tools.image_text_regions import native_regions
from app.services.document_tools.image_terminology import translate_image_texts, image_translation_options
from app.services.document_tools.document_ir import ToolError


def native_pdf(path, text=b'Quantity 00123 Length 0.05mm'):
    writer=PdfWriter();page=writer.add_blank_page(400,200)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    data=DecodedStreamObject();data.set_data(b'BT /F1 14 Tf 20 130 Td ('+text+b') Tj ET BT /F1 14 Tf 20 40 Td (________________) Tj ET 10 50 m 390 50 l S')
    page[NameObject('/Contents')]=writer._add_object(data);writer.write(path)


def test_native_word_boundaries_separate_numbers_before_translation(tmp_path):
    source=tmp_path/'native.pdf';native_pdf(source)
    with pdfplumber.open(source) as pdf:
        regions=native_regions(pdf.pages[0],2)
    assert [r['sourceText'] for r in regions if not r['protected']]==['Quantity','Length']
    assert [r['sourceText'] for r in regions if r['protected']]==['00123','0.05mm']
    for r in regions:
        assert 0<=r['box']['x']<800 and 0<=r['box']['y']<400


def test_native_material_code_and_brand_are_isolated_before_translation(tmp_path):
    source=tmp_path/'native.pdf';native_pdf(source,b'Yellow BR Tricot PEANUTS')
    with pdfplumber.open(source) as pdf:
        regions=native_regions(pdf.pages[0],2)
    assert [r['sourceText'] for r in regions if not r['protected']]==['Yellow','Tricot']
    assert [r['sourceText'] for r in regions if r['protected']]==['BR','PEANUTS']


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


@pytest.mark.parametrize('scale', [1, 110 / 72, 2, 3, 4])
@pytest.mark.parametrize('background', [(255, 255, 255), (235, 244, 249)])
def test_erased_pdf_text_does_not_reappear_at_other_zoom_levels(tmp_path, scale, background):
    import pypdfium2 as pdfium
    from pypdf.generic import FloatObject, RectangleObject

    source = tmp_path / 'original.pdf'
    native_pdf(source)
    # Real office PDFs have fractional page dimensions. Their raster grid is
    # rounded up, and viewers rasterize the original fonts at different scales.
    writer = PdfWriter()
    page = writer.add_page(PdfReader(source).pages[0])
    page.mediabox = RectangleObject([0, 0, FloatObject(400.44), FloatObject(200.68)])
    content = DecodedStreamObject()
    fill = ' '.join(str(value / 255) for value in background)
    content.set_data(f'q {fill} rg 0 0 401 201 re f Q\n'.encode() + page.get_contents().get_data())
    page[NameObject('/Contents')] = writer._add_object(content)
    writer.write(source)
    with pdfium.PdfDocument(source) as document:
        bitmap = document[0].render(scale=2)
        original = bitmap.to_pil().convert('RGB')
        bitmap.close()
    result = original.copy()
    # Erase only the word Quantity, like the compositor; digits remain intact.
    background = original.getpixel((0, 0))
    ImageDraw.Draw(result).rectangle((36, 114, 151, 150), fill=background)
    before, after = tmp_path / 'before.png', tmp_path / 'after.png'
    original.save(before)
    result.save(after)
    output = PdfWriter()
    append_preserved_pdf(output, PdfReader(source).pages[0], before, after, 400.44, 200.68)
    target = tmp_path / 'translated.pdf'
    output.write(target)
    with pdfium.PdfDocument(target) as document:
        bitmap = document[0].render(scale=scale)
        rendered = np.asarray(bitmap.to_pil().convert('RGB'))
        bitmap.close()
    erased = rendered[round(57 * scale):round(75 * scale), round(18 * scale):round(75 * scale)]
    assert np.max(np.abs(erased.astype(int) - background)) <= 1, 'Original English glyph edges are visible through the overlay'
    assert PdfReader(target).pages[0].extract_text().strip() == PdfReader(source).pages[0].extract_text().strip()


@pytest.mark.parametrize('scale', [110 / 72, 3, 4])
def test_pdf_export_padding_keeps_neighboring_digits_and_rules(tmp_path, monkeypatch, scale):
    import pypdfium2 as pdfium
    from app.services.document_tools import image_translation as engine
    from app.services.document_tools import translation_engine

    source = tmp_path / 'native.pdf'
    native_pdf(source)
    with pdfplumber.open(source) as document:
        protected = [r['box'] for r in native_regions(document.pages[0], 2) if r['protected']]
    digit = protected[0]

    def typeset(pages, *_):
        for page in pages:
            with Image.open(page['input']) as image:
                result = image.convert('RGB')
            draw = ImageDraw.Draw(result)
            # Simulate replacement glyphs close enough for padding to reach a
            # numeric box and the horizontal rule, without changing either.
            x = math.floor(digit['x']) - 4
            draw.rectangle((x - 3, digit['y'], x, digit['y'] + digit['height']), fill='black')
            draw.rectangle((50, 293, 90, 295), fill='black')
            result.save(page['output'])
        return []

    monkeypatch.setattr(engine, 'require_runtime', lambda: None)
    monkeypatch.setattr(translation_engine.local, 'document_translation_status', lambda _: {'available': True})
    monkeypatch.setattr(engine, 'run_node', typeset)
    work = tmp_path / 'work'
    engine.convert_image_translation(source, {}, work, lambda *_: None, lambda: False)
    target = next(p for p in work.glob('*.pdf') if p.name != 'normalized.pdf')
    images = []
    for path in (source, target):
        with pdfium.PdfDocument(path) as document:
            bitmap = document[0].render(scale=scale)
            images.append(np.array(bitmap.to_pil().convert('RGB')))
            bitmap.close()
    for box in protected + [{'x': 20, 'y': 299, 'width': 760, 'height': 2}]:
        x0, y0 = math.floor(box['x'] * scale / 2), math.floor(box['y'] * scale / 2)
        x1 = math.ceil((box['x'] + box['width']) * scale / 2)
        y1 = math.ceil((box['y'] + box['height']) * scale / 2)
        assert np.array_equal(images[0][y0:y1, x0:x1], images[1][y0:y1, x0:x1])


def test_image_view_captions_use_manufacturing_meanings_without_model_calls():
    def unexpected_model_call(*args):
        raise AssertionError('view captions should use the image glossary')
    assert translate_image_texts(
        ['FRONT', 'BACK', 'LEFT', 'RIGHT', 'TOP', 'BOTTOM',
         'FRONT RIGHT', 'FRONT LEFT', 'BACK RIGHT', 'BACK LEFT', 'Standing Plush', 'Plush Guide'],
        'en_to_zh', unexpected_model_call,
    ) == ['正面', '背面', '左侧', '右侧', '顶部', '底部',
          '右前方', '左前方', '右后方', '左后方', '站立式毛绒玩具', '毛绒玩具指南']


def test_bad_translation_is_isolated_without_changing_numbers():
    def translate(texts,direction):
        if 'unknown' in texts: raise ToolError('TRANSLATION_NUMBERS_CHANGED','bad output')
        return ['安全文字']*len(texts)
    assert translate_image_texts(['Hair','good','unknown'],'en_to_zh',translate)==['头发','安全文字','unknown']


def test_plush_pattern_captions_use_parts_and_materials_instead_of_proper_names():
    def unexpected_model_call(*args):
        raise AssertionError('pattern captions should use the image glossary')
    assert translate_image_texts(
        ['EAR', 'EYE', 'NOSE', 'SPOT', 'LEG', 'SIDE HEAD', 'CENTER HEAD',
         'ARM', 'UNDER ARM', 'SOLE', 'TAIL', 'FRONT BODY', 'BACK BODY',
         'Seam Allowance', 'Cut', 'White Plush', 'Black Flock', 'Tricot',
         'Red Vinyl', 'Snoopy', 'Sitting Plush Pattern', 'Seam Allowanc e'],
        'en_to_zh', unexpected_model_call,
    ) == ['耳朵', '眼睛', '鼻子', '斑点', '腿部', '侧头片', '中间头片',
          '手臂', '内臂片', '脚底', '尾巴', '前身片', '后身片',
          '缝份', '裁', '白色毛绒布', '黑色植绒布', '经编布',
          '红色胶片', '史努比', '坐姿毛绒玩具纸样', '缝份']
    assert translate_image_texts(['WING', 'UPPER', 'UNDER TAIL', 'UPPER TAIL', 'Yellow Plush'],
        'en_to_zh', unexpected_model_call) == ['翅膀', '上侧', '下尾片', '上尾片', '黄色毛绒布']


def test_online_provider_errors_are_not_silently_hidden():
    import pytest
    def translate(*args):raise ToolError('TRANSLATION_NETWORK','unavailable')
    with pytest.raises(ToolError,match='unavailable'):
        translate_image_texts(['unknown'],'en_to_zh',translate)


def test_image_textile_terms_keep_wrappers_and_complete_ocr_letters():
    def unexpected_model_call(*args):
        raise AssertionError('known craft captions should use the image glossary')
    assert translate_image_texts(
        ['Materials &Swatches', 'Black felt', 'body fleece', '(Thread mix)',
         'Satin &French', 'knot mix)', 'Debossed', 'cap fabric', 'Di gestives'],
        'en_to_zh', unexpected_model_call,
    ) == ['材料与色样', '黑色毛毡', '身体绒布', '(混合绣线)',
          '缎面绣与法国结绣', '混合结粒绣)', '凹压纹', '帽子面料', '消化饼干']
    calls = []
    def model(texts, direction):
        calls.append((texts, direction))
        return ['模型译文'] * len(texts)
    assert translate_image_texts(['Thread mx', 'Thread mix 123', '混合绣线'], 'en_to_zh', model) == ['模型译文'] * 3
    assert translate_image_texts(['Thread mix'], 'zh_to_en', model) == ['模型译文']
    assert calls == [(['Thread mx', 'Thread mix 123', '混合绣线'], 'en_to_zh'), (['Thread mix'], 'zh_to_en')]


def test_online_image_context_preserves_user_terminology_and_offline_options():
    options = {'translation_engine': 'online', 'translation_direction': 'en_to_zh'}
    contextual = image_translation_options(options)
    assert contextual is not options and options == {'translation_engine': 'online', 'translation_direction': 'en_to_zh'}
    assert '刺绣' in contextual['glossary'] and 'thread mix=混合绣线' in contextual['glossary']
    custom = {**options, 'glossary': 'Thread mix=客户混线'}
    assert image_translation_options(custom)['glossary'].endswith(custom['glossary'])
    assert 'thread mix=混合绣线' not in image_translation_options(custom)['glossary']
    for untouched in ({}, {'translation_engine': 'offline'}, {**options, 'translation_direction': 'zh_to_en'}):
        assert image_translation_options(untouched) == untouched


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
