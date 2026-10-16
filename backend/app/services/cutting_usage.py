"""P3b first slice: signed custody balance, actual use/loss and versioned batch cost.

Warehouse alone owns warehouse stock. Counted remainders are checks on the same
signed material, never a second receipt or an independently editable stock balance.
"""
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import uuid4
from sqlalchemy import inspect, select, text
from app.models.cutting_material_usage import CuttingMaterialEvent as Event
from app.services import cutting_ops as c, cutting_orders as orders, warehouse_operations as wh
from app.services.transaction_lock import lock_transaction

TABLE = Event.__table__


def schema_ready(bind):
    inspector = inspect(bind)
    if TABLE.name not in inspector.get_table_names() or not {x.name for x in TABLE.columns} <= {x['name'] for x in inspector.get_columns(TABLE.name)}:
        return False
    with (bind.connect() if hasattr(bind, 'connect') else nullcontext(bind)) as connection:
        if connection.dialect.name == 'sqlite':
            names = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='cutting_ops_material_events'")).scalars())
            return {'cutting_material_no_update', 'cutting_material_no_delete'} <= names
        if connection.dialect.name == 'postgresql':
            return bool(connection.execute(text("SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass('cutting_ops_material_events') AND tgname='cutting_material_immutable' AND tgenabled IN ('O','A')")).scalar())
    return False


def ensure_schema(db):
    c.require(schema_ready(db.connection()), 'P3b耗用与批次成本需先完成0156迁移及证据保护', 503)


def events(db):
    return [dict(id=e.id, line_id=e.line_id, version=e.version, document_id=e.document_id, action=e.action,
                 data=e.data, actor_id=e.actor_id, actor=e.actor_name, date=e.created_at, reason=e.reason)
            for e in db.scalars(select(Event).where(Event.factory_id == c.FACTORY).order_by(Event.version))]


def documents(history):
    result = {}
    for event in history:
        if event['action'] in {'price', 'allocate'}:
            continue
        document = result.setdefault(event['document_id'], dict(posted=None, review=None, voided=False, history=[]))
        document['history'].append(event)
        if event['action'] == 'post':
            document.update(posted=event, review=None, voided=False)
        elif event['action'] == 'void':
            document.update(posted=None, review=None, voided=True)
        elif event['action'] == 'review':
            document['review'] = event
    return result


def issue_context(entries, issue_id):
    issue = entries.get(issue_id)
    request = entries.get(issue['data'].get('original_id')) if issue and issue['kind'] == 'ISSUE' else None
    frozen = request['data'].get('cutting_request') if request and request['kind'] == 'REQUEST' else None
    c.require(issue and frozen, '请选择有裁床申请依据的原实发批次', 422)
    batch = issue['batch_snapshot']
    return dict(**frozen, issue_id=issue_id, request_id=request['id'], root_batch_id=batch['original_batch_id'],
        item_code=issue['data']['item_code'], item_name=issue['data']['item_name'], unit=issue['data']['unit'],
        lot=batch['lot'], roll_no=batch['roll_no'], location=batch['location'])


def warehouse_cutoff(entries, event):
    """Freeze the same-day count instant; legacy evidence uses its original timestamp."""
    if 'warehouse_cutoff' in event['data']:
        return event['data']['warehouse_cutoff']
    posted_at = datetime.fromisoformat(event['date']).astimezone(UTC)
    return max((e['sequence'] for e in entries.values()
                if datetime.fromisoformat(e['occurred_at']).astimezone(UTC) <= posted_at), default=0)


def movements(entries, issue_id):
    return [e for e in entries.values() if e['kind'] in {'CUTTING_RECEIPT', 'RETURN'}
            and not e.get('reversed') and e['data']['original_id'] == issue_id]


def replay(entries, history):
    docs = documents(history)
    grouped = {}
    for document in docs.values():
        if document['posted']:
            event = document['posted']
            grouped.setdefault(event['data']['entry']['issue_id'], []).append(event)
    result = {}
    for issue_id, uses in grouped.items():
        issue = entries.get(issue_id)
        c.require(issue and issue['kind'] == 'ISSUE' and not issue.get('reversed'), '已有有效耗用，不能撤销原实发或签收')
        daily = {}
        for movement in movements(entries, issue_id):
            daily.setdefault(movement['business_date'], dict(incoming=[], uses=[]))['incoming'].append(movement)
        for event in uses:
            daily.setdefault(event['data']['entry']['day'], dict(incoming=[], uses=[]))['uses'].append(event)
        balance, consumed, loss = Decimal(0), Decimal(0), Decimal(0)
        for day in sorted(daily):
            current = daily[day]
            c.require(len(current['uses']) <= 1, '同一原实发批次同一天仅可登记一张有效耗用单，请使用更正原单')
            cutoff = warehouse_cutoff(entries, current['uses'][0]) if current['uses'] else float('inf')
            before = [m for m in current['incoming'] if m['sequence'] <= cutoff]
            after = [m for m in current['incoming'] if m['sequence'] > cutoff]
            for is_after, segment in ((False, before), (True, after)):
                for movement in sorted(segment, key=lambda e: e['sequence']):
                    balance += wh.decimal(movement['data']['quantity']) * (1 if movement['kind'] == 'CUTTING_RECEIPT' else -1)
                    c.require(balance >= 0, '该业务时点签收净额不足，不能退回已耗用物料或撤销相关签收')
                if is_after:
                    continue
                for event in current['uses']:
                    entry = event['data']['entry']
                    normal, scrap = wh.decimal(entry['consumed_quantity']), wh.decimal(entry['loss_quantity'])
                    balance -= normal + scrap
                    c.require(balance >= 0, f"耗用单 {event['document_id']}（{day}）超过登记时点已签收、扣除退仓后的可用数量")
                    c.require(balance == wh.decimal(entry['counted_remaining']),
                              f"耗用单 {event['document_id']}（{day}）盘余不平：账面应为 {wh.text(balance)}，填写 {entry['counted_remaining']}；请先核对该单及后续依赖，不自动补损耗")
                    consumed += normal
                    loss += scrap
        result[issue_id] = dict(consumed_quantity=wh.text(consumed), loss_quantity=wh.text(loss), remaining_quantity=wh.text(balance))
    return docs, result


def balance_preview(db, line_id, issue_id, day, *, document_id=''):
    ensure_schema(db)
    wh.ensure_schema(db)
    c.require(day <= wh.business_now().date(), '实际业务日期不能晚于今天', 422)
    lock_transaction(db, 'cutting-master', c.FACTORY)
    wh.procurement.lock_factory(db)
    _, entries = wh.projection(db, 'fabric')
    context = issue_context(entries, issue_id)
    c.require(context['line_id'] == line_id, '原实发不属于当前订单', 404)
    c.require(not entries[issue_id].get('reversed'), '原实发已冲销')
    c.require(day.isoformat() >= entries[issue_id]['business_date'], '耗用日期不能早于原实发日期', 422)
    history = events(db)
    docs, _ = replay(entries, history)
    cutoff = max((e['sequence'] for e in entries.values()), default=0)
    if document_id:
        document = docs.get(document_id)
        c.require(document and document['posted'] and document['posted']['line_id'] == line_id, '更正原耗用单不存在或已撤销')
        original = document['posted']
        c.require(original['data']['entry']['issue_id'] == issue_id and original['data']['entry']['day'] == day.isoformat(), '更正须保留原实发和原业务日期', 422)
        cutoff = warehouse_cutoff(entries, original)
    included = [m for m in movements(entries, issue_id) if m['business_date'] < day.isoformat()
                or m['business_date'] == day.isoformat() and m['sequence'] <= cutoff]
    incoming = sum((wh.decimal(m['data']['quantity']) for m in included if m['kind'] == 'CUTTING_RECEIPT'), Decimal(0))
    returned = sum((wh.decimal(m['data']['quantity']) for m in included if m['kind'] == 'RETURN'), Decimal(0))
    previous, later = [], []
    for identifier, document in docs.items():
        event = document['posted']
        if not event or identifier == document_id or event['data']['entry']['issue_id'] != issue_id:
            continue
        if event['data']['entry']['day'] <= day.isoformat(): previous.append(event)
        else: later.append(dict(document_id=identifier, day=event['data']['entry']['day']))
    consumed = sum((wh.decimal(e['data']['entry']['consumed_quantity']) for e in previous), Decimal(0))
    loss = sum((wh.decimal(e['data']['entry']['loss_quantity']) for e in previous), Decimal(0))
    return dict(day=day.isoformat(), warehouse_cutoff=cutoff, received_quantity=wh.text(incoming), returned_quantity=wh.text(returned),
                consumed_quantity=wh.text(consumed), loss_quantity=wh.text(loss), available_quantity=wh.text(incoming-returned-consumed-loss),
                same_day_document_ids=[e['document_id'] for e in previous if e['data']['entry']['day'] == day.isoformat()],
                later_documents=later, revision=max((e['version'] for e in history), default=0))


def guard_warehouse_change(db, entries, entry):
    # P3a deployments with no P3b table remain usable. A partial/broken P3b
    # migration must fail closed once its evidence table exists.
    if TABLE.name not in inspect(db.connection()).get_table_names():
        return
    ensure_schema(db)
    history = events(db)
    issue_id = None
    if entry['kind'] == 'RETURN':
        issue_id = entry['data']['original_id']
    elif entry['kind'] == 'CUTTING_RECEIPT_VOID':
        receipt = entries.get(entry['data']['original_id'])
        issue_id = receipt['data']['original_id'] if receipt else None
    elif entry['kind'] == 'CORRECTION':
        original = entries.get(entry['data']['original_id'])
        if original and original['kind'] == 'ISSUE':
            issue_id = original['id']
    if issue_id:
        c.require(not any(e['action'] == 'void' and e['data']['context']['issue_id'] == issue_id
                          and e['data']['entry']['day'] > entry['business_date'] for e in history),
                  '退仓、撤签或出库冲销日期不能早于相关耗用撤销日期')
    replay(entries, history)


def prices(history):
    result = {}
    for event in history:
        if event['action'] == 'price':
            result[event['data']['context']['root_batch_id']] = event
    return result


def amount(quantity, price):
    with localcontext() as context:
        context.prec = 50
        return format((wh.decimal(quantity) * wh.decimal(price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')


def cost_summary(rows):
    """Group existing rounded issue costs, retaining physical and currency boundaries."""
    tasks, materials = {}, {}
    task_fields = ('dispatch_id', 'bom_id', 'bom_version', 'task_id', 'resource_id', 'resource_version')
    quantity_fields = ('received_quantity', 'returned_quantity', 'consumed_quantity', 'loss_quantity', 'remaining_quantity')
    with localcontext() as precision:
        precision.prec = 60
        for row in rows:
            if row['reversed']:
                continue
            context = row['context']
            identity = tuple(context.get(field) for field in task_fields)
            if identity not in tasks:
                tasks[identity] = dict(key=f'task-{len(tasks)}', context={
                    field: context.get(field) for field in (*task_fields, 'task_name', 'resource_name', 'execution')},
                    issue_count=0, pending_pricing=0, costs={})
            material = context['warehouse_material']
            identity = (material['id'], material['revision'], context['unit'])
            if identity not in materials:
                materials[identity] = dict(key=f'material-{len(materials)}', material=material,
                    item_code=context['item_code'], item_name=context['item_name'], unit=context['unit'],
                    **{field: '0' for field in quantity_fields}, pending_quantity='0',
                    issue_count=0, pending_pricing=0, costs={})
            task = tasks[tuple(context.get(field) for field in task_fields)]
            grouped_material = materials[identity]
            for field in quantity_fields:
                grouped_material[field] = wh.text(wh.decimal(grouped_material[field]) + wh.decimal(row[field]))
            used = wh.decimal(row['consumed_quantity']) + wh.decimal(row['loss_quantity'])
            for group in (task, grouped_material):
                group['issue_count'] += 1
                if used <= 0:
                    continue
                if not row['price']:
                    group['pending_pricing'] += 1
                    continue
                currency = row['price']['data']['entry']['currency']
                costs = group['costs'].setdefault(currency, dict(normal='0.00', loss='0.00', total='0.00'))
                costs['normal'] = format(wh.decimal(costs['normal']) + wh.decimal(row['normal_cost']), '.2f')
                costs['loss'] = format(wh.decimal(costs['loss']) + wh.decimal(row['loss_cost']), '.2f')
                costs['total'] = format(wh.decimal(costs['normal']) + wh.decimal(costs['loss']), '.2f')
            if used > 0 and not row['price']:
                grouped_material['pending_quantity'] = wh.text(wh.decimal(grouped_material['pending_quantity']) + used)
    return dict(tasks=list(tasks.values()), materials=list(materials.values()))


def read(db, line_id, *, show_costs=False):
    ensure_schema(db)
    c.require(orders.latest(db, line_id) is not None, '裁床来源订单不存在', 404)
    wh.ensure_schema(db)
    # A single consistent cross-ledger view also on PostgreSQL READ COMMITTED.
    # A linked warehouse write takes these same locks in this order.
    lock_transaction(db, 'cutting-master', c.FACTORY)
    wh.procurement.lock_factory(db)
    _, entries = wh.projection(db, 'fabric')
    history = events(db)
    docs, balances = replay(entries, history)
    price_map = prices(history)
    rows, root_ids = [], set()
    for issue in entries.values():
        if issue['kind'] != 'ISSUE':
            continue
        request = entries.get(issue['data'].get('original_id'))
        if not request or request['data'].get('cutting_request', {}).get('line_id') != line_id:
            continue
        context = issue_context(entries, issue['id'])
        received = wh.decimal(issue.get('cutting_received_quantity', '0'))
        returned = wh.decimal(issue.get('returned_quantity', '0'))
        balance = balances.get(issue['id'], dict(consumed_quantity='0', loss_quantity='0', remaining_quantity=wh.text(received-returned)))
        root_ids.add(context['root_batch_id'])
        row = dict(issue_id=issue['id'], context=context, reversed=issue.get('reversed', False),
            issued_quantity=issue['data']['quantity'], received_quantity=wh.text(received), returned_quantity=wh.text(returned), **balance)
        if show_costs:
            price = price_map.get(context['root_batch_id'])
            row.update(price=price, cost_status='已计价' if price else '待计价',
                normal_cost=amount(balance['consumed_quantity'], price['data']['entry']['unit_cost']) if price else None,
                loss_cost=amount(balance['loss_quantity'], price['data']['entry']['unit_cost']) if price else None)
        rows.append(row)
    output_docs = []
    for identifier, document in docs.items():
        first = document['history'][0]
        if first['line_id'] != line_id:
            continue
        output_docs.append(dict(id=identifier, voided=document['voided'], reviewed=bool(document['review']),
            entry=first['data']['entry'], context=first['data']['context'], actor=first['actor'],
            created_at=first['date'], reason=first['reason'], warehouse_cutoff=warehouse_cutoff(entries, first),
            replaces_document_id=first['data'].get('replaces_document_id'),
            replaced_by_document_id=next((e['data'].get('replaced_by_document_id') for e in document['history'] if e['action'] == 'void'), None),
            history=[dict({k: e[k] for k in ('id', 'action', 'version', 'actor', 'date', 'reason')}, business_day=e['data']['entry']['day']) for e in document['history']],
            **({'cost_at_post': first['data'].get('cost_at_post')} if show_costs else {})))
    result = dict(revision=max((e['version'] for e in history), default=0), issues=rows, documents=output_docs)
    if show_costs:
        currencies = {}
        with localcontext() as context:
            context.prec = 60
            for row in rows:
                if row['price']:
                    currency = row['price']['data']['entry']['currency']
                    currencies[currency] = wh.text(wh.decimal(currencies.get(currency, '0')) + wh.decimal(row['normal_cost']) + wh.decimal(row['loss_cost']))
        result.update(amounts=currencies, pending_pricing=sum(1 for r in rows if not r['price'] and wh.decimal(r['consumed_quantity']) + wh.decimal(r['loss_quantity']) > 0),
                      price_history=[e for e in history if e['action'] == 'price' and e['data']['context']['root_batch_id'] in root_ids],
                      cost_summary=cost_summary(rows))
        from app.services import cutting_cost_allocation as allocation
        result['cost_allocation'] = allocation.view(db, line_id, rows, history)
    return result


def execute(db, actor, line_id, body, action):
    if action == 'allocate':
        from app.services import cutting_cost_allocation as allocation
        return allocation.confirm(db, actor, line_id, body)
    ensure_schema(db)
    c.require(orders.latest(db, line_id) is not None, '裁床订单不存在', 404)
    wh.ensure_schema(db)
    # All callers hold the cutting factory lock. Warehouse uses the same lock
    # before changing linked signatures/returns; preserve cutting -> fabric order.
    wh.procurement.lock_factory(db)
    _, entries = wh.projection(db, 'fabric')
    history = events(db)
    revision = max((e['version'] for e in history), default=0)
    c.require(body.expected_version == revision, '耗用或成本记录已变化，请保留填写并刷新后核对')
    c.require(body.day <= wh.business_now().date(), '实际业务日期不能晚于今天', 422)
    identifier = uuid4().hex
    document_id = identifier
    if action in {'post', 'price', 'correct'}:
        context = issue_context(entries, body.issue_id)
        c.require(context['line_id'] == line_id, '原实发不属于当前订单', 404)
        c.require(not entries[body.issue_id].get('reversed'), '原实发已冲销')
        entry = body.model_dump(mode='json', exclude={'factory_id', 'operation_id', 'expected_version', 'reason'})
        if action in {'post', 'correct'}:
            c.require(body.day.isoformat() >= entries[body.issue_id]['business_date'], '耗用日期不能早于原实发日期', 422)
        data = dict(entry=entry, context=context)
        if action in {'post', 'correct'}:
            price = prices(history).get(context['root_batch_id'])
            data['warehouse_cutoff'] = max((e['sequence'] for e in entries.values()), default=0)
            data['cost_at_post'] = dict(version=price['version'], **price['data']['entry']) if price else None
    else:
        document = documents(history).get(body.document_id)
        c.require(document and document['posted'] and document['posted']['line_id'] == line_id, '原耗用单不存在、已撤销或不属于当前订单')
        posted = document['posted']
        c.require(body.day.isoformat() >= posted['data']['entry']['day'], '撤销或抽查日期不能早于原耗用日期', 422)
        if action == 'review':
            c.require(not document['review'], '本张耗用单已抽查')
        document_id = body.document_id
        data = dict(entry={'day': body.day.isoformat()}, context=posted['data']['context'])
    event = dict(id=identifier, line_id=line_id, version=revision+1, document_id=document_id, action=action,
        data=data, actor_id=actor.id, actor=actor.display_name, date=datetime.now(UTC).isoformat(), reason=body.reason)
    pending = [event]
    from app.services.cutting_period_guards import guard_days, guard_price
    if action == 'price':
        guard_price(db, data['context']['root_batch_id'])
    elif action in {'post', 'correct', 'void'}:
        original = documents(history).get(getattr(body, 'document_id', ''))
        guard_days(db, body.day, original['posted']['data']['entry']['day'] if original and original['posted'] else None)
    if action == 'correct':
        old = documents(history).get(body.document_id)
        c.require(old and old['posted'] and old['posted']['line_id'] == line_id, '更正原耗用单不存在、已撤销或不属于当前订单')
        original = old['posted']
        c.require(original['data']['entry']['issue_id'] == body.issue_id and original['data']['entry']['day'] == body.day.isoformat(), '更正须保留原实发和原业务日期', 422)
        event.update(action='post', version=revision+2)
        data['warehouse_cutoff'] = warehouse_cutoff(entries, original)
        data['replaces_document_id'] = body.document_id
        data['entry'].pop('document_id', None)
        cancellation = dict(event, id=uuid4().hex, document_id=body.document_id, version=revision+1, action='void',
                            data=dict(entry={'day': wh.business_now().date().isoformat()}, context=original['data']['context'], replaced_by_document_id=identifier))
        pending = [cancellation, event]
    replay(entries, history+pending)
    for item in pending:
        db.add(Event(id=item['id'], line_id=line_id, factory_id=c.FACTORY, version=item['version'], document_id=item['document_id'],
            action=item['action'], data=item['data'], actor_id=actor.id, actor_name=actor.display_name, created_at=item['date'], reason=body.reason))
    db.flush()
    return dict(id=identifier, document_id=document_id, version=pending[-1]['version'])
