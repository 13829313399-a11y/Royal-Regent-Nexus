"""Read-only carton projections from the native combined ledger and stock report.

Native navigation and model/browser acceptance have separate evidence gates.
"""
import base64
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from app import db as database
from app.core.time import parse_business_timestamp
from app.models.carton_customer_assignment import CartonCustomerAssignment
from app.models.carton_procurement import CartonCustomer
from app.schemas.carton_unified_orders import Selection
from app.services import carton_procurement as core, carton_special_requests as special
from app.services import carton_order_queries as orders, carton_unified_order_actions as selections
from app.services.carton_inventory_report import inventory_report
from app.services.auth import has_permission_in_scope
from .errors import AssistantError
from .evidence import stable_id
from .help_registry import supplier_only
from .tool_result import validate_result

NAME = 'get_carton_overview'
KINDS = {'PURCHASE', 'SAMPLE', 'WORKSHOP_MISC', 'SUPPLIER_GIFT'}
ORDER_FILTERS = {'responsibility_scope', 'kind', 'customer_name', 'status_filter', 'due_filter', 'sort', 'collaboration_filter'}
ROW_FIELDS = {'resource_ref', 'id', 'kind', 'number', 'factory_id', 'customer_code', 'customer_name',
              'status', 'revision', 'order_date', 'due_date', 'updated_at', 'contract_no', 'item_no',
              'product_name', 'quantity_basis', 'product_order_quantity', 'supplier_acceptance',
              'lines', 'line_count', 'lines_truncated', 'truncated_fields', 'order_id', 'order_line_id',
              'packaging_type', 'paper_quality', 'specification', 'unit', 'opening_quantity', 'inbound_quantity',
              'outbound_quantity', 'adjustment_quantity', 'ending_quantity', 'last_movement_at',
              'current_usage_quantity', 'current_usage_status', 'current_usage_label', 'current_positions',
              'position_count', 'positions_truncated', 'available_quantity'}
DEFINITIONS = {
    'carton.count.v1': '完整授权筛选范围的单据数；包含正单、样板、车间杂单及供应商赠品，以kind区分。不是当前页行数。',
    'carton.pending.v1': '原合并台账统计：状态不是COMPLETED/CANCELLED的单据数。',
    'carton.overdue.v1': '原合并台账统计：未结束且纸品要求到货日早于查询时上海业务日期；不是订单客户交期。',
    'carton.required.v1': '完整筛选范围所有单据原纸品行需求量，包含已结束单据；按原单位分别求和，不换算为产品数量。',
    'carton.received.v1': '原单据纸品行received_quantity：正单为冲回及补料规则后的履约收料，特殊单为有效已确认收料；不是可用库存。',
    'carton.remaining.v1': '完整筛选范围尚未结束的纸品行remaining_quantity之和；排除CANCELLED/COMPLETED，按原单位分别汇总；不是库存缺口。',
    'carton.available.v1': '源系统未提供可分配、预留及质检扣减后的可用库存口径，保持未知；采购未到、账面结存和仓位数量不能替代可用量。',
    'carton.stock_count.v1': '原库存报表完整筛选范围的库存标识行数；同订单不同纸品/单位独立，不是订单数。',
    'carton.opening.v1': '原库存报表期间首日前的账面结存；未指定开始日则自流水起点计算。',
    'carton.inbound.v1': '原库存报表期间有效入库，包含原入库的冲回负数；不是当前页流水之和。',
    'carton.outbound.v1': '原库存报表期间有效出库，包含原出库的冲回负数。',
    'carton.adjustment.v1': '原库存报表期间有符号库存调整。',
    'carton.ending.v1': '原库存报表期间末日账面结存=期初+入库-出库+调整；未指定末日则截至本次读取。不是可分配量。',
    'carton.positions.v1': 'current_positions为本次读取时正结存仓位，current_usage为当前使用进度；两者均不是历史报表末日状态，不与历史结存混算。',
    'carton.scope.v1': '订单默认OWN本人负责范围；ALL仅使用原台账允许的全部范围，特殊单仍逐单检查创建者/负责人权限。库存报表沿用原厂区read权限，不冒称本人订单范围。',
    'carton.time.v1': 'as_of为本轮数据库一致性读取时间；updated_at/last_movement_at保留原记录时间。读取不会刷新业务数据。',
}


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def decimal(value):
    return format(Decimal(value), 'f')


def timestamp(value):
    parsed = parse_business_timestamp(value)
    return parsed.isoformat() if parsed else None


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    view: Literal['orders', 'inventory'] = 'orders'
    resource_id: str | None = Field(default=None, min_length=1, max_length=128)
    responsibility_scope: Literal['OWN', 'ALL'] = 'OWN'
    kind: Literal['ALL', 'PURCHASE', 'SAMPLE', 'WORKSHOP_MISC', 'SUPPLIER_GIFT'] = 'ALL'
    search: str = Field(default='', max_length=128)
    customer_name: str = Field(default='', max_length=128)
    customer_code: str = Field(default='', max_length=64)
    status_filter: str = Field(default='', max_length=32)
    date_from: str = Field(default='', max_length=10)
    date_to: str = Field(default='', max_length=10)
    due_filter: Literal['ALL', 'OVERDUE', 'TODAY', 'DUE_SOON', 'UPCOMING'] = 'ALL'
    sort: Literal['ORDER_DESC', 'DUE_ASC', 'DUE_DESC'] = 'DUE_ASC'
    collaboration_filter: Literal['ALL', 'NOT_ISSUED', 'PENDING_CHANGE', 'PENDING', 'PARTIAL', 'ACCEPTED', 'NOT_REQUIRED', 'CANCELLED', 'LATE_PROMISE'] = 'ALL'
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode='after')
    def valid(self):
        for value in (self.date_from, self.date_to):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError('invalid date')
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('reversed dates')
        changed = {k for k, v in self.model_dump().items() if k not in {'factory_id', 'view', 'resource_id', 'limit'}
                   and v != type(self).model_fields[k].default}
        if self.view == 'inventory' and changed & ORDER_FILTERS:
            raise ValueError('order filters do not apply to inventory')
        if self.view == 'orders' and self.customer_code:
            raise ValueError('order ledger filters customers by native name')
        if self.resource_id:
            kind, sep, ident = self.resource_id.partition(':')
            if (not sep or not ident or len(ident) > 96 or ident != ident.strip()
                or kind not in (KINDS if self.view == 'orders' else {'INVENTORY'})):
                raise ValueError('typed native identity required')
            # Inventory periods remain explicit; an order selection has no list filters.
            allowed = {'date_from', 'date_to'} if self.view == 'inventory' else set()
            if changed - allowed:
                raise ValueError('selection cannot silently combine list filters')
        return self


def authorize(db, user, factory, view='orders'):
    if user is None or supplier_only(user):
        raise AssistantError('business_forbidden', '当前身份不可使用内部纸箱查询。', 403)
    try:
        if factory != core.require_carton_factory(factory):
            raise HTTPException(422)
        if view == 'orders':
            special.access(db, user, factory)
        elif not any(has_permission_in_scope(user, 'carton_procurement:read', factory, dept) for dept in core.CARTON_DEPARTMENTS):
            raise HTTPException(403)
    except HTTPException as exc:
        code = 'factory_unavailable' if exc.status_code == 422 else 'business_forbidden'
        raise AssistantError(code, '请选择支持且有读取权限的纸箱厂区。', exc.status_code) from None


def responsibility_fingerprint(db, factory):
    rows = db.execute(select(CartonCustomerAssignment.customer_id, CartonCustomerAssignment.user_id,
        CartonCustomer.customer_code).join(CartonCustomer, CartonCustomer.id == CartonCustomerAssignment.customer_id)
        .where(CartonCustomerAssignment.factory_id == factory, CartonCustomer.factory_id == factory)
        .order_by(CartonCustomerAssignment.customer_id, CartonCustomerAssignment.user_id)).all()
    return stable_id(compact([list(row) for row in rows]))


def visible(db, user, source):
    """Recheck every contributing record, including records beyond the returned page.

    ALL list authority is intentionally different from native selected authority.
    A customer assignment changes scope without changing the IAM fingerprint.
    """
    factory = source['scope']['factory_id']
    filters = source['scope']['filters']
    view = filters['view']
    authorize(db, user, factory, view)
    if view not in {'orders', 'inventory'} or source.get('responsibility_fingerprint') != responsibility_fingerprint(db, factory):
        return False
    from .auth_snapshot import matches
    if not matches(db, user, source.get('authorization_fingerprint')):
        return False
    resources = source['resources']
    expected_type = 'inventory' if view == 'inventory' else 'order'
    if any(r.get('module_id') != 'carton-procurement' or r.get('resource_type') != expected_type for r in resources):
        return False
    if view == 'inventory':
        report = inventory_report(db, factory, customer_code=filters.get('customer_code', ''),
            search=filters.get('search', ''), date_from=filters.get('date_from', ''), date_to=filters.get('date_to', ''))
        current = {'INVENTORY:'+hashlib.sha256(row.key.encode()).hexdigest() for row in report.order_rows}
        return all(r['resource_id'] in current for r in resources)
    from app.models.carton_special_requests import SpecialVersion
    for resource in resources:
        kind, separator, ident = resource['resource_id'].partition(':')
        if not separator or kind not in KINDS:
            return False
        try:
            if kind == 'PURCHASE':
                if not special.allowed(user, factory, 'read'):
                    return False
                row = core.get_order_by_no(db, factory, ident)
                if filters.get('responsibility_scope') != 'ALL':
                    core.ensure_customer_operation(db, user, factory, row.customer_code)
            else:
                row = special.access(db, user, factory, ident)
                if row.kind != kind or db.scalar(select(SpecialVersion.id).where(
                    SpecialVersion.request_id == ident, SpecialVersion.factory_id == factory, SpecialVersion.action == 'DELETED').limit(1)):
                    return False
        except HTTPException as exc:
            if exc.status_code not in (403, 404):
                raise
            return False
    return True


def selected_record(db, user, factory, ident, *, date_from='', date_to=''):
    """Shared exact authority boundary for an original-record action."""
    if not isinstance(ident, str):
        return None
    try:
        args = Arguments(factory_id=factory, view='inventory' if ident.startswith('INVENTORY:') else 'orders',
            resource_id=ident, date_from=date_from, date_to=date_to)
        authorize(db, user, factory, args.view)
        rows, _ = read(db, user, args)
        return rows[0] if len(rows) == 1 else None
    except (HTTPException, ValidationError, ValueError, TypeError):
        return None


def clipped(value, key, truncated):
    if isinstance(value, str) and len(value) > 300:
        truncated.append(key)
        return value[:300]
    return value


def order_out(entry):
    regular = entry['kind'] == 'PURCHASE'
    raw = entry['order'].model_dump(mode='json') if regular else entry['special']
    ident = entry['kind'] + ':' + (raw['order_no'] if regular else raw['id'])
    truncated = []
    row = {k: clipped(raw[k], k, truncated) for k in ('factory_id', 'customer_code', 'customer_name', 'status', 'revision')}
    row.update(id=ident, resource_ref='carton-procurement:order:'+ident, kind=entry['kind'],
        number=raw['order_no'] if regular else raw['request_no'],
        order_date=raw['order_date'] if regular else raw['created_at'][:10],
        due_date=raw['due_date'] if regular else raw['required_date'], updated_at=timestamp(raw['updated_at']))
    if regular:
        row.update({k: clipped(raw[k], k, truncated) for k in ('contract_no', 'item_no', 'product_name', 'quantity_basis', 'product_order_quantity')})
        row['supplier_acceptance'] = {k: raw['supplier_acceptance'][k] for k in ('status', 'label', 'accepted_at')}
    lines = []
    for paper in raw['lines']:
        item = {k: clipped(paper[k], 'lines.'+k, truncated) for k in ('id', 'line_no', 'packaging_type', 'paper_quality', 'specification', 'dimension_unit', 'unit')}
        item.update(required_quantity=decimal(paper['required_quantity'] if regular else paper['quantity']),
                    received_quantity=decimal(paper['received_quantity']), remaining_quantity=decimal(paper['remaining_quantity']))
        lines.append(item)
    row.update(lines=lines, line_count=len(lines), lines_truncated=False, truncated_fields=sorted(set(truncated)))
    return row


def inventory_out(raw):
    ident = 'INVENTORY:' + hashlib.sha256(raw.key.encode()).hexdigest()
    truncated = []
    row = {k: clipped(getattr(raw, k), k, truncated) for k in ('order_id', 'order_line_id', 'order_date', 'customer_code',
        'customer_name', 'contract_no', 'item_no', 'product_name', 'packaging_type', 'paper_quality', 'specification', 'unit',
        'current_usage_status', 'current_usage_label')}
    row.update({k: decimal(getattr(raw, k)) for k in ('opening_quantity', 'inbound_quantity', 'outbound_quantity',
        'adjustment_quantity', 'ending_quantity', 'current_usage_quantity')})
    row.update(id=ident, kind='INVENTORY', resource_ref='carton-procurement:inventory:'+ident,
        last_movement_at=timestamp(raw.last_movement_at), available_quantity=None,
        current_positions=[dict(location=clipped(p['location'], 'current_positions.location', truncated),
            quantity=decimal(p['quantity'])) for p in raw.current_positions],
        position_count=len(raw.current_positions), positions_truncated=False,
        truncated_fields=sorted(set(truncated)))
    return row


def read(db, user, args):
    if args.view == 'inventory':
        report = inventory_report(db, args.factory_id, customer_code=args.customer_code.strip(),
            search=args.search.strip(), date_from=args.date_from, date_to=args.date_to)
        rows = [inventory_out(row) for row in report.order_rows]
        return [row for row in rows if row['id'] == args.resource_id] if args.resource_id else rows, {}
    if args.resource_id:
        kind, ident = args.resource_id.split(':', 1)
        native = selections.selected(db, user, Selection(factory_id=args.factory_id, items=[dict(kind=kind, id=ident)]))
        return [order_out(item) for item in native], {}
    native = orders.ledger(db, user, args.factory_id, **{k: getattr(args, k) for k in ORDER_FILTERS},
        search=args.search, order_from=args.date_from, order_to=args.date_to, limit=None)
    return [order_out(item) for item in native['items']], native['statistics']


def totals(rows, view, statistics):
    def metric(value, unit, definition):
        return dict(value=value, unit=unit, definition_id='carton.'+definition+'.v1', status='unknown' if value is None else 'known')
    metrics = {'record_count': metric(len(rows), '库存标识行' if view == 'inventory' else '单据', 'stock_count' if view == 'inventory' else 'count')}
    metrics['available_quantity'] = metric(None, '未确定', 'available')
    sums = defaultdict(lambda: defaultdict(Decimal))
    if view == 'orders':
        for row in rows:
            for paper in row['lines']:
                unit = paper['unit']
                sums[unit]['required'] += Decimal(paper['required_quantity'])
                sums[unit]['received'] += Decimal(paper['received_quantity'])
                sums[unit]['remaining'] += Decimal(paper['remaining_quantity']) if row['status'] not in {'CANCELLED', 'COMPLETED'} else 0
        if statistics:
            for key in ('pending', 'overdue'):
                metrics[key+'_count'] = metric(statistics[key], '单据', key)
    else:
        for row in rows:
            for key in ('opening', 'inbound', 'outbound', 'adjustment', 'ending'):
                sums[row['unit']][key] += Decimal(row[key+'_quantity'])
    for unit, fields in sums.items():
        for key, value in fields.items():
            metrics[key+'_quantity['+unit+']'] = metric(decimal(value), unit, key)
    return metrics


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except (ValidationError, ValueError, TypeError):
        raise AssistantError('tool_invalid', '纸箱查询参数无效，请核对单据类型、厂区、筛选及日期范围。', 422) from None
    requested = core.business_now()
    from .auth_snapshot import fingerprint
    with database.SessionLocal() as db:
        authorize(db, user, args.factory_id, args.view)
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        auth = fingerprint(db, user)
        responsibility = responsibility_fingerprint(db, args.factory_id)
        try:
            all_rows, statistics = read(db, user, args)
        except HTTPException as exc:
            if exc.status_code not in (403, 404):
                raise
            raise AssistantError('source_unavailable', '纸箱记录不存在或已不在当前可见范围。', 404) from None
        if args.resource_id and not all_rows:
            raise AssistantError('source_unavailable', '纸箱记录不存在或已不在当前可见范围。', 404)
        filters = args.model_dump(exclude={'resource_id', 'limit', 'cursor', 'factory_id'})
        if args.view == 'inventory':
            filters = {k: v for k, v in filters.items() if k not in ORDER_FILTERS}
        metrics = totals(all_rows, args.view, statistics)
        key = stable_id(auth, responsibility, compact(filters), args.factory_id, args.resource_id,
            compact(all_rows), compact(metrics), requested.date().isoformat())
        offset, anchor = 0, requested
        if args.cursor:
            try:
                cursor = json.loads(base64.urlsafe_b64decode(args.cursor.encode('ascii')))
                anchor = datetime.fromisoformat(cursor['at'])
                offset = cursor['offset']
                if (anchor.tzinfo is None or type(offset) is not int or not 0 < offset < len(all_rows)
                    or cursor['key'] != stable_id(key, anchor.isoformat(), offset)
                    or not 0 <= (requested-anchor).total_seconds() <= 300):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                raise AssistantError('cursor_invalid', '纸箱数据、权限或筛选已变化，请从第一页重新查询。', 422) from None
        rows = all_rows[offset:offset+args.limit]
        for row in rows:
            if 'lines' in row:
                row['lines_truncated'] = row['line_count'] > 50
                row['lines'] = row['lines'][:50]
            if 'current_positions' in row:
                row['positions_truncated'] = row['position_count'] > 50
                row['current_positions'] = row['current_positions'][:50]
        unknowns = [dict(field='available_quantity', reason=DEFINITIONS['carton.available.v1'])]
        if any(row['truncated_fields'] or row.get('lines_truncated') or row.get('positions_truncated') for row in rows):
            unknowns.append(dict(field='rows', reason='部分长文本仅返回前300字，纸品行及仓位最多50条；完整指标仍按全部源记录计算。'))
        retrieved = core.business_now().isoformat()
        selected = bool(args.resource_id)
        label = args.factory_id + (' / 原库存报表全厂读取范围' if args.view == 'inventory' else ' / 纸品合并台账 / '+('本人负责' if args.responsibility_scope == 'OWN' else '全部可见'))
        if selected:
            label += ' / 选中记录'
        source_id = stable_id(run_id, NAME, key, offset, requested.isoformat())
        resource_type = 'inventory' if args.view == 'inventory' else 'order'
        # Totals derive from all rows. Rechecking only the returned page could
        # expose a hidden/deleted contributor in a historical aggregate.
        resources = [dict(module_id='carton-procurement', resource_type=resource_type, resource_id=row['id']) for row in all_rows]
        refs = [row['resource_ref'] for row in rows]
        source = dict(kind='business', source_id=source_id, run_id=run_id, title='纸品库存报表' if args.view == 'inventory' else '纸品订单台账',
            tool_name=NAME, resources=resources, scope=dict(factory_id=args.factory_id, scope_label=label, authorization='current_user', filters=filters),
            as_of=requested.isoformat(), observed_at=None, retrieved_at=retrieved, data_mode='snapshot',
            unknown_fields=[u['reason'] for u in unknowns], authorization_fingerprint=auth, responsibility_fingerprint=responsibility)
        actions = []
        for row in rows:
            # Native ALL lists can expose a purchase summary while its selected
            # endpoint denies current responsibility. Never advertise that link.
            if args.view == 'orders' and selected_record(db, user, args.factory_id, row['id']) is None:
                continue
            query = dict(factory=args.factory_id, tab='inventory-summary' if args.view == 'inventory' else 'orders', carton_record=row['id'])
            if args.view == 'inventory':
                if args.date_from: query['carton_from'] = args.date_from
                if args.date_to: query['carton_to'] = args.date_to
            actions.append(dict(type='open_record', label='打开原记录：'+str(row.get('number') or row.get('contract_no') or row.get('item_no') or '库存')[:60],
                route_name='carton-procurement', params={}, query=query,
                resource=dict(module_id='carton-procurement', resource_type=resource_type, resource_id=row['id'])))
        truncated = offset + len(rows) < len(all_rows)
        cursor = base64.urlsafe_b64encode(compact(dict(at=anchor.isoformat(), offset=offset+len(rows),
            key=stable_id(key, anchor.isoformat(), offset+len(rows)))).encode()).decode() if truncated else None
        result = dict(record_type='tool_result', contract_version=3, tool_name=NAME, tool_version='cartons-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id, key, offset), run_id=run_id, step_id=step_id or NAME,
            status='empty' if not all_rows else 'partial',
            scope=dict(factory_ids=[args.factory_id], module_id='carton-procurement', filters=filters,
                resource_refs=refs if selected else [], coverage='selected_resources' if selected else 'filtered_scope', label=label),
            requested_at=requested.isoformat(), as_of=requested.isoformat(), observed_at=None, retrieved_at=retrieved,
            timezone='Asia/Shanghai', business_date=requested.date().isoformat(), data_mode='snapshot',
            freshness=dict(state='fresh', max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id='carton-current-v1'),
            metrics=metrics, rows=rows, total_count=len(all_rows), returned_count=len(rows), truncated=truncated,
            next_cursor=cursor, definitions=DEFINITIONS, unknown_fields=unknowns, source_refs=[source_id],
            allowed_actions=[dict(action_id=stable_id(source_id, action['resource']['resource_id']), kind='navigate', label=action['label'],
                resource_ref='carton-procurement:'+resource_type+':'+action['resource']['resource_id']) for action in actions], diagnostic_code=None)
        return validate_result(result, registered_sources=[source_id], registered_resources=refs, row_fields=ROW_FIELDS), source, actions
