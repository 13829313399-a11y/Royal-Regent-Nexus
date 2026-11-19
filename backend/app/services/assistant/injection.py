"""Read-only injection snapshots over the native factory/filter/query contract."""
import base64
from datetime import datetime
from decimal import Decimal, localcontext
import json

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.exc import ArgumentError

from app import db as database
from app.models.injection_scheduling import Demand
from app.schemas.injection_scheduling import Query
from app.services.injection_scheduling import calculations, queries
from app.services.injection_scheduling.field_registry import FACTORIES
from .errors import AssistantError
from .evidence import stable_id
from .tool_result import validate_result

NAME = 'get_injection_overview'
ROW_FIELDS = ('id', 'revision', 'updated_at', 'order_no', 'item_no', 'part_name', 'mold_code',
              'dispatch_state', 'remaining_shots', 'remaining_units', 'allocation_mode', 'quantity_basis',
              'remaining_material_kg', 'delivery_slack_hours', 'delivery_due_at', 'planned_start_at',
              'planned_end_at', 'machine_code', 'unplaced_reason')
DEFINITIONS = {
    'injection.demand_count.v1': '当前明确厂区及原排期筛选后的需求行总数，非返回样本数；选中需求仅统计该行。',
    'injection.held_count.v1': '同一范围内调度状态非 READY 的需求行数，包含待料及其他挂起原因，不等于缺料数。',
    'injection.wait_material_count.v1': '同一范围内调度状态恰为 WAIT_MATERIAL 的需求行数；这是排产标记，不证明仓库实际缺料。',
    'injection.remaining_material_kg.v1': '同一范围内需求的预计剩余生产用料之和，单位 kg，不是仓库短缺量；任一需求用料未知则完整总量未知。',
    'injection.known_remaining_material_kg.v1': '仅对同一范围中用料已知的需求按 Decimal 求和，未知需求未计入；这是已知小计，不代表完整总量。',
    'injection.remaining_material_unknown_count.v1': '同一范围内预计剩余生产用料为空的需求行数。',
    'injection.forecast_late_count.v1': '同一范围内 delivery_slack_hours < 0 的需求行数，沿用原排期 late_count；只是已知预计排期超期风险，不是实际交货延期数。',
    'injection.forecast_unknown_count.v1': '同一范围内交期宽裕小时未知的需求行数；不能将这些需求认定为无排期风险。',
    'injection.warehouse_shortage_kg.v1': '此连接器没有读取仓库可用库存及占用，实际库存短缺量未知。',
    'injection.actual_delivery_late_count.v1': '此连接器没有读取实际交货结果，实际交货延期数未知。',
}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False)


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    resource_id: str | None = Field(default=None, min_length=1, max_length=160)
    filter: dict | None = Field(default=None, description='原注塑筛选：{field,op,value} 或 {op:and/or,children:[...]}，例如 dispatch_state eq WAIT_MATERIAL。')
    search: dict | None = Field(default=None, description='原列表查找：{field,mode,text}；mode 为 exact/contains/prefix/in，field 如 mold_code/order_no。')
    sort: list[dict] = Field(default_factory=list, max_length=10, description='原列表排序：[{field,direction:asc/desc}]；默认交货完成期升序。')
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode='after')
    def bounded(self):
        if any(len(compact(value)) > cap for value, cap in ((self.filter, 12000), (self.search, 4000), (self.sort, 2000))):
            raise ValueError('query too large')
        if self.resource_id and (self.filter or self.search or self.sort or self.cursor):
            raise ValueError('selected demand cannot combine list filters')
        return self


def context_arguments(filters):
    """Freeze native JSON queries inside the existing flat selection wire format."""
    result = {}
    try:
        for key in ('filter', 'search', 'sort'):
            if key + '_json' in filters:
                raw = filters[key + '_json']
                if not isinstance(raw, str) or len(raw) > 12000:
                    raise ValueError()
                result[key] = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        raise AssistantError('tool_invalid', '注塑列表筛选无法读取，请重新选择当前范围。', 422) from None
    return result


def decimal_text(value):
    if not value:
        return '0'
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def row_out(row):
    result = {}
    truncated = []
    for key in ROW_FIELDS:
        value = getattr(row, key)
        if isinstance(value, Decimal):
            value = decimal_text(value)
        elif isinstance(value, datetime):
            value = calculations.timestamp(value).isoformat()
        elif isinstance(value, str) and len(value) > 300:
            value = value[:300]
            truncated.append(key)
        result[key] = value
    return dict(result, resource_ref='injection-scheduling:demand:' + row.id, truncated_fields=truncated)


def totals(db, conditions):
    """Stream typed Decimal columns; SQLite SUM would introduce binary rounding."""
    value = dict(demand_count=0, held_count=0, wait_material_count=0, remaining_material_unknown_count=0,
                 forecast_late_count=0, forecast_unknown_count=0)
    material = Decimal(0)
    stmt = select(Demand.dispatch_state, Demand.remaining_material_kg, Demand.delivery_slack_hours).where(*conditions)
    with localcontext() as context:
        context.prec = 50
        for state, remaining, slack in db.execute(stmt.execution_options(yield_per=1000)):
            value['demand_count'] += 1
            value['held_count'] += state != 'READY'
            value['wait_material_count'] += state == 'WAIT_MATERIAL'
            value['remaining_material_unknown_count'] += remaining is None
            value['forecast_unknown_count'] += slack is None
            value['forecast_late_count'] += slack is not None and slack < 0
            if remaining is not None:
                material += remaining
    value['known_remaining_material_kg'] = decimal_text(material)
    value['remaining_material_kg'] = None if value['remaining_material_unknown_count'] else decimal_text(material)
    return dict(value, warehouse_shortage_kg=None, actual_delivery_late_count=None)


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise AssistantError('tool_invalid', '注塑查询参数无效；请核对厂区、原列表筛选或分页。', 422) from None
    requested = calculations.now()
    from .business import authorize, fingerprint
    with database.SessionLocal() as db:
        authorize(db, user, NAME, args.factory_id)
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        auth = fingerprint(db, user)
        revision = queries.revision(db, args.factory_id)
        filters = {k + '_json': compact(getattr(args, k)) for k in ('filter', 'search', 'sort')}
        anchor, offset = requested, 0
        scope_key = stable_id(auth, args.factory_id, filters, args.resource_id, revision)
        if args.cursor:
            try:
                cursor = json.loads(base64.urlsafe_b64decode(args.cursor.encode('ascii')))
                anchor = calculations.timestamp(cursor['as_of'])
                offset = cursor['offset']
                if (not isinstance(cursor['as_of'], str) or datetime.fromisoformat(cursor['as_of']).tzinfo is None
                    or type(offset) is not int or not 0 < offset <= 10000000
                    or cursor['key'] != stable_id(scope_key, anchor.isoformat(), offset)
                    or not 0 <= (requested - anchor).total_seconds() <= 300):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                raise AssistantError('cursor_invalid', '注塑范围、数据版本或分页时效已变化，请从第一页重新查询。', 422) from None
        payload = Query(factory_id=args.factory_id, filter=args.filter, search=args.search, sort=args.sort)
        try:
            conditions = queries.query_conditions(payload, anchor)
            ordered = queries.ordered_query(payload, anchor)
        except (HTTPException, ArgumentError, ValueError, TypeError, KeyError, AttributeError):
            raise AssistantError('tool_invalid', '原注塑列表不支持此筛选或排序，请检查查询条件。', 422) from None
        if args.resource_id:
            conditions.append(Demand.id == args.resource_id)
            ordered = ordered.where(Demand.id == args.resource_id)
        values = totals(db, conditions)
        total = values['demand_count']
        rows = db.scalars(ordered.offset(offset).limit(args.limit)).all()
        if args.resource_id and not rows:
            raise AssistantError('source_unavailable', '选中需求不存在或不在当前厂区。', 404)
        if offset and offset >= total:
            raise AssistantError('cursor_invalid', '注塑需求列表已变化，请从第一页重新查询。', 422)
        items = [row_out(row) for row in rows]
        unknowns = [dict(field=k, reason=DEFINITIONS['injection.' + k + '.v1'])
                    for k in ('warehouse_shortage_kg', 'actual_delivery_late_count')]
        if values['remaining_material_unknown_count']:
            unknowns.append(dict(field='remaining_material_kg', reason='部分需求预计用料未知；完整总量为空，仅保留已知小计。'))
        if values['forecast_unknown_count']:
            unknowns.append(dict(field='forecast_late_count', reason='部分需求预测交期未知；已知风险数不包含这些需求，不能据此认定全部无风险。'))
        if any(item['truncated_fields'] for item in items):
            unknowns.append(dict(field='rows', reason='部分长文本仅显示前300字；完整内容请在原排期页查看。'))
        metrics = {k: dict(value=v, unit='kg' if k.endswith('_kg') else '需求行',
            definition_id='injection.' + k + '.v1', status='unknown' if v is None else 'known') for k, v in values.items()}
        refs = [item['resource_ref'] for item in items]
        resources = [dict(module_id='injection-scheduling', resource_type='demand', resource_id=r.id) for r in rows]
        selected = bool(args.resource_id)
        filtered = bool(args.filter or args.search and args.search.get('text'))
        label = FACTORIES[args.factory_id] + (' / 选中需求' if selected else ' / 已筛选需求' if filtered else ' / 全部需求')
        # The query clock anchors relative date filters across pages. It does not
        # assert a new production observation; each row retains its source update.
        as_of = requested.isoformat()
        source_id = stable_id(run_id, NAME, scope_key, offset, as_of)
        retrieved_at = calculations.now().isoformat()
        source = dict(kind='business', source_id=source_id, run_id=run_id, title='注塑排期', tool_name=NAME,
            resources=resources, scope=dict(factory_id=args.factory_id, scope_label=label, authorization='current_user', filters=filters),
            as_of=as_of, observed_at=None, retrieved_at=retrieved_at, data_mode='snapshot',
            unknown_fields=[u['reason'] for u in unknowns], authorization_fingerprint=auth)
        actions = [dict(type='open_record', label='打开注塑排期', route_name='injection-scheduling', params={},
            query=dict(factory=args.factory_id), resource=dict(module_id='injection-scheduling', resource_type='overview', resource_id=args.factory_id))]
        actions.extend(dict(type='open_record', label='打开需求：' + (row.order_no or row.mold_code)[:60],
            route_name='injection-scheduling', params={}, query=dict(factory=args.factory_id, demand=row.id),
            resource=resource) for row, resource in zip(rows, resources))
        truncated = offset + len(rows) < total
        next_cursor = base64.urlsafe_b64encode(compact(dict(as_of=anchor.isoformat(), offset=offset + len(rows),
            key=stable_id(scope_key, anchor.isoformat(), offset + len(rows)))).encode()).decode() if truncated else None
        result = dict(record_type='tool_result', contract_version=3, tool_name=NAME, tool_version='injection-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id, scope_key, offset), run_id=run_id, step_id=step_id or NAME,
            status='empty' if not total else 'partial' if truncated or unknowns else 'ok',
            scope=dict(factory_ids=[args.factory_id], module_id='injection-scheduling',
                filters={} if selected else dict(filters, query_anchor=anchor.isoformat(), **revision), resource_refs=refs if selected else [],
                coverage='selected_resources' if selected else 'filtered_scope' if filtered else 'authorized_scope', label=label),
            requested_at=requested.isoformat(), as_of=as_of, observed_at=None, retrieved_at=retrieved_at,
            timezone='Asia/Shanghai', business_date=requested.date().isoformat(), data_mode='snapshot',
            freshness=dict(state='fresh', max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id='injection-current-v1'),
            metrics=metrics, rows=items, total_count=total, returned_count=len(rows), truncated=truncated, next_cursor=next_cursor,
            definitions=DEFINITIONS, unknown_fields=unknowns, source_refs=[source_id], diagnostic_code=None,
            allowed_actions=[dict(action_id=stable_id(source_id, i), kind='navigate', label=action['label'],
                resource_ref='injection-scheduling:demand:' + action['resource']['resource_id'] if i else None)
                for i, action in enumerate(actions)])
        return validate_result(result, registered_sources=[source_id], registered_resources=refs,
                               row_fields={*ROW_FIELDS, 'truncated_fields', 'resource_ref'}), source, actions
