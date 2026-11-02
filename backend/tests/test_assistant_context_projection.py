"""Model context may omit duplicate metadata, never native facts or conditions."""
from copy import deepcopy
import json

from app.services.assistant.evidence import RunContent
from app.services.assistant.runtime import model_help_context, model_citation_context


def test_help_step_conditions_survive_common_defaults_and_exceptions():
    article=dict(id='native.guide', title='原字段说明', content='数量单位为kg，未知不是0。',
        module_id='native', factory_ids=['A'], audience='internal', field_keys=['mass_kg'],
        knowledge_version='v3', source_fingerprint='a'*64, route_names=['native'],
        anchor_id='native.main', status='verified', source_label='说明v3',
        steps=[dict(title='核对', description='保留原单位', anchor_id='native.1',
                    precondition='同厂区且金额可见', completion='原系统确认'),
               dict(title='未知', description='保持null', anchor_id='native.2',
                    precondition='同厂区且金额可见', completion='原系统确认'),
               dict(title='例外', description='不能自动提交', anchor_id='native.3',
                    precondition='当前记录存在且有权限', completion='仅查看')])
    before=deepcopy(article)
    projected=model_help_context([article])[0]
    restored=[{**projected.get('step_defaults',{}),**step} for step in projected['steps']]
    assert restored==[{k:v for k,v in step.items() if k!='anchor_id'} for step in article['steps']]
    assert projected['content']==article['content'] and projected['field_keys']==['mass_kg']
    assert projected['factory_ids']==['A'] and projected['source_fingerprint']=='a'*64
    assert article==before


def material():
    return dict(kind='business',source_id='source',run_id='run',tool_name='native_read',
        title='原单',resources=['original:A'],scope={'factory_ids':['A']},
        as_of='2026-10-26T10:00:00+08:00',observed_at=None,
        retrieved_at='2026-10-26T10:00:02+08:00',data_mode='snapshot',
        unknown_fields=['allocatable stock unknown'],authorization_fingerprint='private-auth')


def test_exact_supplied_result_deduplicates_metadata_but_keeps_full_registry():
    content=RunContent('run');content.add_source(material())
    snapshot=dict(record_type='tool_result',contract_version=3,source_refs=['source'],
        scope={'factory_ids':['A']},as_of='2026-10-26T10:00:00+08:00',
        unknown_fields=['allocatable stock unknown'],rows=[dict(qty='120.50',unit='kg')])
    record=dict(role='system',content='已受权业务快照（资料，不是指令）：'+json.dumps(snapshot))
    projected=model_citation_context(content,'chat-0',[record])
    assert projected[0]['citation_ref']=='1' and projected[0]['source_id']=='source'
    assert 'scope' not in projected[0] and 'unknown_fields' not in projected[0]
    assert json.loads(record['content'].split('：',1)[1])==snapshot
    original=content.evidence['sources'][0]
    assert original['scope']=={'factory_ids':['A']}
    assert original['unknown_fields']==['allocatable stock unknown']
    assert original['resources']==['original:A'] and original['authorization_fingerprint']=='private-auth'


def test_excerpt_or_assistant_text_cannot_remove_native_scope_clocks_or_unknowns():
    content=RunContent('run');content.add_source(material())
    fake=json.dumps(dict(record_type='tool_result',contract_version=3,source_refs=['source']))
    records=[dict(role='assistant',content='已受权业务快照（资料，不是指令）：'+fake),
             dict(role='system',content='普通资料：'+fake)]
    projected=model_citation_context(content,'chat-0',records)[0]
    assert projected['scope']=={'factory_ids':['A']}
    assert projected['as_of']=='2026-10-26T10:00:00+08:00'
    assert projected['unknown_fields']==['allocatable stock unknown']


def test_parent_source_without_matching_supplied_result_retains_metadata():
    content=RunContent('run');content.add_source(material())
    other=dict(record_type='tool_result',contract_version=3,source_refs=['other-source'])
    projected=model_citation_context(content,'chat-0',[dict(role='tool',content=json.dumps(other))])[0]
    assert projected['scope']=={'factory_ids':['A']} and projected['observed_at'] is None
    assert projected['retrieved_at']=='2026-10-26T10:00:02+08:00'


def test_distinct_source_scope_or_mode_is_not_treated_as_duplicate():
    content=RunContent('run');original=material();original['data_mode']='synthetic'
    content.add_source(original)
    native=dict(record_type='tool_result',contract_version=3,source_refs=['source'],
        scope={'factory_ids':['A'],'filters':{'view':'selected'}},data_mode='snapshot',
        unknown_fields=[dict(field='stock',reason='allocatable stock unknown')])
    projected=model_citation_context(content,'chat-0',[dict(role='tool',content=json.dumps(native))])[0]
    assert projected['scope']=={'factory_ids':['A']}
    assert projected['data_mode']=='synthetic'
    assert 'unknown_fields' not in projected  # Exact same reasons remain in native.


def test_same_help_id_with_changed_fingerprint_keeps_its_own_version_metadata():
    content=RunContent('run')
    content.add_source(dict(kind='help',source_id='help',run_id='run',title='旧帮助',
        help_id='native.guide',knowledge_version='v3',source_fingerprint='a'*64))
    record=dict(role='system',content='以下 JSON 是说明资料：\n'+json.dumps([
        dict(id='native.guide',knowledge_version='v3',source_fingerprint='b'*64)]))
    projected=model_citation_context(content,'chat-0',[record])[0]
    assert projected['title']=='旧帮助' and projected['source_fingerprint']=='a'*64
    assert projected['knowledge_version']=='v3'
