"""Order drill-down uses relational keys, never fuzzy item-name matching."""
from sqlalchemy import select
from app.models import spray_ops as m
from .common import get


def related_order(db, factory, demand_id, collection, stmt):
    if not demand_id:
        return stmt
    get(db, m.SprayOpsDemand, factory, demand_id)

    def ids(model, condition):
        return select(model.id).where(model.factory_id == factory, condition)

    lines = ids(m.SprayOpsDemandLine, m.SprayOpsDemandLine.demand_id == demand_id)
    stocks = ids(m.SprayOpsStock, m.SprayOpsStock.line_id.in_(lines))
    task_ids = select(m.SprayOpsTaskAllocation.task_id).where(m.SprayOpsTaskAllocation.factory_id == factory, m.SprayOpsTaskAllocation.line_id.in_(lines))
    report_ids = select(m.SprayOpsReportRow.report_id).where(m.SprayOpsReportRow.factory_id == factory, m.SprayOpsReportRow.task_id.in_(task_ids))
    delivery_lines = ids(m.SprayOpsDeliveryLine, m.SprayOpsDeliveryLine.stock_id.in_(stocks))
    delivery_ids = select(m.SprayOpsDeliveryLine.delivery_id).where(m.SprayOpsDeliveryLine.factory_id == factory, m.SprayOpsDeliveryLine.id.in_(delivery_lines))
    settlement_ids = select(m.SprayOpsSettlementLine.settlement_id).where(m.SprayOpsSettlementLine.factory_id == factory, m.SprayOpsSettlementLine.delivery_line_id.in_(delivery_lines))
    predicates = {
        'demands': m.SprayOpsDemand.id == demand_id,
        'demand-lines': m.SprayOpsDemandLine.id.in_(lines),
        'batches': m.SprayOpsBatch.line_id.in_(lines),
        'stock': m.SprayOpsStock.id.in_(stocks),
        'tasks': m.SprayOpsTask.id.in_(task_ids),
        'reports': m.SprayOpsReport.id.in_(report_ids),
        'forecasts': m.SprayOpsForecast.line_id.in_(lines),
        'deliveries': m.SprayOpsDelivery.id.in_(delivery_ids),
        'delivery-lines': m.SprayOpsDeliveryLine.id.in_(delivery_lines),
        'returns': m.SprayOpsReturn.delivery_line_id.in_(delivery_lines),
        'settlements': m.SprayOpsSettlement.id.in_(settlement_ids),
        'settlement-lines': m.SprayOpsSettlementLine.delivery_line_id.in_(delivery_lines),
    }
    return stmt.where(predicates[collection]) if collection in predicates else stmt
