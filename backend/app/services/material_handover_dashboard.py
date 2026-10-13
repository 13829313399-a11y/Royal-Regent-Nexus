"""Read-only receiving reminders, derived from the existing handover and stock ledger."""
import json
from collections import defaultdict

from sqlalchemy import select

from app.models.material_handover import HandoverDocument
from app.services import material_handover as handover


def pending_deliveries(db, limit=50, offset=0):
    inventory = handover.inventory
    stock, entries = inventory.projection(db, 'fabric')
    by_document = defaultdict(dict)
    for identifier, entry in entries.items():
        document_id = entry['data'].get('handover_document_id')
        if document_id:
            by_document[document_id][identifier] = entry

    totals = defaultdict(lambda: inventory.decimal('0'))
    for batch in stock.values():
        totals[batch['unit']] += inventory.decimal(batch['quantity'])

    pending = []
    rows = db.scalars(select(HandoverDocument).where(
        HandoverDocument.factory_id == handover.FACTORY,
        HandoverDocument.status == 'CONFIRMED',
    ).order_by(HandoverDocument.created_at, HandoverDocument.id))
    for row in rows:
        body = json.loads(row.data_json)
        if body['kind'] != 'DELIVERY':
            continue
        amounts, _ = handover.progress(db, row.id, entries=by_document[row.id])
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
    return {
        'total': len(pending), 'items': pending[offset:offset + limit], 'limit': limit, 'offset': offset,
        'stock_totals': [{'unit': unit, 'quantity': inventory.text(value)}
                         for unit, value in sorted(totals.items()) if value != 0],
    }
