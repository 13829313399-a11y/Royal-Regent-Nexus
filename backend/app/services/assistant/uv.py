"""UV reader over native task/batch facts; no device or production commands.

Native Run rows never count as physical output. Registry acceptance remains
implemented_unverified until the complete native/API/browser/model gates pass.
"""
import base64
from datetime import datetime
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select

from app import db as database
from app.core.time import business_now, parse_business_timestamp
from app.models import uv_operations as m
from app.services.uv_operations import authz, common as c, production
from .auth_snapshot import fingerprint, matches
from .errors import AssistantError
from .evidence import stable_id
from .help_registry import supplier_only
from .tool_result import validate_result

NAME = 'get_uv_operations_snapshot'
MODULE = 'uv-operations'
TASK_FIELDS = ('id', 'code', 'demand_id', 'parent_task_id', 'quantity', 'status',
               'product_snapshot', 'version', 'created_at', 'updated_at')
BATCH_FIELDS = ('id', 'task_id', 'quantity', 'pass_index', 'remaining', 'intermediate',
                'good', 'rework', 'scrap', 'pending', 'reserved', 'received', 'version', 'updated_at')
SCHEDULE_FIELDS = ('id', 'task_id', 'batch_id', 'machine_id', 'start_at', 'end_at', 'status', 'version')
DEFINITIONS = {
    'uv.tasks.v1': '明确华康A范围的原任务数，包含取消及返工任务；分页不改变总数。',
    'uv.original_tasks.v1': '未取消且无parent_task_id的原生产任务数；返工任务不重复增加原计划数量。',
    'uv.rework_tasks.v1': '当前范围内有parent_task_id的返工任务数，包含取消任务；不是已完成返工产量。',
    'uv.cancelled_tasks.v1': '当前范围status为cancelled的任务数，取消任务不计入原生产计划和进度。',
    'uv.planned.v1': '未取消原任务的quantity之和，单位件；不是打印次数、板数或设备Run数量。',
    'uv.completed.v1': '同一原任务范围的active批次good之和，即最终合格数量；不累加工序报工、返工任务或设备Run。',
    'uv.remaining.v1': '同一active批次remaining+intermediate+rework+pending之和，即尚未最终处置的数量；不包含合格及报废，不是逾期量。',
    'uv.scrap.v1': '同一active批次scrap之和，报废独立于合格及剩余量。',
    'uv.incomplete_tasks.v1': '未取消原任务中存在尚未最终处置数量的任务数；无完整守恒批次时未知，绝不等于逾期数。',
    'uv.overdue_tasks.v1': '本读取未确定交期与实际交付口径，逾期任务数未知。',
    'uv.material_shortage.v1': '本读取未计算可用物料与占用，实际缺料数量未知。',
    'uv.financial.v1': '本读取仅提供生产数量，未读取成本、工资或结算；read权限不能替代cost_read/payroll_read。',
    'uv.batch_scope.v1': '原任务详情展示原任务active批次；返工任务详情展示其绑定的原批次现状，绝不是该返工任务自身的新增产量。',
    'uv.clock.v1': 'as_of为本次数据库一致性快照的读取时间；updated_at保留原记录时间，不表示新设备观测。多域结果各有时点。',
}


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode='after')
    def scope(self):
        if self.resource_id and (self.resource_id != self.resource_id.strip() or self.cursor):
            raise ValueError('ambiguous selection')
        return self


def authorize(db, user, factory):
    if user is None or supplier_only(user):
        raise AssistantError('business_forbidden', '当前身份不可读取UV生产。', 403)
    try:
        authz.authorize(user, factory)
        authz.ready(db)
    except c.DomainError as error:
        raise AssistantError(error.body['code'], error.body['message'], error.status,
                             retryable=error.status == 503) from None


def totals(db, statement):
    """Sum integer physical buckets once per original task, across the full scope."""
    tasks = statement.subquery()
    batches = select(m.UvOpsBatch.task_id,
        func.sum(m.UvOpsBatch.quantity).label('quantity'),
        func.sum(m.UvOpsBatch.good).label('good'),
        func.sum(m.UvOpsBatch.scrap).label('scrap'),
        func.sum(m.UvOpsBatch.remaining + m.UvOpsBatch.intermediate +
                 m.UvOpsBatch.rework + m.UvOpsBatch.pending).label('remaining'),
    ).where(m.UvOpsBatch.factory_id == m.FACTORY, m.UvOpsBatch.active.is_(True)).group_by(m.UvOpsBatch.task_id).subquery()
    rows = select(tasks.c.parent_task_id, tasks.c.status, tasks.c.quantity,
                  batches.c.quantity, batches.c.good, batches.c.scrap, batches.c.remaining).select_from(
                      tasks.outerjoin(batches, batches.c.task_id == tasks.c.id))
    values = dict(tasks=0, original_tasks=0, rework_tasks=0, cancelled_tasks=0,
                  planned=0, completed=0, remaining=0, scrap=0, incomplete_tasks=0)
    complete = True
    for parent, status, quantity, batch_qty, good, scrap, remaining in db.execute(rows.execution_options(yield_per=1000)):
        values['tasks'] += 1
        values['rework_tasks'] += parent is not None
        values['cancelled_tasks'] += status == 'cancelled'
        if parent is not None or status == 'cancelled':
            continue
        values['original_tasks'] += 1
        values['planned'] += quantity
        if batch_qty != quantity or good is None or good + scrap + remaining != quantity:
            complete = False
            continue
        values['completed'] += good
        values['scrap'] += scrap
        values['remaining'] += remaining
        values['incomplete_tasks'] += remaining > 0
    # An all-rework selection has no independent physical denominator. Zero
    # would incorrectly imply no output; keep that progress explicitly unknown.
    if not complete or values['tasks'] and not values['original_tasks']:
        for field in ('completed', 'remaining', 'scrap', 'incomplete_tasks'):
            values[field] = None
    return values


def row_out(db, task):
    # Exact native task-detail semantics, then an allowlist. Prices, wage policy,
    # raw file paths, staff and arbitrary JSON never enter model-visible facts.
    native = production.task_detail(db, task)
    batches = sorted(native['batches'], key=lambda row: row['id'])
    schedule = sorted(native['schedule'], key=lambda row: row['id'])
    return {**{key: native[key] for key in TASK_FIELDS},
        'resource_ref': f'{MODULE}:task:{task.id}',
        'batch_scope': 'bound_original_batches' if task.parent_task_id else 'original_task_batches',
        'batches': [{key: row[key] for key in BATCH_FIELDS} for row in batches[:50]],
        'schedule': [{key: row[key] for key in SCHEDULE_FIELDS} for row in schedule[:50]],
        'batches_total': len(batches), 'schedule_total': len(schedule),
        'detail_truncated': len(batches) > 50 or len(schedule) > 50}


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except (ValidationError, ValueError, TypeError):
        raise AssistantError('tool_invalid', 'UV查询参数无效，请核对明确厂区、任务或分页。', 422) from None
    requested = business_now()
    with database.SessionLocal() as db:
        # Start the read snapshot before schema/identity/business reads. No
        # native command or lazy create path is used in this private session.
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        authorize(db, user, args.factory_id)
        auth = fingerprint(db, user)
        revision = c.revision(db)
        config = db.scalar(c.query(m.UvOpsSettings))
        statement = c.query(m.UvOpsTask)
        if args.resource_id:
            statement = statement.where(m.UvOpsTask.id == args.resource_id)
        scope_key = stable_id(auth, args.factory_id, args.resource_id, revision)
        after = ''
        anchor = requested.isoformat()
        if args.cursor:
            try:
                cursor = json.loads(base64.b64decode(args.cursor.encode('ascii'), altchars=b'-_', validate=True))
                after, anchor = cursor['after'], cursor['as_of']
                if (not isinstance(after, str) or not 0 < len(after) <= 64 or not isinstance(anchor, str)
                    or datetime.fromisoformat(anchor).tzinfo is None
                    or parse_business_timestamp(anchor) is None
                    or not 0 <= (requested - parse_business_timestamp(anchor)).total_seconds() <= 300
                    or cursor['key'] != stable_id(scope_key, after, anchor)):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
                raise AssistantError('cursor_invalid', 'UV范围、授权、数据版本或分页时效已变化，请重新读取第一页。', 422) from None
        values = totals(db, statement)
        total = values['tasks']
        rows = list(db.scalars(statement.where(m.UvOpsTask.id > after).order_by(m.UvOpsTask.id).limit(args.limit + 1)))
        if args.resource_id and not rows:
            raise AssistantError('source_unavailable', '选中UV任务不存在或不在当前范围。', 404)
        if after and not rows:
            raise AssistantError('cursor_invalid', 'UV任务分页已失效，请重新读取第一页。', 422)
        truncated = len(rows) > args.limit
        rows = rows[:args.limit]
        items = [row_out(db, row) for row in rows]
        unknowns = [dict(field=field, reason=DEFINITIONS['uv.' + field + '.v1'])
                    for field in ('overdue_tasks', 'material_shortage', 'financial')]
        if values['completed'] is None:
            unknowns.append(dict(field='physical_progress', reason='当前范围无独立原任务或active批次未形成完整守恒分母；不得把绑定原批次当成返工任务产量。'))
        if any(row['detail_truncated'] for row in items):
            unknowns.append(dict(field='rows', reason='任务批次或排程仅返回前50条，完整内容需读取原任务。完整总量不使用该截断样本计算。'))
        values.update(overdue_tasks=None, material_shortage=None)
        metrics = {key: dict(value=value, unit='未明确' if key == 'material_shortage' else '任务' if key.endswith('tasks') else '件',
            definition_id='uv.' + key + '.v1', status='unknown' if value is None else 'known') for key, value in values.items()}
        refs = [item['resource_ref'] for item in items]
        label = '华康A / ' + ('选中UV任务' if args.resource_id else '全部UV任务')
        as_of = requested.isoformat()
        source_id = stable_id(run_id, NAME, scope_key, after, as_of)
        retrieved = business_now().isoformat()
        filters = dict(view_revision=revision, source_data_mode=config.data_mode)
        resources = [dict(module_id=MODULE, resource_type='task', resource_id=row.id) for row in rows]
        source = dict(kind='business', source_id=source_id, run_id=run_id, title='UV生产任务', tool_name=NAME,
            resources=resources,
            scope=dict(factory_id=args.factory_id, scope_label=label, authorization='current_user', filters=filters),
            as_of=as_of, observed_at=None, retrieved_at=retrieved, data_mode='snapshot',
            unknown_fields=[u['reason'] for u in unknowns], authorization_fingerprint=auth)
        cursor = dict(after=rows[-1].id, as_of=anchor, key=stable_id(scope_key, rows[-1].id, anchor)) if truncated else None
        next_cursor = base64.urlsafe_b64encode(json.dumps(cursor, separators=(',', ':')).encode()).decode() if cursor else None
        actions = [dict(type='open_record', label='打开原UV任务：' + row.code[:60],
            route_name='uv-planning', params={}, query=dict(factory=args.factory_id, uv_task=row.id),
            resource=resource) for row, resource in zip(rows, resources)]
        result = dict(record_type='tool_result', contract_version=3, tool_name=NAME, tool_version='uv-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id, scope_key, after), run_id=run_id, step_id=step_id or NAME,
            status='empty' if not total else 'partial',
            scope=dict(factory_ids=[args.factory_id], module_id=MODULE, filters=filters,
                resource_refs=refs if args.resource_id else [],
                coverage='selected_resources' if args.resource_id else 'authorized_scope', label=label),
            requested_at=as_of, as_of=as_of, observed_at=None, retrieved_at=retrieved,
            timezone='Asia/Shanghai', business_date=requested.date().isoformat(), data_mode='snapshot',
            freshness=dict(state='fresh', max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id='uv-current-v1'),
            metrics=metrics, rows=items, total_count=total, returned_count=len(rows), truncated=truncated, next_cursor=next_cursor,
            definitions=DEFINITIONS, unknown_fields=unknowns, source_refs=[source_id],
            allowed_actions=[dict(action_id=stable_id(source_id, i), kind='navigate', label=action['label'], resource_ref=refs[i])
                             for i, action in enumerate(actions)], diagnostic_code=None)
        return validate_result(result, registered_sources=[source_id], registered_resources=refs,
            row_fields={*TASK_FIELDS, 'resource_ref', 'batch_scope', 'batches', 'schedule',
                        'batches_total', 'schedule_total', 'detail_truncated'}), source, actions


def visible(db, user, source):
    authorize(db, user, source.get('scope', {}).get('factory_id'))
    if source.get('tool_name') != NAME or not matches(db, user, source.get('authorization_fingerprint')):
        return False
    for resource in source.get('resources', []):
        if (resource.get('module_id') != MODULE or resource.get('resource_type') != 'task'
            or not db.scalar(c.query(m.UvOpsTask).where(m.UvOpsTask.id == resource.get('resource_id')))):
            return False
    return True
