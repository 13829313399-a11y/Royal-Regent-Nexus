import json
import threading
import time

import httpx2 as httpx
from PIL import Image
from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.services.document_tools import general_translation as general
from app.services.document_tools.document_ir import Cancelled, ToolError


@pytest.fixture(autouse=True)
def no_live_provider(monkeypatch):
    original=httpx.Client
    def deny(request):raise AssertionError('Unit tests must mock every provider request')
    def client(**kwargs):
        kwargs.setdefault('transport',httpx.MockTransport(deny))
        return original(**kwargs)
    monkeypatch.setattr(general.httpx,'Client',client)


def stub_document_translation(monkeypatch):
    from app.services.document_tools import document_pipeline as pipeline
    monkeypatch.setattr(pipeline,'prepare_context',lambda *args:pipeline.Context())
    def translate(reading,*args):
        for b in reading.blocks:
            b.translation=('标签 '+b.source.split()[-1]) if b.source.startswith('Label ') else '不要把线拉得过紧'
    monkeypatch.setattr(general,'repair_reading',translate)


def block(source="Do not pull the thread too tight", translation="不要把线拉得过紧", **extra):
    return {"id":"b1", "source":source, "translation":translation, "bbox":[10,10,400,150], **extra}


@pytest.mark.parametrize("source,target,problem", [
    ("Novel heading", "Novel heading", "应译文字仍为原文"),
    ("NO TRIM NEEDED", "需要饰边", "否定或限制含义需要复核"),
    ("Seam allowance 3/16", "缝份 31/6", "数字、小数、分数或百分比不一致"),
    ("Quantity 00123", "数量 123", "数字、小数、分数或百分比不一致"),
    ("Model AB123", "型号 CD123", "型号或编号不一致"),
])
def test_translation_validation_checks_content_not_only_json(source, target, problem):
    assert problem in general.translation_problems(source,target,"en_to_zh")


def test_ordinary_heading_and_mixed_numeric_sentence_are_not_codes():
    assert not general.retained(general.ReadingBlock(**block(source="A NEW HEADING")))
    assert not general.retained(general.ReadingBlock(**block(source="Cut 2 pieces, model AB123")))
    assert general.retained(general.ReadingBlock(**block(source="PANTONE 706 C",kind="code")))
    assert general.retained(general.ReadingBlock(**block(source="PANTONE 706 C",kind="table-cell")))
    assert general.retained(general.ReadingBlock(**block(source="PANTONE WHITE C",kind="code")))
    assert general.retained(general.ReadingBlock(**block(source="X",kind="table-cell")))
    assert not general.retained(general.ReadingBlock(**block(source="PMS 4287 C- Pupils",kind="code")))
    assert not general.retained(general.ReadingBlock(**block(source="PANTONE 182 C Jeans",kind="table-cell")))
    assert general.translation_problems("Do not pull 3/16 inch","不要拉动 3/16 英寸","en_to_zh")==[]
    assert general.translation_problems('Control No. Q91075','控制编号 Q91075','en_to_zh')==[]
    assert general.translation_problems('Asst No. ：40620','组合编号：40620','en_to_zh')==[]
    assert not general.retained(general.ReadingBlock(**block(source='JACKE1',kind='heading')))
    for label in ['COLLAR','ARM','CENTER HEAD','UNDER ARM']:
        b=general.ReadingBlock(**block(source=label,translation=label,kind='code',preserved_terms=[label]))
        assert not general.retained(b)
        assert general.translation_problems(b.source,b.translation,'en_to_zh',b.preserved_terms)
    assert not general.retained(general.ReadingBlock(**block(source='For Acme Production & Sourcing',kind='brand',preserved_terms=['Acme'])))
    assert not general.retained(general.ReadingBlock(**block(source='Initial release: 11/03/2026',kind='date')))
    assert general.retained(general.ReadingBlock(**block(source='John Tsang',kind='proper-name',preserved_terms=['John Tsang'])))
    assert general.translation_problems('Page1of18','第 1 页，共 18 页','en_to_zh')==[]


def test_chinese_fragment_does_not_certify_a_partly_untranslated_block():
    problems=general.translation_problems('NOVEL GARMENT DESIGN\nHighly Confidential','NOVEL GARMENT DESIGN\n高度机密','en_to_zh')
    assert any('英文' in p for p in problems)
    assert general.translation_problems('Acme Corp material','Acme Corp 材料','en_to_zh',['Acme Corp'])==[]
    assert general.translation_problems('请不要拉紧缝线','Do not pull 缝线','zh_to_en')
    assert '否定或限制含义需要复核' in general.translation_problems('禁止拉紧缝线','Pull the thread tight','zh_to_en')
    assert general.translation_problems('禁止拉紧缝线','Do not pull the thread tight','zh_to_en')==[]


def test_manufacturing_words_are_not_codes_and_short_codes_cannot_hide_word_prefixes():
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block(
        source='Black BR Tricot',translation='黑色 BR Tricot',preserved_terms=['BR','Tricot']))])
    general.constrain_preserved_terms(reading,{})
    assert reading.blocks[0].preserved_terms==['BR']
    assert general.translation_problems('Black BR Tricot','黑色 BRTricot','en_to_zh',['BR'])
    assert general.translation_problems('Brown BR fabric','Brown BR 面料','en_to_zh',['BR'])


def test_anchor_completion_never_merges_a_nearby_repeated_word():
    image=Image.new('RGB',(400,300),'white')
    anchors=[{'id':'a0','text':'UNIVERSAL JACKET','bbox_pt':[20,20,260,45]},
             {'id':'a1','text':'JACKET','bbox_pt':[20,70,130,95]}]
    result=general._position_reading({'complete':True,'blocks':[block(source='UNIVERSAL JACKET',anchor_ids=['a0'])]},anchors,image)
    positioned=result['blocks'][0]
    assert positioned['anchor_ids']==['a0']
    assert positioned['bbox'][3]==150


def test_unreliable_vlm_coordinates_never_become_pixel_placement():
    image=Image.new('RGB',(400,300),'white')
    result=general._position_reading({'complete':True,'blocks':[block(bbox=[1400,0,1500,100])]},[],image)
    assert result['blocks'][0]['located'] is False
    assert result['blocks'][0]['bbox']==[0,0,1000,1000]


def test_metadata_and_uncertainty_cannot_become_confirmed_content():
    image=Image.new('RGB',(100,100),'white')
    result=general._position_reading({'complete':True,'blocks':[block(source='a3')]},
        [{'id':'a3','text':'<3>','bbox_pt':[10,10,30,25]}],image)
    assert result['blocks']==[]
    page=general._validate_reading({'complete':True,'blocks':[block(note='Possibly a product name',uncertain=False)]})
    assert page.blocks[0].uncertain
    assert not general.note_is_uncertain('无需标不确定')


@pytest.mark.parametrize("bbox", [[0,0,0,5],[-1,0,5,5],[0,0,float('nan'),5],[0,0,1001,5]])
def test_invalid_layout_coordinates_are_rejected(bbox):
    with pytest.raises(ToolError,match="坐标"):
        general._validate_reading({"complete":True,"blocks":[block(bbox=bbox)]})


def test_mimo_multimodal_request_uses_dedicated_connection_and_never_logs_key(monkeypatch):
    monkeypatch.setattr(settings,"document_tools_translation_base_url","https://api.xiaomimimo.com/v1")
    monkeypatch.setattr(settings,"document_tools_translation_protocol","mimo")
    monkeypatch.setattr(settings,"document_tools_translation_api_key",SecretStr("test-private-key"))
    monkeypatch.setattr(settings,"document_tools_translation_model","mimo-v2.6-flash")
    def handle(request):
        body=json.loads(request.content)
        assert request.headers['Authorization']=="Bearer test-private-key"
        assert body['thinking']=={'type':'disabled'}
        assert body['messages'][1]['content'][0]['image_url']['url'].startswith('data:image/png;base64,')
        return httpx.Response(200,json={'model':'mimo-v2.6-flash','choices':[{'finish_reason':'stop','message':{'content':'{"complete":true,"blocks":[]}'}}]})
    client=httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(general.httpx,"Client",lambda **kwargs:client)
    traces=[]
    assert general.request_json('instruction',{},Image.new('RGB',(10,10)),lambda:False,traces,'read')['complete']
    assert 'test-private-key' not in json.dumps(traces)


def test_review_cannot_silently_drop_a_previously_read_region(monkeypatch):
    values=iter([{'complete':True,'blocks':[block()]},{'complete':True,'blocks':[]}])
    monkeypatch.setattr(general,'request_json',lambda *args:next(values))
    result,evidence=general.read_page(Image.new('RGB',(100,100)),[],{},lambda:False,[])
    assert not result.complete
    assert result.blocks[0].source=='Do not pull the thread too tight'
    assert result.blocks[0].uncertain
    assert evidence['draft']['blocks']


def test_independent_ocr_candidate_is_not_silently_lost(monkeypatch):
    monkeypatch.setattr(general,'request_json',lambda *args:{'complete':True,'blocks':[]})
    result,_=general.read_page(Image.new('RGB',(100,100)),[{'text':'Unread source 00123','bbox_pt':[10,10,80,25]}],{},lambda:False,[])
    assert not result.complete and result.blocks[0].uncertain
    assert result.blocks[0].source=='Unread source 00123'


def test_cancellation_does_not_wait_for_remote_or_native_work():
    started=threading.Event();release=threading.Event()
    def work():
        started.set();release.wait(2)
    begin=time.monotonic()
    try:
        with pytest.raises(Cancelled):
            general.interruptible(work,started.is_set)
        assert time.monotonic()-begin<.8
    finally:
        release.set()


def test_crop_review_removes_drawing_noise_but_recovers_missing_actual_text(monkeypatch):
    monkeypatch.setattr(general,'request_json',lambda *args:{'candidates':[
        {'id':'a0','is_text':False},
        {'id':'a1','is_text':True,'source':'New label','translation':'新标签','uncertain':False}]})
    anchors=[{'id':'a0','text':'<3>','bbox_pt':[5,5,20,20]},
             {'id':'a1','text':'New label','bbox_pt':[30,30,80,45]}]
    page=general.ReadingPage(complete=True,blocks=[])
    missing,evidence=general.verify_candidates(Image.new('RGB',(100,100)),anchors,page,{},lambda:False,[])
    assert missing==[] and len(evidence)==1
    assert [b.source for b in page.blocks]==['New label']


def test_crop_metadata_never_becomes_confirmed_source_text(monkeypatch):
    def response(prompt,data,images,*args):
        assert isinstance(images,list) and len(images)==1
        # No candidate label is painted onto the actual source crop.
        assert images[0].getextrema()==((255,255),(255,255),(255,255))
        return {'candidates':[{'id':'a3','is_text':True,'source':'a3','translation':'a3','uncertain':False}]}
    monkeypatch.setattr(general,'request_json',response)
    anchors=[{'id':'a3','text':'<3>','bbox_pt':[10,10,30,25]}]
    page=general.ReadingPage(complete=True,blocks=[])
    missing,_=general.verify_candidates(Image.new('RGB',(100,100),'white'),anchors,page,{},lambda:False,[])
    assert len(missing)==1 and page.blocks==[]


def test_semantic_editor_corrects_target_and_keeps_ambiguous_source_flagged(monkeypatch):
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block())])
    monkeypatch.setattr(general,'request_json',lambda *args:{'complete':True,'issues':[
        {'id':'b1','translation':'不要把线拉得过紧','uncertain':True,'note':'含义需核对'}]})
    general.review_semantics(Image.new('RGB',(100,100)),reading,{},lambda:False,[])
    assert reading.blocks[0].source=='Do not pull the thread too tight'
    assert reading.blocks[0].uncertain
    assert reading.blocks[0].translation=='不要把线拉得过紧'


def test_semantic_editor_rejects_unknown_block_association(monkeypatch):
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block())])
    monkeypatch.setattr(general,'request_json',lambda *args:{'complete':True,'issues':[
        {'id':'different','translation':'译文','uncertain':False,'note':'校对'}]})
    result=general.review_semantics(Image.new('RGB',(100,100)),reading,{},lambda:False,[])
    assert result['response_rejected'] and not reading.complete
    assert reading.blocks[0].translation=='不要把线拉得过紧'


def test_repair_cannot_export_an_entire_page_as_one_short_block(tmp_path,monkeypatch):
    from app.services.document_tools import local_ocr
    source=tmp_path/'source.png';Image.new('RGB',(100,100),'white').save(source)
    monkeypatch.setattr(local_ocr,'recognize',lambda *args:[])
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block(source='AB',translation='',kind='table-cell'))])
    monkeypatch.setattr(general,'request_json',lambda *args:{'blocks':[{'id':'b1','translation':'其他文字'*100}]})
    general.repair_reading(reading,{},lambda:False,[])
    region=general.build_regions(reading,[],Image.new('RGB',(100,100)),{'translation_engine':'online'})[0]
    assert region['translatedText']=='' and region['translationStatus']=='needs_review'


def test_repairs_are_bounded_batches_with_exact_block_correspondence(monkeypatch):
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block(id=f'b{i}',source=f'Label {i}',translation=f'Label {i}')) for i in range(25)])
    sizes=[]
    def repair(prompt,data,*args):
        sizes.append(len(data['blocks']))
        return {'blocks':[{'id':b['id'],'translation':'标签 '+b['source'].split()[-1]} for b in data['blocks']]}
    monkeypatch.setattr(general,'request_json',repair)
    general.repair_reading(reading,{},lambda:False,[])
    assert sizes==[12,12,1]
    assert all(not general.translation_problems(b.source,b.translation,'en_to_zh') for b in reading.blocks)


def test_partial_repair_does_not_resend_correct_ids_or_assign_an_unknown_translation(monkeypatch):
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(
        **block(id=f'b{i}',source=f'Label {i}',translation='')) for i in range(4)])
    requests=[]
    def repair(prompt,payload,*args):
        ids=[b['id'] for b in payload['blocks']];requests.append(ids)
        if len(requests)==1:
            return {'blocks':[{'id':'b2','translation':'标签 2'},{'id':'b0','translation':'标签 0'},
                              {'id':'b1','translation':'标签 1'},{'id':'b1','translation':'错误 1'},
                              {'id':'not-requested','translation':'另一个段落'}]}
        if ids==['b1']:return {'blocks':[{'id':'b1','translation':'标签 1'}]}
        return {'blocks':[{'id':'another','translation':'不对应标签 3'}]}
    monkeypatch.setattr(general,'request_json',repair)
    general.repair_reading(reading,{},lambda:False,[])
    assert requests==[['b0','b1','b2','b3'],['b1'],['b3']]
    assert [b.translation for b in reading.blocks]==['标签 0','标签 1','标签 2','']
    with Image.new('RGB',(200,100),'white') as image:
        regions=general.build_regions(reading,[],image,{'translation_engine':'online'})
        assert regions[-1]['sourceText']=='Label 3' and regions[-1]['translationStatus']=='needs_review'


def test_online_pages_overlap_remote_wait_but_keep_original_page_order(tmp_path,monkeypatch):
    from app.services.document_tools import local_ocr
    stub_document_translation(monkeypatch)
    pages=[]
    for i in range(3):
        source=tmp_path/f'source{i}.png';Image.new('RGB',(100,100),(i,0,0)).save(source)
        pages.append({'input':str(source)})
    monkeypatch.setattr(local_ocr,'recognize',lambda *args:[])
    barrier=threading.Barrier(2);seen=[];lock=threading.Lock()
    def read(image,*args):
        value=image.getpixel((0,0))[0]
        with lock:seen.append(value)
        if value<2:barrier.wait(timeout=2)
        return general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block(source=f'Label {value}',translation=f'标签 {value}'))]),{}
    monkeypatch.setattr(general,'read_page',read)
    monkeypatch.setattr(general,'review_semantics',lambda *args:{'complete':True,'issues':[]})
    def render(layouts):
        assert [p['regions'][0]['sourceText'] for p in layouts]==['Label 0','Label 1','Label 2']
        return [{'record':{'translations':p['regions']}} for p in layouts]
    assert len(general.process_pages(pages,{'translation_engine':'online'},tmp_path,lambda *args:None,lambda:False,render))==3
    assert sorted(seen)==[0,1,2]


def test_failed_page_cancels_another_inflight_page_without_waiting_for_http(tmp_path,monkeypatch):
    from app.services.document_tools import local_ocr
    pages=[]
    for i in range(2):
        source=tmp_path/f'p{i}.png';Image.new('RGB',(100,100),(i,0,0)).save(source)
        pages.append({'input':str(source)})
    monkeypatch.setattr(local_ocr,'recognize',lambda *args:[])
    waiting=threading.Event();release=threading.Event()
    def read(image,anchors,options,cancelled,traces):
        if image.getpixel((0,0))[0]==0:
            assert waiting.wait(1)
            raise ToolError('TEST_FAILURE','测试失败')
        waiting.set()
        general.interruptible(lambda:release.wait(3),cancelled)
    monkeypatch.setattr(general,'read_page',read)
    begin=time.monotonic()
    try:
        with pytest.raises(ToolError,match='测试失败'):
            general.process_pages(pages,{'translation_engine':'online'},tmp_path,lambda *args:None,lambda:False,lambda pages:[])
        assert time.monotonic()-begin<1.5
    finally:release.set()


def test_malformed_page_reading_is_retried_then_preserves_unverified_native_source(monkeypatch):
    calls=[]
    def respond(prompt,data,image,cancelled,traces,stage):
        calls.append(stage)
        return {'complete':True,'blocks':'malformed'}
    monkeypatch.setattr(general,'request_json',respond)
    with Image.new('RGB',(200,100),'white') as image:
        reading,evidence=general.read_page(image,[{'text':'Measure 12 mm','method':'native',
            'bbox_pt':[10,10,120,26]}],{},lambda:False,[])
        assert calls==['read','read','review','review']
        assert evidence['source_fallback'] and len(evidence['rejected_responses'])==4
        assert not reading.complete and reading.blocks[0].uncertain
        assert reading.blocks[0].source=='Measure 12 mm'
        assert general.build_regions(reading,[],image,{'translation_engine':'online'})[0]['skipReason']=='source-uncertain'


def test_source_response_rekeys_duplicate_model_ids_without_dropping_distinct_text():
    blocks=[{'id':'same','source':'Label one','anchor_ids':None},
            {'id':'same','source':'Label two','anchor_ids':[{}]}]
    with Image.new('RGB',(200,100),'white') as image:
        reading=general._validate_reading(general._position_reading({'complete':True,'blocks':blocks},[],image))
    assert [b.source for b in reading.blocks]==['Label one','Label two']
    assert len({b.id for b in reading.blocks})==2 and not any(b.located for b in reading.blocks)


def test_page_translation_survives_failure_to_fit_original_layout(tmp_path,monkeypatch):
    from app.services.document_tools import local_ocr
    stub_document_translation(monkeypatch)
    source=tmp_path/'source.png';Image.new('RGB',(400,200),'white').save(source)
    monkeypatch.setattr(local_ocr,'recognize',lambda *args:[])
    reading=general.ReadingPage(complete=True,blocks=[general.ReadingBlock(**block())])
    monkeypatch.setattr(general,'read_page',lambda *args:(reading,{}))
    monkeypatch.setattr(general,'review_semantics',lambda *args:{'complete':True,'issues':[]})
    def render(pages):
        regions=pages[0]['regions']
        for r in regions:r.update(rendered=False,skipReason='layout-space')
        return [{'event':'page','index':0,'record':{'translations':regions}}]
    result=general.process_pages([{'input':str(source),'output':str(tmp_path/'output.png')}],
        {'translation_engine':'online'},tmp_path,lambda *args:None,lambda:False,render)
    region=result[0]['record']['translations'][0]
    assert region['translationStatus']=='translated'
    assert region['translatedText']=='不要把线拉得过紧'
    assert not region['rendered']
