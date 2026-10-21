"""Cutting requests and signatures share the warehouse's immutable document ledger.

No stock mirror, no automatic readiness or cost postings. Dual-domain lock order:
cutting factory -> source order (when issuing/requesting) -> fabric factory.
"""
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select
from app.models.cutting_ops import CuttingOrder, CuttingOrderRevision
from app.models.warehouse_operations import WarehouseOperation
from app.services import cutting_ops as c, cutting_orders as orders, cutting_planning as plans
from app.services import warehouse_operations as wh, fabric_master as masters
from app.services.transaction_lock import lock_transaction
from app.schemas.warehouse_operations import WarehouseDocumentRequest

SOURCE = 'CUTTING_P3A'
INTERNAL_KINDS = {'CUTTING_RECEIPT', 'CUTTING_RECEIPT_VOID', 'CUTTING_REQUEST_REUSE'}


def catalog(db, q='', page=1):
    masters.ensure_schema(db)
    rows = []
    for item in masters.records(db):
        if item.kind != 'MATERIAL' or item.status != 'ACTIVE': continue
        record = masters.record_data(item)
        data = record['data']
        # Never expose supplier, pricing or warehouse-wide stock through cutting read.
        row = {k: record[k] for k in ('id', 'code', 'name', 'revision')}
        row.update({k: data.get(k, '') for k in ('unit', 'category', 'spec', 'color')})
        if not q or q.casefold() in ' '.join(str(v) for v in row.values()).casefold(): rows.append(row)
    rows.sort(key=lambda r: (r['code'], r['id']))
    return dict(items=rows[(page-1)*50:page*50], total=len(rows), page=page)


def linked(db, identifier):
    row = db.get(WarehouseOperation, identifier) if identifier else None
    if not row or row.factory_id != c.FACTORY or row.warehouse != 'fabric': return None
    entry = wh.entry_data(row)
    if entry['kind'] == 'REQUEST' and entry['data'].get('cutting_request'): return entry
    if entry['kind'] in {'ISSUE', 'RETURN', 'CUTTING_RECEIPT', 'CUTTING_RECEIPT_VOID', 'CORRECTION'}:
        return linked(db, entry['data'].get('original_id'))
    return None


def current_context(db, line_id, task_id, expected=None):
    line, dispatch = orders.lock_source(db, line_id)
    order = db.get(CuttingOrder, line_id)
    c.require(order is not None and order.dispatch_id == dispatch.id and line.status == 'active', '订单已取消或来源有变，请关闭旧申请余量并核对新版本')
    if expected is not None: c.require(order.version == expected, '裁床记录已变化，请刷新后重新核对')
    data = orders.revision(db, order)['data']
    plan = data.get('planning', {}).get('published')
    c.require(plan and not plans.summary(db, data)['published_stale'], '需先发布并复核当前任务、BOM与采购依据')
    task = next((t for t in plan['tasks'] if t['task_id'] == task_id), None)
    c.require(task is not None, '原执行任务已移除，请关闭旧申请余量')
    return data, plan, task


def guard_current(db, request, *, reuse=False):
    frozen = request['data']['cutting_request']
    data, plan, task = current_context(db, frozen['line_id'], frozen['task_id'])
    c.require(data['dispatch_id'] == frozen['dispatch_id']
              and data['bom']['id'] == frozen['bom_id'] and data['bom']['version'] == frozen['bom_version']
              and task['resource_id'] == frozen['resource_id'] and task['resource_version'] == frozen['resource_version'],
              '原领料申请的订单、BOM或发布计划已变更，请关闭未发余量后重新申请')
    accepted = request.get('accepted_plan_version', frozen['plan_version'])
    if reuse:
        old = db.get(CuttingOrderRevision, (frozen['line_id'], frozen['plan_version']))
        original_plan = (old.data.get('planning', {}).get('published') if old else None) or {}
        original_task = next((t for t in original_plan.get('tasks', []) if t['task_id'] == frozen['task_id']), None)
        c.require(original_task and original_task['target_sets'] == task['target_sets'],
                  '原任务数量范围已变化或历史依据缺失，请关闭余量后重新申请')
        c.require(not request.get('closed') and wh.decimal(request['issued_quantity']) < wh.decimal(request['data']['quantity']), '申请已关闭或没有未发余量')
        c.require(plan['version'] != accepted, '申请已对应当前发布计划，无需重复续用')
    else:
        c.require(plan['version'] == accepted, '发布计划已变化，请由裁床核对续用或关闭未发余量')
    material = next((m for m in masters.records(db) if m.id == frozen['warehouse_material']['id']), None)
    c.require(material is not None and material.status == 'ACTIVE' and material.revision == frozen['warehouse_material']['revision'],
              '仓库物料资料已变更，请重新核对领料申请')
    return plan


def before_warehouse_lock(db, warehouse, payload):
    if warehouse != 'fabric': return
    request = linked(db, payload.original_id)
    if request:
        lock_transaction(db, 'cutting-master', c.FACTORY)
        # Only new issues depend on a current active source. Historical signatures and
        # returns still settle the old executor after cancellation or republishing.
        if payload.kind == 'ISSUE':
            # Lock only: replay of an already committed issue must remain possible
            # after source changes. Current-source validation belongs to new writes.
            db.scalar(select(orders.OrderLedgerLine).where(
                orders.OrderLedgerLine.id == request['data']['cutting_request']['line_id'],
                orders.OrderLedgerLine.factory_id == c.FACTORY).with_for_update().execution_options(populate_existing=True))


def guard_post(db, warehouse, body, metadata, stock, entries):
    c.require(metadata is not None or (body['source_system'] != SOURCE and body['kind'] not in INTERNAL_KINDS),
              '裁床来源及签收凭据只能从裁床接口提交', 422)
    request = linked(db, body.get('original_id')) if warehouse == 'fabric' else None
    if body['kind'] == 'REQUEST_CLOSE':
        c.require(request is not None and body['original_id'] == request['id'], '仅可关闭已对接裁床申请的未发余量', 422)
    if not request: return
    request = entries[request['id']]
    from app.services.cutting_period_guards import guard_warehouse
    guard_warehouse(db, entries, body, request)
    if body['kind'] == 'ISSUE':
        from app.core.config import settings
        c.require(settings.cutting_ops_enabled, '裁床业务尚未启用，不能继续发料', 503)
        guard_current(db, request)
        batch = wh.batch_for(stock, body['batch_id'])
        c.require(batch['item_name'] == request['data']['item_name'] and batch['material_category'] == request['data']['material_category'],
                  '批次名称或物料类别与冻结申请不符，请核对仓库物料身份', 422)
        # An issue belongs to this single request/task; arbitrary allocations cannot relabel it.
        c.require(not body['allocations'], '裁床关联出库按原申请归属，不另作生产单分配', 422)
        body['source_system'] = SOURCE
        body['source_no'] = request['data']['source_no']
        body['production_no'] = request['data']['production_no']
        body['purpose'] = request['data']['purpose']
    elif body['kind'] == 'RETURN':
        original = entries[body['original_id']]
        daily = {}
        for e in entries.values():
            if e['kind'] not in {'CUTTING_RECEIPT', 'RETURN'} or e['data']['original_id'] != original['id'] or e.get('reversed'): continue
            day = e['business_date']
            daily[day] = daily.get(day, Decimal(0)) + wh.decimal(e['data']['quantity']) * (1 if e['kind'] == 'CUTTING_RECEIPT' else -1)
        day = body['business_date']
        daily[day] = daily.get(day, Decimal(0)) - wh.decimal(body['quantity'])
        balance = Decimal(0)
        for day in sorted(daily):
            balance += daily[day]
            c.require(balance >= 0, '裁床退料不能超过各业务日已签收的净可退数量，请核对签收日期及数量')


def projection_event(stock, entries, entry):
    """Replay only evidence; never mutate the warehouse stock projection here."""
    data, kind = entry['data'], entry['kind']
    if kind not in INTERNAL_KINDS | {'REQUEST_CLOSE'}: return False
    original = wh.original_for(entries, data['original_id'], {'REQUEST'} if kind in {'REQUEST_CLOSE', 'CUTTING_REQUEST_REUSE'} else {'ISSUE'} if kind == 'CUTTING_RECEIPT' else {'CUTTING_RECEIPT'})
    c.require(entry['business_date'] >= original['business_date'], '签收／关闭日期不能早于原单日期', 422)
    wh.required(data, 'reason')
    if kind == 'CUTTING_REQUEST_REUSE':
        c.require(original['data'].get('cutting_request') and not original.get('closed'), '申请已关闭或不是裁床关联申请')
        original['accepted_plan_version'] = data['reuse_plan_version']
    elif kind == 'REQUEST_CLOSE':
        c.require(original['data'].get('cutting_request') and not original.get('closed'), '申请已关闭或不是裁床关联申请')
        c.require(not any(e['kind'] == 'ISSUE' and e['data']['original_id'] == original['id']
            and e['business_date'] > entry['business_date'] for e in entries.values()), '关闭日期不能早于已发料日期', 422)
        original['closed'] = True
        original['close_reason'] = data['reason']
    elif kind == 'CUTTING_RECEIPT':
        request = entries.get(original['data']['original_id'])
        c.require(request and request['data'].get('cutting_request'), '签收必须关联裁床申请实发', 422)
        q = wh.quantity(data['quantity'], '本次签收数量')
        received = wh.decimal(original.get('cutting_received_quantity', '0'))
        c.require(received + q <= wh.decimal(original['data']['quantity']), '累计签收不能超过原单实发数量')
        original['cutting_received_quantity'] = wh.text(received + q)
        data['quantity'] = wh.text(q)
        entry['cutting_request_id'] = request['id']
    else:
        issue = entries[original['data']['original_id']]
        returns = [e for e in entries.values() if e['kind'] == 'RETURN' and e['data']['original_id'] == issue['id']]
        c.require(not any(not e.get('reversed') for e in returns), '原出库已有有效退料，不能直接撤销签收，请先核对或冲销退料')
        c.require(not any(e['kind'] == 'CORRECTION' and e['data']['original_id'] in {r['id'] for r in returns}
                          and e['business_date'] > entry['business_date'] for e in entries.values()), '撤签日期不能早于退料冲销日期')
        issue['cutting_received_quantity'] = wh.text(wh.decimal(issue['cutting_received_quantity']) - wh.decimal(original['data']['quantity']))
        original['reversed'] = True
        data['quantity'] = original['data']['quantity']
    wh.describe_item(data, original.get('batch_snapshot') or original['data'])
    data['counterparty'] = original['data']['counterparty']
    entries[entry['id']] = entry
    return True


def receipt_reader(db):
    """Lazy, single-read-call projection under the caller's cutting lock.

    Never store this on the session or use it across mutations/transactions.
    Write paths omit it and continue to load fresh evidence.
    """
    transaction = db.get_transaction()
    entries = None
    def read():
        nonlocal entries
        if db.get_transaction() is not transaction:
            raise RuntimeError('Receipt projection cannot cross transactions')
        if entries is None:
            wh.ensure_schema(db)
            _, entries = wh.projection(db, 'fabric')
        return entries
    return read


def receipt_evidence(db, data, task, *, receipt_entries=None):
    """Validate explicit scheduling links; receipt evidence never proves full readiness."""
    ids = task.get('material_receipt_ids', [])
    if not ids:
        return []
    if receipt_entries is None:
        wh.ensure_schema(db)
        _, entries = wh.projection(db, 'fabric')
    else:
        entries = receipt_entries()
    result = []
    for identifier in ids:
        receipt = entries.get(identifier)
        c.require(receipt and receipt['kind'] == 'CUTTING_RECEIPT' and not receipt.get('reversed'), '关联签收已撤销或不存在，请重新核对实际领料凭据')
        issue = entries.get(receipt['data']['original_id'])
        # The validated fabric projection already contains the entire immutable
        # receipt -> issue -> request chain. Do not re-query all three rows.
        request = entries.get(issue['data']['original_id']) if issue else None
        if not request or request['kind'] != 'REQUEST' or not request['data'].get('cutting_request'):
            request = None
        frozen = request['data']['cutting_request'] if request else {}
        c.require(issue and not issue.get('reversed') and frozen.get('dispatch_id') == data['dispatch_id']
                  and frozen.get('bom_id') == data['bom']['id'] and frozen.get('bom_version') == data['bom']['version']
                  and frozen.get('task_id') == task['task_id'] and frozen.get('resource_id') == task['resource_id'],
                  '签收不属于当前订单、BOM及执行任务，请重新核对')
        c.require(wh.decimal(issue.get('cutting_received_quantity', '0')) > wh.decimal(issue.get('returned_quantity', '0')),
                  '关联实发的签收已全部退仓，请重新核对实际领料依据')
        result.append(dict(id=identifier, date=receipt['business_date'], quantity=receipt['data']['quantity'],
            issue_id=issue['id'], request_id=request['id'], returned_quantity=issue.get('returned_quantity', '0')))
    c.require(task.get('actual_issue_date') == max(r['date'] for r in result), '实际领料日期须为所选有效签收的最晚日期', 422)
    return result


def receipts_changed(db, data, plan, *, receipt_entries=None):
    if not plan:
        return False
    from fastapi import HTTPException
    for task in plan['tasks']:
        if not task.get('material_receipt_ids'):
            continue
        try:
            if receipt_evidence(db, data, task, receipt_entries=receipt_entries) != task.get('material_receipts', []):
                return True
        except HTTPException as error:
            if error.status_code == 503:
                raise
            return True
    return False


def totals(requests, db):
    """Exact quantities grouped by original task/BOM identity, never pooled across units."""
    groups = {}
    for request in requests:
        frozen = request['context']
        key = (frozen['dispatch_id'], frozen['bom_id'], frozen['bom_version'], frozen['task_id'],
               frozen['resource_id'], frozen['resource_version'], frozen['row'], request['unit'])
        if key not in groups:
            old = db.get(CuttingOrderRevision, (frozen['line_id'], frozen['plan_version']))
            data = old.data if old else {}
            task = next((t for t in (data.get('planning', {}).get('published') or {}).get('tasks', []) if t['task_id'] == frozen['task_id']), None)
            requirements = (data.get('bom') or {}).get('data', {}).get('requirements', [])
            theoretical = None
            if task and frozen['row'] < len(requirements):
                theoretical = wh.text(wh.decimal(requirements[frozen['row']]['quantity_per_set']) * Decimal(task['target_sets']))
            groups[key] = dict(dispatch_id=key[0], bom_id=key[1], bom_version=key[2], task_id=key[3],
                resource_id=key[4], resource_version=key[5], row=key[6], unit=key[7], task_name=frozen['task_name'],
                basis_plan_version=frozen['plan_version'], basis_target_sets=task['target_sets'] if task else None,
                material_name=frozen['cutting_material']['name'], theoretical_quantity=theoretical,
                requested_quantity=Decimal(0), effective_requested_quantity=Decimal(0), issued_quantity=Decimal(0),
                received_quantity=Decimal(0), returned_quantity=Decimal(0), outstanding_quantity=Decimal(0))
        group = groups[key]
        quantity, issued = wh.decimal(request['quantity']), wh.decimal(request['issued_quantity'])
        group['requested_quantity'] += quantity
        group['effective_requested_quantity'] += issued if request['closed'] else quantity
        group['issued_quantity'] += issued
        group['outstanding_quantity'] += Decimal(0) if request['closed'] else quantity - issued
        group['received_quantity'] += sum((wh.decimal(r['quantity']) for r in request['receipts'] if not r['reversed']), Decimal(0))
        group['returned_quantity'] += sum((wh.decimal(i['returned_quantity']) for i in request['issues'] if not i['reversed']), Decimal(0))
    result = []
    for group in groups.values():
        group['net_received_quantity'] = group['received_quantity'] - group['returned_quantity']
        group['exceeds_theoretical'] = group['theoretical_quantity'] is not None and group['effective_requested_quantity'] > wh.decimal(group['theoretical_quantity'])
        result.append({k: wh.text(v) if isinstance(v, Decimal) else v for k, v in group.items()})
    return result


def read(db, line_id):
    c.require(orders.latest(db, line_id) is not None, '华康C裁床来源订单不存在', 404)
    wh.ensure_schema(db)
    _, entries = wh.projection(db, 'fabric')
    requests = [e for e in entries.values() if e['kind'] == 'REQUEST' and e['data'].get('cutting_request', {}).get('line_id') == line_id]
    result = []
    for request in requests:
        issues = [e for e in entries.values() if e['kind'] == 'ISSUE' and e['data']['original_id'] == request['id']]
        issue_ids = {e['id'] for e in issues}
        receipts = [e for e in entries.values() if e['kind'] == 'CUTTING_RECEIPT' and e['data']['original_id'] in issue_ids]
        related = {request['id'], *issue_ids, *(e['id'] for e in receipts)}
        history = []
        for e in entries.values():
            if e['id'] in related or (e['data'].get('original_id') in related and e['kind'] != 'COMMAND_ABANDONED'):
                related.add(e['id'])
                history.append(dict(id=e['id'], original_id=e['data'].get('original_id', ''), kind=e['kind'],
                    date=e['business_date'], occurred_at=e['occurred_at'], actor=e['actor_name'],
                    reason=e['data']['reason'], quantity=e['data'].get('quantity', ''), reversed=e.get('reversed', False),
                    plan_version=e['data'].get('reuse_plan_version')))
        result.append(dict(id=request['id'], date=request['business_date'], quantity=request['data']['quantity'],
            due_date=request['data'].get('due_date'), history=history,
            accepted_plan_version=request.get('accepted_plan_version', request['data']['cutting_request']['plan_version']),
            unit=request['data']['unit'], item_name=request['data']['item_name'], item_code=request['data']['item_code'],
            issued_quantity=request['issued_quantity'], closed=request.get('closed', False), close_reason=request.get('close_reason', ''),
            context=request['data']['cutting_request'], reason=request['data']['reason'],
            issues=[dict(id=e['id'], date=e['business_date'], quantity=e['data']['quantity'], reversed=e.get('reversed', False),
                received_quantity=e.get('cutting_received_quantity', '0'), returned_quantity=e.get('returned_quantity', '0'),
                lot=e['batch_snapshot']['lot'], roll_no=e['batch_snapshot']['roll_no'], location=e['batch_snapshot']['location']) for e in issues],
            receipts=[dict(id=e['id'], original_id=e['data']['original_id'], date=e['business_date'], quantity=e['data']['quantity'],
                reason=e['data']['reason'], actor=e['actor_name'], reversed=e.get('reversed', False)) for e in receipts]))
    return dict(revision=max((e['sequence'] for e in entries.values()), default=0), requests=result, totals=totals(result, db))


def execute(db, actor, line_id, body, action):
    wh.ensure_schema(db); masters.ensure_schema(db)
    if action == 'request':
        data, plan, task = current_context(db, line_id, body.task_id, body.expected_version)
        c.require(plan['version'] == body.plan_version, '发布计划已更新')
    elif action == 'reuse':
        request = linked(db, body.original_id)
        c.require(request and request['id'] == body.original_id and request['data']['cutting_request']['line_id'] == line_id, '原申请不属于当前订单', 404)
        current_context(db, line_id, request['data']['cutting_request']['task_id'])
    else:
        c.require(orders.latest(db, line_id) is not None, '裁床订单不存在', 404)
    state = wh.procurement.lock_factory(db)
    _, entries = wh.projection(db, 'fabric')
    revision = max((e['sequence'] for e in entries.values()), default=0)
    common = dict(factory_id=c.FACTORY, request_id=uuid5(NAMESPACE_URL, f'cutting-material:{actor.id}:{body.operation_id}'),
        expected_revision=revision, business_date=body.business_date, reason=body.reason, source_system=SOURCE)
    metadata = {}
    if action == 'request':
        requirements = data['bom']['data']['requirements']
        c.require(body.row < len(requirements), 'BOM物料行不存在', 422)
        requirement = requirements[body.row]
        c.validate_references(db, data['bom']['data'], publishing=True)
        local = c.view(db, c.master(db, requirement['material_id']), requirement['material_version'])
        material = next((m for m in masters.records(db) if m.id == body.material_id and m.kind == 'MATERIAL' and m.status == 'ACTIVE'), None)
        c.require(material is not None and material.revision == body.material_revision, '请重新选择有效仓库物料版本')
        master = masters.record_data(material)
        md = master['data']
        c.require(md['unit'] == requirement['unit'], '申请与仓库物料单位必须一致，本阶段不自动换算', 422)
        c.require((local['data']['category'] == 'fabric') == (md['category'] == 'FABRIC'), '裁床与仓库物料类别不一致', 422)
        c.require(body.due_date is None or body.due_date >= body.business_date, '需料日期不能早于申请日期', 422)
        frozen = dict(line_id=line_id, dispatch_id=data['dispatch_id'], order_no=data['order']['reference_no'],
            bom_id=data['bom']['id'], bom_version=data['bom']['version'], plan_version=plan['version'], task_id=task['task_id'],
            task_name=task['name'], resource_id=task['resource_id'], resource_version=task['resource_version'],
            resource_name=task['resource']['data']['name'], execution=task['resource']['data']['execution'], row=body.row,
            cutting_material=dict(id=local['id'], version=local['version'], code=local['code'], **local['data']),
            warehouse_material={**{k: master[k] for k in ('id','revision','code','name')},
                **{k: md.get(k, '') for k in ('spec','color','unit','category')}}, mapping_basis=body.mapping_basis,
            required_for_cutting=requirement['required_for_cutting'], stage=requirement['stage'])
        metadata = {'cutting_request': frozen}
        payload = WarehouseDocumentRequest(**common, kind='REQUEST', quantity=str(body.quantity), item_code=material.code,
            item_name=material.name, unit=md['unit'], material_category=md['category'], counterparty=frozen['resource_name'],
            production_no=frozen['order_no'], source_no='CUT-'+body.operation_id, source_line=str(body.row+1), source_version=str(plan['version']),
            purpose=frozen['task_name'], due_date=body.due_date)
    else:
        c.require(body.expected_version == revision, '仓库收发或签收已变化，请刷新后核对')
        request = linked(db, body.original_id)
        c.require(request and request['data']['cutting_request']['line_id'] == line_id, '原单不属于当前裁床订单', 404)
        kind = {'receive':'CUTTING_RECEIPT', 'void':'CUTTING_RECEIPT_VOID', 'close':'REQUEST_CLOSE', 'reuse':'CUTTING_REQUEST_REUSE'}[action]
        if action == 'reuse':
            plan = guard_current(db, entries[request['id']], reuse=True)
            c.require(plan['version'] == body.plan_version, '发布计划已更新，请重新核对续用')
            metadata = {'reuse_plan_version': plan['version'], 'previous_plan_version': entries[request['id']].get('accepted_plan_version', request['data']['cutting_request']['plan_version'])}
        payload = WarehouseDocumentRequest(**common, kind=kind, original_id=body.original_id, quantity=str(body.quantity) if action=='receive' else '')
    return wh.post(db, actor, 'fabric', payload, _state=state, _commit=False, _metadata=metadata)
