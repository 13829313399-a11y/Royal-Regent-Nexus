"""Bounded four-factory spray snapshots, preserving native units and authority.

Native source navigation is bound separately. Coverage remains unverified until
the complete API/browser/model gates pass. No business commands are issued.
"""
import base64
from datetime import date, datetime
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select, or_, and_

from app import db as database
from app.core.time import business_now, parse_business_timestamp
from app.models import spray_ops as m
from app.services.spray_ops import authz, common as c, production, progress
from app.services.spray_ops.query_filters import collection_statement
from .auth_snapshot import fingerprint, matches
from .errors import AssistantError
from .evidence import stable_id
from .help_registry import supplier_only
from .tool_result import validate_result

NAME = 'get_spray_operations_snapshot'
MODULE = 'spray-production'
FACTORY_LABELS = dict(huaxing='华兴', huadeng='华登', **{'huakang-a': '华康A', 'huakang-b': '华康B'})
DEMAND_FIELDS = ('id', 'factory_id', 'document_no', 'counterparty', 'business_date', 'status', 'version', 'created_at', 'updated_at')
LINE_FIELDS = ('id', 'demand_id', 'item_no', 'part', 'color', 'quantity', 'unit', 'expected_arrival', 'due_date',
               'priority', 'split_allowed', 'route_id', 'received', 'opening_balance', 'balances', 'balances_by_unit', 'updated_at')
TASK_FIELDS = ('id', 'factory_id', 'scenario_id', 'step_id', 'resource_id', 'start_at', 'end_at', 'actual_start',
               'actual_end', 'quantity', 'reported', 'status', 'version', 'created_at', 'updated_at')
ALLOCATION_FIELDS = ('id', 'task_id', 'stock_id', 'line_id', 'quantity', 'consumed', 'updated_at')
DEFINITIONS = {
    'spray.records.v1': '完整筛选范围内的原需求单或执行任务数；分页不改变总数。',
    'spray.planned.v1': '筛选需求单所有行声明的数量，包含草稿，分原单位；不是已排任务量或收料量。',
    'spray.white.v1': '关联需求行当前white实体库存数量，包含尚未喷油及已回到白胚环节的返工。',
    'spray.wip.v1': '关联需求行当前wip实体库存数量，仅指已进入中间工序状态的在制品。',
    'spray.hold.v1': '关联需求行当前hold待处理库存，未自动认定为已返工或报废。',
    'spray.finished.v1': '关联需求行当前finished合格成品库存；已发货不在库，因此不等于累计产量或客户验收量。',
    'spray.in_process.v1': '待最终处置实体库存=white+wip+hold，分库存原单位；不等于狭义wip、排程剩余或交付欠数。',
    'spray.scrap.v1': '已生效production_scrap与quality_scrap物料流数量，排除已冲销流，按输入库存单位；不包含来料或客户拒收。',
    'spray.arrival_rejected.v1': '关联需求行来料批次rejected数量，按来料单位；没有转为可用库存，不是生产返工量。',
    'spray.rework_current.v1': 'white/wip/hold中具有rework_origin的当前实体数量；拒收或退货亦可能标记此来源，不表示已实际重喷。',
    'spray.rework_processed.v1': '已确认未冲销报工中，投入库存有rework_origin的processed，分输入单位；工序处理次数可重复，不是新增成品。',
    'spray.dispatched.v1': '已发出送货单关联行quantity累计，按库存单位；再次交接会再次记录，不能视作唯一原件数。',
    'spray.handover_accepted.v1': '已发出送货单关联行accepted累计验收数量，尚未扣退货；独立于合格在库数量。',
    'spray.handover_rejected.v1': '已发出送货单关联行rejected累计拒收数量，不能自动当作已重喷或报废。',
    'spray.returned.v1': '已验收交接行returned累计实物退货数量，不是财务红字或扣款。',
    'spray.in_transit.v1': '已发出送货行quantity-accepted-rejected，分库存单位，表示尚待验收。',
    'spray.net_accepted.v1': '交接行accepted-returned，分库存单位；不代表结算数量或金额。',
    'spray.scheduled_input.v1': '未取消执行任务quantity之和，按工序输入单位，是工序工作量；多工序与返工可重复，不能称成品量。',
    'spray.reported_input.v1': '同范围未取消任务reported之和，已由原系统扣除冲销报工；工序处理量不能当合格产出。',
    'spray.pending_input.v1': '同范围未取消任务quantity-reported之和，按工序输入单位；不是实体库存、缺料或交付欠数。',
    'spray.material_shortage.v1': '未对物料、占用及备料进行缺口计算，缺料数量未知。',
    'spray.settled_amount.v1': '生产读取不读取单价、成本、工资或结算。财务金额须沿cost_read/payroll_read/settle独立授权，本结果未知。',
    'spray.clock.v1': 'as_of为一致性数据库快照读取时点；updated_at保留源记录时点。业务日期按Asia/Shanghai，查询时间不是设备观测。',
    'spray.stage.v1': 'journey.good已经按确认工序比例换算为output_unit，不再乘比例。任务reports的processed/good/hold/scrap为工序输入单位，step给出输出单位和比例。两者都是工序实绩，未必完成最终工序，不能跨工序相加作为成品。',
    'spray.scope.v1': '需求进度只计关联行，未匹配需求的批次不在范围；任务按demand_id筛选时包含整条合并任务及其所有分配，不是仅该需求的贡献。日期仅筛需求单business_date，所列库存及流转为当前/累计，非该期间发生额。',
    'spray.precision.v1': '数量沿原系统Decimal六位小数精度，以十进制字符串传输；缺少确认换算时只按原单位并列，不合并单位。列表未读取journey/日报时total为null，不表示无报工。',
}


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    view: Literal['demands', 'tasks'] = 'demands'
    task_scope: Literal['all', 'active'] = 'all'
    resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    q: str = Field(default='', max_length=128)
    status: str = Field(default='', max_length=24)
    date_from: str = Field(default='', max_length=10)
    date_to: str = Field(default='', max_length=10)
    demand_id: str = Field(default='', max_length=64)
    limit: int = Field(default=10, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode='after')
    def valid_scope(self):
        for value in (self.factory_id, self.resource_id or '', self.demand_id, self.status):
            if value != value.strip():
                raise ValueError('invalid identifier')
        if self.resource_id and any((self.cursor, self.q, self.status, self.date_from, self.date_to, self.demand_id, self.task_scope != 'all')):
            raise ValueError('selected record cannot silently intersect filters')
        if self.view == 'tasks' and (self.q or self.date_from or self.date_to):
            raise ValueError('native tasks have no document search or business date filter')
        if self.view == 'demands' and self.demand_id:
            raise ValueError('use resource_id for a selected demand')
        if self.view == 'demands' and self.task_scope != 'all':
            raise ValueError('task scope only applies to tasks')
        for value in (self.date_from, self.date_to):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError('invalid date')
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('reversed date range')
        return self


def authorize(db, user, factory):
    if user is None or supplier_only(user):
        raise AssistantError('business_forbidden', '当前身份不可读取喷油生产。', 403)
    try:
        authz.authorize(user, factory)
        return authz.ready(db, factory)
    except c.DomainError as error:
        raise AssistantError(error.body['code'], error.body['message'], error.status, retryable=error.status == 503) from None


def row_out(db, factory, view, record, selected):
    if view == 'demands':
        native = production.demand_detail(db, factory, record)
        lines = sorted(native['lines'], key=lambda row: row['id'])
        journey = c.json_value(production.demand_journey(db, factory, record.id)) if selected else []
        return {**{key: native[key] for key in DEMAND_FIELDS},
            'resource_ref': f'{MODULE}:demand:{record.id}',
            'lines': [{key: row[key] for key in LINE_FIELDS} for row in lines[:25]],
            'lines_total': len(lines), 'journey': journey[:25], 'journey_total': len(journey) if selected else None,
            'journey_included': selected, 'detail_truncated': len(lines) > 25 or len(journey) > 25}
    native = production.task_detail(db, factory, record)
    allocations = sorted(native['allocations'], key=lambda row: row['id'])
    step = c.get(db, m.SprayOpsStep, factory, record.step_id)
    reports, report_total = progress.task_reports(db, factory, record.id) if selected else ([], 0)
    return {**{key: native[key] for key in TASK_FIELDS},
        'resource_ref': f'{MODULE}:task:{record.id}',
        'step': {key: c.json_value(getattr(step, key)) for key in ('id', 'code', 'name', 'input_unit', 'output_unit', 'output_ratio')},
        'allocations': [{key: row[key] for key in ALLOCATION_FIELDS} for row in allocations[:25]],
        'allocations_total': len(allocations), 'reports': reports, 'reports_total': report_total if selected else None,
        'reports_included': selected, 'detail_truncated': len(allocations) > 25 or report_total > 25}


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except (ValidationError, ValueError, TypeError):
        raise AssistantError('tool_invalid', '喷油查询参数无效，请核对明确厂区、需求或任务及筛选。', 422) from None
    requested = business_now()
    with database.SessionLocal() as db:
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        gate = authorize(db, user, args.factory_id)
        auth = fingerprint(db, user)
        model = m.SprayOpsDemand if args.view == 'demands' else m.SprayOpsTask
        try:
            statement = collection_statement(db, args.factory_id, args.view, model, search=args.q, status=args.status,
                from_date=args.date_from, to_date=args.date_to, demand_id=args.demand_id, task_scope=args.task_scope)
        except c.DomainError as error:
            raise AssistantError('source_unavailable', '关联喷油需求不存在或不在当前厂区。', error.status) from None
        if args.resource_id:
            statement = statement.where(model.id == args.resource_id)
        filters = args.model_dump(include={'view', 'q', 'status', 'date_from', 'date_to', 'demand_id', 'task_scope'})
        filters['factory_revision'] = gate.revision
        scope_key = stable_id(auth, args.factory_id, args.resource_id, filters)
        after, created, anchor = '', '', requested.isoformat()
        if args.cursor:
            try:
                cursor = json.loads(base64.b64decode(args.cursor.encode('ascii'), altchars=b'-_', validate=True))
                after, created, anchor = cursor['after'], cursor['created_at'], cursor['as_of']
                if (not isinstance(after, str) or not 0 < len(after) <= 64 or not isinstance(created, str)
                    or not isinstance(anchor, str) or datetime.fromisoformat(anchor).tzinfo is None
                    or parse_business_timestamp(anchor) is None or datetime.fromisoformat(created).tzinfo is None
                    or not 0 <= (requested - parse_business_timestamp(anchor)).total_seconds() <= 300
                    or cursor['key'] != stable_id(scope_key, after, created, anchor)):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
                raise AssistantError('cursor_invalid', '喷油范围、授权、版本或分页时效已变化，请重读第一页。', 422) from None
        total = db.scalar(select(func.count()).select_from(statement.subquery()))
        values = (progress.demand_totals if args.view == 'demands' else progress.task_totals)(db, args.factory_id, statement)
        page_statement = statement
        if after:
            page_statement = statement.where(or_(model.created_at < created, and_(model.created_at == created, model.id > after)))
        rows = list(db.scalars(page_statement.order_by(model.created_at.desc(), model.id).limit(args.limit + 1)))
        if args.resource_id and not rows:
            raise AssistantError('source_unavailable', '选中喷油记录不存在或不在当前范围。', 404)
        if after and not rows:
            raise AssistantError('cursor_invalid', '喷油分页已失效，请重新读取第一页。', 422)
        truncated = len(rows) > args.limit
        rows = rows[:args.limit]
        items = [row_out(db, args.factory_id, args.view, row, bool(args.resource_id)) for row in rows]
        metrics = dict(records=dict(value=total, unit='需求单' if args.view == 'demands' else '任务',
            definition_id='spray.records.v1', status='known'))
        for unit, quantities in sorted(values.items()):
            for key, value in quantities.items():
                metrics[key + ':' + unit] = dict(value=format(value, 'f'), unit=unit, definition_id='spray.' + key + '.v1', status='known')
        unknowns = [dict(field=key, reason=DEFINITIONS['spray.' + key + '.v1']) for key in ('material_shortage', 'settled_amount')]
        for key in ('material_shortage', 'settled_amount'):
            metrics[key] = dict(value=None, unit='未明确', definition_id='spray.' + key + '.v1', status='unknown')
        if args.view == 'tasks':
            unknowns.append(dict(field='final_output', reason='任务结果只有工序工作量；请查询需求进度读取实体库存与交接。'))
        if any(row['detail_truncated'] for row in items):
            unknowns.append(dict(field='rows', reason='单记录的明细最多返回25条，超出部分需查看原记录；汇总来自完整范围。'))
        refs = [item['resource_ref'] for item in items]
        resource_type = 'demand' if args.view == 'demands' else 'task'
        filtered = bool(any((args.q, args.status, args.date_from, args.date_to, args.demand_id)) or args.task_scope != 'all')
        label = FACTORY_LABELS[args.factory_id] + ' / ' + ('选中' if args.resource_id else '筛选' if filtered else '全部') + ('喷油需求' if args.view == 'demands' else '喷油执行任务')
        as_of, retrieved = requested.isoformat(), business_now().isoformat()
        source_id = stable_id(run_id, NAME, scope_key, after, as_of)
        resources = [dict(module_id=MODULE, resource_type=resource_type, resource_id=row.id) for row in rows]
        source = dict(kind='business', source_id=source_id, run_id=run_id, title='喷油需求进度' if args.view == 'demands' else '喷油执行任务',
            tool_name=NAME, resources=resources, scope=dict(factory_id=args.factory_id, scope_label=label, authorization='current_user', filters=filters),
            as_of=as_of, observed_at=None, retrieved_at=retrieved, data_mode='snapshot',
            unknown_fields=[u['reason'] for u in unknowns], authorization_fingerprint=auth)
        cursor = dict(after=rows[-1].id, created_at=rows[-1].created_at, as_of=anchor,
                      key=stable_id(scope_key, rows[-1].id, rows[-1].created_at, anchor)) if truncated else None
        next_cursor = base64.urlsafe_b64encode(json.dumps(cursor, separators=(',', ':')).encode()).decode() if cursor else None
        actions = [dict(type='open_record', label='打开原喷油' + ('需求：' + row.document_no[:60] if args.view == 'demands' else '任务'),
            route_name='spray-demands' if args.view == 'demands' else 'spray-execution', params={},
            query={'factory': args.factory_id, 'spray_' + resource_type: row.id}, resource=resource) for row, resource in zip(rows, resources)]
        result = dict(record_type='tool_result', contract_version=3, tool_name=NAME, tool_version='spray-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id, scope_key, after), run_id=run_id, step_id=step_id or NAME,
            status='empty' if not total else 'partial',
            scope=dict(factory_ids=[args.factory_id], module_id=MODULE, filters=filters,
                resource_refs=refs if args.resource_id else [],
                coverage='selected_resources' if args.resource_id else 'filtered_scope' if filtered else 'authorized_scope', label=label),
            requested_at=as_of, as_of=as_of, observed_at=None, retrieved_at=retrieved,
            timezone='Asia/Shanghai', business_date=requested.date().isoformat(), data_mode='snapshot',
            freshness=dict(state='fresh', max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id='spray-current-v1'),
            metrics=metrics, rows=items, total_count=total, returned_count=len(rows), truncated=truncated, next_cursor=next_cursor,
            definitions=DEFINITIONS, unknown_fields=unknowns, source_refs=[source_id],
            allowed_actions=[dict(action_id=stable_id(source_id, i), kind='navigate', label=action['label'], resource_ref=refs[i]) for i, action in enumerate(actions)], diagnostic_code=None)
        return validate_result(result, registered_sources=[source_id], registered_resources=refs,
            row_fields={*DEMAND_FIELDS, *TASK_FIELDS, 'resource_ref', 'lines', 'lines_total', 'journey', 'journey_total', 'journey_included',
                        'step', 'allocations', 'allocations_total', 'reports', 'reports_total', 'reports_included', 'detail_truncated'}), source, actions


def visible(db, user, source):
    factory = source.get('scope', {}).get('factory_id')
    authorize(db, user, factory)
    if source.get('tool_name') != NAME or not matches(db, user, source.get('authorization_fingerprint')):
        return False
    view = source.get('scope', {}).get('filters', {}).get('view')
    if view not in ('demands', 'tasks'):
        return False
    model, kind = (m.SprayOpsDemand, 'demand') if view == 'demands' else (m.SprayOpsTask, 'task')
    for resource in source.get('resources', []):
        if (resource.get('module_id') != MODULE or resource.get('resource_type') != kind
            or not db.scalar(c.scoped(db, model, factory).where(model.id == resource.get('resource_id')))):
            return False
    return True
