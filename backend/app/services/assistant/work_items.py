"""Current-authority work-center reads. No personal-state or domain writes."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app import db as database
from app.core.time import BUSINESS_TIME_ZONE
from app.services.work_center import service as work
from .errors import AssistantError
from .evidence import now_iso, stable_id
from .tool_result import validate_result

NAME = 'get_my_work'
FILTER_KEYS = {'view', 'module', 'q', 'due', 'unread_only', 'limit', 'cursor'}
FIELDS = ('id', 'kind', 'module', 'title', 'summary', 'lifecycle', 'source_factory', 'execution_factory',
          'due_at', 'why_me', 'verification_state', 'content_version', 'attention_version')
SUMMARY_LABELS = {
    'actionable_total': '可处理事项', 'assigned_total': '指派给本人', 'team_queue_total': '团队队列',
    'waiting_total': '流程跟进', 'overdue_total': '逾期事项', 'due_today_total': '今日到期事项',
    'unread_total': '未读事项', 'info_unread_total': '未读知会', 'info_total': '知会',
    'focus_total': '需关注事项', 'snoozed_total': '本人稍后处理事项',
    'verification_required_total': '业务版本或来源待核对事项',
}


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    resource_id: str | None = Field(default=None, min_length=1, max_length=160)
    view: Literal['todo', 'assigned', 'team', 'waiting', 'info', 'history', 'verification'] = 'todo'
    module: str = Field(default='', max_length=64)
    q: str = Field(default='', max_length=200)
    due: Literal['all', 'none', 'today', 'overdue'] = 'all'
    unread_only: bool = False
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode='after')
    def selected_scope(self):
        if self.resource_id and (self.cursor or self.module or self.q or self.due != 'all' or self.unread_only or self.view != 'todo'):
            raise ValueError('selected entry cannot combine list filters')
        return self


def in_factory(item, factory):
    return factory == 'authorized' or any((item.get(k) or {}).get('id') == factory for k in ('source_factory', 'execution_factory'))


def local_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(BUSINESS_TIME_ZONE).isoformat()


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except ValidationError:
        raise AssistantError('tool_invalid', '事项查询参数无效；请核对视图、厂区、筛选或分页。', 422) from None
    requested_at = local_time(now_iso())
    from .business import authorize, fingerprint
    with database.SessionLocal() as db:
        authorize(db, user, NAME, args.factory_id)
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        filters = {k: v for k, v in args.model_dump().items() if k in FILTER_KEYS - {'limit', 'cursor'}}
        # Native snapshot applies the authoritative source/epoch/role predicates,
        # exact full-filter count and keyset cursor before bounded presentation.
        value = work.snapshot(db, user, factory_scope=args.factory_id, limit=args.limit, cursor=args.cursor, **filters)
        if args.resource_id:
            items = [work.detail(db, user, args.resource_id)]
            if not in_factory(items[0], args.factory_id):
                raise AssistantError('source_unavailable', '选中事项不存在或不在当前厂区。', 404)
        else:
            items = value['items']
        rows = []
        for item in items:
            row = {k: item.get(k) for k in FIELDS}
            row['read_state'] = item.get('personal', {}).get('read_state', 'legacy_unknown')
            row['truncated_fields'] = []
            for key, cap in (('title', 200), ('summary', 500), ('why_me', 300)):
                if isinstance(row[key], str) and len(row[key]) > cap:
                    row[key] = row[key][:cap]
                    row['truncated_fields'].append(key)
            row['resource_ref'] = 'work-center:entry:' + item['id']
            rows.append(row)
        health = value['health']
        incomplete_sources = bool(health.get('unavailable_sources'))
        selected = bool(args.resource_id)
        total = 1 if selected else None if incomplete_sources else value['query']['filtered_total']
        next_cursor = None if selected else value['next_cursor']
        unknowns = [dict(field='coverage', reason='仅统计事项中心已接入来源；未接入模块不在范围内。')]
        if health['status'] == 'partial':
            unknowns.append(dict(field='source_health', reason='部分来源不可用或原业务版本待核对；当前可见事项不代表全部业务均已同步。'))
        if any(row['truncated_fields'] for row in rows):
            unknowns.append(dict(field='summary', reason='部分长文本已截断；请打开原事项查看全文。'))
        definitions = {
            'work.filtered_count.v1': '当前厂区、视图、关键词、期限及未读筛选后的事项总量，非返回样本数；选中记录查询只统计该记录。来源不可用时完整总量未知。',
            'work.coverage.v1': '原事项中心接入范围：' + str(health['coverage']),
        }
        metrics = {'filtered_count': dict(value=total, unit='事项', definition_id='work.filtered_count.v1', status='unknown' if total is None else 'known')}
        # Keep full-authorization summaries explicitly separate from filtered and
        # selected counts. No inferred "all work total" is made by summing categories.
        if not selected:
            for key, count in value['summary'].items():
                definition = f'work.authorized.{key}.v1'
                definitions[definition] = '本人全部授权范围（未应用厂区/视图/关键词/未读筛选）的' + SUMMARY_LABELS.get(key, key) + '；沿用原事项中心口径，各分类可能重叠，不可相加。'
                metrics['authorized_' + key] = dict(value=None if incomplete_sources else count, unit='事项', definition_id=definition, status='unknown' if incomplete_sources else 'known')
        as_of = local_time(health['as_of'])
        auth = fingerprint(db, user)
        scope_label = ('本人全部授权范围' if args.factory_id == 'authorized' else args.factory_id) + (' / 选中事项' if selected else ' / 当前事项筛选')
        resources = [dict(module_id='work-center', resource_type='entry', resource_id=item['id']) for item in items]
        refs = [row['resource_ref'] for row in rows]
        source_id = stable_id(run_id, NAME, auth, args.model_dump(), as_of)
        source = dict(kind='business', source_id=source_id, run_id=run_id, title='我的工作', tool_name=NAME,
            resources=resources, scope=dict(factory_id=None if args.factory_id=='authorized' else args.factory_id,
                scope_label=scope_label, filters=filters, authorization='current_user'), as_of=as_of, observed_at=None,
            retrieved_at=local_time(now_iso()), data_mode='snapshot', unknown_fields=[u['reason'] for u in unknowns], authorization_fingerprint=auth)
        navigation = dict(factory=args.factory_id, view=args.view, **{k: v for k, v in filters.items() if k in ('module', 'q', 'due') and v and v != 'all'})
        if args.unread_only: navigation['unread'] = '1'
        actions = [dict(type='open_record', label='打开当前事项列表', route_name='notification-center', params={}, query=navigation,
            resource=dict(module_id='work-center', resource_type='overview', resource_id=args.factory_id))] if not selected else []
        actions.extend(dict(type='open_record', label='打开事项：'+str(row['title'])[:60], route_name='notification-center', params={},
            query=dict(factory=args.factory_id, entry=row['id']), resource=resource) for row, resource in zip(rows, resources))
        result = dict(record_type='tool_result', contract_version=3, tool_name=NAME, tool_version='work-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id, NAME, args.model_dump()), run_id=run_id, step_id=step_id or NAME,
            status='partial' if next_cursor or health['status']=='partial' or any(row['truncated_fields'] for row in rows) else 'empty' if total==0 else 'ok',
            scope=dict(factory_ids=[] if args.factory_id=='authorized' else [args.factory_id], module_id='work-center', filters={} if selected else filters,
                resource_refs=refs if selected else [], coverage='selected_resources' if selected else 'filtered_scope', label=scope_label),
            requested_at=requested_at, as_of=as_of, observed_at=None, retrieved_at=source['retrieved_at'], timezone='Asia/Shanghai', business_date=as_of[:10],
            data_mode='snapshot', freshness=dict(state='unknown' if incomplete_sources else 'fresh', max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id='work-current-v1'),
            metrics=metrics, rows=rows, total_count=total, returned_count=len(rows), truncated=bool(next_cursor), next_cursor=next_cursor,
            definitions=definitions, unknown_fields=unknowns, source_refs=[source_id], diagnostic_code='work_sources_partial' if incomplete_sources else None,
            allowed_actions=[dict(action_id=stable_id(source_id, i), kind='navigate', label=action['label'],
                resource_ref=('work-center:entry:'+action['resource']['resource_id']) if action['resource']['resource_type']=='entry' else None) for i, action in enumerate(actions)])
        return validate_result(result, registered_sources=[source_id], registered_resources=refs,
            row_fields={*FIELDS, 'read_state', 'truncated_fields', 'resource_ref'}), source, actions
