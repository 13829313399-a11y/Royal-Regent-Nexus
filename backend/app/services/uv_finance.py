"""Transactional UV inventory and financial extensions. No implicit currency/rate defaults."""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from app.models import uv_finance as m

D = Decimal
CURRENCY_PLACES = {'CNY': 2, 'HKD': 2, 'USD': 2, 'JPY': 0, 'EUR': 2, 'GBP': 2}
CATEGORIES = {'equipment', 'tooling', 'material', 'sundry', 'maintenance', 'processing', 'rent',
              'utilities', 'management_wage', 'night_subsidy', 'recoverable_wage', 'recoverable_paint'}


def fail(message, field=None, status=422):
    raise HTTPException(status, {'code': 'uv_finance_invalid' if status == 422 else 'uv_finance_conflict',
                                'message': message, 'fields': {field: message} if field else {}, 'retryable': False})


def decimal(value, field, *, positive=False, signed=False, scale=6):
    try:
        if isinstance(value, (bool, float)) or value is None:
            raise ValueError()
        n = D(str(value))
        if not n.is_finite() or abs(n) >= D('1e14') or n.as_tuple().exponent < -scale:
            raise ValueError()
        if (positive and n <= 0) or (not signed and n < 0):
            raise ValueError()
        return n
    except (InvalidOperation, ValueError):
        fail('请输入精度和范围内的十进制数值', field)


def currency(value):
    if value not in CURRENCY_PLACES:
        fail('请明确币种；当前支持 CNY、HKD、USD、JPY、EUR、GBP', 'currency')
    return value


def rounded(n, code):
    return D(n).quantize(D(1).scaleb(-CURRENCY_PLACES[currency(code)]), rounding=ROUND_HALF_UP)


def money(n, code):
    return {'currency': code, 'amount': format(rounded(n, code), 'f')}


def day(value, field='occurred_on'):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        fail('请填写 YYYY-MM-DD 日期', field)


def month(value):
    if not isinstance(value, str) or len(value) != 7:
        fail('请填写 YYYY-MM 月份', 'month')
    day(value + '-01', 'month')
    return value


def text(value, field, required=False, limit=2000):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        fail('字段缺失或过长', field)
    return value.strip()


def fields(payload, allowed):
    unexpected = set(payload) - set(allowed) - {'factory_id', 'operation_id', 'expected_version'}
    if unexpected:
        fail('不支持的字段：' + ', '.join(sorted(unexpected)), sorted(unexpected)[0])


def base(factory, actor, **values):
    return dict(id=uuid4().hex, factory_id=factory, created_by=actor, **values)


def find(db, cls, factory, ident):
    row = db.scalar(select(cls).where(cls.factory_id == factory, cls.id == ident).execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, '对象不存在或不在当前厂区')
    return row


def check_version(row, p):
    if isinstance(p.get('expected_version'), bool) or p.get('expected_version') != row.version:
        fail('数据版本已变化，请刷新后重试', 'expected_version', 409)


def serial(row):
    return {c.name: (format(getattr(row, c.name), 'f') if isinstance(getattr(row, c.name), D) else getattr(row, c.name))
            for c in row.__table__.columns if c.name != 'created_by'}


def ensure_open(db, factory, business_date):
    business_date = day(business_date, 'business_date')
    closed = db.scalar(select(m.UvPeriod.id).where(m.UvPeriod.factory_id == factory, m.UvPeriod.status == 'closed',
                         m.UvPeriod.period.in_([business_date, business_date[:7]])))
    if closed:
        fail('期间已关闭，需在后续开放期间记录调整，不能改写原账', 'business_date', 409)


def ensure_report_mutable(db, factory, report_id):
    for batch in db.scalars(select(m.UvPayrollBatch).where(m.UvPayrollBatch.factory_id == factory,
                                                          m.UvPayrollBatch.status == 'confirmed')):
        if any(v['id'] == report_id for v in batch.source_versions):
            fail('报工已进入确认工资，请使用后续开放期间的工资调整', 'report_id', 409)


def validate_machine(db, factory, machine_id):
    if machine_id:
        from app.models.uv_printing import UvMachine
        find(db, UvMachine, factory, machine_id)


def sku_output(sku, cost=True):
    result = serial(sku)
    result.pop('stock_value', None)
    result.pop('available_ml', None)
    if cost:
        result['unit_cost'] = (format(sku.stock_value / sku.available_ml, '.8f')
                               if sku.stock_value is not None and sku.available_ml else None)
    else:
        result.pop('currency', None)
    return result


def balance_output(sku):
    return dict(sku_id=sku.id, available_ml=format(sku.available_ml, 'f'), package_ml=format(sku.package_ml, 'f'),
                bottle_equivalent=format(sku.available_ml / sku.package_ml, '.6f'), threshold_ml=format(sku.threshold_ml, 'f'),
                low_stock=sku.available_ml < sku.threshold_ml, cost_pending=sku.stock_value is None)


def movement_output(db, row, cost=True):
    result = serial(row)
    sku = find(db, m.UvInkSku, row.factory_id, row.sku_id)
    result.update(sku_label=f'{sku.supplier} · {sku.material} · {sku.color}', created_by_name=row.created_by,
                  cost_pending=row.cost_value is None)
    result.pop('cost_value', None)
    result.pop('currency', None)
    if cost:
        result['amount'] = money(abs(row.cost_value), row.currency) if row.cost_value is not None else None
    else:
        result.pop('unit_cost', None)
    return result


def create_sku(db, factory, actor, p):
    fields(p, {'supplier', 'material', 'color', 'color_aliases', 'package_ml', 'location', 'threshold_ml'})
    if p.get('material') not in {'hard', 'soft', 'other'}:
        fail('请选择软/硬/其他材质', 'material')
    aliases = p.get('color_aliases', [])
    if not isinstance(aliases, list) or len(aliases) > 50 or any(not isinstance(v, str) for v in aliases):
        fail('颜色别名应为字符串数组', 'color_aliases')
    row = m.UvInkSku(**base(factory, actor, supplier=text(p.get('supplier'), 'supplier', True, 128),
          material=p['material'], color=text(p.get('color'), 'color', True, 64), color_aliases=aliases,
          package_ml=decimal(p.get('package_ml'), 'package_ml', positive=True),
          threshold_ml=decimal(p.get('threshold_ml', '0'), 'threshold_ml'),
          location=text(p.get('location', 'UV仓'), 'location', True, 128)))
    db.add(row)
    db.flush()
    return sku_output(row)


def create_movement(db, factory, actor, p):
    fields(p, {'sku_id', 'kind', 'quantity_ml', 'bottle_input', 'occurred_on', 'posted_on', 'machine_id', 'purpose',
               'source_doc', 'created_by_name', 'unit_cost', 'currency', 'evidence', 'direction', 'source_movement_id'})
    kind = p.get('kind')
    if kind not in {'opening', 'purchase_in', 'issue_out', 'return_in', 'stocktake'}:
        fail('不支持的墨水流水类型', 'kind')
    sku = find(db, m.UvInkSku, factory, p.get('sku_id'))
    if not sku.is_active:
        fail('SKU已停用', 'sku_id')
    occurred = day(p.get('occurred_on'))
    posted = day(p.get('posted_on', occurred), 'posted_on')
    ensure_open(db, factory, occurred)
    ensure_open(db, factory, posted)
    # Backdated moving-average mutations would silently reprice downstream issues.
    latest = db.scalar(select(m.UvInkMovement.posted_on).where(m.UvInkMovement.factory_id == factory,
                      m.UvInkMovement.sku_id == sku.id).order_by(m.UvInkMovement.posted_on.desc()).limit(1))
    if latest and posted < latest:
        fail('已有后续库存流水，请按当前归属日记录调整并保留原发生日', 'posted_on', 409)
    qty = decimal(p.get('quantity_ml'), 'quantity_ml', positive=True)
    bottles = None if p.get('bottle_input') is None else decimal(p['bottle_input'], 'bottle_input', positive=True)
    if bottles is not None and bottles * sku.package_ml != qty:
        fail('瓶数与SKU包装容量换算后的ml不一致', 'quantity_ml')
    validate_machine(db, factory, p.get('machine_id'))
    evidence = text(p.get('evidence', ''), 'evidence')
    purpose = text(p.get('purpose', ''), 'purpose', True)
    if kind == 'stocktake' and (p.get('direction') not in {'in', 'out'} or not evidence):
        fail('盘点须明确增减方向和盘点凭证', 'direction')
    direction = -1 if kind == 'issue_out' or (kind == 'stocktake' and p['direction'] == 'out') else 1
    if kind == 'opening' and db.scalar(select(m.UvInkMovement.id).where(m.UvInkMovement.sku_id == sku.id).limit(1)):
        fail('期初只能建立一次；请使用有证据的盘点调整', 'kind', 409)
    if direction < 0 and sku.available_ml < qty:
        fail('当前SKU库存不足，其他供应商/材质库存不可抵用', 'quantity_ml', 409)
    if direction < 0:
        unit = sku.stock_value / sku.available_ml if sku.stock_value is not None and sku.available_ml else None
        code = sku.currency
    else:
        unit = None if p.get('unit_cost') is None else decimal(p['unit_cost'], 'unit_cost')
        code = currency(p.get('currency')) if unit is not None else None
        if kind == 'return_in':
            original = find(db, m.UvInkMovement, factory, p.get('source_movement_id'))
            if original.sku_id != sku.id or original.kind != 'issue_out' or original.reversed_by_id:
                fail('退回必须引用当前SKU未冲销的领用单', 'source_movement_id')
            returned = sum((r.quantity_ml for r in db.scalars(select(m.UvInkMovement).where(
                m.UvInkMovement.source_movement_id == original.id, m.UvInkMovement.kind == 'return_in',
                m.UvInkMovement.reversed_by_id.is_(None)))), D(0))
            if returned + qty > original.quantity_ml:
                fail('累计退回量超过原领用量', 'quantity_ml', 409)
            unit, code = original.unit_cost, original.currency
        if sku.available_ml and sku.currency and code and code != sku.currency:
            fail('同一SKU现有库存币种不同，不能混币移动平均', 'currency')
    value = (qty * unit).quantize(D('.00000001'), rounding=ROUND_HALF_UP) if unit is not None else None
    prior_qty = sku.available_ml
    sku.available_ml += direction * qty
    if prior_qty == 0 and direction > 0:
        sku.stock_value = value
        sku.currency = code
    elif sku.stock_value is not None and value is not None:
        sku.stock_value += direction * value
    else:
        sku.stock_value = None
    if sku.available_ml == 0:
        sku.stock_value = D(0)
    sku.version += 1
    sku.updated_at = m.now()
    row = m.UvInkMovement(**base(factory, actor, sku_id=sku.id, kind=kind, occurred_on=occurred, posted_on=posted,
          quantity_ml=qty, signed_ml=direction * qty, bottle_input=bottles, unit_cost=unit,
          cost_value=None if value is None else direction * value, currency=code, machine_id=p.get('machine_id'),
          purpose=purpose, source_doc=text(p.get('source_doc', ''), 'source_doc', limit=255), evidence=evidence,
          source_movement_id=p.get('source_movement_id') if kind == 'return_in' else None,
          balance_after_ml=sku.available_ml))
    db.add(row)
    db.flush()
    return movement_output(db, row)


def reverse_movement(db, factory, actor, p):
    fields(p, {'target_id', 'reason'})
    row = find(db, m.UvInkMovement, factory, p.get('target_id'))
    check_version(row, p)
    ensure_open(db, factory, row.posted_on)
    reason = text(p.get('reason'), 'reason', True)
    if row.reversed_by_id or row.kind == 'reversal':
        fail('流水已冲销或属于冲销记录', 'target_id', 409)
    if db.scalar(select(m.UvInkMovement.id).where(m.UvInkMovement.source_movement_id == row.id,
                  m.UvInkMovement.reversed_by_id.is_(None)).limit(1)):
        fail('原领用已有退回，请先核对冲销退回流水', 'target_id', 409)
    sku = find(db, m.UvInkSku, factory, row.sku_id)
    if sku.available_ml and sku.currency and row.currency and sku.currency != row.currency:
        fail('当前SKU库存币种与原流水不同，不能跨币种冲销混账', 'target_id', 409)
    if row.signed_ml > 0:
        later = db.scalar(select(m.UvInkMovement.id).where(m.UvInkMovement.sku_id == sku.id,
                        m.UvInkMovement.created_at > row.created_at, m.UvInkMovement.kind != 'reversal',
                        m.UvInkMovement.reversed_by_id.is_(None)).limit(1))
        if later:
            fail('该入库已有后续流水，须先按相反顺序核对冲销，不能改写历史出库成本', 'target_id', 409)
    if sku.available_ml - row.signed_ml < 0:
        fail('冲销将导致负库存，请先核对后续流水', 'target_id', 409)
    if sku.available_ml == 0 and row.signed_ml < 0:
        sku.currency = row.currency
    sku.available_ml -= row.signed_ml
    sku.stock_value = (sku.stock_value - row.cost_value
                       if sku.stock_value is not None and row.cost_value is not None else None)
    if sku.available_ml == 0:
        sku.stock_value = D(0)
    sku.version += 1
    sku.updated_at = m.now()
    reversal = m.UvInkMovement(**base(factory, actor, sku_id=sku.id, kind='reversal', occurred_on=row.occurred_on,
                 posted_on=row.posted_on, quantity_ml=row.quantity_ml, signed_ml=-row.signed_ml, unit_cost=row.unit_cost,
                 cost_value=None if row.cost_value is None else -row.cost_value, currency=row.currency,
                 purpose=reason, source_doc=row.source_doc, evidence=row.evidence, machine_id=row.machine_id,
                 reverses_movement_id=row.id, balance_after_ml=sku.available_ml))
    row.reversed_by_id = reversal.id
    row.version += 1
    row.updated_at = m.now()
    db.add(reversal)
    db.flush()
    return movement_output(db, reversal)


def expense_output(row):
    result = serial(row)
    result['amount'] = money(row.amount, row.currency)
    result.pop('currency', None)
    return result


def create_expense(db, factory, actor, p):
    fields(p, {'category', 'occurred_on', 'period', 'currency', 'amount', 'machine_id', 'evidence', 'note'})
    if p.get('category') not in CATEGORIES:
        fail('请选择支持的费用类别；油墨成本由领用账本生成，禁止重复录入', 'category')
    occurred = day(p.get('occurred_on'))
    period = month(p.get('period'))
    if period != occurred[:7]:
        fail('费用发生月与归属月不一致，须通过明确期间调整处理', 'period')
    ensure_open(db, factory, occurred)
    policy = latest_policy(db, factory, period)
    if p['category'] in {'rent', 'utilities', 'management_wage'} and policy and getattr(policy, p['category']) is not None:
        fail('该类别已通过月参数分摊，不能重复计入费用', 'category', 409)
    validate_machine(db, factory, p.get('machine_id'))
    evidence = text(p.get('evidence'), 'evidence', True)
    existing = db.scalar(select(m.UvExpense.id).where(m.UvExpense.factory_id == factory,
                         m.UvExpense.evidence == evidence, m.UvExpense.category == p['category'],
                         m.UvExpense.reverses_expense_id.is_(None)))
    if existing:
        fail('该费用凭证已入账，请查阅原单或冲销，不能重复扣款', 'evidence', 409)
    code = currency(p.get('currency'))
    row = m.UvExpense(**base(factory, actor, category=p['category'], occurred_on=occurred, period=period,
          amount=rounded(decimal(p.get('amount'), 'amount'), code), currency=code, machine_id=p.get('machine_id'),
          evidence=evidence, note=text(p.get('note', ''), 'note')))
    db.add(row)
    db.flush()
    return expense_output(row)


def reverse_expense(db, factory, actor, p):
    fields(p, {'target_id', 'reason'})
    row = find(db, m.UvExpense, factory, p.get('target_id'))
    check_version(row, p)
    ensure_open(db, factory, row.occurred_on)
    if row.reverses_expense_id or db.scalar(select(m.UvExpense.id).where(m.UvExpense.reverses_expense_id == row.id)):
        fail('费用已冲销或属于冲销记录', 'target_id', 409)
    reversal = m.UvExpense(**base(factory, actor, category=row.category, occurred_on=row.occurred_on, period=row.period,
                    amount=-row.amount, currency=row.currency, machine_id=row.machine_id, evidence=row.evidence,
                    note=text(p.get('reason'), 'reason', True), reverses_expense_id=row.id))
    db.add(reversal)
    row.version += 1
    row.updated_at = m.now()
    db.flush()
    return expense_output(reversal)


def latest_policy(db, factory, period):
    return db.scalar(select(m.UvMonthlyPolicy).where(m.UvMonthlyPolicy.factory_id == factory,
                   m.UvMonthlyPolicy.month == period).order_by(m.UvMonthlyPolicy.version.desc()).limit(1))


def save_policy(db, factory, actor, p):
    fields(p, {'month', 'working_days', 'allocation_method', 'rent', 'utilities', 'management_wage', 'note'})
    period = month(p.get('month'))
    old = latest_policy(db, factory, period)
    if old:
        check_version(old, p)
    elif p.get('expected_version') not in (None, 0):
        fail('新分摊版本应为0', 'expected_version', 409)
    all_days = [f'{period}-{i:02d}' for i in range(1, calendar.monthrange(int(period[:4]), int(period[5:]))[1] + 1)]
    for value in all_days:
        ensure_open(db, factory, value)
    method = p.get('allocation_method')
    if method not in {'working_days', 'calendar_days'}:
        fail('不支持的分摊方法', 'allocation_method')
    days = p.get('working_days')
    if not isinstance(days, list) or any(not isinstance(v, str) for v in days) or len(days) != len(set(days)) or any(v not in all_days for v in days):
        fail('工作日必须为本月不重复日期', 'working_days')
    days = all_days if method == 'calendar_days' else sorted(days)
    if not days:
        fail('请明确至少一个分摊日', 'working_days')
    values = {}
    for key in ('rent', 'utilities', 'management_wage'):
        value = p.get(key)
        if value is not None and not isinstance(value, dict):
            fail('金额应包含明确币种和十进制字符串amount', key)
        if value is not None:
            entries = list(db.scalars(select(m.UvExpense).where(m.UvExpense.factory_id == factory,
                                m.UvExpense.period == period, m.UvExpense.category == key)))
            reversed_ids = {entry.reverses_expense_id for entry in entries if entry.reverses_expense_id}
            if any(not entry.reverses_expense_id and entry.id not in reversed_ids for entry in entries):
                fail('该月已有同类手工费用，请先核对冲销，不能重复分摊', key, 409)
        values[key] = None if value is None else money(decimal(value.get('amount'), key), currency(value.get('currency')))
    row = m.UvMonthlyPolicy(**base(factory, actor, version=old.version + 1 if old else 1, month=period,
          working_days=days, allocation_method=method, note=text(p.get('note', ''), 'note'), **values))
    db.add(row)
    db.flush()
    for key, value in values.items():
        if value is None:
            continue
        code = value['currency']
        factor = 10 ** CURRENCY_PLACES[code]
        units = int(D(value['amount']) * factor)
        quotient, remainder = divmod(units, len(days))
        for index, value_day in enumerate(days):
            db.add(m.UvPolicyAllocation(**base(factory, actor, policy_id=row.id, business_date=value_day,
                   category=key, currency=code, amount=D(quotient + (index < remainder)) / factor)))
    db.flush()
    return serial(row)


def day_costs(db, factory, business_date, machine_id=None):
    ink = select(m.UvInkMovement).where(m.UvInkMovement.factory_id == factory, m.UvInkMovement.posted_on == business_date)
    expenses = select(m.UvExpense).where(m.UvExpense.factory_id == factory, m.UvExpense.occurred_on == business_date)
    if machine_id:
        ink = ink.where(m.UvInkMovement.machine_id == machine_id)
        expenses = expenses.where(m.UvExpense.machine_id == machine_id)
    totals, reasons = {}, []
    ink_seen = expense_seen = False
    ink_missing = False
    def add(code, key, amount):
        totals.setdefault(code, {'ink_cost': D(0), 'expense_amount': D(0)})[key] += amount
    for row in db.scalars(ink):
        original = find(db, m.UvInkMovement, factory, row.reverses_movement_id) if row.kind == 'reversal' else row
        if original.kind not in {'issue_out', 'return_in'}:
            continue
        ink_seen = True
        if row.cost_value is None:
            ink_missing = True
        else:
            add(row.currency, 'ink_cost', -row.cost_value)
    for row in db.scalars(expenses):
        expense_seen = True
        add(row.currency, 'expense_amount', -row.amount if row.category.startswith('recoverable_') else row.amount)
    policy = latest_policy(db, factory, business_date[:7])
    if policy and not machine_id:
        for row in db.scalars(select(m.UvPolicyAllocation).where(m.UvPolicyAllocation.policy_id == policy.id,
                                                                m.UvPolicyAllocation.business_date == business_date)):
            expense_seen = True
            add(row.currency, 'expense_amount', row.amount)
        if any(getattr(policy, key) is None for key in ('rent', 'utilities', 'management_wage')):
            reasons.append('月固定费用有未填写项')
    else:
        reasons.append('尚未配置月分摊；机台筛选不分摊未归属机台的公共费用')
    if not ink_seen or ink_missing:
        reasons.append('油墨领用成本缺失或待核')
    if not expense_seen:
        reasons.append('费用尚未填写，不能当作零成本')
    if len(totals) > 1:
        reasons.append('含多币种，未配置换算，不合并金额')
    only = next(iter(totals), None) if len(totals) == 1 else None
    return {'ink_cost': money(totals[only]['ink_cost'], only) if only and ink_seen and not ink_missing else None,
            'expense_amount': money(totals[only]['expense_amount'], only) if only and expense_seen else None,
            'provisional_reasons': reasons,
            'by_currency': {code: {key: money(value, code) for key, value in values.items()} for code, values in totals.items()}}


def cost_dates(db, factory, scope):
    dates = set()
    for cls, column in ((m.UvInkMovement, m.UvInkMovement.posted_on), (m.UvExpense, m.UvExpense.occurred_on)):
        query = select(column).where(cls.factory_id == factory)
        if cls is m.UvInkMovement:
            operating_ids = select(m.UvInkMovement.id).where(m.UvInkMovement.factory_id == factory,
                             m.UvInkMovement.kind.in_(['issue_out', 'return_in']))
            query = query.where((m.UvInkMovement.kind.in_(['issue_out', 'return_in'])) |
                               m.UvInkMovement.reverses_movement_id.in_(operating_ids))
        if scope.get('machine_id'):
            query = query.where(cls.machine_id == scope['machine_id'])
        dates.update(db.scalars(query))
    if not scope.get('machine_id'):
        dates.update(db.scalars(select(m.UvPayrollBatch.date_from).where(m.UvPayrollBatch.factory_id == factory,
                     m.UvPayrollBatch.status == 'confirmed', m.UvPayrollBatch.adjustment_of.is_not(None))))
        policies = list(db.scalars(select(m.UvMonthlyPolicy).where(m.UvMonthlyPolicy.factory_id == factory)))
        latest = {}
        for policy in policies:
            if policy.month not in latest or policy.version > latest[policy.month].version:
                latest[policy.month] = policy
        for policy in latest.values():
            dates.update(policy.working_days)
    return sorted(d for d in dates if (not scope.get('business_date') or d == scope['business_date'])
                  and (not scope.get('date_from') or d >= scope['date_from']) and (not scope.get('date_to') or d <= scope['date_to']))


def summary_counts(db, factory, scope):
    rows = list(db.scalars(select(m.UvInkSku).where(m.UvInkSku.factory_id == factory, m.UvInkSku.is_active.is_(True))))
    return {'low_stock_skus': sum(r.available_ml < r.threshold_ml for r in rows)}


def payroll_adjustments(db, factory, scope):
    # Adjustments belong to workers and a posting date, never silently to a machine/product.
    if scope.get('machine_id') or scope.get('product_id') or scope.get('shift'):
        return []
    query = select(m.UvPayrollBatch).where(m.UvPayrollBatch.factory_id == factory,
                 m.UvPayrollBatch.status == 'confirmed', m.UvPayrollBatch.adjustment_of.is_not(None))
    result = []
    for batch in db.scalars(query):
        posted = batch.date_from
        if (scope.get('business_date') and scope['business_date'] != posted
            or scope.get('date_from') and posted < scope['date_from'] or scope.get('date_to') and posted > scope['date_to']):
            continue
        for line in db.scalars(select(m.UvPayrollBatchLine).where(m.UvPayrollBatchLine.batch_id == batch.id)):
            result.append(dict(worker_id=line.worker_id, worker_name=line.worker_name, currency=line.currency,
                amount=format(line.amount, 'f'), business_date=posted, batch_id=batch.id, reason=batch.reason))
    return result


def pricing(p):
    fields(p, {'currency', 'daily_hours', 'board_hours', 'pieces_per_board', 'labor_cost_per_day', 'ink_cost_per_day',
               'markup_rate', 'target_margin_rate', 'loss_rate'})
    code = currency(p.get('currency'))
    keys = ('daily_hours', 'board_hours', 'pieces_per_board', 'labor_cost_per_day', 'ink_cost_per_day', 'markup_rate', 'target_margin_rate')
    values = {key: decimal(p.get(key), key) for key in keys}
    loss = D(0) if p.get('loss_rate') is None else decimal(p['loss_rate'], 'loss_rate')
    if loss >= 1:
        fail('损耗率须小于100%', 'loss_rate')
    boards = values['daily_hours'] / values['board_hours'] if values['board_hours'] else None
    pieces = boards * values['pieces_per_board'] if boards is not None else None
    cost = ((values['labor_cost_per_day'] + values['ink_cost_per_day']) / pieces / (1 - loss)) if pieces else None
    markup = cost * (1 + values['markup_rate']) if cost is not None else None
    target = cost / (1 - values['target_margin_rate']) if cost is not None and values['target_margin_rate'] < 1 else None
    as_string = lambda value: format(value.quantize(D('.000001'), rounding=ROUND_HALF_UP), 'f') if value is not None else None
    result = dict(input={key: value for key, value in p.items() if key not in {'factory_id', 'operation_id', 'expected_version'}},
            boards_per_day=as_string(boards), full_boards_per_day=int(boards) if boards is not None else None,
            pieces_per_day=as_string(pieces), direct_unit_cost=as_string(cost), markup_price=as_string(markup),
            markup_implied_margin=as_string(values['markup_rate'] / (1 + values['markup_rate'])),
            target_margin_price=as_string(target), currency=code, formula_version='uv-pricing-v1',
            not_computable_reason='每板耗时或日产能为0，无法计算' if cost is None else None,
            cost_scope='含人工、油墨与已填损耗' if loss else '仅含已填写的人工和油墨', warnings=[])
    result['steps'] = [dict(key=key, label=label, formula=formula, value=result[key], unit=unit) for key, label, formula, unit in (
            ('boards_per_day', '理论每日板数', '每日可用工时 ÷ 每板耗时', '板/天'),
            ('pieces_per_day', '理论日产能', '理论每日板数 × 每板件数', '件/天'),
            ('direct_unit_cost', '直接单位成本', '日直接成本 ÷ 理论日产能 ÷ (1 - 损耗率)', code + '/件'),
            ('markup_price', '成本加成报价', '单位成本 × (1 + 加成率)', code + '/件'),
            ('target_margin_price', '目标毛利报价', '单位成本 ÷ (1 - 目标毛利率)', code + '/件'))]
    if values['target_margin_rate'] >= 1:
        result['warnings'].append({'code': 'margin_not_usable', 'message': '目标毛利率须小于100%', 'tone': 'warning'})
    return result


def save_quote(db, factory, actor, p):
    fields(p, {'id', 'label', 'product_id', 'input', 'note'})
    from app.models.uv_printing import UvProduct
    if p.get('product_id'):
        find(db, UvProduct, factory, p['product_id'])
    if p.get('id'):
        fail('测算版本不可覆盖，请另存新测算', 'id', 409)
    result = pricing(p.get('input', {}))
    row = m.UvPricingQuote(**base(factory, actor, label=text(p.get('label'), 'label', True, 128),
          product_id=p.get('product_id'), input=result['input'], result=result, note=text(p.get('note', ''), 'note')))
    db.add(row)
    db.flush()
    output = serial(row)
    output['created_by_name'] = actor
    return output


def adopt_quote(db, factory, actor, p):
    fields(p, {'quote_id', 'rate_kind', 'effective_from'})
    from app.services import uv_printing as core
    row = find(db, m.UvPricingQuote, factory, p.get('quote_id'))
    check_version(row, p)
    if row.adopted_rate_version_id or not row.product_id:
        fail('测算已采用或未关联产品', 'quote_id', 409)
    if p.get('rate_kind') != 'commercial':
        fail('商业测算建议不得直接采用为独立工价或面积价', 'rate_kind')
    value = row.result.get('markup_price')
    if value is None:
        fail('此测算不可计算', 'quote_id')
    rate = core.ACTIONS['rate-create'](db, factory, actor, dict(factory_id=factory, operation_id=p['operation_id'],
             expected_version=0, rate_kind='commercial', product_id=row.product_id, process_version_id=None,
             machine_id=None, price_group=None, currency=row.result['currency'], unit_price=value,
             effective_from=day(p.get('effective_from'), 'effective_from'), effective_to=None, note='来自测算 ' + row.id))
    row.adopted_rate_version_id = rate['id']
    row.version += 1
    row.updated_at = m.now()
    return rate


ACTIONS = {'ink-sku-create': create_sku, 'ink-movement-create': create_movement, 'ink-movement-reverse': reverse_movement,
           'expense-create': create_expense, 'expense-reverse': reverse_expense, 'monthly-policy-save': save_policy,
           'pricing-quote-create': save_quote, 'pricing-quote-adopt': adopt_quote}


def payroll_sources(db, factory, scope):
    from app.models.uv_printing import UvReport
    from app.services import uv_printing as core
    return sorted([{'id': r.id, 'version': r.version} for r in core.query_rows(db, UvReport, factory, scope, True)], key=lambda r: r['id'])


def create_payroll(db, factory, actor, p):
    fields(p, {'date_from', 'date_to', 'shift', 'reason'})
    from app.services import uv_printing as core
    scope = {key: p[key] for key in ('date_from', 'date_to', 'shift') if p.get(key) is not None}
    scope['include_adjustments'] = False
    start, end = day(p.get('date_from'), 'date_from'), day(p.get('date_to'), 'date_to')
    if start > end or scope.get('shift') not in {None, 'day', 'night'}:
        fail('日期范围或班次无效')
    preview = core.payroll_preview(db, factory, scope)
    if preview['coverage'] != 'complete' or preview['batch_total'] is None:
        fail('工资仍有未定价、未排班、待质量或混币项目，不能生成核定批次', status=409)
    row = m.UvPayrollBatch(**base(factory, actor, date_from=start, date_to=end, shift=scope.get('shift'),
          snapshot=preview, source_versions=payroll_sources(db, factory, scope), reason=text(p.get('reason', ''), 'reason')))
    db.add(row)
    db.flush()
    for line in preview['lines']:
        if line['amount'] is None:
            fail('工资分摊尚未核齐', status=409)
        db.add(m.UvPayrollBatchLine(**base(factory, actor, batch_id=row.id, worker_id=line['worker_id'],
               worker_name=line['worker_name'], currency=line['amount']['currency'], amount=D(line['amount']['amount']))))
    db.flush()
    return serial(row)


def confirm_payroll(db, factory, actor, p):
    fields(p, {'target_id', 'reason'})
    row = find(db, m.UvPayrollBatch, factory, p.get('target_id'))
    check_version(row, p)
    if row.status != 'draft':
        fail('工资批次已确认', status=409)
    for source in row.source_versions:
        from app.models.uv_printing import UvReport
        report = find(db, UvReport, factory, source['id'])
        ensure_open(db, factory, report.business_date)
        ensure_report_mutable(db, factory, report.id)
    scope = {'date_from': row.date_from, 'date_to': row.date_to, 'include_adjustments': False}
    if row.shift:
        scope['shift'] = row.shift
    from app.services import uv_printing as core
    if payroll_sources(db, factory, scope) != row.source_versions or core.payroll_preview(db, factory, scope) != row.snapshot:
        fail('工资来源或计算已变化，请重新生成预览', status=409)
    row.status = 'confirmed'
    row.version += 1
    row.updated_at = m.now()
    row.reason = text(p.get('reason'), 'reason', True)
    return serial(row)


def adjust_payroll(db, factory, actor, p):
    fields(p, {'target_id', 'business_date', 'reason', 'lines'})
    old = find(db, m.UvPayrollBatch, factory, p.get('target_id'))
    check_version(old, p)
    if old.status != 'confirmed':
        fail('只能调整已确认工资批次', status=409)
    posted = day(p.get('business_date'), 'business_date')
    ensure_open(db, factory, posted)
    if posted <= old.date_to:
        fail('工资调整应进入后续开放期间', 'business_date')
    lines = p.get('lines')
    if not isinstance(lines, list) or not lines or len(lines) > 200:
        fail('请填写1至200条明确工资调整明细', 'lines')
    reason = text(p.get('reason'), 'reason', True)
    from app.models.uv_printing import UvWorker
    seen = set()
    normalized = []
    for line in lines:
        if not isinstance(line, dict):
            fail('工资调整明细必须为包含员工、币种和金额的对象', 'lines')
        worker = find(db, UvWorker, factory, line.get('worker_id'))
        if worker.id in seen:
            fail('同一员工调整不能重复', 'lines')
        seen.add(worker.id)
        code = currency(line.get('currency'))
        amount = rounded(decimal(line.get('amount'), 'amount', signed=True), code)
        normalized.append(dict(worker_id=worker.id, worker_name=worker.display_name, currency=code, amount=amount))
    row = m.UvPayrollBatch(**base(factory, actor, date_from=posted, date_to=posted, shift=None,
          status='confirmed', adjustment_of=old.id, snapshot={'lines': [{**v, 'amount': format(v['amount'], 'f')} for v in normalized]},
          source_versions=[], reason=reason))
    db.add(row)
    db.flush()
    for line in normalized:
        db.add(m.UvPayrollBatchLine(**base(factory, actor, batch_id=row.id, **line)))
    db.flush()
    return serial(row)


def close_period(db, factory, actor, p):
    fields(p, {'period', 'reason'})
    period = p.get('period')
    if len(str(period)) == 7:
        period = month(period)
        last = calendar.monthrange(int(period[:4]), int(period[5:]))[1]
        scope = {'date_from': period + '-01', 'date_to': f'{period}-{last:02d}'}
    else:
        period = day(period, 'period')
        scope = {'business_date': period}
    if db.scalar(select(m.UvPeriod.id).where(m.UvPeriod.factory_id == factory, m.UvPeriod.period == period)):
        fail('期间已关闭', 'period', 409)
    from app.services import uv_printing as core
    reports = core.daily_projection(db, factory, scope)
    if not reports or any(r['unpriced_reports'] or r['quality_pending_reports'] or r['operating_result'] is None or r.get('provisional_reasons') for r in reports):
        fail('数量、工价、质量或经营成本覆盖未核齐，不能关闭期间', 'period', 409)
    row = m.UvPeriod(**base(factory, actor, period=period, reason=text(p.get('reason'), 'reason', True),
          snapshot={'scope': scope, 'daily': reports, 'as_of': m.now(), 'formula_version': 'uv-operating-v1'}))
    db.add(row)
    db.flush()
    return serial(row)


ACTIONS.update({'payroll-batch-create': create_payroll, 'payroll-batch-confirm': confirm_payroll,
                'payroll-batch-adjust': adjust_payroll, 'period-close': close_period})
