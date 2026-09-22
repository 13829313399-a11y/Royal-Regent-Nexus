"""Versioned valuation, reproducible wage trials, partial settlements and periods."""
from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

from sqlalchemy import select, func

from app.models import spray_ops as m
from .common import add, get, scoped, serialize, require, version, touch, check_period, digest
from .production import rows
from .materials import active_rule

CENT = Decimal("0.01")


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def split_money(total, weights):
    """Largest remainder, with stable IDs as a deterministic tie breaker."""
    require(weights and all(weight > 0 for weight in weights.values()), "allocation_weights", "班组分摊权重必须为正", 422)
    total = money(total)
    require(total >= 0, "negative_pool", "班组金额不得为负", 422)
    denominator = sum(weights.values())
    raw = {key: total * weight / denominator for key, weight in weights.items()}
    rounded = {key: value.quantize(CENT, rounding=ROUND_FLOOR) for key, value in raw.items()}
    residual = int((total - sum(rounded.values())) / CENT)
    for key in sorted(weights, key=lambda key: (-(raw[key] - rounded[key]), key))[:residual]:
        rounded[key] += CENT
    return rounded


def create_rule(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新规则版本应为 0")
    if b.material_id:
        get(db, m.SprayOpsMaterial, f, b.material_id)
    if b.step_id:
        get(db, m.SprayOpsStep, f, b.step_id)
    if b.kind == "wage" and b.parameters.get("exchange_rule_id"):
        active_rule(db, f, b.parameters["exchange_rule_id"], "exchange", b.effective_from, approved=False)
    rule = add(db, m.SprayOpsRule, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "effective_from", "effective_until"}), effective_from=str(b.effective_from), effective_until=str(b.effective_until) if b.effective_until else None)
    return serialize(rule)


def confirm_rule(db, f, rule_id, b, actor):
    rule = get(db, m.SprayOpsRule, f, rule_id)
    version(rule, b.expected_version)
    require(rule.status == "draft", "rule_immutable", "已确认规则不可改写，请建立新版本")
    if rule.kind == "wage" and rule.parameters["method"] == "historical_normalized":
        require(rule.parameters["reference_hours"] and rule.parameters["paid_hours"], "coefficients_unconfirmed", "历史折算必须明确基准与计薪时长")
    rule.status, rule.confirmed_by, rule.confirmed_at = "confirmed", actor, m.now()
    rule.evidence += "\n确认：" + b.reason
    touch(rule)
    return serialize(rule)


def payroll_sources(db, f, day):
    reports = list(db.scalars(scoped(db, m.SprayOpsReport, f).where(m.SprayOpsReport.business_date == str(day), m.SprayOpsReport.status == "confirmed").order_by(m.SprayOpsReport.id)))
    report_rows = list(db.scalars(scoped(db, m.SprayOpsReportRow, f).where(m.SprayOpsReportRow.report_id.in_([report.id for report in reports])).order_by(m.SprayOpsReportRow.id)))
    labor = list(db.scalars(scoped(db, m.SprayOpsLabor, f).where(m.SprayOpsLabor.row_id.in_([row.id for row in report_rows]), m.SprayOpsLabor.active.is_(True)).order_by(m.SprayOpsLabor.id)))
    return reports, report_rows, labor


def payroll_fingerprint(db, f, day, assignments):
    reports, report_rows, labor = payroll_sources(db, f, day)
    rule_ids = set(assignments.values())
    for rule_id in list(rule_ids):
        rule = get(db, m.SprayOpsRule, f, rule_id)
        if rule.parameters.get("exchange_rule_id"):
            rule_ids.add(rule.parameters["exchange_rule_id"])
    return digest(dict(reports=[serialize(r) for r in reports], rows=[serialize(r) for r in report_rows], labor=[serialize(l) for l in labor], rules=[serialize(get(db, m.SprayOpsRule, f, rule_id)) for rule_id in sorted(rule_ids)], assignments=assignments))


def payroll_detail(db, f, payroll):
    lines = rows(db, m.SprayOpsPayrollLine, f, payroll_id=payroll.id)
    return {**serialize(payroll), "lines": [{**serialize(line), "allocations": [serialize(a) for a in rows(db, m.SprayOpsPayrollAllocation, f, payroll_line_id=line.id)]} for line in lines]}


def payroll_trial(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新工资试算版本应为 0")
    _, report_rows, labor = payroll_sources(db, f, b.business_date)
    require(report_rows and labor, "no_payroll_source", "当天尚无已确认报工及实名工时记录")
    require(set(b.row_rules) <= {row.id for row in report_rows}, "row_mismatch", "工资规则引用了其他日期或工厂日报", 422)
    require(len({a.employee_id for a in b.adjustments}) == len(b.adjustments), "duplicate_adjustment", "每位员工只能有一条调整汇总", 422)
    assignments = {row.id: b.row_rules.get(row.id, b.rule_id) for row in report_rows}
    amounts, guarantees, line_allocations = defaultdict(lambda: Decimal(0)), {}, defaultdict(list)
    currencies = set()
    fixed_paid = set()
    for row in report_rows:
        team = [person for person in labor if person.row_id == row.id]
        require(team or row.processed == 0, "labor_missing", "有产量的日报行缺少员工分摊")
        if not team:
            continue
        rule = active_rule(db, f, assignments[row.id], "wage", b.business_date, approved=False)
        task = get(db, m.SprayOpsTask, f, row.task_id)
        require(rule.step_id is None or rule.step_id == task.step_id, "wage_scope", "工资规则不适用于当前工序")
        params = rule.parameters
        factor, currency = Decimal(1), params["currency"]
        if params["exchange_rule_id"]:
            fx = active_rule(db, f, params["exchange_rule_id"], "exchange", b.business_date, approved=False)
            require(fx.parameters["from_currency"] == currency, "currency_mismatch", "工资汇率方向错误", 422)
            factor, currency = Decimal(fx.parameters["factor"]), fx.parameters["to_currency"]
        currencies.add(currency)
        rate = Decimal(params["rate"])
        overtime_rate = Decimal(params["overtime_rate"]) if params["overtime_rate"] is not None else rate
        basis = row.good if params["basis"] == "good" else row.processed
        method = params["method"]
        require(method == "fixed_shift" or row.overtime == 0 and all(person.overtime_hours == 0 for person in team) or params["overtime_rate"] is not None,
                "overtime_rate_missing", "存在加班实绩，须明确加班计件或工时单价；不能默认为正班单价")
        allocation = {}
        if method in {"team_piece", "historical_normalized"}:
            require(params["basis"] != "good" or row.overtime == 0 or rate == overtime_rate, "good_overtime_basis", "合格数未拆分正加班，不能使用不同加班计件价")
            pool = basis * rate if params["basis"] == "good" else row.normal * rate + row.overtime * overtime_rate
            if method == "historical_normalized":
                require(params["reference_hours"] and params["paid_hours"], "coefficients_missing", "历史试算须输入确认或待核对的时长参数", 422)
                pool *= Decimal(params["paid_hours"]) / Decimal(params["reference_hours"])
            allocation = split_money(pool * factor, {person.id: person.weight for person in team})
        elif method == "personal_piece":
            require(all(person.personal_quantity is not None for person in team), "personal_quantity_missing", "个人计件须记录每人的真实加工数")
            require(sum(person.personal_quantity for person in team) == basis, "personal_quantity_mismatch", "个人产量分摊合计须等于选定生产口径")
            require(row.overtime == 0 or overtime_rate == rate, "personal_overtime_basis", "个人计件加班分摊未确认，不能推算不同加班单价")
            allocation = {person.id: money(person.personal_quantity * rate * factor) for person in team}
        elif method == "hourly":
            allocation = {person.id: money((person.hours * rate + person.overtime_hours * overtime_rate) * factor) for person in team}
        else:
            for person in sorted(team, key=lambda person: person.id):
                key = person.employee_id, rule.id
                allocation[person.id] = money(rate * factor) if key not in fixed_paid else Decimal(0)
                fixed_paid.add(key)
        for person in team:
            require(person.nonproductive_hours == 0 or params["nonproductive_rate"] is not None, "nonproductive_rate_missing", "无产值工时尚无计薪规则")
            value = allocation[person.id] + money(person.nonproductive_hours * Decimal(params["nonproductive_rate"] or "0") * factor)
            guarantee = money(Decimal(params["daily_guarantee"]) * factor)
            require(person.employee_id not in guarantees or guarantees[person.employee_id] == guarantee, "guarantee_conflict", "同一员工当天的保底规则不一致")
            guarantees[person.employee_id] = guarantee
            amounts[person.employee_id] += value
            line_allocations[person.employee_id].append((person.id, rule.id, value))
    require(len(currencies) == 1, "currency_mismatch", "工资汇总前须统一币种并确认汇率")
    require({a.employee_id for a in b.adjustments} <= amounts.keys(), "employee_mismatch", "调整员工不在当天报工中", 422)
    payroll = add(db, m.SprayOpsPayroll, f, document_no=b.document_no, business_date=str(b.business_date), rule_id=b.rule_id, currency=next(iter(currencies)), source_fingerprint=payroll_fingerprint(db, f, b.business_date, assignments))
    for employee_id in sorted(amounts):
        adjustment = next((a for a in b.adjustments if a.employee_id == employee_id), None)
        subsidy = money(adjustment.subsidy) if adjustment else Decimal(0)
        signed = money(adjustment.adjustment) if adjustment else Decimal(0)
        guarantee = max(Decimal(0), guarantees[employee_id] - amounts[employee_id])
        total = amounts[employee_id] + guarantee + subsidy + signed
        require(total >= 0, "negative_wage", "工资调整后不得为负", 422)
        line = add(db, m.SprayOpsPayrollLine, f, payroll_id=payroll.id, employee_id=employee_id, base_amount=amounts[employee_id], guarantee=guarantee, subsidy=subsidy, adjustment=signed, payroll_amount=total, evidence=adjustment.evidence if adjustment else "")
        for labor_id, rule_id, amount in line_allocations[employee_id]:
            add(db, m.SprayOpsPayrollAllocation, f, payroll_line_id=line.id, labor_id=labor_id, rule_id=rule_id, payroll_amount=amount)
    return payroll_detail(db, f, payroll)


def confirm_payroll(db, f, payroll_id, expected):
    payroll = get(db, m.SprayOpsPayroll, f, payroll_id)
    version(payroll, expected)
    check_period(db, f, payroll.business_date)
    require(payroll.status == "trial", "payroll_state", "只能确认工资试算")
    assignments = {}
    lines = rows(db, m.SprayOpsPayrollLine, f, payroll_id=payroll.id)
    for line in lines:
        for allocation in rows(db, m.SprayOpsPayrollAllocation, f, payroll_line_id=line.id):
            labor = get(db, m.SprayOpsLabor, f, allocation.labor_id)
            rule = active_rule(db, f, allocation.rule_id, "wage", payroll.business_date)
            if rule.parameters["exchange_rule_id"]:
                active_rule(db, f, rule.parameters["exchange_rule_id"], "exchange", payroll.business_date)
            assignments[labor.row_id] = rule.id
    _, report_rows, _ = payroll_sources(db, f, payroll.business_date)
    assignments = {row.id: assignments.get(row.id, payroll.rule_id) for row in report_rows}
    require(payroll.source_fingerprint == payroll_fingerprint(db, f, payroll.business_date, assignments), "stale_payroll", "日报或规则已改变，请重新试算")
    existing = db.scalar(scoped(db, m.SprayOpsPayroll, f).where(m.SprayOpsPayroll.business_date == payroll.business_date, m.SprayOpsPayroll.status == "confirmed"))
    require(existing is None, "duplicate_payroll", "当天已有正式工资，不能重复结算员工保底和产量")
    payroll.status = "confirmed"
    touch(payroll)
    return payroll_detail(db, f, payroll)


def expense(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新费用记录版本应为 0")
    if b.line_id:
        get(db, m.SprayOpsDemandLine, f, b.line_id)
    return serialize(add(db, m.SprayOpsExpense, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "business_date"}), business_date=str(b.business_date)))


def confirm_expense(db, f, entity_id, b):
    item = get(db, m.SprayOpsExpense, f, entity_id)
    version(item, b.expected_version)
    check_period(db, f, item.business_date)
    require(item.included is None, "expense_frozen", "费用归集已确认，请另记有依据的调整")
    item.included = b.included
    item.evidence += "\n归集确认：" + b.reason
    touch(item)
    return serialize(item)


def material_costs(db, f, month):
    events = list(db.scalars(scoped(db, m.SprayOpsMaterialMovement, f).where(m.SprayOpsMaterialMovement.business_date.startswith(month), m.SprayOpsMaterialMovement.kind.in_(["consume", "cost_adjustment"]))))
    resolved = {item.issue_id for item in events if item.kind == "cost_adjustment"}
    return [item for item in events if item.id not in resolved]


def value_report(db, f, b):
    report = get(db, m.SprayOpsReport, f, b.report_id)
    version(report, b.expected_version)
    check_period(db, f, report.business_date)
    require(report.status == "confirmed", "report_state", "仅已确认日报可登记工序产值")
    rule = active_rule(db, f, b.rule_id, "operation_price", report.business_date)
    created = []
    for row in rows(db, m.SprayOpsReportRow, f, report_id=report.id):
        task = get(db, m.SprayOpsTask, f, row.task_id)
        if task.step_id != rule.step_id:
            continue
        for allocation in rows(db, m.SprayOpsReportAllocation, f, row_id=row.id):
            ta = get(db, m.SprayOpsTaskAllocation, f, allocation.task_allocation_id)
            stock = get(db, m.SprayOpsStock, f, ta.stock_id)
            require(stock.rework_origin is None, "rework_valuation", "返工不能重复登记正常工序产值")
            price = Decimal(rule.parameters["price"])
            created.append(serialize(add(db, m.SprayOpsValuation, f, report_allocation_id=allocation.id, rule_id=rule.id, quantity=allocation.good, price=price, amount=money(allocation.good * price), currency=rule.parameters["currency"], business_date=report.business_date)))
    require(created, "no_valuation", "没有适用于此价格版本的工序")
    return dict(id=report.id, valuations=created)


def settlement_detail(db, f, settlement):
    detail = []
    for line in rows(db, m.SprayOpsSettlementLine, f, settlement_id=settlement.id):
        delivery_line = get(db, m.SprayOpsDeliveryLine, f, line.delivery_line_id)
        delivery = get(db, m.SprayOpsDelivery, f, delivery_line.delivery_id)
        stock = get(db, m.SprayOpsStock, f, delivery_line.stock_id)
        demand_line = get(db, m.SprayOpsDemandLine, f, stock.line_id)
        demand = get(db, m.SprayOpsDemand, f, demand_line.demand_id)
        detail.append({**serialize(line), "delivery_document_no": delivery.document_no, "delivery_date": delivery.business_date,
                       "demand_id": demand.id, "order_document_no": demand.document_no,
                       "item_part": demand_line.item_no + " / " + demand_line.part, "unit": stock.unit})
    return {**serialize(settlement), "lines": detail}


def create_settlement(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新结算版本应为 0")
    check_period(db, f, b.month)
    require(str(b.business_date).startswith(b.month), "period_mismatch", "结算业务日期必须属于所选月份", 422)
    require(len({item.delivery_line_id for item in b.lines}) == len(b.lines), "duplicate_line", "不能重复选择送货行", 422)
    factor = Decimal(1)
    fx = active_rule(db, f, b.rule_id, "exchange", b.business_date) if b.rule_id else None
    if fx:
        require(fx.parameters["to_currency"] == b.currency, "currency_direction", "汇率目标币种不匹配", 422)
        factor = Decimal(fx.parameters["factor"])
    frozen, selected = [], []
    for item in b.lines:
        line = get(db, m.SprayOpsDeliveryLine, f, item.delivery_line_id)
        delivery = get(db, m.SprayOpsDelivery, f, line.delivery_id)
        require(delivery.counterparty == b.counterparty, "counterparty_mismatch", "结算往来方不匹配", 422)
        accepted_through_month = sum(event.quantity for event in rows(db, m.SprayOpsMovement, f, kind="delivery_accept", reference_id=line.id) if event.business_date[:7] <= b.month)
        require(accepted_through_month > 0, "acceptance_period", "不能结算未来月份或未验收送货")
        eligible = min(line.accepted - line.returned - line.settled, accepted_through_month - line.settled)
        require(item.quantity <= eligible, "settlement_overflow", "结算数量超过本月截止的净验收未结算数量")
        require(line.price is not None, "price_unconfirmed", "送货行未定价，不能正式结算")
        require(line.currency == b.currency or fx and line.currency == fx.parameters["from_currency"], "currency_mismatch", "结算币种不同，须选择对应确认汇率")
        rate = factor if line.currency != b.currency else Decimal(1)
        price = line.price * rate
        amount = money(item.quantity * price)
        selected.append((line, item.quantity, price, amount))
        frozen.append(dict(delivery=serialize(delivery), line=serialize(line), selected_quantity=str(item.quantity), price=str(price), amount=str(amount)))
    settlement = add(db, m.SprayOpsSettlement, f, document_no=b.document_no, counterparty=b.counterparty, month=b.month, currency=b.currency, rule_id=b.rule_id, business_date=str(b.business_date), status="confirmed", total_amount=sum(item[3] for item in selected), frozen_snapshot=dict(deliveries=frozen, exchange=serialize(fx) if fx else None))
    for line, qty, price, amount in selected:
        add(db, m.SprayOpsSettlementLine, f, settlement_id=settlement.id, delivery_line_id=line.id, quantity=qty, price=price, amount=amount)
        line.settled += qty
        touch(line)
    return settlement_detail(db, f, settlement)


def credit(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新贷项版本应为 0")
    returned = get(db, m.SprayOpsReturn, f, b.return_id)
    settlement_line = get(db, m.SprayOpsSettlementLine, f, b.settlement_line_id)
    require(returned.delivery_line_id == settlement_line.delivery_line_id, "credit_mismatch", "退货与原结算行不匹配", 422)
    total_return_credit = sum(item.quantity for item in rows(db, m.SprayOpsCredit, f, return_id=returned.id))
    total_settlement_credit = sum(item.quantity for item in rows(db, m.SprayOpsCredit, f, settlement_line_id=settlement_line.id))
    require(b.quantity <= returned.quantity - total_return_credit and b.quantity <= settlement_line.quantity - total_settlement_credit, "credit_overflow", "贷项超过退货或原结算的剩余额度")
    settlement = get(db, m.SprayOpsSettlement, f, settlement_line.settlement_id)
    return serialize(add(db, m.SprayOpsCredit, f, return_id=returned.id, settlement_line_id=settlement_line.id, quantity=b.quantity, amount=money(b.quantity * settlement_line.price), currency=settlement.currency, business_date=str(b.business_date), reason=b.reason))


def set_price(db, f, line_id, b):
    line = get(db, m.SprayOpsDeliveryLine, f, line_id)
    version(line, b.expected_version)
    delivery = get(db, m.SprayOpsDelivery, f, line.delivery_id)
    check_period(db, f, delivery.business_date)
    require(line.settled == 0, "frozen_price", "已结算行单价被冻结，请使用调整单")
    line.price = b.price
    line.price_evidence = b.evidence
    touch(line)
    return serialize(line)


def economics(db, f, month, currency):
    report_query = scoped(db, m.SprayOpsReport, f).where(m.SprayOpsReport.business_date.startswith(month), m.SprayOpsReport.status == "confirmed")
    reports = list(db.scalars(report_query))
    report_ids = [report.id for report in reports]
    report_rows = list(db.scalars(scoped(db, m.SprayOpsReportRow, f).where(m.SprayOpsReportRow.report_id.in_(report_ids))))
    allocations = list(db.scalars(scoped(db, m.SprayOpsReportAllocation, f).where(m.SprayOpsReportAllocation.row_id.in_([row.id for row in report_rows]))))
    values = list(db.scalars(scoped(db, m.SprayOpsValuation, f).where(m.SprayOpsValuation.business_date.startswith(month))))
    costs = material_costs(db, f, month)
    payrolls = list(db.scalars(scoped(db, m.SprayOpsPayroll, f).where(m.SprayOpsPayroll.business_date.startswith(month), m.SprayOpsPayroll.status == "confirmed")))
    wages = list(db.scalars(scoped(db, m.SprayOpsPayrollLine, f).where(m.SprayOpsPayrollLine.payroll_id.in_([item.id for item in payrolls]))))
    expenses = list(db.scalars(scoped(db, m.SprayOpsExpense, f).where(m.SprayOpsExpense.business_date.startswith(month))))
    cost_lots = {lot.id: lot for lot in rows(db, m.SprayOpsMaterialLot, f)}
    valued_ids = {item.report_allocation_id for item in values}
    pricing_complete = all(a.id in valued_ids or a.good == 0 for a in allocations) and all(item.currency == currency for item in values)
    payroll_complete = {report.business_date for report in reports} <= {item.business_date for item in payrolls} and all(item.currency == currency for item in payrolls)
    material_complete = bool(costs) and all(item.cost is not None and cost_lots[item.lot_id].currency == currency for item in costs)
    expenses_complete = bool(expenses) and all(item.included is not None and (not item.included or item.currency == currency) for item in expenses)
    output = sum(item.amount for item in values if item.currency == currency)
    material_cost = sum(item.cost for item in costs if item.cost is not None and cost_lots[item.lot_id].currency == currency)
    wage = sum(item.payroll_amount for item in wages if any(parent.id == item.payroll_id and parent.currency == currency for parent in payrolls))
    expense_total = sum((-item.amount if item.kind == "recovery" else item.amount) for item in expenses if item.included and item.currency == currency)
    complete = bool(reports) and pricing_complete and payroll_complete and material_complete and expenses_complete
    coverage = dict(production="complete" if reports else "unknown", pricing="complete" if pricing_complete and reports else "partial" if values else "unknown", payroll="complete" if payroll_complete and reports else "partial" if payrolls else "unknown", material_cost="complete" if material_complete else "partial" if costs else "unknown")
    return dict(month=month, currency=currency, coverage=coverage, operating_value=output if any(item.currency == currency for item in values) else None,
                material_cost=material_cost if any(cost_lots[item.lot_id].currency == currency for item in costs) and all(item.cost is not None for item in costs if cost_lots[item.lot_id].currency == currency) else None,
                payroll_amount=wage if any(item.currency == currency for item in payrolls) else None, expense_amount=expense_total if expenses_complete else None,
                surplus=output - material_cost - wage - expense_total if complete else None,
                is_partial=not complete, label="经营结余（管理口径）", missing=dict(unpriced_allocations=sum(a.id not in valued_ids and a.good > 0 for a in allocations), unconfirmed_payroll_days=len({r.business_date for r in reports} - {p.business_date for p in payrolls}), unknown_material_cost=sum(item.cost is None for item in costs), unconfirmed_expenses=sum(item.included is None for item in expenses) + int(bool(reports) and not expenses)))


def close_preview(db, f, month):
    blockers = []
    demands = list(db.scalars(scoped(db, m.SprayOpsDemandLine, f).join(m.SprayOpsDemand, (m.SprayOpsDemand.id == m.SprayOpsDemandLine.demand_id) & (m.SprayOpsDemand.factory_id == m.SprayOpsDemandLine.factory_id)).where(m.SprayOpsDemand.business_date.startswith(month))))
    for line in demands:
        if line.commercial_price is None:
            blockers.append(dict(code="price_unconfirmed", entity_id=line.id, message="订单单价未确认"))
    for batch in rows(db, m.SprayOpsBatch, f):
        if batch.business_date.startswith(month) and not batch.line_id:
            blockers.append(dict(code="unmatched_batch", entity_id=batch.id, message="来料尚未匹配订单"))
    for job in rows(db, m.SprayOpsImport, f):
        if job.status not in {"completed", "cancelled"} and job.snapshot.get("business_month") == month:
            blockers.append(dict(code="import_unresolved", entity_id=job.id, message="导入仍有未处理差异"))
    # Closing freezes facts in their original currencies. It does not require
    # every source to already use CNY, or invent an FX conversion for profit.
    coverage = economics(db, f, month, "CNY")
    for code, count in coverage["missing"].items():
        if count:
            blockers.append(dict(code=code, message=f"{count} 条记录尚未完成核对"))
    consumes = material_costs(db, f, month)
    if coverage["coverage"]["production"] == "complete" and (not consumes or any(item.cost is None for item in consumes)):
        blockers.append(dict(code="material_coverage", message="存在生产实绩，但材料耗用成本尚未完整确认"))
    for report in rows(db, m.SprayOpsReport, f):
        if report.business_date.startswith(month) and report.status == "draft":
            blockers.append(dict(code="report_draft", entity_id=report.id, message="日报草稿尚未确认"))
    for returned in rows(db, m.SprayOpsReturn, f):
        if not returned.business_date.startswith(month):
            continue
        line = get(db, m.SprayOpsDeliveryLine, f, returned.delivery_line_id)
        needed = max(Decimal(0), line.settled - (line.accepted - line.returned))
        credited = sum(item.quantity for item in rows(db, m.SprayOpsCredit, f) if get(db, m.SprayOpsReturn, f, item.return_id).delivery_line_id == line.id)
        if credited < needed:
            blockers.append(dict(code="credit_pending", entity_id=returned.id, message="已结算退货尚未登记贷项"))
    # Freeze entity versions, not just totals, so a same-total rewrite invalidates it.
    evidence = {}
    for model in (m.SprayOpsReport, m.SprayOpsBatch, m.SprayOpsDelivery, m.SprayOpsMaterialReceipt, m.SprayOpsMaterialMovement, m.SprayOpsPayroll, m.SprayOpsExpense, m.SprayOpsSettlement, m.SprayOpsCredit, m.SprayOpsContainer, m.SprayOpsValuation):
        evidence[model.__tablename__] = [serialize(item) for item in db.scalars(scoped(db, model, f).where(model.business_date.startswith(month)).order_by(model.id))]
    snapshot = dict(month=month, evidence=evidence, blockers=blockers)
    return dict(month=month, blockers=blockers, fingerprint=digest(snapshot), snapshot=snapshot)


def close_period(db, f, b):
    period = db.scalar(scoped(db, m.SprayOpsPeriod, f).where(m.SprayOpsPeriod.month == b.month))
    require(period is None and b.expected_version == 0 or period is not None and period.version == b.expected_version, "version_conflict", "期间版本已变化")
    require(not period or period.status == "open", "period_closed", "期间已锁定")
    preview = close_preview(db, f, b.month)
    require(preview["fingerprint"] == b.fingerprint, "stale_close_preview", "锁月核对依据已改变，请重新预览")
    require(not preview["blockers"], "close_blocked", "尚有未完成的核对事项", conflicts=preview["blockers"])
    if not period:
        period = add(db, m.SprayOpsPeriod, f, month=b.month)
    period.status, period.frozen_snapshot, period.reason = "closed", preview["snapshot"], b.reason
    touch(period)
    return serialize(period)


def reopen_period(db, f, period_id, b):
    period = get(db, m.SprayOpsPeriod, f, period_id)
    version(period, b.expected_version)
    require(period.status == "closed", "period_open", "期间尚未关闭")
    period.status = "open"
    # Preserve every previous freeze as immutable audit evidence.
    add(db, m.SprayOpsExport, f, name=f"{period.month}-freeze-v{period.version}.json", kind="period_snapshot", payload=__import__("json").dumps(period.frozen_snapshot, ensure_ascii=False).encode(), sha256=digest(period.frozen_snapshot), source_fingerprint=digest(period.frozen_snapshot), required_permissions=["settle", "cost_read", "payroll_read"])
    period.reason = b.reason
    touch(period)
    return serialize(period)
