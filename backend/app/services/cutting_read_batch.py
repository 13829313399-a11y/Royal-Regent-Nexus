"""Request-local production evidence, loaded only under the caller's locks."""
from itertools import islice
from sqlalchemy import select, tuple_, func
from app.models.cutting_ops import CuttingProductionEvent, CuttingOrderRevision, CuttingOrder, CuttingMaster, CuttingRevision
from app.models.customer_order_ledger import OrderLedgerDispatch
from app.services import cutting_ops as c, cutting_reporting as reporting


def batches(rows, size=50):
    iterator = iter(rows)
    while batch := list(islice(iterator, size)):
        yield batch


def dispatches(db, line_ids):
    """Latest cutting dispatch per line; factory/recipient scope is explicit."""
    result={}
    for ids in batches(line_ids,200):
        latest=select(OrderLedgerDispatch.line_id,func.max(OrderLedgerDispatch.version).label('version')).where(
            OrderLedgerDispatch.factory_id==c.FACTORY,OrderLedgerDispatch.recipient=='cutting',
            OrderLedgerDispatch.line_id.in_(ids)).group_by(OrderLedgerDispatch.line_id).subquery()
        query=select(OrderLedgerDispatch).join(latest,
            (OrderLedgerDispatch.line_id==latest.c.line_id)&(OrderLedgerDispatch.version==latest.c.version)).where(
                OrderLedgerDispatch.factory_id==c.FACTORY,OrderLedgerDispatch.recipient=='cutting')
        result.update({row.line_id:row for row in db.scalars(query)})
    return result


def current_revisions(db, line_ids):
    result={}
    for ids in batches(line_ids,200):
        query=select(CuttingOrderRevision).join(CuttingOrder,
            (CuttingOrder.line_id==CuttingOrderRevision.line_id)&(CuttingOrder.version==CuttingOrderRevision.version)).where(
                CuttingOrder.factory_id==c.FACTORY,CuttingOrder.line_id.in_(ids))
        result.update({row.line_id:row for row in db.scalars(query)})
    return result


def planning_references(db, revisions):
    """Keep current master/revision objects alive for one locked monthly read."""
    identifiers=set()
    for revision in revisions:
        data=revision.data;planning=data.get('planning',{})
        if not planning:continue
        identifiers.update(r['material_id'] for r in (data.get('bom') or {}).get('data',{}).get('requirements',[]))
        for plan in (planning.get('published'),planning.get('draft')):
            identifiers.update(t['resource_id'] for t in (plan or {}).get('tasks',[]))
    references=[]
    for ids in batches(sorted(identifiers),200):
        references.extend(db.execute(select(CuttingMaster,CuttingRevision).outerjoin(CuttingRevision,
            (CuttingRevision.master_id==CuttingMaster.id)&(CuttingRevision.version==CuttingMaster.version)).where(
                CuttingMaster.factory_id==c.FACTORY,CuttingMaster.id.in_(ids))).all())
    return references


def production(db, line_ids, *, revisions=False):
    """Keep all event dates/actions; filtering before replay loses corrections."""
    histories = {line_id: [] for line_id in line_ids}
    for ids in batches(histories, 200):
        query = select(CuttingProductionEvent).where(
            CuttingProductionEvent.factory_id == c.FACTORY,
            CuttingProductionEvent.line_id.in_(ids)).order_by(
                CuttingProductionEvent.line_id, CuttingProductionEvent.version)
        for row in db.scalars(query):
            histories[row.line_id].append(dict(id=row.id, version=row.version,
                document_id=row.document_id, action=row.action, data=row.data,
                actor_id=row.actor_id, created_at=row.created_at, reason=row.reason))
    docs = {line_id: reporting.documents(history) for line_id, history in histories.items()}
    versions = {}
    if revisions:
        keys = sorted({(line_id, doc['posted']['data']['context']['plan_version'])
            for line_id, documents in docs.items() for doc in documents.values() if doc['posted']})
        for batch in batches(keys, 200):
            query = select(CuttingOrderRevision).where(
                tuple_(CuttingOrderRevision.line_id, CuttingOrderRevision.version).in_(batch))
            versions.update({(row.line_id, row.version): row for row in db.scalars(query)})
    return docs, versions
