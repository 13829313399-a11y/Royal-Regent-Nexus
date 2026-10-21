"""Read-only workspace projections over the existing cutting evidence.

No new ledger, stock mutation or grant. Totals are calculated before pagination;
financial sources are removed before searching/paging for unauthorized readers.
"""
from datetime import timedelta
import hashlib
import json
from decimal import Decimal, localcontext
from sqlalchemy import select, func, literal, union_all, cast, JSON, inspect, DateTime, case
from app.models.cutting_ops import (
    CuttingMaster, CuttingRevision, CuttingOrder, CuttingOrderRevision,
    CuttingProductionEvent,
)
from app.models.cutting_material_usage import CuttingMaterialEvent
from app.models.cutting_period import CuttingPeriodEvent
from app.models.cutting_settlement import CuttingSettlementEvent
from app.models.cutting_payment import CuttingPaymentEvent
from app.models.customer_order_ledger import OrderLedgerDispatch, OrderLedgerLine
from app.models.warehouse_operations import WarehouseOperation
from app.services import cutting_ops as c, cutting_orders as orders, cutting_planning as plans
from app.services import cutting_reporting as reporting, cutting_usage as usage
from app.services.transaction_lock import lock_transaction
from app.services import cutting_read_batch


def paged(rows, page, **extra):
    return dict(data=rows[(page-1)*50:page*50], total=len(rows), page=page, page_size=50, **extra)


def sources(db, q=''):
    newest = select(OrderLedgerDispatch.line_id, func.max(OrderLedgerDispatch.version).label('version')).where(
        OrderLedgerDispatch.factory_id == c.FACTORY, OrderLedgerDispatch.recipient == 'cutting'
    ).group_by(OrderLedgerDispatch.line_id).subquery()
    query = select(OrderLedgerDispatch, CuttingOrder, CuttingOrderRevision).join(newest,
        (newest.c.line_id == OrderLedgerDispatch.line_id) & (newest.c.version == OrderLedgerDispatch.version)
    ).join(OrderLedgerLine).outerjoin(CuttingOrder, CuttingOrder.line_id == OrderLedgerDispatch.line_id).outerjoin(
        CuttingOrderRevision, (CuttingOrderRevision.line_id == CuttingOrder.line_id) &
        (CuttingOrderRevision.version == CuttingOrder.version)
    ).where(OrderLedgerDispatch.factory_id == c.FACTORY, OrderLedgerDispatch.recipient == 'cutting')
    if q.strip():
        query = query.where(OrderLedgerLine.reference_no.contains(q.strip(), autoescape=True) |
                            OrderLedgerLine.product_no.contains(q.strip(), autoescape=True))
    yield from orders.planning_rows(db, query.order_by(OrderLedgerDispatch.created_at.desc(), OrderLedgerDispatch.id))


def order_identity(dispatch):
    return dict(line_id=dispatch.line_id, order_no=dispatch.snapshot.get('reference_no', ''),
        customer=dispatch.snapshot.get('customer_name', ''), item_no=dispatch.snapshot.get('product_no', ''))


def production_sources(db, q='', *, snapshot=None):
    ready = reporting.schema_ready(db.connection()) if snapshot is not None else True
    for batch in cutting_read_batch.batches(sources(db, q)):
        ids = [order.line_id for _, order, revision in batch if order and revision
               and (snapshot is None or order.line_id in snapshot['issues'])]
        docs, versions = cutting_read_batch.production(db, ids, revisions=snapshot is not None) if ready else ({}, {})
        if snapshot is not None:
            snapshot['production'] = (ready, docs, versions)
        for dispatch, order, revision in batch:
            yield dispatch, order, revision, docs.get(order.line_id, {}) if order else {}


def scheduling(db, q='', status='', bucket='', page=1, plan_status=''):
    lock_transaction(db, 'cutting-master', c.FACTORY)
    from app.services.cutting_materials import receipt_reader
    receipt_entries = receipt_reader(db)
    stats = dict(total=0, scheduled=0, unscheduled=0, partial=0, review=0)
    rows = []
    for dispatch, order, revision in sources(db, q):
        if dispatch.snapshot.get('status') == 'cancelled':
            continue
        data = revision.data if revision else {}
        needs = order is None or order.dispatch_id != dispatch.id
        if status and orders.workflow_status(data, dispatch.snapshot.get('status'), needs) != status:
            continue
        summary = plans.summary(db, data, needs, receipt_entries=receipt_entries)
        if plan_status and plan_status not in summary['states']:
            continue
        published = data.get('planning', {}).get('published') or {}
        quantity = sum(d['sets'] for t in published.get('tasks', []) for d in t['days'])
        scheduled = bool(quantity and not summary['published_stale'])
        stats['total'] += 1
        stats['scheduled' if scheduled else 'unscheduled'] += 1
        stats['partial'] += int(scheduled and quantity < (data.get('target_sets') or 0))
        stats['review'] += int(summary['published_stale'])
        if bucket and bucket != ('scheduled' if scheduled else 'unscheduled'):
            continue
        if (page-1)*50 <= len(rows) < page*50:
            current = None if revision is None else dict(version=revision.version, data=data,
                actor_id=revision.actor_id, created_at=revision.created_at, reason=revision.reason)
            rows.append(orders.view(db, dispatch, (order, current), summary))
        else:
            rows.append(None)
    return dict(data=[r for r in rows[(page-1)*50:page*50] if r is not None], total=len(rows),
                page=page, page_size=50, stats=stats)


def task_board(db, day, q='', execution='', scope='daily', page=1):
    c.require(reporting.schema_ready(db.connection()), '每日填数依据尚未就绪', 503)
    lock_transaction(db, 'cutting-master', c.FACTORY)
    from app.services.cutting_materials import receipt_reader
    receipt_entries = receipt_reader(db)
    all_rows = []
    previous = (day-timedelta(days=1)).isoformat()
    date = day.isoformat()
    today = plans.business_today().isoformat()
    for dispatch, order, revision, docs in production_sources(db, q):
        if not order or not revision:
            continue
        data = revision.data
        published = data.get('planning', {}).get('published') or {}
        summary = plans.summary(db, data, order.dispatch_id != dispatch.id, receipt_entries=receipt_entries)
        valid = dispatch.snapshot.get('status') != 'cancelled' and not summary['published_stale']
        balances, _ = reporting.replay(docs, date)
        before, _ = reporting.replay(docs, previous)
        task_map = {t['task_id']: t for t in published.get('tasks', [])}
        task_ids = dict.fromkeys([*task_map, *balances])
        for task_id in task_ids:
            task = task_map.get(task_id)
            balance = balances.get(task_id, {})
            context = balance.get('context', {})
            executor = context.get('execution') or (task['resource']['data']['execution'] if task else '')
            if execution and execution != executor:
                continue
            days = task['days'] if task else []
            planned = sum(d['sets'] for d in days if d['day'] == date) if valid else 0
            effective = [d['posted'] for d in docs.values() if d['posted'] and
                d['posted']['data']['entry']['task_id'] == task_id and d['posted']['data']['entry']['day'] == date]
            reported = any(e['data']['entry']['kind'] == 'daily' for e in effective)
            due = max((d['day'] for d in days), default='')
            reasons = []
            if task and summary['published_stale']:
                reasons.append('计划依据已变更')
            target = task['target_sets'] if task else context.get('task_target', 0)
            if task and valid and due and due < min(date, today) and balance.get('completed', 0) < target:
                reasons.append('计划已逾期未完成')
            if planned and task and task.get('actual_review_pending', True):
                reasons.append('物料及前置条件待实际核定')
            if balance.get('returned', 0) > balance.get('accepted', 0) + balance.get('rejected', 0):
                reasons.append('外发收回待验收')
            if planned and date < today and not reported:
                reasons.append('已结束业务日未填报')
            old = before.get(task_id, {})
            all_rows.append(dict(**order_identity(dispatch), task_id=task_id,
                task_name=task['name'] if task else context.get('task_name', task_id),
                resource_name=context.get('resource_name') or (task['resource']['data']['name'] if task else ''),
                execution=executor, planned=planned, reported=reported, has_fact=bool(effective),
                day_completed=balance.get('completed', 0)-old.get('completed', 0),
                day_handed=balance.get('handed', 0)-old.get('handed', 0),
                completed=balance.get('completed', 0), target_sets=target,
                returned=balance.get('returned', 0), accepted=balance.get('accepted', 0),
                historical=not task or not valid, reasons=reasons))
    daily = [r for r in all_rows if r['planned'] > 0]
    stats = dict(tasks=len(daily), reported=sum(r['reported'] for r in daily),
        unreported=sum(not r['reported'] for r in daily), planned=sum(r['planned'] for r in daily),
        completed=sum(r['day_completed'] for r in all_rows), handed=sum(r['day_handed'] for r in all_rows),
        abnormal=sum(bool(r['reasons']) for r in all_rows),
        unplanned_facts=sum(r['has_fact'] and not r['planned'] for r in all_rows))
    rows = [r for r in all_rows if
        (scope == 'daily' and r['planned']) or
        (scope == 'abnormal' and r['reasons']) or
        (scope == 'unreported' and r['planned'] and not r['reported']) or
        (scope == 'reported' and r['planned'] and r['reported']) or
        (scope == 'history' and r['has_fact'] and not r['planned'])]
    return paged(rows, page, stats=stats, day=date)


def material_snapshot(db):
    usage.ensure_schema(db)
    usage.wh.ensure_schema(db)
    lock_transaction(db, 'cutting-master', c.FACTORY)
    usage.wh.procurement.lock_factory(db)
    _, entries = usage.wh.projection(db, 'fabric')
    history = usage.events(db)
    docs, balances = usage.replay(entries, history)
    by_issue, by_document, by_history, by_price = {}, {}, {}, {}
    for issue in entries.values():
        if issue['kind'] == 'ISSUE':
            request = entries.get(issue['data'].get('original_id'), {})
            line = request.get('data', {}).get('cutting_request', {}).get('line_id')
            if line:
                by_issue.setdefault(line, []).append(issue)
    for identifier, doc in docs.items():
        by_document.setdefault(doc['history'][0]['line_id'], []).append((identifier, doc))
    for event in history:
        by_history.setdefault(event['line_id'], []).append(event)
        if event['action'] == 'price':
            by_price.setdefault(event['data']['context']['root_batch_id'], []).append(event)
    return dict(projection=(entries, history, docs, balances, usage.prices(history)),
        issues=by_issue, documents=by_document, history=by_history, prices=by_price,
        revision=max((e['version'] for e in history), default=0))


def inventory(db, q='', execution='', page=1, view='issues'):
    snapshot = material_snapshot(db)
    rows = []
    units = {}
    for dispatch, order, _ in sources(db, q):
        if not order:
            continue
        if dispatch.line_id not in snapshot['issues']:
            continue
        ledger = usage.read(db, dispatch.line_id, _snapshot=snapshot)
        for issue in ledger['issues']:
            if issue['reversed'] or (execution and issue['context']['execution'] != execution):
                continue
            row = dict(**order_identity(dispatch), **issue)
            row['unsigned_quantity'] = usage.wh.text(Decimal(issue['issued_quantity'])-Decimal(issue['received_quantity']))
            rows.append(row)
            totals = units.setdefault(issue['context']['unit'], {k: Decimal(0) for k in
                ('received_quantity', 'returned_quantity', 'consumed_quantity', 'loss_quantity', 'remaining_quantity', 'unsigned_quantity')})
            with localcontext() as ctx:
                ctx.prec = 60
                for key in totals:
                    totals[key] += Decimal(row[key])
    if view == 'orders':
        grouped = {}
        quantities = ('issued_quantity','received_quantity','returned_quantity','consumed_quantity','loss_quantity','remaining_quantity','unsigned_quantity')
        for row in rows:
            context = row['context']
            material = context['warehouse_material']
            key = (row['line_id'], context['dispatch_id'], context['bom_id'], context['bom_version'],
                context['task_id'], context['resource_id'], context['resource_version'],
                material['id'], material['revision'], context['unit'])
            target = grouped.setdefault(key, dict(row, issue_id='|'.join(map(str,key)), issue_count=0,
                **{k:'0' for k in quantities}))
            target['issue_count'] += 1
            with localcontext() as ctx:
                ctx.prec=60
                for field in quantities:
                    target[field] = usage.wh.text(Decimal(target[field])+Decimal(row[field]))
        rows = list(grouped.values())
    return paged(rows, page, units={unit: {k: usage.wh.text(v) for k, v in totals.items()} for unit, totals in units.items()})


def cost_overview(db, q='', page=1):
    snapshot = material_snapshot(db)
    rows, currencies = [], {}
    pending = 0
    for dispatch, order, _, _reports in production_sources(db, q, snapshot=snapshot):
        if not order:
            continue
        if dispatch.line_id not in snapshot['issues']:
            continue
        ledger = usage.read(db, dispatch.line_id, show_costs=True, _snapshot=snapshot)
        if not ledger['issues']:
            continue
        pending += ledger['pending_pricing']
        normal, loss = {}, {}
        for group in ledger['cost_summary']['tasks']:
            for currency, values in group['costs'].items():
                with localcontext() as ctx:
                    ctx.prec = 60
                    normal[currency] = normal.get(currency, Decimal(0)) + Decimal(values['normal'])
                    loss[currency] = loss.get(currency, Decimal(0)) + Decimal(values['loss'])
        groups = ledger.get('cost_allocation', {}).get('groups', [])
        completed, wip, incomplete = {}, {}, set()
        for group in groups:
            for currency, values in group['costs'].items():
                if values['completed'] is None or values['wip'] is None:
                    incomplete.add(currency)
                else:
                    with localcontext() as ctx:
                        ctx.prec = 60
                        completed[currency] = completed.get(currency, Decimal(0))+Decimal(values['completed'])
                        wip[currency] = wip.get(currency, Decimal(0))+Decimal(values['wip'])
        for currency in normal:
            total = currencies.setdefault(currency, dict(normal=Decimal(0), loss=Decimal(0), completed=Decimal(0), wip=Decimal(0)))
            with localcontext() as ctx:
                ctx.prec = 60
                total['normal'] += normal[currency]
                total['loss'] += loss[currency]
                for field, values in (('completed', completed), ('wip', wip)):
                    total[field] = None if total[field] is None or currency in incomplete else total[field]+values.get(currency, Decimal(0))
        rows.append(dict(**order_identity(dispatch), pending_pricing=ledger['pending_pricing'],
            normal={k: usage.wh.text(v) for k, v in normal.items()}, loss={k: usage.wh.text(v) for k, v in loss.items()},
            completed={k: None if k in incomplete else usage.wh.text(completed.get(k, Decimal(0))) for k in normal},
            wip={k: None if k in incomplete else usage.wh.text(wip.get(k, Decimal(0))) for k in normal},
            allocation_pending=sum(g['status'] != 'confirmed' for g in groups)))
    return paged(rows, page, pending_pricing=pending,
        currencies={key: {k: None if v is None else usage.wh.text(v) for k, v in values.items()} for key, values in currencies.items()})


def master_summary(db):
    rows = db.execute(select(CuttingMaster.kind, CuttingRevision.status, func.count()).join(
        CuttingRevision, (CuttingRevision.master_id == CuttingMaster.id) &
        (CuttingRevision.version == CuttingMaster.version)).where(CuttingMaster.factory_id == c.FACTORY)
        .group_by(CuttingMaster.kind, CuttingRevision.status))
    stats = dict(bom=0, draft=0, material=0, resource=0)
    for kind, status, count in rows:
        if kind == 'bom':
            stats['bom'] += count
            if status == 'draft':
                stats['draft'] += count
        elif status == 'active':
            stats[kind] += count
    return stats


def monthly(db, user, month):
    lock_transaction(db, 'cutting-master', c.FACTORY)
    existing = set(inspect(db.connection()).get_table_names())
    result = dict(month=month, domains=[], frozen=[])
    definitions = [
        ('period', CuttingPeriodEvent, 'cost_read', 'lock', CuttingPeriodEvent.month),
        ('settlement', CuttingSettlementEvent, 'settlement_read', 'confirm', CuttingSettlementEvent.document_id),
        ('payment', CuttingPaymentEvent, 'payment_read', 'confirm', CuttingPaymentEvent.document_id),
    ]
    for name, model, permission, frozen_action, key in definitions:
        if not c.allowed(user, permission):
            result['domains'].append(dict(kind=name, available=False, reason='无查询权限'))
            continue
        if model.__tablename__ not in existing:
            result['domains'].append(dict(kind=name, available=False, reason='尚未完成迁移'))
            continue
        latest = select(key.label('key'), func.max(model.version).label('version')).where(
            model.factory_id == c.FACTORY, model.action != 'price').group_by(key).subquery()
        current = list(db.scalars(select(model).join(latest,
            (key == latest.c.key) & (model.version == latest.c.version)).where(model.factory_id == c.FACTORY)))
        def event_month(event):
            return event.month if name == 'period' else (
                event.data.get('snapshot', {}).get('day', '')[:7] if name == 'payment'
                else event.data.get('snapshot', {}).get('month', ''))
        states = {}
        for event in current:
            if event_month(event) == month:
                states[event.action] = states.get(event.action, 0)+1
        result['domains'].append(dict(kind=name, available=True, states=states, count=sum(states.values())))
        current_ids = {event.id for event in current}
        month_field = model.month if name == 'period' else (
            func.substr(model.data['snapshot']['day'].as_string(), 1, 7) if name == 'payment'
            else model.data['snapshot']['month'].as_string())
        events = db.scalars(select(model).where(model.factory_id == c.FACTORY, model.action == frozen_action,
            month_field == month).order_by(model.version.desc()).limit(201))
        rows = list(events)
        c.require(len(rows) <= 200, '本月冻结历史超过 200 条，请通过操作日志按来源分页追溯。', 422)
        result['frozen'].extend(dict(kind=name, event_id=e.id, document_id=e.month if name == 'period' else e.document_id,
            version=e.version, month=month, valid=e.id in current_ids, actor=e.actor_name, date=e.created_at) for e in rows)
    return result


def activity(db, user, source='', q='', page=1, expected_token='', order_q='', month=''):
    """Union only authorized immutable metadata. Never serialize raw snapshots."""
    lock_transaction(db, 'cutting-master', c.FACTORY)
    existing = set(inspect(db.connection()).get_table_names())
    empty = literal('')
    queries = []
    def add(model, name, identifier, line, action, date, document, reason, reference=empty, month=empty, predicate=None, join=None):
        if model.__tablename__ not in existing or (source and source != name):
            return
        query = select(literal(name).label('source'), identifier.label('id'), line.label('line_id'),
            model.version.label('version'), action.label('action'), model.created_at.label('occurred_at'),
            date.label('business_day'), document.label('document_id'), model.actor_id.label('actor'),
            reason.label('reason'), reference.label('related_id'), month.label('month'))
        if join is not None:
            query = query.select_from(join)
        if hasattr(model, 'factory_id'):
            query = query.where(model.factory_id == c.FACTORY)
        if predicate is not None:
            query = query.where(predicate)
        queries.append(query)
    add(CuttingRevision, 'master', CuttingRevision.master_id, empty, CuttingRevision.status, empty,
        CuttingRevision.master_id, CuttingRevision.reason, predicate=CuttingMaster.factory_id == c.FACTORY,
        join=CuttingRevision.__table__.join(CuttingMaster))
    add(CuttingOrderRevision, 'order', CuttingOrderRevision.line_id, CuttingOrderRevision.line_id, literal('revision'),
        empty, CuttingOrderRevision.line_id, CuttingOrderRevision.reason, predicate=CuttingOrder.factory_id == c.FACTORY,
        join=CuttingOrderRevision.__table__.join(CuttingOrder))
    e = CuttingProductionEvent
    add(e, 'production', e.id, e.line_id, e.action, e.data['entry']['day'].as_string(), e.document_id, e.reason)
    e = CuttingMaterialEvent
    add(e, 'material', e.id, e.line_id, e.action, e.data['entry']['day'].as_string(), e.document_id, e.reason,
        case((e.action == 'allocate', e.data['replaces_id'].as_string()), else_=e.data['replaces_document_id'].as_string()),
        predicate=None if c.allowed(user, 'cost_read') else ~e.action.in_(['price', 'allocate']))
    if c.allowed(user, 'cost_read'):
        e = CuttingPeriodEvent
        add(e, 'period', e.id, empty, e.action, empty, e.month, e.reason, month=e.month)
    if c.allowed(user, 'settlement_read'):
        e = CuttingSettlementEvent
        add(e, 'settlement', e.id, e.data['line_id'].as_string(), e.action, empty, e.document_id, e.reason,
            e.data['replaces_id'].as_string(), month=e.data['snapshot']['month'].as_string())
    if c.allowed(user, 'payment_read'):
        e = CuttingPaymentEvent
        add(e, 'payment', e.id, empty, e.action, e.data['input']['day'].as_string(), e.document_id, e.reason,
            e.data['input']['replaces_document_id'].as_string(), month=func.substr(e.data['input']['day'].as_string(), 1, 7))
    if WarehouseOperation.__tablename__ in existing and source in ('', 'warehouse'):
        w = WarehouseOperation
        payload = cast(w.payload_json, JSON) if db.bind.dialect.name != 'sqlite' else func.json(w.payload_json, type_=JSON)
        related = select(w.id.label('id'), payload['cutting_request']['line_id'].as_string().label('line_id')).where(
            w.factory_id == c.FACTORY, w.warehouse == 'fabric', w.kind == 'REQUEST',
            payload['cutting_request']['line_id'].as_string().is_not(None)).cte('cutting_linked', recursive=True)
        related = related.union_all(select(w.id, related.c.line_id).join(related,
            payload['original_id'].as_string() == related.c.id).where(w.factory_id == c.FACTORY,
            w.warehouse == 'fabric', w.kind != 'COMMAND_ABANDONED'))
        queries.append(select(literal('warehouse').label('source'), w.id.label('id'), related.c.line_id.label('line_id'),
            w.sequence.label('version'), w.kind.label('action'), w.occurred_at.label('occurred_at'),
            w.business_date.label('business_day'), w.id.label('document_id'), w.actor_id.label('actor'),
            payload['reason'].as_string().label('reason'), payload['original_id'].as_string().label('related_id'),
            func.substr(w.business_date, 1, 7).label('month')).join(related, related.c.id == w.id))
    if not queries:
        return paged([], page)
    combined = union_all(*queries).subquery()
    orders_ready = OrderLedgerLine.__tablename__ in existing
    query = (select(combined, OrderLedgerLine.reference_no.label('order_no')).outerjoin(
        OrderLedgerLine, (OrderLedgerLine.id == combined.c.line_id) & (OrderLedgerLine.factory_id == c.FACTORY))
        if orders_ready else select(combined, empty.label('order_no')))
    if month:
        query = query.where((combined.c.month == month) |
            (func.substr(combined.c.business_day, 1, 7) == month))
    if order_q.strip() and not orders_ready:
        query = query.where(literal(False))
    elif order_q.strip():
        matched_lines = select(OrderLedgerLine.id).where(
            OrderLedgerLine.factory_id == c.FACTORY,
            OrderLedgerLine.reference_no.contains(order_q.strip(), autoescape=True) |
            OrderLedgerLine.product_no.contains(order_q.strip(), autoescape=True))

        def array_values(value, name):
            if db.bind.dialect.name == 'sqlite':
                return func.json_each(value).table_valued('key', 'value').alias(name)
            from sqlalchemy.dialects.postgresql import JSONB
            return func.jsonb_array_elements(cast(value, JSONB)).table_valued('value').alias(name)

        def json_value(column):
            return func.json(column, type_=JSON) if db.bind.dialect.name == 'sqlite' else cast(column, JSON)

        fee = CuttingSettlementEvent
        fee_rows = array_values(fee.data['snapshot']['rows'], 'fee_order_rows')
        matching_fees = select(fee.id).where(fee.factory_id == c.FACTORY,
            select(literal(1)).select_from(fee_rows).where(
                json_value(fee_rows.c.value)['line_id'].as_string().in_(matched_lines)).exists())
        payment = CuttingPaymentEvent
        allocations = array_values(payment.data['snapshot']['allocations'], 'payment_order_rows')
        matching_payments = select(payment.id).where(payment.factory_id == c.FACTORY,
            select(literal(1)).select_from(allocations).where(
                json_value(allocations.c.value)['settlement_event_id'].as_string().in_(matching_fees)).exists())
        matches = combined.c.line_id.in_(matched_lines)
        if fee.__tablename__ in existing:
            if c.allowed(user, 'settlement_read'):
                matches = matches | ((combined.c.source == 'settlement') & combined.c.id.in_(matching_fees))
            if payment.__tablename__ in existing and c.allowed(user, 'payment_read'):
                matches = matches | ((combined.c.source == 'payment') & combined.c.id.in_(matching_payments))
        query = query.where(matches)
    if q.strip():
        query = query.where(combined.c.document_id.contains(q.strip(), autoescape=True) |
            combined.c.actor.contains(q.strip(), autoescape=True) | combined.c.reason.contains(q.strip(), autoescape=True))
    filtered = query.subquery()
    total = db.scalar(select(func.count()).select_from(filtered))
    counts = db.execute(select(filtered.c.source, func.count()).group_by(filtered.c.source)).all()
    token = hashlib.sha256(json.dumps([source, q.strip(), order_q.strip(), month, sorted(tuple(r) for r in counts)]).encode()).hexdigest()
    c.require(not expected_token or expected_token == token, '操作日志已新增或查看范围已变化，请刷新第一页后继续。')
    instant = func.julianday(combined.c.occurred_at) if db.bind.dialect.name == 'sqlite' else cast(combined.c.occurred_at, DateTime(timezone=True))
    rows = db.execute(query.order_by(instant.desc(), combined.c.source, combined.c.id,
        combined.c.version.desc()).offset((page-1)*50).limit(50)).mappings().all()
    output = [dict(r) for r in rows]
    # Price confirmation is a source event, not a monthly settlement document.
    price_ids = [r['id'] for r in output if r['source'] == 'settlement' and r['action'] == 'price']
    prices = {e.id: e for e in db.scalars(select(CuttingSettlementEvent).where(
        CuttingSettlementEvent.factory_id == c.FACTORY, CuttingSettlementEvent.id.in_(price_ids)))} if price_ids else {}
    for row in output:
        if row['id'] in prices and row['source'] == 'settlement':
            data = prices[row['id']].data
            row['price_evidence'] = {key: data.get(key) for key in ('line_id', 'task_id', 'unit_price', 'currency', 'evidence')}
    return dict(data=output, total=total, page=page, page_size=50, token=token)
