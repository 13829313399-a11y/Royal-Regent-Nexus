"""P4b internal month preparation, immutable snapshots, locking and controlled reopen."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
from sqlalchemy import select
from app.models.cutting_ops import CuttingOrder
from app.models.cutting_period import CuttingPeriodEvent as Event
from app.services import cutting_ops as c, cutting_orders as orders, cutting_reporting as reporting
from app.services import cutting_closing as preview, cutting_usage as usage, cutting_cost_allocation as allocation
from app.services import cutting_period_guards as guards, warehouse_operations as wh
from app.services.cutting_period_evidence import fingerprint_basis, relevant_order
from app.services.cutting_period_review import comparison
from app.services.transaction_lock import lock_transaction
from app.core.config import settings


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def next_month(month):
    return (date.fromisoformat(guards.end_day(month)) + timedelta(days=1)).strftime('%Y-%m')


def state(event):
    return {'save': 'draft', 'submit': 'submitted', 'return': 'returned', 'lock': 'locked', 'reopen': 'reopened'}[event.action] if event else 'open'


def period_history(events):
    return [dict(id=e.id, month=e.month, version=e.version, action=e.action, actor=e.actor_name,
                 actor_id=e.actor_id, date=e.created_at, reason=e.reason) for e in events]


def sequence(events):
    """The first ever lock anchors the chain even when every month is reopened."""
    states = guards.latest(events)
    locked = sorted(month for month, event in states.items() if event.action == 'lock')
    established = sorted({event.month for event in events if event.action == 'lock'})
    first = established[0] if established else None
    required = first
    while required in locked:
        required = next_month(required)
    return dict(first_month=first, next_month=required, locked_months=locked,
                pending_reclose=[month for month in established if month not in locked],
                sequence_repair=bool(required and any(month > required for month in locked)))


def prepare(db, month):
    guards.ensure_schema(db)
    start, end, through = preview.period(month, wh.business_now().date())
    c.require(through == end and end < wh.business_now().date().isoformat(), '月份尚未结束，仅可查看 P4a 实时核对，不能编制正式月结')
    lock_transaction(db, 'cutting-master', c.FACTORY)
    events = guards.history(db)
    states = guards.latest(events)
    c.require(not states.get(month) or states[month].action != 'lock', '该月已锁定，请查看冻结快照或先反结')
    chain = sequence(events)
    c.require(not chain['sequence_repair'], '历史锁月顺序存在缺口，请先从最近已锁月逐月反结，再从最早待重结月份办理')
    c.require(not chain['next_month'] or month == chain['next_month'],
              f"请先办理 {chain['next_month']}，须从首次月结起点连续结转或重结")
    locks = {key: event for key, event in states.items() if event.action == 'lock'}
    previous = locks.get(max(locks)) if locks else None
    # All source rows are locked before fabric, matching linked issue writes.
    items = list(db.scalars(select(CuttingOrder).where(CuttingOrder.factory_id == c.FACTORY).order_by(CuttingOrder.line_id)))
    for item in items:
        orders.lock_source(db, item.line_id)
    wh.ensure_schema(db)
    wh.procurement.lock_factory(db)
    usage.ensure_schema(db)
    c.require(reporting.schema_ready(db.connection()), '内部月结需先完成0155迁移及证据保护', 503)
    _, warehouse = wh.projection(db, 'fabric')
    usage_history = usage.events(db)
    uses, _ = usage.replay(warehouse, usage_history)
    price_map = usage.prices(usage_history)
    prior = previous.data['snapshot'] if previous else None
    prior_rows = {r['issue_id']: r for r in (prior or {}).get('allocations', [])}
    reports, rows, blockers, notices = [], [], [], []
    before_day = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    for item in items:
        result = preview.read(db, item.line_id, month, show_costs=True)
        result.pop('generated_at', None)
        result.pop('current_allocation_review', None)  # Today's allocation is never a month-end basis.
        result.pop('wip_status', None)
        result['issues'] = [issue for issue in result['issues'] if issue['code'] != 'period_wip_unconfirmed']
        if not relevant_order(result):
            continue
        current = orders.revision(db, item)['data']
        result['order_snapshot'] = current.get('order', {})
        reports.append(result)
        for issue in result['issues']:
            notice = dict(issue, line_id=item.line_id)
            (blockers if issue['code'] == 'report_draft' else notices).append(notice)
        documents = reporting.documents(reporting.events(db, item.line_id))
        for row in result['materials']:
            context = row['context']
            totals = {side: dict(normal=Decimal(0), loss=Decimal(0)) for side in ('opening', 'ending')}
            for document in uses.values():
                event = document['posted']
                if not event or event['data']['entry']['issue_id'] != row['issue_id']:
                    continue
                entry = event['data']['entry']
                for side, cutoff in (('opening', before_day), ('ending', end)):
                    if entry['day'] <= cutoff:
                        totals[side]['normal'] += wh.decimal(entry['consumed_quantity'])
                        totals[side]['loss'] += wh.decimal(entry['loss_quantity'])
            completions = {}
            for side, cutoff in (('opening', before_day), ('ending', end)):
                clipped = {key: doc for key, doc in documents.items() if doc['posted'] and doc['posted']['data']['entry']['day'] <= cutoff}
                completed, _, error = allocation.production_basis(db, item.line_id, context, clipped, True)
                completions[side] = completed
                if error:
                    blockers.append(dict(code='identity', message=error, line_id=item.line_id, issue_id=row['issue_id']))
            previous_row = prior_rows.get(row['issue_id'])
            price = price_map.get(context['root_batch_id'])
            if not price:
                blockers.append(dict(code='price', message=context['item_name'] + ' 原批次成本尚未确认', line_id=item.line_id, issue_id=row['issue_id']))
            if prior:
                expected = previous_row['ending_normal_quantity'] if previous_row else '0'
                expected_custody = previous_row['ending_custody'] if previous_row else '0'
                if wh.decimal(expected) != totals['opening']['normal'] or wh.decimal(expected_custody) != wh.decimal(row['opening_quantity']):
                    blockers.append(dict(code='opening_changed', message='期初与上月冻结期末不一致，须核对并反结相关月份', line_id=item.line_id, issue_id=row['issue_id']))
            rows.append(dict(issue_id=row['issue_id'], line_id=item.line_id, context=context, price=price,
                opening_normal_quantity=wh.text(totals['opening']['normal']), ending_normal_quantity=wh.text(totals['ending']['normal']),
                opening_loss_quantity=wh.text(totals['opening']['loss']), ending_loss_quantity=wh.text(totals['ending']['loss']),
                opening_custody=row['opening_quantity'], ending_custody=row['ending_quantity'],
                opening_sets=completions['opening'], ending_sets=completions['ending'],
                carried_completed_quantity=previous_row['completed_quantity'] if previous_row else ('0' if prior else None)))
    if prior and set(prior_rows) - {row['issue_id'] for row in rows}:
        blockers.append(dict(code='opening_missing', message='上月冻结实发依据缺失，请核对历史数据'))
    basis = dict(month=month, start=start, end=end, previous_lock_id=previous.id if previous else None,
                 previous_month=previous.month if previous else None, orders=reports, rows=rows, blockers=blockers, notices=notices)
    return dict(basis, basis_token=digest(fingerprint_basis(basis)), revision=events[-1].version if events else 0,
                state=state(states.get(month)), history=period_history([e for e in events if e.month == month]))


def calculate(basis, body):
    selected = {r.issue_id: r for r in body.allocations}
    c.require(set(selected) == {r['issue_id'] for r in basis['rows']}, '归集须逐行覆盖本月全部原实发，不能漏项或增添其他订单')
    rows, currencies, blockers = [], {}, deepcopy(basis['blockers'])
    if not body.materials_complete:
        blockers.append(dict(code='materials', message='全部物料耗用尚未核对完整'))
    if body.public_material_pending:
        blockers.append(dict(code='public', message='公共耗料尚待核清，本批不自动分摊'))
    if not body.opening_verified or body.unrecorded_opening:
        blockers.append(dict(code='opening', message='期初须完整核对；有系统外期初时先补齐专门依据，不能视为零'))
    if basis['notices'] and not body.exceptions_reviewed:
        blockers.append(dict(code='exceptions', message='请核对未收回、未签收、计划差异等跨月事项并填写处理依据'))
    with localcontext() as precision:
        precision.prec = 60
        for source in basis['rows']:
            chosen = selected[source['issue_id']]
            opening = wh.decimal(source['opening_normal_quantity'])
            ending = wh.decimal(source['ending_normal_quantity'])
            carried = source['carried_completed_quantity']
            prior = wh.decimal(carried) if carried is not None else chosen.opening_completed_quantity
            if carried is not None:
                c.require(chosen.opening_completed_quantity == prior, '期初完工归属必须承接上月冻结期末')
            finished = chosen.completed_quantity
            c.require(0 <= prior <= opening and prior <= finished <= ending, '完工耗用归属须在累计正常耗用内，并不得小于已冻结期初归属', 422)
            c.require(not prior or source['opening_sets'], '期初没有合格完成套数，不能归属期初完工耗用', 422)
            c.require(not finished or source['ending_sets'], '截至月末没有合格完成套数，不能归属完工耗用', 422)
            row = dict(source, opening_completed_quantity=wh.text(prior), completed_quantity=wh.text(finished),
                       opening_wip_quantity=wh.text(opening-prior), ending_wip_quantity=wh.text(ending-finished))
            if source['price']:
                price = source['price']['data']['entry']
                amount = lambda q: wh.decimal(usage.amount(q, price['unit_cost']))
                values = dict(opening_normal=amount(opening), ending_normal=amount(ending),
                              opening_completed=amount(prior), ending_completed=amount(finished),
                              opening_loss=amount(wh.decimal(source['opening_loss_quantity'])),
                              ending_loss=amount(wh.decimal(source['ending_loss_quantity'])),
                              opening_custody=amount(wh.decimal(source['opening_custody'])), ending_custody=amount(wh.decimal(source['ending_custody'])))
                values['opening_wip'] = values['opening_normal'] - values['opening_completed']
                values['ending_wip'] = values['ending_normal'] - values['ending_completed']
                for key in ('normal', 'completed', 'loss'):
                    values['period_' + key] = values['ending_' + key] - values['opening_' + key]
                row.update(currency=price['currency'], amounts={key: format(value, '.2f') for key, value in values.items()})
                bucket = currencies.setdefault(price['currency'], {key: Decimal(0) for key in values})
                for key, value in values.items():
                    bucket[key] += value
            rows.append(row)
    captured_at = wh.business_now().isoformat()
    captured_orders = [dict(order, generated_at=captured_at) for order in basis['orders']]
    return dict(month=basis['month'], start=basis['start'], end=basis['end'], orders=captured_orders, allocations=rows,
                costs={currency: {key: format(value, '.2f') for key, value in values.items()} for currency, values in currencies.items()},
                blockers=blockers, notices=basis['notices'], previous_lock_id=basis['previous_lock_id'], previous_month=basis['previous_month'],
                price_roots=sorted({r['context']['root_batch_id'] for r in rows if r['price']}),
                generated_at=captured_at)


def read(db, month, event_id=None):
    guards.ensure_schema(db)
    preview.period(month, wh.business_now().date())
    lock_transaction(db, 'cutting-master', c.FACTORY)
    events = guards.history(db)
    own = [e for e in events if e.month == month]
    selected = next((e for e in own if e.id == event_id), None) if event_id else (own[-1] if own else None)
    if event_id:
        c.require(selected is not None, '月结历史版本不存在', 404)
    return dict(month=month, revision=events[-1].version if events else 0, state=state(own[-1] if own else None),
                selected_state=state(selected), event_id=selected.id if selected else None,
                data=selected.data if selected else None, history=period_history(own),
                comparison=comparison(own, selected),
                **sequence(events))


def execute(db, user, body, action):
    guards.ensure_schema(db)
    events = guards.history(db)
    revision = events[-1].version if events else 0
    c.require(body.expected_version == revision, '月结记录已变化，请保留填写并刷新核对')
    current = guards.latest(events).get(body.month)
    current_state = state(current)
    if action == 'save':
        c.require(current_state in {'open', 'draft', 'returned', 'reopened'}, '请先退回或反结，再重新编制')
        basis = prepare(db, body.month)
        c.require(body.basis_token == basis['basis_token'], '生产、物料、成本或来源依据已变化，请保留填写并重新核对')
        data = dict(basis_token=basis['basis_token'], input=body.model_dump(mode='json'), snapshot=calculate(basis, body),
                    prepared_by=user.id, submitted_by=None, replaces_id=current.id if current else None)
    else:
        c.require(current is not None, '请先编制月结草稿')
        data = deepcopy(current.data)
        data['replaces_id'] = current.id
        if action == 'reopen':
            c.require(current_state == 'locked', '仅已锁月份可以反结')
            locks = guards.locked(db)
            c.require(body.month == max(locks), '有后续已锁月份，请从最近月份逐月反结')
        elif action == 'return':
            c.require(current_state == 'submitted', '仅待复核月结可以退回')
        else:
            c.require(current_state in ({'draft', 'returned'} if action == 'submit' else {'submitted'}), '月结状态已变化，请核对后操作')
            basis = prepare(db, body.month)
            c.require(data['basis_token'] == basis['basis_token'], '月结依据已变化，须重新编制并提交复核')
            c.require(not data['snapshot']['blockers'], '仍有缺价、期初、归集或未提交更正问题，不能提交或锁月')
            if action == 'submit':
                data['submitted_by'] = user.id
            else:
                # The built-in local admin may exercise both roles for acceptance only.
                local_admin = (settings.cutting_period_admin_acceptance and settings.app_env == 'development'
                               and user.id == 'user-admin' and 'admin' in user.role_codes)
                same_person = user.id in {data['prepared_by'], data['submitted_by']}
                c.require(not same_person or local_admin, '编制、提交人与复核锁月人须不同')
                data['local_admin_acceptance'] = bool(local_admin and same_person)
                data['locked_at'] = wh.business_now().isoformat()
    event = Event(id=body.operation_id, factory_id=c.FACTORY, month=body.month, version=revision+1, action=action,
                  data=data, actor_id=user.id, actor_name=user.display_name, created_at=wh.business_now().isoformat(), reason=body.reason)
    db.add(event)
    db.flush()
    return dict(id=event.id, month=event.month, version=event.version, state=state(event))
