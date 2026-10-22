"""Current, unclosed material allocation; no stock movements or period settlement.

One full task confirmation replaces its prior confirmation by appending evidence.
Production and use evidence are hashed, so corrections require explicit re-review.
"""
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import uuid4

from app.models.cutting_ops import CuttingOrderRevision
from app.models.cutting_material_usage import CuttingMaterialEvent
from app.services import cutting_ops as c, cutting_reporting as reporting, cutting_usage as usage

FIELDS = ('dispatch_id', 'bom_id', 'bom_version', 'task_id', 'resource_id', 'resource_version')


def identity(context):
    return tuple(context.get(key) for key in FIELDS)


def production_basis(db, line_id, context, docs, ready, versions=None):
    if not ready:
        return None, [], '需先完成每日填数迁移及证据保护'
    selected = {key: d for key, d in docs.items() if d['posted'] and
                d['posted']['data']['entry']['task_id'] == context['task_id']}
    basis = []
    for document in selected.values():
        event = document['posted']
        frozen = event['data']['context']
        key = (line_id, frozen['plan_version'])
        revision = db.get(CuttingOrderRevision, key) if versions is None else versions.get(key)
        plan = (revision.data.get('planning', {}).get('published') if revision else None) or {}
        task = next((t for t in plan.get('tasks', []) if t['task_id'] == context['task_id']), None)
        version = task.get('resource_version') if task else None
        if (any(frozen.get(k) != context.get(k) for k in ('dispatch_id', 'bom_id', 'bom_version', 'resource_id'))
                or version is None or version != context.get('resource_version')):
            return None, [], '实绩与领料的订单、BOM或执行方版本不一致，需核对任务归属'
        # Handover does not change the qualified-completion denominator.
        if event['data']['entry']['kind'] != 'handover':
            basis.append(dict(id=event['id'], document_id=event['document_id'], version=event['version'], data=event['data']))
    balances, _ = reporting.replay(selected)
    return balances.get(context['task_id'], {}).get('completed', 0), basis, ''


def view(db, line_id, rows, history, *, production_snapshot=None):
    if production_snapshot is None:
        ready = reporting.schema_ready(db.connection())
        reports = reporting.documents(reporting.events(db, line_id)) if ready else {}
        versions = None
    else:
        ready, all_reports, versions = production_snapshot
        reports = all_reports.get(line_id, {})
    uses = usage.documents(history)
    confirmations = [e for e in history if e['action'] == 'allocate' and e['line_id'] == line_id]
    latest = {identity(e['data']['context']): e for e in confirmations}
    groups = {}
    for row in rows:
        if not row['reversed']:
            groups.setdefault(identity(row['context']), []).append(row)
    result = []
    with localcontext() as precision:
        precision.prec = 60
        for key, members in groups.items():
            context = members[0]['context']
            completed, production, blocked = production_basis(db, line_id, context, reports, ready, versions)
            ids = {row['issue_id'] for row in members}
            used = [d['posted'] for d in uses.values() if d['posted'] and d['posted']['data']['entry']['issue_id'] in ids]
            # Price revisions revalue unlocked reports, but never invalidate confirmed physical allocation.
            evidence = dict(identity=key, issues=sorted(ids), production=production,
                            uses=[dict(id=e['id'], version=e['version'], data={k: v for k, v in e['data'].items() if k != 'cost_at_post'}) for e in used])
            basis_documents = dict(
                usage=[dict(document_id=e['document_id'], event_id=e['id'], version=e['version'], entry=e['data']['entry']) for e in used],
                production=[dict(document_id=e['document_id'], event_id=e['id'], version=e['version'], entry=e['data']['entry']) for e in production])
            token = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            previous = latest.get(key)
            valid = bool(previous and previous['data']['basis_token'] == token and not blocked)
            entry = previous['data']['entry'] if previous else {}
            assigned = {r['issue_id']: r['completed_quantity'] for r in entry.get('allocations', [])} if valid else {}
            if valid and (set(assigned) != ids or any(not 0 <= usage.wh.decimal(assigned[r['issue_id']]) <= usage.wh.decimal(r['consumed_quantity']) for r in members)):
                blocked, valid, assigned = '归属数量与当前正常耗用不符，请重新核对', False, {}
            quantities, costs, pending = [], {}, 0
            for row in members:
                normal = usage.wh.decimal(row['consumed_quantity'])
                allocated = usage.wh.decimal(assigned.get(row['issue_id'], '0')) if valid else None
                wip = normal - allocated if allocated is not None else None
                quantity = dict(issue_id=row['issue_id'], item_name=row['context']['item_name'], unit=row['context']['unit'],
                    root_batch_id=row['context']['root_batch_id'], consumed_quantity=row['consumed_quantity'],
                    completed_quantity=usage.wh.text(allocated) if allocated is not None else None,
                    wip_quantity=usage.wh.text(wip) if wip is not None else None)
                quantities.append(quantity)
                if normal + usage.wh.decimal(row['loss_quantity']) <= 0:
                    continue
                if not row['price']:
                    pending += 1
                    continue
                price = row['price']['data']['entry']
                money = costs.setdefault(price['currency'], dict(completed=Decimal(0), wip=Decimal(0), loss=Decimal(0)))
                money['loss'] += usage.wh.decimal(row['loss_cost'])
                if valid:
                    finished = usage.wh.decimal(usage.amount(allocated, price['unit_cost']))
                    money['completed'] += finished
                    # Keep the original rounded normal cost exactly conserved, including cent residuals.
                    money['wip'] += usage.wh.decimal(row['normal_cost']) - finished
            reasons = []
            if blocked: reasons.append(blocked)
            if not previous: reasons.append('尚未确认完工耗用归属')
            elif not valid: reasons.append('耗用或实绩依据已变更，请重新确认')
            if not entry.get('materials_complete'): reasons.append('全部物料耗用尚未核对完整')
            if entry.get('public_material_pending', True): reasons.append('公共耗料仍待分配核对')
            if pending: reasons.append('已有耗用的实发记录仍待计价')
            if not completed: reasons.append('没有可用于核算的合格完成套数')
            status = 'blocked' if blocked else 'unconfirmed' if not previous else 'stale' if not valid else 'pending' if reasons else 'confirmed'
            formatted = {currency: dict(
                completed=format(m['completed'], '.2f') if valid else None,
                wip=format(m['wip'], '.2f') if valid else None,
                loss=format(m['loss'], '.2f'),
                unit_cost=format((m['completed'] / Decimal(completed)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP), '.6f') if status == 'confirmed' else None)
                for currency, m in costs.items()}
            result.append(dict(key=members[0]['issue_id'], context={k: context.get(k) for k in (*FIELDS, 'task_name', 'resource_name', 'execution')},
                basis_token=token, basis_documents=basis_documents, completed_sets=completed, status=status, reasons=reasons, pending_pricing=pending,
                rows=quantities, costs=formatted, materials_complete=entry.get('materials_complete', False),
                public_material_pending=entry.get('public_material_pending', True), latest_id=previous['id'] if previous else None))
    return dict(schema_ready=ready, groups=result, history=[dict(id=e['id'], version=e['version'], actor=e['actor'],
        date=e['date'], reason=e['reason'], context=e['data']['context'], entry=e['data']['entry'],
        completed_sets=e['data']['completed_sets'], replaces_id=e['data'].get('replaces_id'),
        price_snapshot=e['data'].get('price_snapshot', []), basis_documents=e['data'].get('basis_documents', {})) for e in confirmations])


def confirm(db, actor, line_id, body):
    # usage.read takes cutting -> fabric locks; all report mutations use cutting lock.
    current = usage.read(db, line_id, show_costs=True)
    c.require(current['revision'] == body.expected_version, '耗用或成本记录已变化，请保留填写并刷新后核对')
    c.require(body.day == usage.wh.business_now().date(), '归集确认按今天登记，不支持倒签历史月结', 422)
    groups = current['cost_allocation']['groups']
    group = next((g for g in groups if any(r['issue_id'] == body.issue_id for r in g['rows'])), None)
    c.require(group is not None, '请选择有效原实发所属任务', 422)
    c.require(group['status'] != 'blocked', '；'.join(group['reasons']))
    c.require(group['basis_token'] == body.basis_token, '耗用、实绩或任务依据已变化，请刷新并重新确认')
    values = {r.issue_id: r.completed_quantity for r in body.allocations}
    c.require(set(values) == {r['issue_id'] for r in group['rows']}, '确认须逐笔覆盖本任务全部有效实发，不能跨任务归集', 422)
    for row in group['rows']:
        c.require(values[row['issue_id']] <= usage.wh.decimal(row['consumed_quantity']), '完工归属量不能超过该原实发的累计正常耗用', 422)
        c.require(group['completed_sets'] or values[row['issue_id']] == 0, '没有合格完成套数时不能归属完工耗用', 422)
    identifier = uuid4().hex
    entry = body.model_dump(mode='json', exclude={'factory_id', 'operation_id', 'expected_version', 'reason', 'basis_token'})
    data = dict(entry=entry, context=group['context'], basis_token=group['basis_token'], basis_documents=group['basis_documents'],
                completed_sets=group['completed_sets'], replaces_id=group['latest_id'],
                price_snapshot=[dict(issue_id=r['issue_id'], price=r['price'], normal_cost=r['normal_cost'], loss_cost=r['loss_cost'])
                                for r in current['issues'] if r['issue_id'] in values])
    db.add(CuttingMaterialEvent(id=identifier, line_id=line_id, factory_id=c.FACTORY, version=current['revision']+1,
        document_id=identifier, action='allocate', data=data, actor_id=actor.id, actor_name=actor.display_name,
        created_at=datetime.now(UTC).isoformat(), reason=body.reason))
    db.flush()
    return dict(id=identifier, document_id=identifier, version=current['revision']+1)
