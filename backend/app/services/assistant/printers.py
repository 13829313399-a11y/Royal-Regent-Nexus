"""Authorized read-only device evidence; querying never renews telemetry."""
import base64
from datetime import datetime
import json
import math

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app import db as database
from app.core.time import parse_business_timestamp
from app.services import three_d_printing as domain
from .errors import AssistantError
from .evidence import stable_id
from .tool_result import validate_result

NAME = 'get_printer_status'
ROW_FIELDS = ('id', 'machine_no', 'name', 'model', 'enabled', 'connected', 'state', 'status_stale',
              'current_file', 'progress_percent', 'remaining_minutes', 'live_material',
              'nozzle_temperature', 'bed_temperature', 'error_text', 'nozzle_target', 'bed_target', 'layer_num', 'total_layers')
KNOWN_STATES = {'IDLE', 'RUNNING', 'PAUSE', 'FINISH', 'FAILED', 'ERROR', 'PREPARE', 'PREPARING', 'DOWNLOADING', 'SLICING'}
DEFINITIONS = {
    'printer.printer_count.v1': '明确厂区内授权设备总数，含停用设备；选中设备只计该台。不是本页返回数。',
    'printer.current_telemetry_count.v1': '原系统 connected=true 且 status_stale=false 的设备数；不是物理开机或产出证明。',
    'printer.stale_count.v1': '原系统 status_stale=true 的设备数：观测超过30秒、缺失、未来超过5秒或适用的网络健康失效。',
    'printer.unknown_current_state_count.v1': '断连、过期或状态枚举未知的设备数，不能视为空闲、停机或完成。',
    'printer.reported_running_count.v1': '只有当前有效遥测且 state=RUNNING 才计入；不包含准备/下载/暂停，也不代表实际产量。',
    'printer.physically_stopped_count.v1': '没有现场实机证据，无法确定物理停机数量。失联和陈旧状态不能替代现场确认。',
    'printer.task_queue_count.v1': '此工具读取设备上报任务及近期观测，未读取完整排产队列；队列数量未知。',
    'printer.timestamps.v1': 'as_of/requested_at 是本轮数据库查询时点；observed_at/各行 observed_at 是设备原观测时点，查询不更新设备时间。多机观测不同时顶层 observed_at 为空。',
    'printer.task_fields.v1': 'current_file、进度、温度和剩余时间保留最近一次设备上报；stale/断连时只能作为历史观测。准备态的进度不代表实际打印进度。remaining_minutes 是设备估计，不是交付承诺。',
    'printer.network.v1': '站点健康与单机遥测分开。有效的 observation_only 单机观测不因站点部分故障失效；健康采集未配置不表示网络正常。',
    'printer.recent_observations.v1': '选中设备附原详情最新100条窗口内最多10条观测，按 received_at 倒序；不是完整任务历史，无控制操作。',
}


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    resource_id: str | None = Field(default=None, min_length=1, max_length=96)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode='after')
    def selected(self):
        if self.resource_id and self.cursor:
            raise ValueError('selected device has no list cursor')
        return self


def timestamp(value):
    parsed = parse_business_timestamp(value)
    return parsed.isoformat() if parsed else None


def row_out(item):
    clipped = []
    unavailable = []
    result = {}
    for key in ROW_FIELDS:
        if key not in item:
            continue
        value = item[key]
        if key in {'nozzle_target', 'bed_target', 'layer_num', 'total_layers'} and (
            type(value) not in (int, float) or not math.isfinite(value)
        ):
            value = None
            unavailable.append(key)
        if isinstance(value, str) and len(value) > 200:
            value = value[:200]
            clipped.append(key)
        result[key] = value
    current = bool(item['connected'] and not item['status_stale'])
    result.update(resource_ref='three-d-printing:printer:' + item['id'], observed_at=timestamp(item['last_seen_at']),
        current_state=item['state'] if current and item['state'] in KNOWN_STATES else None,
        observation_use='current_telemetry' if current else 'historical_only', truncated_fields=clipped,
        unavailable_fields=unavailable)
    return result


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except (ValidationError, ValueError, TypeError):
        raise AssistantError('tool_invalid', '3D机台查询参数无效，请核对厂区、机台或分页。', 422) from None
    if args.factory_id != 'huakang-a':
        raise AssistantError('factory_unavailable', '3D打印管理仅支持华康A。', 422)
    from .business import authorize, fingerprint
    requested = domain.business_now()
    with database.SessionLocal() as db:
        authorize(db, user, NAME, args.factory_id)
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name == 'postgresql':
            db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        auth = fingerprint(db, user)
        try:
            snapshot = domain.printer_status_snapshot(db, factory_id=args.factory_id, printer_id=args.resource_id, as_of=requested)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            raise AssistantError('source_unavailable', '选中机台不存在或不在当前厂区。', 404) from None
        all_items = snapshot['printers']
        network = {k: snapshot['network_health'].get(k) for k in ('configured', 'status', 'observed_at')}
        network['observed_at'] = timestamp(network['observed_at'])
        # Hash the native projection, not the query clock. Freshness threshold
        # transitions and source updates invalidate the old page continuation.
        projected = [row_out(item) for item in all_items]
        revision = stable_id(compact(projected), compact(network))
        scope_key = stable_id(auth, args.factory_id, args.resource_id, revision)
        offset, anchor = 0, requested
        if args.cursor:
            try:
                cursor = json.loads(base64.urlsafe_b64decode(args.cursor.encode('ascii')))
                anchor = datetime.fromisoformat(cursor['at'])
                offset = cursor['offset']
                if (anchor.tzinfo is None or type(offset) is not int or not 0 < offset < len(all_items)
                    or cursor['key'] != stable_id(scope_key, anchor.isoformat(), offset)
                    or not 0 <= (requested - anchor).total_seconds() <= 300):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                raise AssistantError('cursor_invalid', '机台数据、遥测时效或权限已变化，请从第一页重新查询。', 422) from None
        total = len(all_items)
        page = all_items[offset:offset+args.limit]
        rows = projected[offset:offset+args.limit]
        if args.resource_id:
            from app.services.three_d_workspace import printer_detail
            detail = printer_detail(db, args.resource_id)
            rows[0]['recent_observations'] = [{
                k: timestamp(e[k]) if k in ('observed_at', 'received_at') else e[k][:200] if isinstance(e[k], str) else e[k]
                for k in ('state', 'progress', 'current_file', 'error_text', 'observed_at', 'received_at')
            } for e in detail['events'][:10]]
            rows[0]['recent_observations_truncated'] = len(detail['events']) > 10
        current = [i for i in all_items if i['connected'] and not i['status_stale']]
        stale_count = sum(bool(i['status_stale']) for i in all_items)
        unknown_count = sum(not i['connected'] or i['status_stale'] or i['state'] not in KNOWN_STATES for i in all_items)
        values = dict(printer_count=total, current_telemetry_count=len(current), stale_count=stale_count,
            unknown_current_state_count=unknown_count, reported_running_count=sum(i['state']=='RUNNING' for i in current),
            physically_stopped_count=None, task_queue_count=None)
        unknowns = [dict(field=k, reason=DEFINITIONS['printer.'+k+'.v1']) for k in ('physically_stopped_count', 'task_queue_count')]
        if unknown_count:
            unknowns.append(dict(field='physical_state', reason='部分设备缺少有效当前状态；断连/过期不证明物理停机。'))
        if any(r['truncated_fields'] for r in rows):
            unknowns.append(dict(field='rows', reason='部分长文本只保留前200字；完整内容请查看原设备页。'))
        if any(r['unavailable_fields'] for r in rows):
            unknowns.append(dict(field='telemetry_fields', reason='部分可选遥测值不是有效数字，已标为空值；不解释为零。'))
        refs = [r['resource_ref'] for r in rows]
        resources = [dict(module_id='three-d-printing', resource_type='printer', resource_id=i['id']) for i in page]
        selected = bool(args.resource_id)
        label = '华康A / 选中机台' if selected else '华康A / 全部机台'
        observations = {timestamp(i['last_seen_at']) for i in all_items}
        observed = observations.pop() if len(observations) == 1 else None
        retrieved = domain.business_now().isoformat()
        source_id = stable_id(run_id, NAME, scope_key, offset, requested.isoformat())
        source = dict(kind='business', source_id=source_id, run_id=run_id, title='3D机台状态', tool_name=NAME,
            resources=resources, scope=dict(factory_id=args.factory_id, scope_label=label, authorization='current_user', network_health=network),
            as_of=requested.isoformat(), observed_at=observed, retrieved_at=retrieved, data_mode='telemetry',
            unknown_fields=[u['field'] for u in unknowns], authorization_fingerprint=auth)
        actions = [dict(type='open_record', label=f"查看 {item['machine_no']} 号机", route_name='three-d-printing-management', params={},
            query=dict(factory=args.factory_id, tab='machines', printer=item['id']), resource=resource)
            for item, resource in zip(page, resources)]
        if not actions:
            actions = [dict(type='open_record', label='打开3D机台工作区', route_name='three-d-printing-management', params={},
                query=dict(factory=args.factory_id), resource=dict(module_id='three-d-printing', resource_type='overview', resource_id=args.factory_id))]
        truncated = offset + len(rows) < total
        next_cursor = base64.urlsafe_b64encode(compact(dict(at=anchor.isoformat(), offset=offset+len(rows),
            key=stable_id(scope_key, anchor.isoformat(), offset+len(rows)))).encode()).decode() if truncated else None
        freshness = 'not_applicable' if not total else 'stale' if stale_count else 'unknown' if unknown_count else 'fresh'
        result = dict(record_type='tool_result', contract_version=3, tool_name=NAME, tool_version='printers-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id, scope_key, offset), run_id=run_id, step_id=step_id or NAME,
            status='empty' if not total else 'stale' if stale_count else 'partial',
            scope=dict(factory_ids=[args.factory_id], module_id='three-d-printing',
                filters=dict(network_health=compact(network), source_revision=revision), resource_refs=refs if selected else [],
                coverage='selected_resources' if selected else 'authorized_scope', label=label),
            requested_at=requested.isoformat(), as_of=requested.isoformat(), observed_at=observed, retrieved_at=retrieved,
            timezone='Asia/Shanghai', business_date=requested.date().isoformat(), data_mode='telemetry',
            freshness=dict(state=freshness, max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id='native-printer-telemetry-v1'),
            metrics={k:dict(value=v, unit='台' if k!='task_queue_count' else '任务', definition_id='printer.'+k+'.v1',
                           status='known' if v is not None else 'unknown') for k,v in values.items()},
            rows=rows, total_count=total, returned_count=len(rows), truncated=truncated, next_cursor=next_cursor,
            definitions=DEFINITIONS, unknown_fields=unknowns, source_refs=[source_id], diagnostic_code=None,
            allowed_actions=[dict(action_id=stable_id(source_id, index), kind='navigate', label=action['label'],
                resource_ref=refs[index] if rows else None) for index, action in enumerate(actions)])
        return validate_result(result, registered_sources=[source_id], registered_resources=refs,
            row_fields={*ROW_FIELDS, 'resource_ref', 'observed_at', 'current_state', 'observation_use', 'truncated_fields',
                        'recent_observations', 'recent_observations_truncated', 'unavailable_fields'}), source, actions
