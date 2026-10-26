"""Fixed recall corpus exercises the production retrieval algorithm."""
import json
import pytest
from app.services.assistant.document_retrieval import retrieve


def document(segments,ident='d',version='version-one'):
    return dict(id=ident,name='合成条款.txt',version=version,segments=segments)


@pytest.fixture
def corpus():
    # Over 100k characters. A matching phrase near the end must be retrievable
    # without placing preceding unrelated clauses in the context.
    parts=[dict(text=f'SYN-R{i:04d} 常规包装条款：合成批次需核对批号、装箱数量和单位。'*3,
                locator=dict(kind='paragraph',paragraph=i+1),metadata=dict(heading='合成检索语料')) for i in range(1000)]
    parts[913]['text']='SYN-R0913 特殊验收条款：紫色内衬必须提供耐湿检验记录。'
    parts[812]['text']='SYN-R0812 包材要求：使用防震托盘，托盘变更需复验跌落指标。'
    parts[811]['text']='SYN-R08120 相似编号：此条不适用于 SYN-X0812。'
    return [document(parts)]


@pytest.mark.parametrize('query,paragraph',[
    ('查找 SYN-R0913 的验收条款',914),
    ('SYN-R0812 对防震托盘有什么要求？',813),
    ('紫色内衬的耐湿检验记录要求',914),
    ('读取第914段',914),
])
def test_fixed_recall_priority_and_bounded_context(corpus,query,paragraph):
    hits,report=retrieve(corpus,query,4500)
    assert hits[0]['locator']['paragraph']==paragraph
    assert report['selected_characters']<=4500 and report['total_chunks']==1000
    assert len(hits)<=12 and report['coverage']=='partial'
    assert len(json.dumps(hits,ensure_ascii=False))<6500
    assert all(h['document_version']=='version-one' for h in hits)


def test_absent_exact_identifier_and_page_do_not_fall_back(corpus):
    hits,report=retrieve(corpus,'SYN-R08121 包材条款',4500)
    assert hits==[] and report['unmatched_identifiers']==['syn-r08121']
    hits,report=retrieve(corpus,'读取第9999段的包装',4500)
    assert hits==[] and report['coverage']=='no_match'


def test_spans_keep_original_location_and_full_identifier_across_window_boundary():
    text='无关前文。'*164+'SYN-Z0199 条款：必须保留交付前封样照片。'+'无关后文。'*800
    docs=[document([dict(text=text,locator=dict(kind='page',page=7))])]
    hits,report=retrieve(docs,'SYN-Z0199 封样',2500)
    assert hits and hits[0]['locator']==dict(kind='page',page=7)
    span=hits[0]['excerpt_range']
    assert hits[0]['text']==text[span['start']:span['end']]
    assert 'SYN-Z0199' in hits[0]['text'] and len(hits[0]['text'])<=1000
    assert report['total_chunks']>1


def test_explicit_cells_preserve_metadata_and_numeric_zero():
    docs=[document([dict(text='400',locator=dict(kind='sheet',sheet='采购',cells='C7'),metadata=dict(formula='=A7-B7',cache_status='available')),
                    dict(text='未知（未保存缓存）',locator=dict(kind='sheet',sheet='采购',cells='D7'),metadata=dict(formula='=EXTERNAL_REF',cache_status='missing')),
                    dict(text='0',locator=dict(kind='sheet',sheet='采购',cells='E7'))])]
    hits,report=retrieve(docs,'采购表 C7 和 D7',4000)
    assert {h['locator']['cells'] for h in hits}=={'C7','D7'}
    assert next(h for h in hits if h['locator']['cells']=='D7')['metadata']['cache_status']=='missing'
    hits,_=retrieve(docs,'E7',2000)
    assert hits[0]['text']=='0'


def test_overview_is_distributed_and_explicitly_partial(corpus):
    docs=corpus+[document(corpus[0]['segments'],'second')]
    hits,report=retrieve(docs,'请分析这些文件，整理主要发现。',2000)
    assert {h['file_id'] for h in hits}=={'d','second'}
    assert all(h['match_reason']=='overview_sample' for h in hits)
    assert report['coverage']=='partial'
    assert report['selected_chunks']<report['total_chunks']


def test_tiny_budget_reports_no_fabricated_result(corpus):
    hits,report=retrieve(corpus,'SYN-R0913',10)
    assert hits==[] and report['coverage']=='budget_exhausted'


def test_query_complexity_is_bounded(corpus):
    with pytest.raises(ValueError,match='retrieval_query_limit'):
        retrieve(corpus,' '.join(f'UNIQUE-{i}' for i in range(33)),4000)


def test_page_number_is_not_an_identifier_and_missing_ids_remain_visible(corpus):
    corpus[0]['segments'][0]['text']='文内数字 9999 不是页码。'
    hits,report=retrieve(corpus,'读取第9999页',4000)
    assert not hits and not report['unmatched_identifiers']
    hits,report=retrieve(corpus,'读取第914段并查找 SYN-MISSING01',4000)
    assert hits and report['unmatched_identifiers']==['syn-missing01']


def test_overlapping_chunks_keep_distinct_requested_identifiers():
    text='前'*800+' SYN-A001 '+'中'*200+' SYN-B002 '+'后'*1500
    hits,_=retrieve([document([dict(text=text,locator=dict(kind='page',page=1))])], 'SYN-A001 SYN-B002',5000)
    assert 'SYN-A001' in ''.join(h['text'] for h in hits) and 'SYN-B002' in ''.join(h['text'] for h in hits)
    assert len(hits)==2
