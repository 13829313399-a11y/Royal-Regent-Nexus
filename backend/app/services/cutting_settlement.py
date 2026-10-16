"""Subcontract fees are separate from material cost and internal period locking.

All projections and mutations serialize on the existing cutting factory lock.
Submitted statements reserve acceptance quantities; confirmed statements freeze
the same quantities and prices. No warehouse stock or bank posting occurs here.
"""
from collections import defaultdict
from contextlib import nullcontext
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from sqlalchemy import inspect, select, text
from app.core.config import settings
from app.models.cutting_ops import CuttingOrder, CuttingOrderRevision
from app.models.cutting_settlement import CuttingSettlementEvent as Event
from app.services import cutting_ops as c, cutting_reporting as reports, cutting_planning as planning
from app.services.cutting_period_guards import end_day
from app.services.transaction_lock import lock_transaction
from app.services.warehouse_operations import business_now


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def schema_ready(bind):
    inspector = inspect(bind)
    if Event.__tablename__ not in inspector.get_table_names():
        return False
    if not {col.name for col in Event.__table__.columns} <= {col['name'] for col in inspector.get_columns(Event.__tablename__)}:
        return False
    with (bind.connect() if hasattr(bind, 'connect') else nullcontext(bind)) as connection:
        if connection.dialect.name == 'sqlite':
            names = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='cutting_ops_settlement_events'")).scalars())
            return {'cutting_settlement_no_update', 'cutting_settlement_no_delete'} <= names
        if connection.dialect.name == 'postgresql':
            return bool(connection.execute(text("SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass('cutting_ops_settlement_events') AND tgname='cutting_settlement_immutable' AND tgenabled IN ('O','A')")).scalar())
    return False


def history(db, optional=False):
    if optional and Event.__tablename__ not in inspect(db.connection()).get_table_names():
        return []
    c.require(schema_ready(db.connection()), '外发结算需先完成0165显式迁移及证据保护', 503)
    return list(db.scalars(select(Event).where(Event.factory_id == c.FACTORY).order_by(Event.version)))


def state(event):
    return {'save': 'draft', 'submit': 'submitted', 'return': 'returned', 'confirm': 'confirmed', 'reopen': 'reopened'}[event.action]


def latest(events):
    return {e.document_id: e for e in events if e.action != 'price'}


def prices(events):
    return {(e.data['line_id'], e.data['task_id']): e for e in events if e.action == 'price'}


def context_token(context):
    return digest({key: context[key] for key in ('dispatch_id', 'bom_id', 'bom_version', 'resource_id', 'execution', 'task_target', 'plan_version')})


def evidence(event):
    return dict(id=event.id, version=event.version, actor=event.actor_name, actor_id=event.actor_id,
                date=event.created_at, reason=event.reason, **event.data)


def reserved(events, exclude=None):
    return [e for key, e in latest(events).items() if key != exclude and e.action in {'submit', 'confirm'}]


def usage(events, exclude=None):
    documents, tasks = defaultdict(int), defaultdict(int)
    for event in reserved(events, exclude):
        for row in event.data['snapshot']['rows']:
            documents[(row['line_id'], row['acceptance_id'])] += row['sets']
            tasks[(row['line_id'], row['task_id'])] += row['sets']
    return documents, tasks


def acceptance_rows(db, month, events, exclude=None):
    today = planning.business_today().isoformat()
    c.require(month <= today[:7], '不能核对未来月份', 422)
    cutoff = min(end_day(month), today)
    c.require(reports.schema_ready(db.connection()), '外发结算需先完成每日填数迁移', 503)
    consumed, task_consumed = usage(events, exclude)
    quotes = prices(events)
    rows = []
    for order in db.scalars(select(CuttingOrder).where(CuttingOrder.factory_id == c.FACTORY).order_by(CuttingOrder.line_id)):
        docs = reports.documents(reports.events(db, order.line_id))
        reports.replay(docs)
        for document in docs.values():
            event = document['posted']
            if not event:
                continue
            entry, context = event['data']['entry'], event['data']['context']
            if context['execution'] != 'outsourced' or entry['kind'] != 'accept' or entry['day'] > cutoff:
                continue
            task = (order.line_id, entry['task_id'])
            token = context_token(context)
            quote = quotes.get(task)
            price = evidence(quote) if quote and quote.data['context_token'] == token else None
            revision = db.get(CuttingOrderRevision, (order.line_id, event['version']))
            c.require(revision is not None, '验收订单快照缺失，请核对历史依据')
            used = consumed[(order.line_id, document['document_id'])]
            task_remaining = max(context['task_target'] - task_consumed[task], 0)
            rows.append(dict(line_id=order.line_id, task_id=entry['task_id'], acceptance_id=document['document_id'],
                acceptance_event_id=event['id'], day=entry['day'], accepted_sets=entry['sets'], reserved_sets=used,
                available_sets=max(0, min(entry['sets']-used, task_remaining)), task_remaining_sets=task_remaining,
                correction_pending=bool(document['draft']), context=context, context_token=token,
                order=revision.data['order'], acceptance_evidence=entry['evidence'], acceptance_actor=event['actor_id'],
                acceptance_date=event['created_at'], price=price))
    return cutoff, sorted(rows, key=lambda row: (row['day'], row['line_id'], row['acceptance_id']))


def basis(db, month, document_id=None):
    lock_transaction(db, 'cutting-master', c.FACTORY)
    events = history(db)
    own = latest(events).get(document_id)
    c.require(not own or own.action not in {'submit', 'confirm'}, '请先退回或反结，再重新编制')
    cutoff, rows = acceptance_rows(db, month, events, document_id)
    return dict(month=month, cutoff=cutoff, rows=rows, revision=events[-1].version if events else 0,
                basis_token=digest(dict(month=month, cutoff=cutoff, rows=rows)))


def amount(quantity, price):
    with localcontext() as precision:
        precision.prec = 60
        return (Decimal(quantity)*Decimal(price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate(body, rows, cutoff):
    lookup = {(r['line_id'], r['acceptance_id']): r for r in rows}
    selected, task_totals = [], defaultdict(int)
    for selection in body.selections:
        row = lookup.get((selection.line_id, selection.acceptance_id))
        c.require(row is not None, '选择的验收已作废、移出截止期间或不属于华康C外发')
        c.require(not row['correction_pending'], '所选验收存在未处理更正草稿，请先处理')
        c.require(selection.sets <= row['available_sets'], '本次套数超过验收剩余可结数量或任务额度')
        key = (row['line_id'], row['task_id'])
        task_totals[key] += selection.sets
        c.require(task_totals[key] <= row['task_remaining_sets'], '同一任务合计超过剩余额度；超产费用需另行确认')
        c.require(row['price'] is not None, '请先由单独授权主管确认该任务的含税单价、币种及报价凭据')
        selected.append(dict(deepcopy(row), sets=selection.sets))
    c.require(len({r['context']['resource_id'] for r in selected}) == 1, '一张结算单只能对应一家外发加工厂')
    c.require(len({r['price']['currency'] for r in selected}) == 1, '一张结算单只能使用一种币种，不能自动汇兑')
    # Cumulative rounding per acceptance and immutable quote conserves cents over
    # partial settlements. Allocation order is persisted and protected on reopen.
    for row in selected:
        row['amount'] = format(amount(row['prior_priced_sets']+row['sets'], row['price']['unit_price']) -
                               amount(row['prior_priced_sets'], row['price']['unit_price']), '.2f')
    return dict(month=body.month, cutoff=cutoff, resource_id=selected[0]['context']['resource_id'],
        resource_name=selected[0]['context']['resource_name'], currency=selected[0]['price']['currency'],
        rows=selected, total=format(sum((Decimal(r['amount']) for r in selected), Decimal(0)), '.2f'),
        sets=sum(r['sets'] for r in selected), tax_basis='inclusive', vendor_evidence=body.vendor_evidence)


def priced_rows(rows, events, exclude=None, before_version=None):
    prior = defaultdict(int)
    for event in reserved(events, exclude):
        if before_version is not None and event.data['reserved_version'] >= before_version:
            continue
        for row in event.data['snapshot']['rows']:
            prior[(row['line_id'], row['acceptance_id'], row['price']['id'])] += row['sets']
    return [dict(row, prior_priced_sets=prior[(row['line_id'], row['acceptance_id'], row['price']['id'])] if row['price'] else 0) for row in rows]


def snapshot_basis(snapshot):
    # Availability can change for unrelated rows. Only chosen acceptance/quote
    # identities, allocation and cumulative rounding basis bind this statement.
    keys = ('line_id', 'acceptance_id', 'acceptance_event_id', 'context_token', 'sets', 'price', 'amount', 'prior_priced_sets')
    return digest([dict((key, row[key]) for key in keys) for row in snapshot['rows']])


def confirmation_token(body, snapshot):
    return digest(dict(document_id=body.document_id, month=body.month,
        basis=snapshot_basis(snapshot), vendor_evidence=body.vendor_evidence,
        currency=snapshot['currency'], total=snapshot['total']))


def preview(db, body):
    value = basis(db, body.month, body.document_id)
    c.require(body.basis_token == value['basis_token'], '验收、价格或可结数量已变化，请保留填写并刷新依据')
    snapshot = calculate(body, priced_rows(value['rows'], history(db), body.document_id), value['cutoff'])
    return dict(snapshot=snapshot, confirmation_token=confirmation_token(body, snapshot))


def dependencies(events, current):
    if not current or current.action not in {'submit', 'confirm'}:
        return []
    keys = {(r['line_id'], r['acceptance_id'], r['price']['id']) for r in current.data['snapshot']['rows']}
    result = []
    for other in reserved(events, current.document_id):
        rows = [r for r in other.data['snapshot']['rows'] if (r['line_id'], r['acceptance_id'], r['price']['id']) in keys]
        if rows and other.data['reserved_version'] > current.data['reserved_version']:
            result.append(dict(document_id=other.document_id, month=other.data['snapshot']['month'],
                state=state(other), sets=sum(r['sets'] for r in rows), version=other.data['reserved_version']))
    return sorted(result, key=lambda item: item['version'], reverse=True)


def read(db, month, document_id=None, event_id=None):
    lock_transaction(db, 'cutting-master', c.FACTORY)
    events = history(db)
    current = latest(events)
    selected = next((e for e in events if e.id == event_id and e.action != 'price' and e.document_id == document_id), None) if event_id else current.get(document_id)
    c.require(not event_id or selected is not None, '结算版本不存在', 404)
    c.require(not selected or selected.data['snapshot']['month'] == month, '结算单不属于所选月份', 404)
    statements = [dict(document_id=e.document_id, event_id=e.id, state=state(e), month=e.data['snapshot']['month'],
        resource_name=e.data['snapshot']['resource_name'], currency=e.data['snapshot']['currency'], total=e.data['snapshot']['total'],
        sets=e.data['snapshot']['sets']) for e in reversed(list(current.values())) if e.data['snapshot']['month'] == month]
    previous = next((e for e in reversed(events) if selected and e.document_id == document_id
                     and e.action == 'save' and e.version < selected.version
                     and e.data['snapshot'] != selected.data['snapshot']), None)
    totals = {}
    for item in statements:
        if item['state'] not in {'submitted', 'confirmed'}:
            continue
        key = (item['state'], item['currency'])
        total = totals.setdefault(key, dict(state=key[0], currency=key[1], sets=0, total=Decimal(0)))
        total['sets'] += item['sets']
        total['total'] += Decimal(item['total'])
    return dict(revision=events[-1].version if events else 0, statements=statements,
        totals=[dict(t, total=format(t['total'], '.2f')) for t in totals.values()],
        dependencies=dependencies(events, current.get(document_id)),
        previous_snapshot=previous.data['snapshot'] if previous else None,
        document_id=document_id, state=state(current[document_id]) if document_id in current else 'open',
        selected_state=state(selected) if selected else 'open', event_id=selected.id if selected else None,
        data=selected.data if selected else None,
        history=[dict(id=e.id, action=e.action, version=e.version, actor=e.actor_name, actor_id=e.actor_id,
                      date=e.created_at, reason=e.reason) for e in events if e.document_id == document_id and e.action != 'price'],
        price_history=[evidence(e) for e in events if e.action == 'price' and selected and
                       any((r['line_id'], r['task_id']) == (e.data['line_id'], e.data['task_id']) for r in selected.data['snapshot']['rows'])])


def execute(db, user, body, action):
    from app.services.cutting_settlement_schemas import Save
    events = history(db)
    revision = events[-1].version if events else 0
    c.require(body.expected_version == revision, '外发价格或结算记录已更新，请保留填写并刷新核对')
    if action == 'price':
        # Use actual frozen outsourcing identity, not a client-supplied vendor.
        _, rows = acceptance_rows(db, planning.business_today().strftime('%Y-%m'), events)
        row = next((r for r in rows if (r['line_id'], r['task_id']) == (body.line_id, body.task_id)), None)
        c.require(row is not None, '请先登记该外发任务的合格验收依据', 422)
        c.require(body.context_token == row['context_token'], '任务计价依据已变化，请重新读取')
        data = dict(line_id=body.line_id, task_id=body.task_id, context_token=body.context_token,
                    context=row['context'], unit_price=format(body.unit_price, 'f'), currency=body.currency,
                    evidence=body.evidence, tax_basis='inclusive')
        document_id = body.operation_id
    else:
        document_id = body.document_id
        current = latest(events).get(document_id)
        if action == 'save':
            c.require(not current or current.action in {'save', 'return', 'reopen'}, '已提交或已确认结算不能直接修改')
            if current:
                c.require(body.month == current.data['snapshot']['month'], '修订不能改变原对账月份，请另建结算单')
            value = basis(db, body.month, document_id)
            c.require(body.basis_token == value['basis_token'], '验收、价格或可结数量已变化，请保留填写并刷新依据')
            snapshot = calculate(body, priced_rows(value['rows'], events, document_id), value['cutoff'])
            if current:
                c.require(snapshot['resource_id'] == current.data['snapshot']['resource_id'], '修订不能更换加工厂，请另建结算单')
            data = dict(input=body.model_dump(mode='json'), snapshot=snapshot, prepared_by=user.id, submitted_by=None,
                        replaces_id=current.id if current else None)
            token = confirmation_token(body, snapshot)
            c.require(not body.vendor_confirmation_token or body.vendor_confirmation_token == token,
                      '外厂确认对应的数量、价格或金额已变化，请重新预览并确认')
            data['vendor_confirmation'] = (dict(token=token, actor_id=user.id, actor=user.display_name,
                date=business_now().isoformat()) if body.vendor_confirmation_token and body.vendor_evidence else None)
        else:
            c.require(current is not None, '结算单不存在', 404)
            data = deepcopy(current.data)
            data['replaces_id'] = current.id
            if action in {'return', 'reopen'}:
                c.require(current.action == ('submit' if action == 'return' else 'confirm'), '仅待复核对账可退回，已确认结算须反结')
                if action == 'reopen':
                    from app.services.cutting_payments import guard_reopen
                    guard_reopen(db, document_id)
                # Later partial allocations depend on this rounded prefix. Do not
                # silently change their frozen amounts when releasing this one.
                blockers = dependencies(events, current)
                c.require(not blockers, '请按顺序先退回或反结后续结算单：' + '、'.join(
                    f"{b['month']} / {b['document_id']} ({b['sets']}套)" for b in blockers))
            else:
                c.require(current.action in ({'save', 'return'} if action == 'submit' else {'submit'}), '结算状态已变化，请重新核对')
                c.require(bool(data['snapshot']['vendor_evidence'].strip()), '提交前须填写外厂对账确认凭据')
                saved = Save.model_validate(data['input'])
                cutoff, rows = acceptance_rows(db, saved.month, events, document_id)
                snapshot = calculate(saved, priced_rows(rows, events, document_id,
                    data.get('reserved_version') if action == 'confirm' else None), data['snapshot']['cutoff'])
                c.require(snapshot_basis(snapshot) == snapshot_basis(data['snapshot']), '验收、价格或数量占用已变化，请退回或重新编制对账')
                confirmation = data.get('vendor_confirmation')
                c.require(confirmation and confirmation['token'] == confirmation_token(saved, snapshot),
                          '外厂确认尚未绑定本次明细和金额，请重新编制、预览并确认外厂凭据')
                if action == 'submit':
                    data['submitted_by'] = user.id
                    data['reserved_version'] = revision+1
                else:
                    same = user.id in {data['prepared_by'], data['submitted_by']}
                    local = (settings.cutting_period_admin_acceptance and settings.app_env == 'development'
                             and user.id == 'user-admin' and 'admin' in user.role_codes)
                    c.require(not same or local, '编制、提交人与会计复核人须不同')
                    data['local_admin_acceptance'] = bool(same and local)
                    data['confirmed_at'] = business_now().isoformat()
    event = Event(id=body.operation_id, factory_id=c.FACTORY, document_id=document_id, version=revision+1,
                  action=action, data=data, actor_id=user.id, actor_name=user.display_name,
                  created_at=business_now().isoformat(), reason=body.reason)
    db.add(event)
    db.flush()
    return dict(id=event.id, document_id=document_id, version=event.version, state='priced' if action == 'price' else state(event))


def guard_report(db, line_id, document_id, action):
    """Held acceptance identity may only change after return/controlled reopen."""
    if action not in {'save', 'post', 'void'}:
        return
    events = history(db, optional=True)
    affected = [e.document_id for e in reserved(events) if any(
        row['line_id'] == line_id and row['acceptance_id'] == document_id for row in e.data['snapshot']['rows'])]
    c.require(not affected, '该验收已被外发对账或结算占用，请先退回／反结相关结算单：' + '、'.join(affected))
