"""Request-local production evidence, loaded only under the caller's locks."""
from itertools import islice
from sqlalchemy import select, tuple_
from app.models.cutting_ops import CuttingProductionEvent, CuttingOrderRevision
from app.services import cutting_ops as c, cutting_reporting as reporting


def batches(rows, size=50):
    iterator = iter(rows)
    while batch := list(islice(iterator, size)):
        yield batch


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
