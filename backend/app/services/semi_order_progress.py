"""Project semi-finished progress from explicit release, batch and original-document links."""
from decimal import Decimal

from app.services.warehouse_operations import decimal, text


def add_quantities(groups, item, **amounts):
    key = (item['item_code'], item['process_state'], item['unit'])
    if key not in groups:
        groups[key] = {field: item[field] for field in ('item_code', 'item_name', 'process_state', 'unit')}
    group = groups[key]
    for field, amount in amounts.items():
        group[field] = text(decimal(group.get(field, '0')) + amount)


def order_progress(stock, entries):
    releases = {
        row['id']: {'release_id': row['id'], 'received': Decimal(0), 'stock': {},
                    'processing': {}, 'packaging': {}, 'document_ids': []}
        for row in entries.values() if row['kind'] == 'SEMI_RELEASE' and not row.get('reversed')
    }
    if not releases:
        return []

    for batch in stock.values():
        progress = releases.get(batch.get('release_id'))
        if progress and decimal(batch['quantity']) > 0:
            add_quantities(progress['stock'], batch, quantity=decimal(batch['quantity']))

    for row in reversed(entries.values()):
        data = row['data']
        progress = releases.get(data.get('release_id'))
        if progress is None:
            continue
        progress['document_ids'].append(row['id'])
        if row.get('reversed'):
            continue
        if row['kind'] == 'RECEIPT':
            progress['received'] += decimal(data['quantity'])
        elif row['kind'] == 'PROCESS_SEND':
            outstanding = decimal(data['quantity']) - decimal(row['consumed_quantity'])
            if outstanding > 0:
                add_quantities(progress['processing'], data, quantity=outstanding)
        elif row['kind'] == 'PACK_SEND':
            sent = decimal(data['quantity'])
            received = decimal(row['received_quantity'])
            returned = decimal(row['returned_quantity'])
            add_quantities(progress['packaging'], data, sent=sent, received=received, returned=returned,
                           pending=sent - received - returned)

    rows = []
    for progress in reversed(releases.values()):
        release = entries[progress['release_id']]
        received = progress['received']
        difference = decimal(release['data']['quantity']) - received
        row = {**progress, 'received': text(received), 'pending_receipt': text(max(difference, Decimal(0))),
               'extra_received': text(max(-difference, Decimal(0)))}
        for name in ('stock', 'processing', 'packaging'):
            groups = progress[name]
            row[name] = [groups[key] for key in sorted(groups)]
        rows.append(row)
    return rows
