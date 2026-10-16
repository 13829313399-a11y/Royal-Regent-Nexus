"""P5a read-only cutover reconciliation. Never posts opening balances."""
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from app.models.cutting_ops import CuttingOrder, CuttingProductionEvent
from app.services import cutting_ops as c, cutting_orders as orders, cutting_closing as closing
from app.services import cutting_reporting as reporting, cutting_usage as usage
from app.services import cutting_periods as periods, cutting_period_guards as guards
from app.services import cutting_settlement as fees, cutting_payments as payments, warehouse_operations as wh
from app.services.cutting_schemas import Strict, Text
from app.services.cutting_period_schemas import Month
from app.services.cutting_usage_schemas import Nonnegative
from app.services.transaction_lock import lock_transaction

PERMISSIONS = {'internal': ('cost_read',), 'finance': ('settlement_read', 'payment_read')}


class Comparison(Strict):
    key: Annotated[str, Field(min_length=1, max_length=400)]
    value: Nonnegative
    unit: Text
    evidence: Annotated[str, Field(min_length=1, max_length=500)]


class External(Strict):
    description: Annotated[str, Field(min_length=1, max_length=500)]
    evidence: Annotated[str, Field(min_length=1, max_length=500)]


class Selection(Strict):
    factory_id: str
    month: Month
    scope: Literal['internal', 'finance']
    batch: Annotated[int, Field(ge=1)] = 1
    batch_size: Annotated[int, Field(ge=1, le=200)] = 50
    query: Annotated[str, Field(max_length=80)] = ''
    token: Annotated[str, Field(max_length=64)] | None = None
    comparisons: Annotated[list[Comparison], Field(max_length=10000)] = []
    external: Annotated[list[External], Field(max_length=100)] = []

    @model_validator(mode='after')
    def unique(self):
        if len({row.key for row in self.comparisons}) != len(self.comparisons):
            raise ValueError('同一系统行不得重复映射；请先核对原始资料')
        if (self.comparisons or self.external) and not self.token:
            raise ValueError('请先读取系统依据，再提交对照预览')
        return self


def row(key, category, label, value, unit, sources, *, line_id='', note='', target=None):
    return dict(key=key, category=category, label=label, value=str(value) if value is not None else None,
                unit=unit, sources=sources, line_id=line_id, note=note, target=target)


def batch_items(items, body, unit):
    pages = max(1, (len(items) + body.batch_size - 1) // body.batch_size)
    c.require(body.batch <= pages, '批次范围已变化，请返回第一批重新读取；原对照资料仍可保留', 422)
    start = (body.batch-1)*body.batch_size
    return items[start:start+body.batch_size], dict(number=body.batch, size=body.batch_size,
        total=len(items), pages=pages, unit=unit, query=body.query.strip())


def internal(db, month, cutoff, body):
    usage.ensure_schema(db)
    wh.ensure_schema(db)
    c.require(reporting.schema_ready(db.connection()), '期初核对需先完成每日填数迁移及证据保护', 503)
    guards.ensure_schema(db)
    all_items = list(db.scalars(select(CuttingOrder).where(CuttingOrder.factory_id == c.FACTORY).order_by(CuttingOrder.line_id)))
    # Preserve the established cutting -> source order -> fabric lock order.
    for item in all_items: orders.lock_source(db, item.line_id)
    wh.procurement.lock_factory(db)
    _, entries = wh.projection(db, 'fabric')
    history = usage.events(db)
    uses, _ = usage.replay(entries, history)
    price_map = usage.prices(history)
    previous = guards.latest(guards.history(db)).get(month)
    frozen = previous.data['snapshot'] if previous and previous.action == 'lock' else None
    frozen_rows = {r['issue_id']: r for r in (frozen or {}).get('allocations', [])}
    # Include historical (even subsequently voided) facts, not unrelated later orders.
    relevant = set(db.scalars(select(CuttingProductionEvent.line_id).where(
        CuttingProductionEvent.factory_id == c.FACTORY,
        CuttingProductionEvent.data['entry']['day'].as_string() <= cutoff).distinct()))
    for entry in entries.values():
        if entry['kind'] == 'ISSUE' and entry['business_date'] <= cutoff:
            request = entries.get(entry['data'].get('original_id'), {})
            line_id = request.get('data', {}).get('cutting_request', {}).get('line_id')
            if line_id: relevant.add(line_id)
    relevant.update(r['line_id'] for r in frozen_rows.values())
    items = [item for item in all_items if item.line_id in relevant]
    if body.query.strip():
        query = body.query.strip().casefold()
        items = [item for item in items if query in str(orders.revision(db, item)['data'].get('order', {})).casefold()
                 or query in item.line_id.casefold()]
    items, batch = batch_items(items, body, '订单')
    rows, notices = [], []
    seen = set()
    for item in items:
        report = closing.read(db, item.line_id, month, show_costs=False)
        report.pop('generated_at', None)
        name = orders.revision(db, item)['data'].get('order', {}).get('reference_no', item.line_id)
        for warning in report['issues']:
            notices.append(dict(message=f"{name}：{warning['message']}", line_id=item.line_id))
        for material in report['materials']:
            key = material['issue_id']; seen.add(key)
            context = material['context']; unit = context['unit']
            label = f"{name} / {context['task_name']} / {context['resource_name']} / {context['item_name']}"
            sources = ['原实发 '+key, '原批次 '+context['root_batch_id']]
            for document in report['usage_documents']:
                if document['context'].get('issue_id') == key:
                    sources.extend(f"耗用 {e['id']} / {e['day']} / {e['action']} / 替代 {e.get('replaces_document_id') or '—'} / 后继 {e.get('replaced_by_document_id') or '—'}" for e in document['history'])
            sources.extend(f"仓库 {e['id']} / {e['day']} / {e['kind']} / 原单 {e.get('original_id') or '—'} / {'已冲销' if e['reversed'] else '关联事实'}" for e in report['warehouse_documents']
                           if (e['context'].get('issue_id') == key or e['id'] == key) and e['day'] <= cutoff)
            normal = sum((wh.decimal(d['posted']['data']['entry']['consumed_quantity']) for d in uses.values()
                          if d['posted'] and d['posted']['data']['entry']['issue_id'] == key
                          and d['posted']['data']['entry']['day'] <= cutoff), Decimal(0))
            saved = frozen_rows.get(key)
            valid = bool(saved and wh.decimal(saved['ending_custody']) == wh.decimal(material['ending_quantity'])
                         and wh.decimal(saved['ending_normal_quantity']) == normal)
            if frozen and not valid:
                notices.append(dict(message=label+'：冻结期末与回放依据不一致或缺少该实发，须先核对', line_id=item.line_id))
            price = price_map.get(context['root_batch_id'])
            # Historical locked amounts use the frozen price, never today's attribution/price.
            pricing = saved.get('price') if valid else price
            price_entry = pricing['data']['entry'] if pricing else None
            currency = price_entry['currency'] if price_entry else '币种待确认'
            custody_cost = saved['amounts']['ending_custody'] if valid and saved.get('amounts') else (
                usage.amount(wh.decimal(material['ending_quantity']), price_entry['unit_cost']) if price_entry else None)
            cost_note = '上月有效冻结金额' if valid else '按当前已确认批次价试算，非冻结金额'
            if pricing: sources.append(pricing['id'])
            if valid: sources.append(previous.id)
            for suffix, category, value, measure, note in (
                ('custody', '现场余料', material['ending_quantity'], unit, '本厂' if context['execution']=='internal' else '外发'),
                ('unsigned', '已发未签', material['unsigned_quantity'], unit, '不计入现场余料'),
                ('custody_cost', '余料费用', custody_cost, currency, cost_note),
                ('wip', '在制正常耗用', saved['ending_wip_quantity'] if valid else None, unit, '仅采用紧邻上月有效锁月归属；未锁月为待确认'),
                ('wip_cost', '在制材料费用', saved.get('amounts', {}).get('ending_wip') if valid else None, currency, '不以当前累计归集替代历史月末在制')):
                rows.append(row(f'{suffix}:{key}', category, label, value, measure, sources, line_id=item.line_id, note=note,
                    target=dict(workspace='costs' if suffix in {'wip', 'wip_cost', 'custody_cost'} else 'materials',
                                kind='issue', id=key, line_id=item.line_id, month=month)))
        for task in report['production']:
            label = f"{name} / {task['task_name']} / {task['resource_name']}"
            documents = [d for d in report['production_documents'] if any(e['data']['entry']['task_id']==task['task_id'] and e['data']['entry']['day']<=cutoff for e in d['history'])]
            if not documents: continue
            production_sources=[f"{e['id']} / {e['data']['entry']['day']} / {e['action']}" for d in documents for e in d['history']]
            for field, title in [('closing_completed', '累计合格完成'), ('completed_unhanded', '完工未交接'),
                                 ('pending_return', '外发自报未收回'), ('pending_acceptance', '收回待验收')]:
                if field.startswith('pending') and task['execution'] != 'outsourced': continue
                rows.append(row(f'{field}:{item.line_id}:{task["task_id"]}', title, label, task[field], '套',
                                production_sources, line_id=item.line_id,
                                target=dict(workspace='reporting', kind='task', id=task['task_id'], line_id=item.line_id, month=month)))
            for part in task['loose']:
                rows.append(row(f'loose:{item.line_id}:{task["task_id"]}:{part["code"]}', '散片', label+' / '+part['name'],
                                part['quantity'], '片', [task['task_id'], part['code']], line_id=item.line_id,
                                target=dict(workspace='reporting', kind='task', id=task['task_id'], line_id=item.line_id, month=month)))
    for key in frozen_rows.keys() - seen:
        if frozen_rows[key]['line_id'] in {item.line_id for item in items}:
            notices.append(dict(message=f'上月冻结实发 {key} 在当前回放中缺失，须核对并按流程处理', line_id=''))
    if not frozen:
        notices.append(dict(message='紧邻上月无当前有效锁月版本，在制及其费用仍待月末归属确认；不能默认零。', line_id=''))
    return rows, notices, [], batch


def financial_trace(events, kind, identifiers):
    """Preserve full chains for selected documents, without counting old versions."""
    groups = []
    labels = {'save': '保存', 'submit': '提交', 'return': '退回', 'confirm': '确认',
              'reopen': '反结', 'reverse': '冲销登记'}
    for identifier in sorted(identifiers):
        chain = [e for e in events if e.document_id == identifier and e.action != 'price']
        current = chain[-1]
        history = []
        for event in chain:
            snapshot = event.data['snapshot']
            day = snapshot.get('day') or snapshot['month']
            history.append(dict(id=event.id, action=labels[event.action], day=day,
                actor=event.actor_name, actor_id=event.actor_id, date=event.created_at, reason=event.reason,
                amount=snapshot.get('amount', snapshot.get('total')), currency=snapshot.get('currency'),
                reference=snapshot.get('voucher_no') or event.data.get('input', {}).get('vendor_evidence', ''),
                replaces_document_id=event.data.get('input', {}).get('replaces_document_id'),
                target=dict(workspace=kind, id=identifier, event_id=event.id, month=day[:7])))
        groups.append(dict(key=kind+':'+identifier, document_id=identifier, kind=kind,
            label=current.data['snapshot'].get('resource_name', ''),
            state=labels[current.action], effective=current.action == 'confirm',
            history=history, target=history[-1]['target'], replacements=[dict(id=e.document_id,
                target=dict(workspace=kind, id=e.document_id, event_id=e.id,
                            month=(e.data['snapshot'].get('day') or e.data['snapshot']['month'])[:7]))
                for e in (payments.latest(events) if kind=='payment' else fees.latest(events)).values()
                if e.data.get('input', {}).get('replaces_document_id') == identifier]))
    return groups


def finance(db, month, cutoff, body):
    fee_events = fees.history(db); payment_events = payments.history(db)
    states = fees.latest(fee_events)
    rows, notices = [], []
    # Recomputed by business dates using today's effective evidence, not as-known-at-the-time balances.
    for event in states.values():
        if event.action != 'confirm': continue
        snapshot = event.data['snapshot']
        if snapshot['month'] > month: continue
        paid = Decimal(0); later = Decimal(0); sources = [event.id]
        for payment in payments.latest(payment_events).values():
            if payment.action != 'confirm': continue
            saved = payment.data['snapshot']
            for allocation in saved['allocations']:
                if allocation['settlement_id'] != event.document_id: continue
                sources.append(payment.id)
                if saved['day'] <= cutoff: paid += Decimal(allocation['amount'])
                else: later += Decimal(allocation['amount'])
        unpaid = Decimal(snapshot['total']) - paid
        c.require(unpaid >= 0, '切入前核销超过有效应付，请核对历史记录')
        rows.append(row('payable:'+event.document_id, '切入前未付', snapshot['resource_name']+' / '+event.document_id,
                        payments.fmt(unpaid), snapshot['currency'], sources,
                        target=dict(workspace='settlement', id=event.document_id, event_id=event.id, month=snapshot['month']),
                        note=f"结算所属月 {snapshot['month']}；有效应付 {snapshot['total']}；切入前已付 {payments.fmt(paid)}；切入后已付 {payments.fmt(later)}。待复核不计已付。"))
    _, accepted = fees.acceptance_rows(db, month, fee_events)
    for accepted_row in accepted:
        settled = 0; sources = [accepted_row['acceptance_event_id']]
        for event in states.values():
            if event.action != 'confirm' or event.data['snapshot']['month'] > month: continue
            for selected in event.data['snapshot']['rows']:
                if (selected['line_id'], selected['acceptance_id']) == (accepted_row['line_id'], accepted_row['acceptance_id']):
                    settled += selected['sets']; sources.append(event.id)
        quantity = accepted_row['accepted_sets'] - settled
        c.require(quantity >= 0, '验收与历史有效结算数量不一致，请核对')
        rows.append(row('acceptance:'+accepted_row['line_id']+':'+accepted_row['acceptance_id'], '切入前验收未结',
                        accepted_row['context']['resource_name']+' / '+accepted_row['context']['task_name'], quantity, '套', sources,
                        line_id=accepted_row['line_id'], note='按结算所属月筛选；可能已在切入后结算。未自动计费，超产及更正仍需另行核对。'))
        rows[-1]['target'] = dict(workspace='reporting', line_id=accepted_row['line_id'], kind='report',
                                 id=accepted_row['acceptance_id'], month=month)
        if accepted_row['correction_pending']:
            notices.append(dict(message='验收 '+accepted_row['acceptance_id']+' 存在更正草稿，须先处理', line_id=accepted_row['line_id']))
    for event in payments.latest(payment_events).values():
        if event.action in {'save', 'submit', 'return'} and event.data['snapshot']['day'] <= cutoff:
            notices.append(dict(message='切入前付款 '+event.document_id+' 尚未确认，不计已付', line_id=''))
        if event.action == 'confirm' and event.data['snapshot']['day'] <= cutoff:
            for allocation in event.data['snapshot']['allocations']:
                target = states.get(allocation['settlement_id'])
                if target and target.data['snapshot']['month'] > month:
                    notices.append(dict(message='付款 '+event.document_id+' 日期在切入前，但对应后期结算，未纳入本期初应付范围，须人工核对', line_id=''))
    for event in states.values():
        if event.action in {'save', 'submit', 'return'} and event.data['snapshot']['month'] <= month:
            notices.append(dict(message='结算 '+event.document_id+' 尚未确认，不计期初应付', line_id=''))
    fee_ids = {e.document_id for e in fee_events if e.action != 'price' and e.data['snapshot']['month'] <= month}
    # Later confirmed allocations are displayed, but later unconfirmed drafts are unrelated.
    payment_ids = {e.document_id for e in payment_events if e.data['snapshot']['day'] <= cutoff or
                   (e.action == 'confirm' and any(a['settlement_id'] in fee_ids for a in e.data['snapshot']['allocations']))}
    trace = financial_trace(fee_events, 'settlement', fee_ids) + financial_trace(payment_events, 'payment', payment_ids)
    units = [dict(key='row:'+r['key'], row=r) for r in rows] + [dict(key='trace:'+t['key'], trace=t) for t in trace]
    if body.query.strip():
        query = body.query.strip().casefold()
        units = [unit for unit in units if query in str(unit).casefold()]
    units, batch = batch_items(sorted(units, key=lambda u: u['key']), body, '明细／凭据链')
    return [u['row'] for u in units if 'row' in u], notices, [u['trace'] for u in units if 'trace' in u], batch


def preview(db, body):
    start = date.fromisoformat(body.month+'-01')
    c.require(date(2000, 2, 1) <= start <= wh.business_now().date(), '切入月份须在2000年2月至当前月份之间', 422)
    cutoff = start-timedelta(days=1)
    lock_transaction(db, 'cutting-master', c.FACTORY)
    with localcontext() as precision:
        precision.prec = 60
        rows, notices, history, batch = (internal if body.scope == 'internal' else finance)(db, cutoff.strftime('%Y-%m'), cutoff.isoformat(), body)
        c.require(len(rows) + sum(len(t['history']) for t in history) <= 10000,
                  '本批期初核对超过10000项，请减少每批数量或缩小查询范围；未返回部分结果', 422)
        # Keys can contain two source identifiers; never trust a browser-provided source quantity.
        token = periods.digest(dict(scope=body.scope, month=body.month, batch=body.batch, size=body.batch_size,
                                    query=body.query.strip(), rows=rows, notices=notices, history=history))
        c.require(not body.token or body.token == token, '系统依据已变化，请保留对照资料并重新读取系统依据')
        lookup = {r['key']: r for r in rows}
        for supplied in body.comparisons:
            c.require(supplied.key in lookup, '对照行已不存在或不属于当前范围，请重新映射', 422)
            actual = lookup[supplied.key]
            c.require(supplied.unit == actual['unit'], '单位或币种不一致，不自动换算', 422)
            actual.update(declared=wh.text(supplied.value), evidence=supplied.evidence,
                          difference=wh.text(supplied.value-Decimal(actual['value'])) if actual['value'] is not None else None)
        for actual in rows:
            actual['status'] = '待确认系统值' if actual['value'] is None else ('未核对' if 'declared' not in actual else
                              '一致' if Decimal(actual['difference']) == 0 else '有差异')
        return dict(month=body.month, start=start.isoformat(), cutoff=cutoff.isoformat(), scope=body.scope,
                    generated_at=wh.business_now().isoformat(), token=token, rows=rows, notices=notices, history=history, batch=batch,
                    external=[r.model_dump() for r in body.external],
                    counts={status: sum(r['status'] == status for r in rows) for status in ('未核对', '待确认系统值', '一致', '有差异')},
                    state='preparation_only', can_post=False)
