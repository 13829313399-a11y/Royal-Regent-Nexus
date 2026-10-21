"""P4e read-only XLSX reports, pinned to immutable evidence or a live read token."""
from copy import deepcopy
from typing import Literal
from types import SimpleNamespace

from pydantic import Field, model_validator
from sqlalchemy import select, func

from app.services import cutting_ops as c, cutting_periods as periods
from app.services import cutting_settlement as fees, cutting_payments as payments
from app.services.cutting_schemas import Strict
from app.services.cutting_period_schemas import Month
from app.services.transaction_lock import lock_transaction
from app.services.warehouse_operations import business_now
from app.services import cutting_export_workbook as workbook_export

PERMISSIONS = {'period': 'cost_read', 'settlement': 'settlement_read', 'payments': 'payment_read'}
TITLES = {'period': '内部月结冻结表', 'settlement': '外发结算冻结单', 'payments': '付款登记及当前未付余额表'}
STATES = {'draft': '草稿', 'submitted': '待复核', 'returned': '已退回', 'locked': '已锁月',
          'confirmed': '已生效', 'reopened': '已反结', 'reversed': '已冲销登记', 'open': '未编制'}
ACTIONS = {'save': '保存编制', 'submit': '提交复核', 'return': '退回', 'lock': '复核锁月', 'reopen': '反结', 'confirm': '复核生效', 'reverse': '冲销登记'}
AMOUNTS = [('opening_custody', '期初结存材料费用'), ('ending_custody', '期末结存材料费用'),
           ('opening_normal', '期初累计正常费用'), ('ending_normal', '期末累计正常费用'),
           ('period_normal', '本期正常费用'), ('opening_completed', '期初累计完工费用'),
           ('ending_completed', '期末累计完工费用'), ('period_completed', '本期转完工费用'),
           ('opening_wip', '期初在制费用'), ('ending_wip', '期末在制费用'),
           ('opening_loss', '期初累计损耗费用'), ('ending_loss', '期末累计损耗费用'), ('period_loss', '本期损耗费用')]


class Selection(Strict):
    factory_id: str
    kind: Literal['period', 'settlement', 'payments']
    month: Month
    event_id: str | None = Field(default=None, max_length=64)
    document_id: str | None = Field(default=None, max_length=64)
    token: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def source(self):
        if self.kind != 'payments' and not self.event_id:
            raise ValueError('冻结报表必须指定所选事件版本')
        if self.kind == 'settlement' and not self.document_id:
            raise ValueError('外发结算必须指定结算单')
        if self.kind == 'payments' and (self.event_id or self.document_id):
            raise ValueError('付款余额表采用当前全量口径，不接收历史单据参数')
        if self.kind == 'period' and self.document_id:
            raise ValueError('内部月结按整月导出')
        return self


def sheet(name, headers, rows):
    return dict(name=name, headers=headers, rows=rows)


def order_values(order):
    return [order.get('customer_name', ''), order.get('reference_no', ''), order.get('product_no', ''),
            order.get('product_name_zh') or order.get('product_name_en', '')]


def trace_rows(order, snapshot):
    """Read frozen evidence only; never resolve old actors/links against today's ledger."""
    rows = []
    for category, label in [('production_documents', '生产填数'), ('usage_documents', '耗用登记'), ('warehouse_documents', '仓库流水')]:
        for document in order.get(category, []):
            warehouse = category == 'warehouse_documents'
            history = [document] if warehouse else document.get('history', [])
            posts = [e['id'] for e in history if e.get('action') == 'post']
            for event in history:
                payload = event.get('data', {})
                entry = payload.get('entry', event.get('entry', {}))
                day = event.get('day') or entry.get('day')
                scope = ('期初' if day < snapshot['start'] else '本期' if day <= snapshot['end'] else '后续期间') if day else '待核对'
                action = event.get('action', event.get('kind'))
                previous = following = ''
                if warehouse:
                    state = '已冲销' if event.get('reversed') else '关联流水'
                    if action == 'CORRECTION': state = '冲销操作'
                elif category == 'production_documents':
                    effective_id = (document.get('posted') or {}).get('id')
                    state = '有效记录' if event['id'] == effective_id else '历史／操作记录'
                    if event['id'] == (document.get('draft') or {}).get('id'): state = '未提交草稿'
                    if action == 'void': state = '作废操作'
                    if event['id'] in posts:
                        index = posts.index(event['id'])
                        previous = posts[index - 1] if index else ''
                        following = posts[index + 1] if index + 1 < len(posts) else ''
                else:
                    state = '有效记录' if document.get('effective') and action == 'post' else '历史／操作记录'
                    if action == 'void': state = '作废操作'
                rows.append([order['line_id'], label, document.get('document_id', document.get('id')), event.get('id'),
                    action, day, event.get('actor') or event.get('actor_id'), event.get('date') or event.get('created_at'),
                    event.get('reason'), scope, state, event.get('original_id') or '',
                    event.get('replaces_document_id') or payload.get('replaces_document_id') or '',
                    event.get('replaced_by_document_id') or payload.get('replaced_by_document_id') or '', previous, following])
    return rows


def period_sheets(snapshot):
    totals = sheet('费用汇总', ['币种'] + [label for _, label in AMOUNTS],
                   [[currency] + [values.get(key) for key, _ in AMOUNTS] for currency, values in sorted(snapshot['costs'].items())])
    production, materials, references = [], [], []
    for order in snapshot['orders']:
        identity = [order['line_id']] + order_values(order.get('order_snapshot', {}))
        for row in order['production']:
            production.append(identity + [row.get(key) for key in ('task_id', 'task_name', 'resource_name')] +
                [{'internal': '本厂', 'outsourced': '外发'}.get(row.get('execution'), row.get('execution'))] +
                [row.get(key) for key in ('planned', 'opening_completed', 'completed', 'closing_completed', 'handed', 'claimed', 'returned',
                'accepted', 'rejected', 'completed_unhanded', 'pending_return', 'pending_acceptance')])
        for row in order['materials']:
            context = row['context']
            materials.append(identity + [row['issue_id'], context.get('root_batch_id'), context.get('task_name'),
                context.get('resource_name'), context.get('item_name'), context.get('unit')] +
                [row.get(key) for key in ('opening_quantity', 'issued_quantity', 'unsigned_quantity', 'received_quantity',
                                        'returned_quantity', 'consumed_quantity', 'loss_quantity', 'ending_quantity')])
        references.extend(trace_rows(order, snapshot))
    allocations = []
    for row in snapshot['allocations']:
        context = row['context']; price = row.get('price') or {}; entry = price.get('data', {}).get('entry', {})
        allocations.append([row['line_id'], row['issue_id'], context.get('root_batch_id'), context.get('task_name'),
            context.get('resource_name'), context.get('item_name'), context.get('unit')] +
            [row.get(key) for key in ('opening_normal_quantity', 'ending_normal_quantity', 'opening_completed_quantity',
                                     'completed_quantity', 'opening_wip_quantity', 'ending_wip_quantity',
                                     'opening_loss_quantity', 'ending_loss_quantity')] +
            [row.get('currency'), entry.get('unit_cost'), price.get('version'), entry.get('price_reference')] +
            [row.get('amounts', {}).get(key) for key, _ in AMOUNTS])
    identity_headers = ['订单明细ID', '客户', '订单号', '货号', '货名']
    return [totals,
        sheet('生产汇总', identity_headers + ['任务ID', '任务', '执行方', '本厂／外发', '本期计划套数', '期初完成套数',
            '本期完成套数', '期末累计完成套数', '本期交接套数', '本期外发自报套数', '本期收回套数', '本期验收套数',
            '本期不合格套数', '期末完成未交接套数', '期末自报未收回套数', '期末收回未验收套数'], production),
        sheet('物料收发耗存', identity_headers + ['原实发ID', '原批次ID', '任务', '执行方', '物料', '单位', '期初结存',
            '本期实发', '截至期末未签收', '本期签收', '本期退仓', '本期正常耗用', '本期损耗', '期末结存'], materials),
        sheet('完工及在制归集', ['订单明细ID', '原实发ID', '原批次ID', '任务', '执行方', '物料', '单位',
            '期初累计正常耗用', '期末累计正常耗用', '期初完工归属量', '期末完工归属量', '期初在制量', '期末在制量',
            '期初累计损耗量', '期末累计损耗量', '币种', '冻结批次单价', '成本版本', '成本凭据'] + [label for _, label in AMOUNTS], allocations),
        sheet('冻结来源索引', ['订单明细ID', '证据类型', '单据ID', '事件ID', '操作', '业务日期', '操作人／原始ID', '时间', '依据',
            '业务日期范围', '冻结时记录状态', '关联原单ID', '更正原单ID', '更正后单ID', '同单前次生效事件ID', '同单后次生效事件ID'], references),
        sheet('跨月核对事项', ['订单明细ID', '原实发ID', '事项', '说明'],
            [[r.get('line_id'), r.get('issue_id'), r['code'], r['message']] for r in snapshot.get('notices', [])])]


def settlement_sheets(snapshot):
    rows = []
    for row in snapshot['rows']:
        price = row['price']; context = row['context']
        rows.append(order_values(row.get('order', {})) + [row['line_id'], row['task_id'], context.get('task_name'),
            row['acceptance_id'], row['acceptance_event_id'], row['day'], row['sets'], price['unit_price'],
            price['currency'], row['amount'], row['prior_priced_sets'], price['id'], price['evidence'], row['acceptance_evidence']])
    return [sheet('结算汇总', ['加工厂', '结算月份', '统计截止日期', '验收结算套数', '币种', '含税应付金额', '外厂确认凭据'],
        [[snapshot['resource_name'], snapshot['month'], snapshot['cutoff'], snapshot['sets'], snapshot['currency'],
          snapshot['total'], snapshot['vendor_evidence']]]),
        sheet('验收计费明细', ['客户', '订单号', '货号', '货名', '订单明细ID', '任务ID', '任务', '验收单ID', '验收事件ID',
            '验收日期', '本次结算套数', '含税单价', '币种', '冻结金额', '此前同价已结套数', '报价版本ID', '报价凭据', '验收凭据'], rows)]


def payment_sheets(value, events):
    current = payments.latest(events)
    documents = [e for e in current.values() if e.data['snapshot']['day'][:7] == value['month']]
    registrations, allocations = [], []
    for event in documents:
        s = event.data['snapshot']; status = STATES[payments.state(event)]
        registrations.append([event.document_id, event.id, s['day'], s['voucher_no'], s['resource_name'], status,
            s['currency'], s['amount'], {'bank': '银行转账', 'cash': '现金', 'cheque': '支票', 'other': '其他'}[s['method']],
            s['evidence'], s.get('replaces_document_id') or '', event.actor_name, event.created_at])
        for row in s['allocations']:
            allocations.append([event.document_id, event.id, s['day'], s['voucher_no'], status,
                row['settlement_id'], row['settlement_event_id'], row['currency'], row['amount']])
    headers = ['有效应付', '已付核销', '未付余额', '待复核占用', '可继续核销']
    keys = ('payable', 'paid', 'unpaid', 'pending', 'available')
    return [sheet('当前全期余额汇总', ['币种'] + headers,
                  [[r['currency']] + [r[k] for k in keys] for r in value['totals']]),
        sheet('当前全期结算余额', ['结算单ID', '冻结结算版本ID', '结算月份', '加工厂', '币种'] + headers,
            [[r['settlement_id'], r['settlement_event_id'], r['month'], r['resource_name'], r['currency']] + [r[k] for k in keys] for r in value['rows']]),
        sheet('所选月付款登记', ['付款单ID', '当前事件ID', '付款日期', '凭证号', '加工厂', '状态', '币种', '登记金额',
            '付款方式', '付款凭据', '关联原冲销单', '当前操作人', '操作时间'], registrations),
        sheet('所选月核销明细', ['付款单ID', '付款事件ID', '付款日期', '凭证号', '当前状态', '结算单ID', '原冻结结算版本ID', '币种', '分配金额'], allocations)]


def frozen_scope(db, selection):
    is_period = selection.kind == 'period'
    if is_period:
        periods.guards.ensure_schema(db)
        periods.preview.period(selection.month, periods.wh.business_now().date())
        model, state = periods.Event, periods.state
        scope = [model.factory_id == c.FACTORY, model.month == selection.month]
    else:
        c.require(fees.schema_ready(db.connection()), '外发结算需先完成0165显式迁移及证据保护', 503)
        model, state = fees.Event, fees.state
        scope = [model.factory_id == c.FACTORY, model.document_id == selection.document_id, model.action != 'price']
    return model, state, scope


def frozen_source(db, selection):
    """One immutable payload and complete trace; caller holds the factory lock."""
    is_period = selection.kind == 'period'
    model, state, scope = frozen_scope(db, selection)
    trace = [dict(row) for row in db.execute(select(model.id, model.version, model.action,
        model.actor_name.label('actor'), model.actor_id, model.created_at.label('date'), model.reason)
        .where(*scope).order_by(model.version)).mappings()]
    selected = next((row for row in trace if row['id'] == selection.event_id), None)
    c.require(selected is not None, '月结历史版本不存在' if is_period else '结算版本不存在', 404)
    data = db.scalar(select(model.data).where(*scope, model.id == selection.event_id))
    c.require(is_period or data['snapshot']['month'] == selection.month, '结算单不属于所选月份', 404)
    return dict(data=data, history=trace, selected_state=state(SimpleNamespace(action=selected['action'])),
                state=state(SimpleNamespace(action=trace[-1]['action'])))


def source_revision(db, selection):
    """Final lightweight fence, under lock, against the captured immutable source.

    Protected append-only ledgers make the latest scoped event sufficient; live
    payments additionally depend on the full settlement revision. No report
    formatting or workbook sizing occurs between this check and lock release.
    """
    lock_transaction(db, 'cutting-master', c.FACTORY)
    if selection.kind == 'payments':
        c.require(payments.schema_ready(db.connection()) and fees.schema_ready(db.connection()),
                  '付款或结算证据保护不完整，不能导出', 503)
        return (db.scalar(select(func.max(payments.Event.version)).where(payments.Event.factory_id == c.FACTORY)) or 0,
                db.scalar(select(func.max(fees.Event.version)).where(fees.Event.factory_id == c.FACTORY)) or 0)
    model, _, scope = frozen_scope(db, selection)
    return db.scalar(select(model.id).where(*scope).order_by(model.version.desc()).limit(1))


def capture(db, selection, *, release_transaction=False, with_revision=False):
    """Capture under lock; HTTP callers release before formatting/sizing tables."""
    lock_transaction(db, 'cutting-master', c.FACTORY)
    if selection.kind == 'payments':
        value = payments.read(db, selection.month)
        c.require(selection.month <= business_now().strftime('%Y-%m'), '不能导出未来月份', 422)
        # Materialize plain fields now: no ORM lazy loads after rollback.
        events = [SimpleNamespace(document_id=e.document_id, id=e.id, action=e.action, data=e.data,
                  actor_name=e.actor_name, created_at=e.created_at) for e in payments.history(db)]
        settlement_revision = db.scalar(select(func.max(fees.Event.version)).where(fees.Event.factory_id == c.FACTORY)) or 0
        revision = (value['revision'], settlement_revision)
    else:
        value = frozen_source(db, selection)
        revision = value['history'][-1]['id']
    if release_transaction:
        db.rollback()
    meta = [['报表', TITLES[selection.kind]], ['厂区／部门', '华康 C／裁床部'], ['所选月份', selection.month]]
    if selection.kind == 'payments':
        data = payment_sheets(value, events)
        meta += [['口径', '所选月付款登记＋当前全部期间有效结算余额；不是历史月末余额或锁月快照'],
                 ['金额规则', '草稿、退回、冲销不计已付；待复核仅占用；已生效才计核销。各币种分别汇总'],
                 ['付款版本', value['revision']], ['结算版本', settlement_revision]]
    else:
        expected = 'locked' if selection.kind == 'period' else 'confirmed'
        c.require(value['selected_state'] == expected, '正式冻结导出只接受已锁月／已确认版本；草稿及待复核不能冒充正式报表')
        selected = next(e for e in value['history'] if e['id'] == selection.event_id)
        active = value['history'][-1]['id'] == selection.event_id
        meta += [['使用状态', '当前有效冻结版本' if active else '历史失效冻结版本，仅供追溯，不计当前有效金额'],
                 ['所选事件ID', selection.event_id], ['版本', selected['version']], ['冻结操作人', selected['actor']],
                 ['冻结时间', selected['date']], ['冻结依据', selected['reason']],
                 ['当前状态', STATES[value['state']]], ['当前事件ID', value['history'][-1]['id']],
                 ['编制人ID', value['data'].get('prepared_by', '')],
                 ['提交人ID', value['data'].get('submitted_by')],
                 ['本地管理员验收', '是，不代表正式双人验收' if value['data'].get('local_admin_acceptance') else '否'],
                 ['快照校验值', periods.digest(value['data']['snapshot'])]]
        if selection.kind == 'period':
            meta += [['口径', '整月全部订单的锁月快照；不受页面明细筛选影响；单价及完工在制归属均来自冻结版本'],
                     ['统计截止日期', value['data']['snapshot']['end']],
                     ['上期月份', value['data']['snapshot'].get('previous_month') or '首次月结'],
                     ['上期冻结事件ID', value['data']['snapshot'].get('previous_lock_id') or '首次月结，无上期冻结事件']]
            data = period_sheets(value['data']['snapshot'])
            data.append(sheet('月结确认事项', ['确认项', '本版记录'], [[label, '是' if value['data']['input'][key] else '否'] for key,label in
                [('materials_complete','物料核对完整'),('public_material_pending','公共耗料待分配'),('opening_verified','期初已核对'),
                 ('unrecorded_opening','存在未录入期初'),('exceptions_reviewed','跨月事项已复核')]]))
        else:
            meta += [['口径', '选定外发结算单的冻结数量、含税单价及金额；不按当前报价重算，不包含付款余额']]
            confirmation = value['data'].get('vendor_confirmation') or {}
            meta += [['外厂确认登记人', confirmation.get('actor')], ['外厂确认登记时间', confirmation.get('date')]]
            data = settlement_sheets(value['data']['snapshot'])
        data.append(sheet('版本操作记录', ['事件ID', '版本', '操作', '操作人', '时间', '原因'],
            [[e['id'], e['version'], ACTIONS.get(e['action'], e['action']), e['actor'], e['date'], e['reason']] for e in value['history'] if e['version'] <= selected['version']]))
        later = [e for e in value['history'] if e['version'] > selected['version']]
        data.append(sheet('后续失效与重结追溯', ['事件ID', '版本', '操作', '操作人', '时间', '原因'],
            [[e['id'], e['version'], ACTIONS.get(e['action'], e['action']), e['actor'], e['date'], e['reason']] for e in later]))
        current = value['history'][-1]
        meta += [['当前有效冻结事件ID', current['id'] if value['state'] == expected else '当前无有效冻结版本'],
                 ['追溯说明', '后续失效与重结追溯为本次查询状态；原版数量、价格和金额不重算']]
        if selection.kind == 'period':
            meta += [['来源索引说明', '范围按各事件业务日期区分；历史、草稿和操作记录仅供追溯，不可将来源索引逐行累加。生产操作人无冻结姓名时保留原始ID。']]
    meta += [['精度说明', '金额及小数数量以精确文本保存，不使用Excel公式或跨币种合计；未知值显示待核对'],
             ['模板版本', 'cutting-p4e-v2']]
    result = deepcopy(dict(kind=selection.kind, month=selection.month, metadata=meta, sheets=data))
    result['delivery'] = workbook_export.delivery(result)
    return (result, revision) if with_revision else result


def render(report, user):
    return workbook_export.render_workbook(report, user, TITLES[report['kind']])


def package(report, user):
    return workbook_export.package(report, user, render)


def package_isolated(report, user):
    from app.services.cutting_export_process import package as isolated
    return isolated(report, user, TITLES[report['kind']])
