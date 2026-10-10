"""Production facts separate from plans, stock, costs and payable quantities."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import UTC, datetime
from sqlalchemy import inspect, select, text
from app.models.cutting_ops import CuttingOrder, CuttingProductionEvent as Event
from app.services import cutting_ops as c, cutting_orders as orders, cutting_planning as planning

TABLE = Event.__table__


def schema_ready(bind):
    inspector = inspect(bind)
    if TABLE.name not in inspector.get_table_names() or not {x.name for x in TABLE.columns} <= {x['name'] for x in inspector.get_columns(TABLE.name)}:
        return False
    with (bind.connect() if hasattr(bind, 'connect') else nullcontext(bind)) as connection:
        if connection.dialect.name == 'sqlite':
            names=set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='cutting_ops_production_events'")).scalars())
            return {'cutting_production_no_update','cutting_production_no_delete'} <= names
        if connection.dialect.name == 'postgresql':
            return bool(connection.execute(text("SELECT 1 FROM pg_trigger WHERE tgrelid = to_regclass('cutting_ops_production_events') AND tgname='cutting_production_immutable' AND tgenabled IN ('O','A')")).scalar())
    return False


def events(db, line_id):
    return [dict(id=r.id, version=r.version, document_id=r.document_id, action=r.action,
                 data=r.data, actor_id=r.actor_id, created_at=r.created_at, reason=r.reason)
            for r in db.scalars(select(Event).where(Event.line_id == line_id, Event.factory_id == c.FACTORY).order_by(Event.version))]


def documents(history):
    result = {}
    for event in history:
        document = result.setdefault(event['document_id'], dict(document_id=event['document_id'], posted=None, draft=None,
            review=None, voided=False, history=[], first_version=event['version'], first_post_version=None))
        document['history'].append(event)
        action = event['action']
        if action == 'save': document['draft'] = event
        if action == 'post':
            document['first_post_version'] = document['first_post_version'] or event['version']
            document.update(posted=event, draft=None, review=None, voided=False)
        if action == 'void': document.update(posted=None, draft=None, review=None, voided=True)
        if action == 'discard': document['draft'] = None
        if action == 'review': document['review'] = event
    return result


def empty_balance(context):
    return dict(context=context, produced=0, completed=0, claimed=0, returned=0, accepted=0, rejected=0,
                handed=0, daily_rejected=0, daily_scrap=0,
                loose={p['code']: 0 for p in context['parts']}, part_rejected={p['code']: 0 for p in context['parts']},
                part_scrap={p['code']: 0 for p in context['parts']}, matchable=0)


def replay(docs, as_of=None):
    balances, daily_keys, movements = {}, set(), []
    effective = [d for d in docs.values() if d['posted'] and (not as_of or d['posted']['data']['entry']['day'] <= as_of)]
    # Preserve original within-day business sequence through corrections.
    effective.sort(key=lambda d: (d['posted']['data']['entry']['day'], d['first_post_version']))
    for document in effective:
        event = document['posted']; entry = event['data']['entry']; context = event['data']['context']
        task_id = entry['task_id']; day = entry['day']; kind = entry['kind']; qty = entry['sets']
        b = balances.setdefault(task_id, empty_balance(context))
        before_completed, before_handed = b['completed'], b['handed']
        external = context['execution'] == 'outsourced'
        if kind == 'daily':
            key = (task_id, day)
            c.require(key not in daily_keys, '同一任务同日只能有一张有效日报，请更正原日报', 422)
            daily_keys.add(key)
            if entry['mode'] == 'parts':
                for part in entry['parts']:
                    b['loose'][part['code']] += part['good']
                    b['part_rejected'][part['code']] += part['rejected']
                    b['part_scrap'][part['code']] += part['scrap']
            else:
                b['produced'] += qty
            b['daily_rejected'] += entry['rejected']; b['daily_scrap'] += entry['scrap']
        elif kind == 'match':
            for part in context['parts']:
                b['loose'][part['code']] -= qty * part['pieces_per_set']
                c.require(b['loose'][part['code']] >= 0, '合格裁片不足，或更正影响了后续核套；请先更正后续记录', 422)
            b['produced'] += qty
        elif kind == 'return':
            c.require(external, '只有外发任务登记收回', 422)
            b['returned'] += qty
        elif kind == 'accept':
            c.require(external, '只有外发任务登记收回验收', 422)
            b['accepted'] += qty; b['rejected'] += entry['rejected']
        elif kind == 'handover':
            b['handed'] += qty
        b['claimed'] = b['produced'] if external else 0
        b['completed'] = b['accepted'] if external else b['produced']
        c.require(b['returned'] <= b['claimed'], '收回数量超过截至当日的外发报称完成数量', 422)
        c.require(b['accepted'] + b['rejected'] <= b['returned'], '验收数量超过截至当日的实际收回量', 422)
        c.require(b['handed'] <= b['completed'], '交接数量超过截至当日的合格可交接套数；先核对上游记录', 422)
        b['matchable'] = min((b['loose'][p['code']] // p['pieces_per_set'] for p in context['parts']), default=0)
        if kind in {'daily', 'match'} and b['produced'] > context['task_target']:
            c.require(entry['exception_reason'], '超过任务目标须填写超产说明；记录实绩不等于批准结算额度', 422)
        movements.append(dict(day=day, completed=b['completed']-before_completed, handed=b['handed']-before_handed))
    return balances, movements


def view(db, line_id, as_of=None):
    order = db.get(CuttingOrder, line_id)
    c.require(order is not None and order.factory_id == c.FACTORY, '裁床订单不存在', 404)
    data = orders.revision(db, order)['data']
    history = events(db, line_id); docs = documents(history)
    balances, movements = replay(docs, as_of)
    today = as_of or planning.business_today().isoformat()
    published = data.get('planning', {}).get('published')
    tasks = []
    modes = {}
    for event in history:
        modes.setdefault(event['data']['entry']['task_id'], event['data']['entry']['mode'])
    for task in (published or {}).get('tasks', []):
        tasks.append(dict(task_id=task['task_id'], name=task['name'], execution=task['resource']['data']['execution'],
            mode=modes.get(task['task_id']), plan_version=published['version'], target_sets=task['target_sets'],
            parts=data['bom']['data']['parts'] if data.get('bom') else [], historical=False,
            balance=balances.get(task['task_id'])))
    for event in history:
        task_id=event['data']['entry']['task_id']
        if any(t['task_id'] == task_id for t in tasks): continue
        context=event['data']['context']
        tasks.append(dict(task_id=task_id, name=context['task_name'], execution=context['execution'], mode=modes[task_id],
            plan_version=context['plan_version'], target_sets=context['task_target'], parts=context['parts'],
            historical=True, balance=balances.get(task_id)))
    completed=sum(b['completed'] for b in balances.values()); handed=sum(b['handed'] for b in balances.values())
    planned=sum(d['sets'] for t in (published or {}).get('tasks', []) for d in t['days'] if d['day'] <= today)
    months={}
    for t in (published or {}).get('tasks', []):
        for d in t['days']:
            if d['day'] <= today: months.setdefault(d['day'][:7], dict(planned=0, completed=0, handed=0))['planned'] += d['sets']
    for m in movements:
        bucket=months.setdefault(m['day'][:7], dict(planned=0, completed=0, handed=0))
        bucket['completed'] += m['completed']; bucket['handed'] += m['handed']
    for t in tasks:
        first_post=next((e for e in history if e['action']=='post' and e['data']['entry']['task_id']==t['task_id']), None)
        t['settlement_context']=first_post['data']['context'] if first_post else None
    return dict(line_id=line_id, version=order.version, as_of=today, tasks=tasks, documents=list(docs.values()),
        summary=dict(order_sets=data.get('target_sets'), completed=completed, handed=handed, actual_delivery=handed,
            remaining=None if data.get('target_sets') is None else data['target_sets']-completed,
            planned=planned, plan_difference=handed-planned, completed_unhanded=completed-handed,
            day_completed=sum(m['completed'] for m in movements if m['day']==today),
            day_handed=sum(m['handed'] for m in movements if m['day']==today), months=months))


def apply(db, user, line_id, body, action):
    # Reuse order optimistic version and the enclosing factory lock, but corrections
    # may repair historical facts even after cancellation or a new dispatch.
    _, dispatch = orders.lock_source(db, line_id)
    order=db.get(CuttingOrder, line_id)
    c.require(order is not None and order.factory_id == c.FACTORY, '裁床订单不存在', 404)
    c.require(order.version == body.expected_version, '裁床记录已更新，请重新读取后操作')
    data=deepcopy(orders.revision(db, order)['data'])
    history=events(db, line_id); docs=documents(history); old=docs.get(body.document_id)
    c.require(not old or not old['voided'], '已作废记录不能重新启用，请另建业务记录')
    if action in {'void', 'review', 'discard'}:
        c.require(old is not None, '原记录不存在', 404)
        c.require(old['draft'] if action=='discard' else old['posted'], '没有可处理的草稿或生效记录')
        payload=deepcopy((old['draft'] if action=='discard' else old['posted'])['data'])
    else:
        entry=body.entry.model_dump(mode='json')
        c.require(entry['day'] <= planning.business_today().isoformat(), '实际生产日期不能晚于今天（上海时间）', 422)
        if old:
            previous=(old['posted'] or old['draft'] or old['history'][0])['data']
            for key in ('task_id', 'mode', 'kind', 'plan_version'):
                c.require(entry[key] == previous['entry'][key], '更正不能改变原任务、报数方式、业务类型或来源计划', 422)
        first_post=next((e for e in history if e['action']=='post' and e['data']['entry']['task_id']==entry['task_id']), None)
        if old and old['posted']:
            context=deepcopy(old['posted']['data']['context'])
        elif entry['kind'] != 'daily' and first_post:
            # Existing loose pieces, completed sets and receipts must remain operable
            # after removal/cancellation. They cannot create a new daily production fact.
            context=deepcopy(first_post['data']['context'])
            c.require(entry['plan_version']==context['plan_version'], '请使用历史任务冻结的计划版本处理剩余数量', 422)
        else:
            c.require(order.dispatch_id==dispatch.id and data['order'].get('status')=='active', '请先签收最新有效订单版本')
            plan=data.get('planning', {}).get('published')
            c.require(plan and plan['version']==entry['plan_version'], '请明确选择当前已发布计划')
            c.require(not planning.summary(db, data)['published_stale'], '计划依据已变更，请先复核并重新发布')
            task=next((t for t in plan['tasks'] if t['task_id']==entry['task_id']), None)
            c.require(task is not None, '任务不属于当前发布计划', 422)
            context=dict(plan_version=plan['version'], dispatch_id=data['dispatch_id'], bom_id=data['bom']['id'],
                bom_version=data['bom']['version'], parts=deepcopy(data['bom']['data']['parts']),
                task_name=task['name'], task_target=task['target_sets'], resource_id=task['resource_id'],
                resource_name=task['resource']['data']['name'], execution=task['resource']['data']['execution'],
                actual_issue_date=task.get('actual_issue_date'), actual_ready=task.get('actual_readiness_date'),
                actual_supply=task.get('actual_supply_date'), actual_review_pending=task.get('actual_review_pending', True))
        for event in history:
            prior=event['data']
            if prior['entry']['task_id'] != entry['task_id']: continue
            c.require(prior['entry']['mode']==entry['mode'], '任务报数方式已固定，不能混用直接报套与裁片核套', 422)
            c.require(all(prior['context'][key]==context[key] for key in ('bom_id','bom_version','resource_id','execution')),
                '已有实绩的任务不能混入不同 BOM 或执行方，请在计划中另建任务', 422)
        if entry['kind']=='daily' and entry['mode']=='parts':
            c.require({p['code'] for p in entry['parts']}=={p['code'] for p in context['parts']}, '裁片日报须逐项覆盖冻结 BOM 部件，未产部件填零', 422)
        if entry['kind'] in {'daily','match'}:
            early=context.get('actual_supply') and entry['day'] < context['actual_supply']
            c.require(not (context['actual_review_pending'] or early) or entry['exception_reason'],
                '实际领料尚未核定或早于核定供数日，请填写现场实绩核对说明；不代表开工批准', 422)
        payload=dict(entry=entry, context=context)
    event=dict(id=body.operation_id, version=order.version+1, document_id=body.document_id, action=action, data=payload,
               actor_id=user.id, created_at=datetime.now(UTC).isoformat(), reason=body.reason)
    prospective=documents(history+[event])
    if action in {'post', 'void'}: replay(prospective)
    db.add(Event(line_id=line_id, factory_id=c.FACTORY, **event))
    # No stock or cost mutation; source re-receipt cannot erase the separate ledger.
    orders.append(db, user, order, data, body.reason)
    return view(db, line_id)
