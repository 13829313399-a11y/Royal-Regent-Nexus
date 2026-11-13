"""Read-only receiving reminders, derived from the existing handover and stock ledger."""
import json
from collections import defaultdict

from sqlalchemy import select

from app.models.material_handover import HandoverDocument
from app.services import material_handover as handover
from app.services.material_handover_rejections import add_summaries


def pending_deliveries(db, limit=50, offset=0):
    inventory = handover.inventory
    stock, entries = inventory.projection(db, 'fabric')
    totals = defaultdict(lambda: inventory.decimal('0'))
    for batch in stock.values():
        totals[batch['unit']] += inventory.decimal(batch['quantity'])

    pending = []
    rows = db.scalars(select(HandoverDocument).where(
        HandoverDocument.factory_id == handover.FACTORY,
        HandoverDocument.status == 'CONFIRMED',
    ).order_by(HandoverDocument.created_at, HandoverDocument.id))
    deliveries = {row.id: (row, body) for row in rows if (body := json.loads(row.data_json))['kind'] == 'DELIVERY'}
    by_document = handover.delivery_amounts(db, deliveries, entries=entries)
    for row, body in deliveries.values():
        amounts = by_document[row.id]
        remaining = [line for line in body['lines']
                     if inventory.decimal(line['quantity']) > amounts.get(line['id'], inventory.decimal('0'))]
        if not remaining:
            continue
        pending.append({
            'id': row.id, 'status': row.status, 'revision': row.revision, 'created_at': row.created_at,
            'data': {key: value for key, value in body.items() if key != 'lines'},
            'line_count': len(body['lines']), 'pending_line_count': len(remaining),
            'processing_status': 'PARTIAL' if any(amounts.values()) else 'PENDING',
            'first_item_name': remaining[0]['item_name'],
        })
    items = pending[offset:offset + limit]
    add_summaries(db, items)
    return {
        'total': len(pending), 'items': items, 'limit': limit, 'offset': offset,
        'stock_totals': [{'unit': unit, 'quantity': inventory.text(value)}
                         for unit, value in sorted(totals.items()) if value != 0],
    }
