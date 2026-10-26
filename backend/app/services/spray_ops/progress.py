"""Pure physical and stage queries. No commands, lazy initialization or finance.

All aggregates use the complete filtered relational scope. A task is work at
one route step; neither its input nor its report good count is final delivery.
"""
from decimal import Decimal

from sqlalchemy import select, func, exists
from sqlalchemy.orm import aliased

from app.models import spray_ops as m
from . import common as c, production

PHYSICAL_FIELDS = ('planned', 'white', 'wip', 'hold', 'finished', 'in_process',
                   'scrap', 'arrival_rejected', 'rework_current', 'rework_processed',
                   'dispatched', 'handover_accepted', 'handover_rejected', 'returned',
                   'in_transit', 'net_accepted')
TASK_FIELDS = ('scheduled_input', 'reported_input', 'pending_input')


def demand_totals(db, factory, statement):
    demands = statement.subquery()
    line = m.SprayOpsDemandLine
    stock = m.SprayOpsStock
    move = m.SprayOpsMovement
    batch = m.SprayOpsBatch
    lines = select(line.id).where(line.factory_id == factory, line.demand_id.in_(select(demands.c.id)))
    values = {}

    def add(unit, field, quantity):
        values.setdefault(unit, {key: Decimal(0) for key in PHYSICAL_FIELDS})[field] += quantity

    for unit, qty in db.execute(select(line.unit, func.sum(line.quantity)).where(
            line.factory_id == factory, line.id.in_(lines)).group_by(line.unit)):
        add(unit, 'planned', qty)
    for unit, state, rework, qty in db.execute(select(stock.unit, stock.state,
            stock.rework_origin.is_not(None), func.sum(stock.quantity)).where(
            stock.factory_id == factory, stock.line_id.in_(lines), stock.quantity > 0
            ).group_by(stock.unit, stock.state, stock.rework_origin.is_not(None))):
        if state in ('white', 'wip', 'hold', 'finished'):
            add(unit, state, qty)
        if state in ('white', 'wip', 'hold'):
            add(unit, 'in_process', qty)
            if rework:
                add(unit, 'rework_current', qty)
    reversal = aliased(move)
    reversed_move = exists(select(reversal.id).where(reversal.factory_id == factory, reversal.reversal_of == move.id))
    for unit, qty in db.execute(select(stock.unit, func.sum(move.quantity)).join(
            stock, (stock.id == move.from_stock_id) & (stock.factory_id == factory)).where(
            move.factory_id == factory, stock.line_id.in_(lines),
            move.kind.in_(('production_scrap', 'quality_scrap')), ~reversed_move).group_by(stock.unit)):
        add(unit, 'scrap', qty)
    for unit, qty in db.execute(select(batch.unit, func.sum(batch.rejected)).where(
            batch.factory_id == factory, batch.line_id.in_(lines), batch.kind == 'arrival').group_by(batch.unit)):
        add(unit, 'arrival_rejected', qty)
    allocation, row, report, task_alloc = m.SprayOpsReportAllocation, m.SprayOpsReportRow, m.SprayOpsReport, m.SprayOpsTaskAllocation
    for unit, qty in db.execute(select(stock.unit, func.sum(allocation.processed)).select_from(allocation).join(
            row, (row.id == allocation.row_id) & (row.factory_id == factory)).join(
            report, (report.id == row.report_id) & (report.factory_id == factory)).join(
            task_alloc, (task_alloc.id == allocation.task_allocation_id) & (task_alloc.factory_id == factory)).join(
            stock, (stock.id == task_alloc.stock_id) & (stock.factory_id == factory)).where(
            allocation.factory_id == factory, task_alloc.line_id.in_(lines),
            report.status == 'confirmed', stock.rework_origin.is_not(None)).group_by(stock.unit)):
        add(unit, 'rework_processed', qty)
    dl, delivery = m.SprayOpsDeliveryLine, m.SprayOpsDelivery
    for unit, sent, accepted, rejected, returned in db.execute(select(stock.unit,
            func.sum(dl.quantity), func.sum(dl.accepted), func.sum(dl.rejected), func.sum(dl.returned)).select_from(dl).join(
            stock, (stock.id == dl.stock_id) & (stock.factory_id == factory)).join(
            delivery, (delivery.id == dl.delivery_id) & (delivery.factory_id == factory)).where(
            dl.factory_id == factory, stock.line_id.in_(lines), delivery.status.in_(('dispatched', 'partial_accepted', 'accepted'))
            ).group_by(stock.unit)):
        for field, qty in dict(dispatched=sent, handover_accepted=accepted, handover_rejected=rejected,
                              returned=returned, in_transit=sent-accepted-rejected, net_accepted=accepted-returned).items():
            add(unit, field, qty)
    return values


def task_totals(db, factory, statement):
    tasks, step = statement.subquery(), m.SprayOpsStep
    values = {}
    for unit, qty, reported in db.execute(select(step.input_unit, func.sum(tasks.c.quantity), func.sum(tasks.c.reported)).select_from(
            tasks).join(step, (step.id == tasks.c.step_id) & (step.factory_id == factory)).where(
            tasks.c.status != 'cancelled').group_by(step.input_unit)):
        values[unit] = dict(scheduled_input=qty, reported_input=reported, pending_input=qty-reported)
    return values


def task_reports(db, factory, task_id, limit=25):
    """Confirmed rows only, without labor, people, pay or arbitrary source text."""
    row, report = m.SprayOpsReportRow, m.SprayOpsReport
    stmt = select(row, report.document_no, report.business_date).join(report,
        (report.id == row.report_id) & (report.factory_id == factory)).where(
        row.factory_id == factory, row.task_id == task_id, report.status == 'confirmed')
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(report.business_date.desc(), report.id, row.id).limit(limit))
    fields = ('id', 'report_id', 'task_id', 'processed', 'good', 'hold', 'scrap', 'normal', 'overtime', 'updated_at')
    return [dict(**{key: c.json_value(getattr(item, key)) for key in fields},
                 document_no=document_no, business_date=day) for item, document_no, day in rows], total


def task_record(db, factory, task):
    """Native read-only passport; no form opening, command or financial read."""
    result = production.task_detail(db, factory, task)
    step = c.get(db, m.SprayOpsStep, factory, task.step_id)
    resource = c.get(db, m.SprayOpsResource, factory, task.resource_id)
    result['step'] = {key: c.json_value(getattr(step, key)) for key in ('id', 'code', 'name', 'input_unit', 'output_unit', 'output_ratio')}
    result['resource'] = {key: getattr(resource, key) for key in ('id', 'code', 'name')}
    for allocation in result['allocations']:
        line = c.get(db, m.SprayOpsDemandLine, factory, allocation['line_id'])
        demand = c.get(db, m.SprayOpsDemand, factory, line.demand_id)
        stock = c.get(db, m.SprayOpsStock, factory, allocation['stock_id'])
        allocation.update(demand_id=demand.id, document_no=demand.document_no, item_no=line.item_no, part=line.part, unit=stock.unit)
    result['reports'], result['reports_total'] = task_reports(db, factory, task.id)
    return result
