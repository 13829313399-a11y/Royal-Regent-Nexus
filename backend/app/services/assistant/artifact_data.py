"""Read-only artifact views of the exact persisted, authorized V3 query snapshot.

No new query, model-produced dataset, refresh, formula or executable chart input.
Every view shares the same content-addressed dataset and its original clocks.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json

from sqlalchemy import select
from app.models.assistant import AssistantMessage

LABELS = {
    'reference_no': '订单编号', 'customer_code': '客户编号', 'customer_name': '客户名称', 'product_no': '产品编号',
    'product_name': '产品名称', 'description': '说明', 'unit': '单位', 'quantity': '数量',
    'order_quantity': '订单数量', 'shipped_quantity': '已走货数量', 'remaining_quantity': '未走货数量',
    'delivery_date': '交付日期', 'due_date': '到期日期', 'status': '状态', 'validity': '有效性',
    'order_count': '订单行数', 'unfinished_count': '未完成订单', 'overdue_count': '逾期订单',
    'unknown_quantity_count': '数量未知订单', 'overdue_unknown_count': '交期未知订单',
    'cancelled_count': '取消订单', 'title': '标题', 'name': '名称', 'type': '类型',
    'pending_count': '待处理数', 'unread_count': '未读数', 'total_count': '总数',
    'completed_count': '完成数', 'printer_name': '打印机', 'printer_count': '打印机数',
    'task_count': '任务数', 'demand_count': '需求数', 'planned_quantity': '计划数量',
    'good_quantity': '良品数量', 'defect_quantity': '不良数量', 'quote_no': '报价编号',
    'version_label': '版本', 'customer': '客户', 'amount': '金额', 'currency': '币种',
    'as_of': '数据时点', 'observed_at': '观测时间', 'updated_at': '更新时间',
    'version': '原单版本', 'overdue': '逾期', 'dispatch_status': '发送状态',
    'order_fields.po_no': '客户PO', 'order_fields.contract_no': '合同号',
    'order_fields.product_name_zh': '产品名称', 'order_fields.product_name_en': '英文品名',
    'order_fields.requested_ship_date': '客户要求交期', 'order_fields.packaging': '包装',
    'order_fields.units_per_carton': '每箱数量', 'order_fields.carton_count': '箱数',
    'order_fields.standard': '标准', 'order_fields.country': '国家',
    'order_fields.note': '备注', 'order_fields.recheck_notice': '待复核说明',
}
HIDDEN = {'id', 'resource_ref', 'authorization_fingerprint', 'truncated_fields', 'revision', 'factory_id', 'requested_ship_date_known'}
ORDER = ['reference_no', 'customer_name', 'product_no', 'order_fields.product_name_zh', 'quantity',
         'shipped_quantity', 'remaining_quantity', 'order_fields.requested_ship_date', 'overdue', 'status',
         'dispatch_status', 'version', 'order_fields.note', 'updated_at', 'customer_code']


def label(key):
    return LABELS.get(key, key)


def cell(value):
    if value is None:
        return '未知'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return str(value)


def display(dataset, key, value):
    if dataset['scope'].get('module_id') == 'customer-orders':
        if key == 'status':
            return {'active': '有效', 'cancelled': '已取消'}.get(value, cell(value))
        if key == 'dispatch_status':
            return {'unsent': '未发送', 'sent': '已发送'}.get(value, cell(value))
    return cell(value)


def datasets(parts):
    evidence = next((p for p in parts if p.get('type') == 'evidence'), {})
    sources = {s['source_id']: s for s in evidence.get('sources', [])}
    result, seen = [], set()
    for part in parts:
        value = part.get('result', {})
        if (part.get('type') not in ('business_snapshot','tool_result') or not isinstance(value,dict) or value.get('contract_version') != 3
                or value.get('status') in {'failed', 'forbidden', 'not_connected'}):
            continue
        if part.get('type')=='tool_result':
            # Help/model payloads cannot become business datasets. Only an
            # explicitly registered current-run domain result is eligible.
            from .registry import BY_MODULE
            scope=value.get('scope')
            connector=BY_MODULE.get(scope.get('module_id')) if isinstance(scope,dict) else None
            refs=value.get('source_refs')
            if (value.get('run_id')!=evidence.get('run_id')
                    or connector is None or not connector.callable or connector.tool_name!=value.get('tool_name')
                    or part.get('name')!=value.get('tool_name') or not isinstance(refs,list) or not refs
                    or any(not isinstance(ref,str) or ref not in sources or sources[ref].get('kind')!='business'
                        or sources[ref].get('run_id')!=value.get('run_id')
                        or sources[ref].get('tool_name')!=value.get('tool_name')
                        or sources[ref].get('citation_eligible') is False for ref in refs)):
                continue
        # The already validated domain projection is immutable after termination.
        identity = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        if identity in seen:
            continue
        seen.add(identity)
        rows = []
        for record in value.get('rows', []):
            row = {k: v for k, v in record.items() if k not in HIDDEN and not k.startswith('_')}
            if value['scope']['module_id'] == 'customer-orders' and isinstance(row.get('order_fields'), dict):
                row.update({'order_fields.' + key: item for key, item in row.pop('order_fields').items()})
            rows.append(row)
        columns = sorted({k for row in rows for k in row}, key=lambda key: (ORDER.index(key) if key in ORDER else len(ORDER), key))
        metrics, groups = [], defaultdict(list)
        for key, metric in value.get('metrics', {}).items():
            item = dict(key=key, label=label(key), **metric)
            metrics.append(item)
            try:
                number = Decimal(str(metric['value']))
                finite = number.is_finite() and abs(number) <= Decimal('1e30')
            except (InvalidOperation, ValueError, TypeError):
                finite = False
            if metric.get('status') == 'known' and finite:
                groups[(metric['unit'], metric.get('currency') or '')].append(key)
        refs = value.get('source_refs', [])
        title = next((sources[ref]['title'] for ref in refs if ref in sources), value['scope']['label'])
        result.append(dict(dataset_id=identity, title=title, scope=value['scope'],
            as_of=value.get('as_of'), observed_at=value.get('observed_at'), retrieved_at=value['retrieved_at'],
            timezone=value['timezone'], status=value['status'], historical=True,
            total_count=value.get('total_count'), returned_count=value['returned_count'],
            truncated=value['truncated'], columns=[dict(key=k, label=label(k)) for k in columns], rows=rows,
            metrics=metrics, definitions=value['definitions'], unknown_fields=value.get('unknown_fields', []),
            source_ids=refs, charts=[dict(type='bar', dataset_id=identity, unit=unit, currency=currency or None,
                metric_keys=keys) for (unit, currency), keys in groups.items()]))
    return result


def for_run(db, run_id):
    message = db.scalar(select(AssistantMessage).where(AssistantMessage.run_id == run_id,
        AssistantMessage.role == 'assistant'))
    return datasets(message.content_parts) if message else []


def scope_lines(dataset):
    count = dataset['total_count']
    as_of = (datetime.fromisoformat(dataset['as_of'].replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S') + '（北京时间）') if dataset['as_of'] else '未知'
    return [dataset['scope']['label'],
        f"历史查询快照；数据时点 {as_of}",
        f"实际返回 {dataset['returned_count']} / {'未知' if count is None else count} 条"
        + ('；仅含当时返回的记录，导出不补查后续页。' if dataset['truncated'] else '；不是重新查询的当前状态。'),
        '数据集 ' + dataset['dataset_id']]


def markdown(items):
    def safe(value):
        return cell(value).replace('\\', '\\\\').replace('|', '\\|').replace('\n', ' / ')
    lines = []
    for dataset in items:
        lines += ['## 原查询数据 · ' + dataset['title'], *scope_lines(dataset), '',
                  '| 指标 | 原值 | 单位 | 口径 |', '| --- | --- | --- | --- |']
        for metric in dataset['metrics']:
            lines.append('| ' + ' | '.join(safe(x) for x in (metric['label'], metric['value'],
                metric['unit'], dataset['definitions'].get(metric['definition_id'], metric['definition_id']))) + ' |')
        if dataset['columns']:
            lines += ['', '| ' + ' | '.join(safe(c['label']) for c in dataset['columns']) + ' |',
                      '| ' + ' | '.join('---' for _ in dataset['columns']) + ' |']
            lines += ['| ' + ' | '.join(safe(display(dataset, c['key'], row.get(c['key']))) for c in dataset['columns']) + ' |'
                      for row in dataset['rows']]
        for unknown in dataset['unknown_fields']:
            lines.append('待核对：' + unknown['field'] + ' — ' + unknown['reason'])
        lines.append('')
    return '\n'.join(lines)
