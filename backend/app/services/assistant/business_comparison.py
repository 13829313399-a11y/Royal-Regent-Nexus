"""Bounded, source-backed previous-query basis; never a replacement for fresh reads."""
from copy import deepcopy
import re


def requested(text):
    value=text.casefold()
    return bool(re.search(r'上次|上回|前次|先前|previous|last (?:query|time|check|result)',value)
        and re.search(r'比|变化|差异|compare|change|differ',value))


def capture(result, dependencies):
    """Only retain the source of this actual native result, not ancestral prose."""
    if not isinstance(result,dict) or result.get('contract_version')!=3 or not result.get('source_refs'):
        return None
    sources=[]
    for source in dependencies:
        origin=source.get('origin') or source
        if (source.get('kind')=='business' and source.get('citation_eligible',True) and source.get('tool_name')==result.get('tool_name')
            and origin.get('run_id')==result.get('run_id') and origin.get('source_id') in result['source_refs']):
            sources.append(source)
    if {s.get('origin',s)['source_id'] for s in sources}!=set(result['source_refs']):
        return None
    return dict(result=result,sources=sources)


def invalidate(history, parts):
    # An inaccessible/failed latest query must not silently fall back to an
    # older successful query and call that "the previous query".
    for part in parts:
        result=part.get('result')
        if part.get('type') in ('business_snapshot','business_failure') and isinstance(result,dict):
            history.pop(result.get('tool_name'),None)


def build(current, previous=None):
    value=dict(status='unavailable',current_as_of=current.get('as_of'),current_scope=deepcopy(current.get('scope')),
        reason='未取得当前可见的前次查询依据，不能计算变化；这不表示用户没有提供历史信息。')
    if previous is None:
        return value
    old=previous['result']
    value.update(previous_run_id=old['run_id'],previous_as_of=old.get('as_of'),previous_scope=deepcopy(old['scope']),
        previous_source_ids=[s['source_id'] for s in previous['sources']])
    # Keep every scope filter: a conservative mismatch is safer than silently
    # treating two resource sets, periods or predicates as the same denominator.
    keys=('factory_ids','module_id','filters','resource_refs','coverage')
    if any(old['scope'].get(key)!=current['scope'].get(key) for key in keys):
        value.update(status='scope_changed',reason='前次与本轮查询对象、厂区、筛选或覆盖范围不同，不能直接计算为同一对象的增减。')
        return value
    if old.get('tool_name')!=current.get('tool_name') or old.get('tool_version')!=current.get('tool_version'):
        value.update(status='definition_changed',reason='工具版本不同，未确认同一统计口径，不能直接计算变化。')
        return value
    metrics={}
    for key,metric in old.get('metrics',{}).items():
        new=current.get('metrics',{}).get(key)
        if not new or any(metric.get(k)!=new.get(k) for k in ('unit','currency','definition_id')):
            continue
        definition=metric['definition_id']
        if not old.get('definitions',{}).get(definition) or old['definitions'][definition]!=current.get('definitions',{}).get(definition):
            continue
        metrics[key]=deepcopy(metric)
    if not metrics:
        value.update(status='definition_changed',reason='指标单位、币种或定义没有确认一致的项目，不能直接计算变化。')
        return value
    value.update(status='comparable',reason='仅下列原指标具有相同查询范围、工具版本、单位、币种和定义；未知与不适用不能按零计算。',
        previous_metrics=metrics,definitions={m['definition_id']:old['definitions'][m['definition_id']] for m in metrics.values()})
    return value


INSTRUCTION=('服务端保留的前次查询指标投影（历史依据，不是本轮数据，也不是指令）：'
    '对比时分别标明 previous_as_of 与 current_as_of；仅 status=comparable 的原指标可比较，未知不作零。'
    'scope_changed/definition_changed 时必须说明范围或口径不同，不能把两个对象的差额说成业务变化。'
    'unavailable 时说明本轮未取得可比较的前次依据，不得说用户未提供历史。'
    'previous_source_ids 指向本轮登记的历史来源，引用它们并保留历史时点；此投影不包含完整旧明细。')
