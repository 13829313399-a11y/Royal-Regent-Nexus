"""P4a live monthly reconciliation. No frozen periods, postings or payables.

Latest effective evidence is attributed by business day. Price is today's confirmed
batch price; monthly cents are the difference of rounded cumulative issue amounts.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, localcontext
import re

from app.models.cutting_ops import CuttingOrder
from app.services import cutting_ops as c, cutting_orders as orders, cutting_reporting as reporting, cutting_planning as planning
from app.services import cutting_usage as usage, warehouse_operations as wh
from app.services.transaction_lock import lock_transaction


def period(month, today):
    c.require(bool(re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month)), '请选择有效核对月份', 422)
    year, number = map(int, month.split('-'))
    c.require(2000 <= year <= 2100, '核对年份须在2000至2100年之间', 422)
    start = date(year, number, 1)
    c.require(start <= today, '未来月份尚无实际月结核对依据', 422)
    end = date(year, number, monthrange(year, number)[1])
    return start.isoformat(), end.isoformat(), min(end, today).isoformat()


def trace_scope(document, start, through):
    """Keep earlier evidence and its later corrections without counting history twice."""
    days = [e['data']['entry']['day'] for e in document['history']]
    effective = document['posted']
    effective_day = effective['data']['entry']['day'] if effective else None
    return dict(opening=bool(effective_day and effective_day < start),
                period=bool(effective_day and start <= effective_day <= through),
                earlier_history=any(day < start for day in days),
                period_history=any(start <= day <= through for day in days))


def physical_context(context):
    return {key: context.get(key) for key in ('task_id', 'task_name', 'resource_name', 'item_code', 'item_name',
                                             'unit', 'issue_id', 'request_id', 'root_batch_id')}


def production(docs, published, start, through):
    before, _ = reporting.replay(docs, (date.fromisoformat(start) - timedelta(days=1)).isoformat())
    after, _ = reporting.replay(docs, through)
    plans = {t['task_id']: t for t in (published or {}).get('tasks', [])}
    rows = []
    for task_id in sorted(set(before) | set(after) | set(plans)):
        plan = plans.get(task_id)
        context = (after.get(task_id) or before.get(task_id) or {}).get('context')
        if not context:
            context = dict(task_name=plan['name'], resource_name=plan['resource']['data']['name'],
                           execution=plan['resource']['data']['execution'], parts=[])
        opening, ending = before.get(task_id, {}), after.get(task_id, {})
        days = [d for d in (plan or {}).get('days', []) if start <= d['day'] <= through]
        reported = {d['posted']['data']['entry']['day'] for d in docs.values() if d['posted']
                    and d['posted']['data']['entry']['task_id'] == task_id
                    and d['posted']['data']['entry']['kind'] == 'daily'}
        row = dict(task_id=task_id, task_name=context['task_name'], resource_name=context['resource_name'],
                   execution=context['execution'], planned=sum(d['sets'] for d in days),
                   opening_completed=opening.get('completed', 0), closing_completed=ending.get('completed', 0),
                   completed_unhanded=ending.get('completed', 0) - ending.get('handed', 0),
                   pending_return=ending.get('claimed', 0) - ending.get('returned', 0),
                   pending_acceptance=ending.get('returned', 0) - ending.get('accepted', 0) - ending.get('rejected', 0),
                   missing_days=[d['day'] for d in days if d['sets'] > 0 and d['day'] not in reported],
                   loose=[dict(code=p['code'], name=p['name'], quantity=ending.get('loose', {}).get(p['code'], 0),
                               rejected=ending.get('part_rejected', {}).get(p['code'], 0) - opening.get('part_rejected', {}).get(p['code'], 0),
                               scrap=ending.get('part_scrap', {}).get(p['code'], 0) - opening.get('part_scrap', {}).get(p['code'], 0))
                          for p in context['parts']])
        for key in ('completed', 'handed', 'claimed', 'returned', 'accepted', 'rejected', 'daily_rejected', 'daily_scrap'):
            row[key] = ending.get(key, 0) - opening.get(key, 0)
        rows.append(row)
    return rows


def material_rows(entries, docs, line_id, start, through, price_map=None):
    """Per original issue, with signed custody separate from warehouse dispatch."""
    rows, costs, pending = [], {}, 0
    with localcontext() as precision:
        precision.prec = 60
        for issue in entries.values():
            request = entries.get(issue['data'].get('original_id'))
            if (issue['kind'] != 'ISSUE' or issue.get('reversed') or issue['business_date'] > through
                    or not request or request['data'].get('cutting_request', {}).get('line_id') != line_id):
                continue
            context = usage.issue_context(entries, issue['id'])
            sums = {part: dict(received=Decimal(0), returned=Decimal(0), consumed=Decimal(0), loss=Decimal(0))
                    for part in ('opening', 'period')}
            for movement in usage.movements(entries, issue['id']):
                day = movement['business_date']
                if day <= through:
                    part = 'opening' if day < start else 'period'
                    key = 'received' if movement['kind'] == 'CUTTING_RECEIPT' else 'returned'
                    sums[part][key] += wh.decimal(movement['data']['quantity'])
            for document in docs.values():
                event = document['posted']
                if not event or event['data']['entry']['issue_id'] != issue['id']:
                    continue
                entry = event['data']['entry']
                if entry['day'] <= through:
                    part = 'opening' if entry['day'] < start else 'period'
                    sums[part]['consumed'] += wh.decimal(entry['consumed_quantity'])
                    sums[part]['loss'] += wh.decimal(entry['loss_quantity'])
            opening, current = sums['opening'], sums['period']
            balance = opening['received'] - opening['returned'] - opening['consumed'] - opening['loss']
            end = balance + current['received'] - current['returned'] - current['consumed'] - current['loss']
            received = opening['received'] + current['received']
            row = dict(issue_id=issue['id'], context=context, opening_quantity=wh.text(balance),
                       issued_quantity=issue['data']['quantity'] if issue['business_date'] >= start else '0',
                       unsigned_quantity=wh.text(wh.decimal(issue['data']['quantity']) - received),
                       received_quantity=wh.text(current['received']), returned_quantity=wh.text(current['returned']),
                       consumed_quantity=wh.text(current['consumed']), loss_quantity=wh.text(current['loss']),
                       ending_quantity=wh.text(end))
            if price_map is not None:
                price = price_map.get(context['root_batch_id'])
                row.update(price=price, normal_cost=None, loss_cost=None)
                if price:
                    entry = price['data']['entry']
                    currency = entry['currency']
                    bucket = costs.setdefault(currency, dict(normal=Decimal(0), loss=Decimal(0)))
                    for field, key in (('normal_cost', 'consumed'), ('loss_cost', 'loss')):
                        # Differences of cumulative rounded costs conserve cents across months.
                        amount = wh.decimal(usage.amount(opening[key] + current[key], entry['unit_cost'])) - wh.decimal(usage.amount(opening[key], entry['unit_cost']))
                        row[field] = format(amount, '.2f')
                        bucket['normal' if key == 'consumed' else 'loss'] += amount
                elif current['consumed'] + current['loss'] > 0:
                    pending += 1
            rows.append(row)
    return rows, {currency: {key: format(value, '.2f') for key, value in amounts.items()} for currency, amounts in costs.items()}, pending


def read(db, line_id, month, *, show_costs=False):
    now = wh.business_now()
    start, end, through = period(month, now.date())
    c.require(reporting.schema_ready(db.connection()), '月度生产核对需先完成0155迁移及证据保护', 503)
    usage.ensure_schema(db)
    wh.ensure_schema(db)
    lock_transaction(db, 'cutting-master', c.FACTORY)
    wh.procurement.lock_factory(db)
    order = db.get(CuttingOrder, line_id)
    c.require(order is not None and order.factory_id == c.FACTORY, '请先签收当前裁床订单，再进行月度核对', 404)
    data = orders.revision(db, order)['data']
    published = data.get('planning', {}).get('published')
    # These cooperating locks fence reports, allocations and all linked warehouse writes.
    _, entries = wh.projection(db, 'fabric')
    history = usage.events(db)
    uses, _ = usage.replay(entries, history)
    reports = reporting.documents(reporting.events(db, line_id))
    production_rows = production(reports, published, start, through)
    materials, costs, pending = material_rows(entries, uses, line_id, start, through, usage.prices(history) if show_costs else None)
    issues = []
    def flag(code, message, workspace, document_id='', *, task_id='', issue_id=''):
        issues.append(dict(code=code, message=message, workspace=workspace, document_id=document_id,
                           task_id=task_id, issue_id=issue_id))
    source_changed = order.dispatch_id != getattr(orders.latest(db, line_id), 'id', None)
    plan_state = planning.summary(db, data, source_changed)
    if source_changed:
        flag('source_changed', '来源订单已变化，当前核对保留已签收及历史证据，请先核对新下发', 'planning')
    if not published:
        flag('no_plan', '尚无已发布计划，无法判断计划和漏报范围', 'planning')
    elif plan_state['published_stale']:
        flag('plan_stale', '已发布计划依据已变化，需重新核对；本期计划及漏报提示仅作参考，实际生产数量仍按生效记录统计', 'planning')
    for row in production_rows:
        if row['missing_days']:
            flag('missing_daily', row['task_name'] + ' 有计划但未填日报：' + '、'.join(row['missing_days']), 'reporting', task_id=row['task_id'])
        if row['execution'] == 'outsourced' and row['pending_return'] > 0:
            flag('outsourced_unreturned', f"{row['task_name']} 截至期末自报未收回 {row['pending_return']} 套", 'reporting', task_id=row['task_id'])
        if row['execution'] == 'outsourced' and row['pending_acceptance'] > 0:
            flag('outsourced_reconcile', f"{row['task_name']} 截至期末收回待验收 {row['pending_acceptance']} 套", 'reporting', task_id=row['task_id'])
    for row in materials:
        if wh.decimal(row['unsigned_quantity']) > 0:
            flag('unsigned_material', row['context']['item_name'] + ' 截至期末有已发未签物料', 'materials', issue_id=row['issue_id'])
    production_trace = []
    for document in reports.values():
        scope = trace_scope(document, start, through)
        if not (scope['earlier_history'] or scope['period_history']):
            continue
        production_trace.append(dict(document, scope=scope))
        if document['draft'] and (scope['opening'] or scope['period'] or document['draft']['data']['entry']['day'] <= through):
            flag('report_draft', '日报或更正草稿尚未提交，当前仍按已生效记录核对', 'reporting', document['document_id'],
                 task_id=document['draft']['data']['entry']['task_id'])
    usage_trace = []
    for identifier, document in uses.items():
        if document['history'][0]['line_id'] != line_id:
            continue
        scope = trace_scope(document, start, through)
        if not (scope['earlier_history'] or scope['period_history']):
            continue
        usage_trace.append(dict(document_id=identifier, effective=bool(document['posted']), scope=scope,
            context=physical_context(document['history'][0]['data']['context']),
            history=[dict(id=e['id'], action=e['action'], version=e['version'], day=e['data']['entry']['day'],
                          entry=e['data']['entry'], actor=e['actor'], date=e['date'], reason=e['reason'],
                          replaces_document_id=e['data'].get('replaces_document_id'),
                          replaced_by_document_id=e['data'].get('replaced_by_document_id')) for e in document['history']]))
    # Follow original-id links so voids/corrections are visible without other orders' data.
    related = {e['id'] for e in entries.values() if e['kind'] == 'REQUEST'
               and e['data'].get('cutting_request', {}).get('line_id') == line_id}
    for entry in entries.values():
        if entry['data'].get('original_id') in related:
            related.add(entry['id'])
    def warehouse_context(identifier):
        seen = set()
        while identifier in entries and identifier not in seen:
            seen.add(identifier)
            entry = entries[identifier]
            if entry['kind'] == 'ISSUE':
                return physical_context(usage.issue_context(entries, identifier))
            if entry['kind'] == 'REQUEST':
                context = entry['data'].get('cutting_request', {})
                return dict(physical_context(context), request_id=identifier, item_name=entry['data'].get('item_name'), unit=entry['data'].get('unit'))
            identifier = entry['data'].get('original_id')
        return {}
    warehouse_trace = [dict(id=e['id'], kind=e['kind'], day=e['business_date'], original_id=e['data'].get('original_id'),
                            quantity=e['data'].get('quantity'), unit=e['data'].get('unit'), reversed=e.get('reversed', False),
                            context=warehouse_context(e['id']),
                            scope='opening' if e['business_date'] < start else 'period' if e['business_date'] <= through else 'later',
                            actor=e['actor_name'], date=e['occurred_at'], reason=e['data'].get('reason', ''))
                       for e in entries.values() if e['id'] in related]
    result = dict(line_id=line_id, month=month, start=start, end=end, through=through,
                  generated_at=now.isoformat(), state='preview', partial=through != end,
                  basis=dict(order_version=order.version, plan_version=(published or {}).get('version'),
                             usage_revision=max((e['version'] for e in history), default=0),
                             warehouse_revision=max((e['sequence'] for e in entries.values()), default=0)),
                  plan_stale=plan_state['published_stale'], production=production_rows, materials=materials, issues=issues,
                  production_documents=production_trace, usage_documents=usage_trace, warehouse_documents=warehouse_trace)
    if show_costs:
        if pending:
            flag('pending_price', f'本期有{pending}笔实发耗用待计价，已计价金额不代表完整费用', 'costs')
        flag('period_wip_unconfirmed', '历史月末在制归属及结转尚未冻结，不能用当前累计归属代替', 'costs')
        # Current attribution is a separate follow-up list, never a historical WIP balance.
        allocation = usage.read(db, line_id, show_costs=True)['cost_allocation']
        relevant = {r['issue_id'] for r in materials}
        review = [dict(task_name=g['context']['task_name'], resource_name=g['context']['resource_name'], status=g['status'], reasons=g['reasons'])
                  for g in allocation['groups'] if relevant.intersection(r['issue_id'] for r in g['rows'])]
        result.update(costs=costs, pending_pricing=pending, wip_status='not_frozen', price_basis='current_confirmed_batch_price',
                      current_allocation_review=review)
    return result
