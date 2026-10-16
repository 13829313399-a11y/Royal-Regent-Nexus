"""Actual-payment evidence and allocations; never sends a bank instruction.

Pending review reserves payable capacity; only confirmed registrations count as
paid. Reversal cancels the registration, not the bank transfer. All writes share
the cutting factory lock with settlement confirmation/reopening.
"""
from collections import defaultdict
from contextlib import nullcontext
from copy import deepcopy
from decimal import Decimal
import unicodedata
from sqlalchemy import inspect, select, text
from app.core.config import settings
from app.models.cutting_payment import CuttingPaymentEvent as Event
from app.services import cutting_ops as c, cutting_settlement as fees, cutting_planning as planning
from app.services.cutting_payment_schemas import Save
from app.services.transaction_lock import lock_transaction
from app.services.warehouse_operations import business_now


def schema_ready(bind):
    inspector = inspect(bind)
    if Event.__tablename__ not in inspector.get_table_names():
        return False
    if not {col.name for col in Event.__table__.columns} <= {col['name'] for col in inspector.get_columns(Event.__tablename__)}:
        return False
    with (bind.connect() if hasattr(bind, 'connect') else nullcontext(bind)) as connection:
        if connection.dialect.name == 'sqlite':
            names = set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='cutting_ops_payment_events'")).scalars())
            return {'cutting_payment_no_update', 'cutting_payment_no_delete'} <= names
        if connection.dialect.name == 'postgresql':
            return bool(connection.execute(text("SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass('cutting_ops_payment_events') AND tgname='cutting_payment_immutable' AND tgenabled IN ('O','A')")).scalar())
    return False


def history(db, optional=False):
    if optional and Event.__tablename__ not in inspect(db.connection()).get_table_names():
        return []
    c.require(schema_ready(db.connection()), '付款登记需先完成0166显式迁移及证据保护', 503)
    return list(db.scalars(select(Event).where(Event.factory_id == c.FACTORY).order_by(Event.version)))


def latest(events):
    return {event.document_id: event for event in events}


def state(event):
    return {'save':'draft', 'submit':'submitted', 'return':'returned', 'confirm':'confirmed', 'reverse':'reversed'}[event.action]


def fmt(value):
    return format(Decimal(value), '.2f')


def voucher_key(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def balances(db, events, exclude=None):
    paid, pending = defaultdict(Decimal), defaultdict(Decimal)
    related = defaultdict(list)
    for event in latest(events).values():
        if event.document_id == exclude or event.action not in {'submit', 'confirm'}:
            continue
        snapshot = event.data['snapshot']
        for row in snapshot['allocations']:
            target = paid if event.action == 'confirm' else pending
            target[row['settlement_id']] += Decimal(row['amount'])
            related[row['settlement_id']].append(dict(document_id=event.document_id, day=snapshot['day'],
                state=state(event), amount=row['amount'], voucher_no=snapshot['voucher_no']))
    rows = []
    for event in fees.latest(fees.history(db)).values():
        if event.action != 'confirm':
            continue
        snapshot = event.data['snapshot']; key = event.document_id
        total = Decimal(snapshot['total']); unpaid = total-paid[key]; available = unpaid-pending[key]
        c.require(available >= 0, '核销余额异常，请核对付款及结算证据')
        rows.append(dict(settlement_id=key, settlement_event_id=event.id, month=snapshot['month'],
            resource_id=snapshot['resource_id'], resource_name=snapshot['resource_name'], currency=snapshot['currency'],
            payable=fmt(total), paid=fmt(paid[key]), pending=fmt(pending[key]), unpaid=fmt(unpaid), available=fmt(available),
            payments=related[key]))
    return sorted(rows, key=lambda row: (row['month'], row['settlement_id']))


def basis(db, document_id=None):
    lock_transaction(db, 'cutting-master', c.FACTORY)
    events = history(db); own = latest(events).get(document_id)
    c.require(not own or own.action in {'save', 'return'}, '待复核或已生效登记不能直接修订；已冲销记录须另建关联重登单')
    rows = balances(db, events, document_id)
    return dict(rows=rows, revision=events[-1].version if events else 0, basis_token=fees.digest(rows),
        document=dict(event_id=own.id, input=own.data['input'], snapshot=own.data['snapshot'], actor=own.actor_name, date=own.created_at) if own else None)


def calculate(body, rows):
    c.require(body.day <= planning.business_today(), '付款日期不能晚于今天', 422)
    lookup = {row['settlement_id']: row for row in rows}
    allocations = []
    for selected in body.allocations:
        row = lookup.get(selected.settlement_id)
        c.require(row is not None, '只能核销当前已确认的有效结算单')
        c.require(body.currency == row['currency'], '付款与结算币种必须一致，不自动汇兑')
        c.require(selected.amount <= Decimal(row['available']), '核销金额超过扣除已付及待复核占用后的可用余额')
        allocations.append(dict(row, amount=fmt(selected.amount)))
    c.require(len({row['resource_id'] for row in allocations}) == 1, '一笔付款只能对应同一家外厂')
    return dict(day=body.day.isoformat(), voucher_no=body.voucher_no, method=body.method, evidence=body.evidence,
        resource_id=allocations[0]['resource_id'], resource_name=allocations[0]['resource_name'],
        currency=body.currency, amount=fmt(body.amount), allocations=allocations,
        replaces_document_id=body.replaces_document_id)


def evidence_basis(snapshot):
    return fees.digest(dict(day=snapshot['day'], voucher_no=snapshot['voucher_no'], method=snapshot['method'],
        evidence=snapshot['evidence'], resource_id=snapshot['resource_id'], currency=snapshot['currency'], amount=snapshot['amount'],
        replaces_document_id=snapshot['replaces_document_id'], allocations=[{key: row[key] for key in
            ('settlement_id', 'settlement_event_id', 'amount', 'currency', 'resource_id')} for row in snapshot['allocations']]))


def validate_reference(body, events):
    current = latest(events)
    replaced = current.get(body.replaces_document_id)
    if body.replaces_document_id:
        c.require(body.replaces_document_id != body.document_id and replaced and replaced.action == 'reverse',
                  '重登必须关联一笔已整笔冲销的原付款登记')
        c.require(not any(e.document_id != body.document_id and e.action != 'reverse' and
            e.data['snapshot'].get('replaces_document_id') == body.replaces_document_id for e in current.values()),
            '原付款已有重登记录，请定位该记录继续处理')
    for other in current.values():
        if other.document_id == body.document_id:
            continue
        if voucher_key(other.data['snapshot']['voucher_no']) != voucher_key(body.voucher_no):
            continue
        c.require(other.action not in {'submit', 'confirm'}, '付款凭证号已被有效登记或待复核记录占用：' + other.document_id)
        if other.action == 'reverse':
            c.require(replaced is not None and voucher_key(replaced.data['snapshot']['voucher_no']) == voucher_key(body.voucher_no),
                      '该凭证号已有冲销历史，请明确关联已冲销的原登记后重登')


def preview(db, body):
    value = basis(db, body.document_id)
    c.require(body.base_event_id == (value['document']['event_id'] if value['document'] else None),
              '本付款草稿已被修改，请刷新并比较最新版本后明确选择填写内容')
    c.require(body.basis_token == value['basis_token'], '应付或核销余额已变化，请保留填写并刷新')
    validate_reference(body, history(db))
    return calculate(body, value['rows'])


def read(db, month, document_id=None, event_id=None):
    lock_transaction(db, 'cutting-master', c.FACTORY)
    events = history(db); current = latest(events)
    selected = next((e for e in events if e.id == event_id and e.document_id == document_id), None) if event_id else current.get(document_id)
    c.require(not event_id or selected is not None, '付款版本不存在', 404)
    c.require(not document_id or selected is not None, '付款登记不存在', 404)
    # Explicit document/event links follow their actual business month after a date correction.
    if selected:
        month = selected.data['snapshot']['day'][:7]
    compilations = [e for e in events if selected and e.document_id == document_id and e.action == 'save' and e.version <= selected.version]
    previous = compilations[-2] if len(compilations) > 1 else None
    rows = balances(db, events)
    original = current.get(selected.data['snapshot'].get('replaces_document_id')) if selected else None
    totals = {}
    for row in rows:
        total = totals.setdefault(row['currency'], dict(currency=row['currency'], payable=Decimal(0), paid=Decimal(0), pending=Decimal(0), unpaid=Decimal(0), available=Decimal(0)))
        for key in ('payable', 'paid', 'pending', 'unpaid', 'available'): total[key] += Decimal(row[key])
    return dict(month=month, current_month=current[document_id].data['snapshot']['day'][:7] if document_id in current else month,
        previous_compilation=dict(event_id=previous.id, snapshot=previous.data['snapshot'], actor=previous.actor_name, date=previous.created_at) if previous else None,
        revision=events[-1].version if events else 0, rows=rows,
        totals=[{key: value if key == 'currency' else fmt(value) for key, value in total.items()} for total in totals.values()],
        documents=[dict(document_id=e.document_id, state=state(e), **{key:e.data['snapshot'][key] for key in
            ('day','voucher_no','resource_name','currency','amount','replaces_document_id')}) for e in reversed(list(current.values())) if e.data['snapshot']['day'][:7] == month],
        document_id=document_id, state=state(current[document_id]) if document_id in current else 'open',
        selected_state=state(selected) if selected else 'open', event_id=selected.id if selected else None,
        data=selected.data if selected else None,
        original=dict(document_id=original.document_id, day=original.data['snapshot']['day'], state=state(original)) if original else None,
        history=[dict(id=e.id, action=e.action, actor=e.actor_name, date=e.created_at, reason=e.reason, month=e.data['snapshot']['day'][:7]) for e in events if e.document_id == document_id],
        replacements=[dict(document_id=e.document_id, day=e.data['snapshot']['day'], state=state(e)) for e in current.values()
            if e.data['snapshot'].get('replaces_document_id') == document_id])


def execute(db, user, body, action):
    events = history(db); revision = events[-1].version if events else 0
    c.require(body.expected_version == revision, '付款或核销已更新，请保留填写并刷新')
    current = latest(events).get(body.document_id)
    if action == 'save':
        c.require(not current or current.action in {'save', 'return'}, '请先退回待复核单；已生效登记须整笔冲销重登')
        if current:
            c.require(body.replaces_document_id == current.data['snapshot']['replaces_document_id'], '修订不能改变原付款重登关联')
        snapshot = preview(db, body)
        data = dict(input=body.model_dump(mode='json'), snapshot=snapshot, prepared_by=user.id, submitted_by=None,
            replaces_id=current.id if current else None)
    else:
        c.require(current is not None, '付款登记不存在', 404)
        data = deepcopy(current.data); data['replaces_id'] = current.id
        if action == 'return':
            c.require(current.action == 'submit', '只能退回待复核付款登记')
        elif action == 'reverse':
            c.require(current.action == 'confirm', '只能冲销已生效付款登记；此操作不代表银行退款')
            data['reversed_at'] = business_now().isoformat()
        else:
            c.require(current.action in ({'save','return'} if action == 'submit' else {'submit'}), '付款状态已变化，请重新读取')
            saved = Save.model_validate(data['input'])
            validate_reference(saved, events)
            snapshot = calculate(saved, balances(db, events, body.document_id))
            c.require(evidence_basis(snapshot) == evidence_basis(data['snapshot']), '原结算版本或核销依据已变化，请退回或重新编制')
            if action == 'submit':
                data['submitted_by'] = user.id
            else:
                same = user.id in {data['prepared_by'], data['submitted_by']}
                local = settings.cutting_period_admin_acceptance and settings.app_env == 'development' and user.id == 'user-admin' and 'admin' in user.role_codes
                c.require(not same or local, '付款登记、提交人与复核人须不同')
                data['local_admin_acceptance'] = bool(same and local)
                data['confirmed_at'] = business_now().isoformat()
    event = Event(id=body.operation_id, factory_id=c.FACTORY, document_id=body.document_id, version=revision+1,
        action=action, data=data, actor_id=user.id, actor_name=user.display_name, created_at=business_now().isoformat(), reason=body.reason)
    db.add(event); db.flush()
    return dict(id=event.id, document_id=event.document_id, version=event.version, state=state(event), month=data['snapshot']['day'][:7])


def blockers(db, settlement_id):
    result = []
    for event in latest(history(db, optional=True)).values():
        if event.action not in {'submit', 'confirm'}:
            continue
        snapshot = event.data['snapshot']
        for row in snapshot['allocations']:
            if row['settlement_id'] == settlement_id:
                result.append(dict(document_id=event.document_id, month=snapshot['day'][:7], state=state(event),
                    amount=row['amount'], currency=snapshot['currency'], voucher_no=snapshot['voucher_no']))
    return result


def guard_reopen(db, settlement_id):
    active = [row['document_id'] for row in blockers(db, settlement_id)]
    c.require(not active, '结算单存在待复核付款或有效核销，请先退回／冲销相关付款登记：' + '、'.join(active))
