"""Conservative, read-only matching of schedule identities to purchase orders."""
from collections import Counter, defaultdict

from app.services.carton_schedule_tracking import identity, normalized, linked_po_matches


def solve(rows, orders, links, *, factory_id):
    """Match validated links first, then real customer PO, then legacy SO values.

    Ambiguous candidate IDs are evidence for review, never an order association.
    Callers must separately handle quantity/packing evidence for PO-less orders.
    """
    def source_scope(row):
        return (normalized(row.get('factory_id') or factory_id), normalized(row.get('schedule_customer_code')), normalized(row.get('contract_no')),
                normalized(row.get('item_no')))

    def order_scope(order):
        return (normalized(order.get('factory_id') or factory_id), normalized(order.get('customer_code')), normalized(order.get('contract_no')),
                normalized(order.get('item_no')))

    grouped = defaultdict(list)
    for row in rows:
        key = row.get('schedule_identity') or identity(row)
        if key and all(source_scope(row)) and (factory_id is None or row.get('factory_id', factory_id) == factory_id):
            grouped[key].append(row)
    usable = {o['id']: o for o in orders if o.get('id') and (factory_id is None or o.get('factory_id') == factory_id)
              and o.get('status') != 'CANCELLED' and not o.get('deleted_at')}
    matches, ambiguous = {}, {}
    orders_by_po = defaultdict(list)
    for order in usable.values():
        orders_by_po[(order_scope(order), normalized(order.get('customer_po')))].append(order['id'])
    source_actual = defaultdict(set)
    for key, values in grouped.items():
        source_actual[(source_scope(values[0]), normalized(values[0].get('customer_po')))].add(key)
    claims = defaultdict(set)
    # A validated link remains a reservation even when its source is absent
    # from this snapshot; an unrelated current SO cannot inherit that order.
    for key, identifiers in links.items():
        for identifier in dict.fromkeys(identifiers):
            if identifier in usable:
                claims[identifier].add(key)
    for key, values in grouped.items():
        ids = [identifier for identifier in dict.fromkeys(links.get(key, []))
               if key in claims.get(identifier, set()) and order_scope(usable[identifier]) == source_scope(values[0])]
        if ids:
            if (len(values) == 1 and len(ids) == 1 and len(claims[ids[0]]) == 1
                    and (normalized(values[0].get('customer_po')) == normalized(usable[ids[0]].get('customer_po'))
                         if usable[ids[0]].get('source_po_semantics') == 'SOURCE_PO'
                         else linked_po_matches(values[0], usable[ids[0]].get('customer_po')))):
                matches[key] = ids
            else:
                ambiguous[key] = ids

    def available_ids(row, value):
        return [identifier for identifier in orders_by_po.get((source_scope(row), value), ()) if identifier not in claims]

    # Reserve actual-PO claims before considering historical SO-in-PO records.
    actual_edges = {}
    for key, values in grouped.items():
        if key in matches or key in ambiguous:
            continue
        po = normalized(values[0].get('customer_po'))
        actual_edges[key] = available_ids(values[0], po) if po else []
    actual_counts = Counter(identifier for ids in actual_edges.values() for identifier in ids)
    source_legacy = defaultdict(set)
    for key, values in grouped.items():
        if key not in matches and key not in ambiguous:
            so = normalized(values[0].get('source_reference'))
            if so:
                source_legacy[(source_scope(values[0]), so)].add(key)
    for key, ids in actual_edges.items():
        if not ids:
            continue
        competing_so = source_legacy.get((source_scope(grouped[key][0]), normalized(grouped[key][0].get('customer_po'))), set()) - {key}
        if len(grouped[key]) == 1 and len(ids) == 1 and actual_counts[ids[0]] == 1 and not competing_so:
            matches[key] = ids
        else:
            ambiguous[key] = ids

    used = {identifier for ids in actual_edges.values() for identifier in ids}
    used.update(identifier for ids in matches.values() for identifier in ids)
    legacy_edges = {}
    for key, values in grouped.items():
        if key in matches or key in ambiguous:
            continue
        row = values[0]
        so = normalized(row.get('source_reference'))
        if not so:
            continue
        # A source's actual PO takes precedence over a different source's old SO.
        competing_real = bool(source_actual.get((source_scope(row), so), set()) - {key})
        ids = available_ids(row, so)
        if any(usable[identifier].get('source_po_semantics') == 'SOURCE_PO' for identifier in ids):
            # A new order edited to its SO is not historical SO-in-PO evidence.
            ambiguous[key] = ids
            continue
        if competing_real:
            if ids:
                ambiguous[key] = ids
            continue
        legacy_edges[key] = [identifier for identifier in ids if identifier not in used]
    legacy_counts = Counter(identifier for ids in legacy_edges.values() for identifier in ids)
    for key, ids in legacy_edges.items():
        if not ids:
            continue
        if len(grouped[key]) == 1 and len(ids) == 1 and legacy_counts[ids[0]] == 1:
            matches[key] = ids
        else:
            ambiguous[key] = ids
    return {'matches': matches, 'ambiguous': ambiguous}


def read_matches(db, factory_id, incoming_rows=None):
    """Resolve latest factory-wide source evidence, without writing business data."""
    from sqlalchemy import select
    import json
    from app.models.carton_procurement import CartonAuditEvent, CartonOrder
    from app.services import carton_procurement as core, carton_schedule_coverage as coverage

    sources = []
    if incoming_rows is not None:
        sources.append(('', incoming_rows))
    sources.extend((entry['batch'].id, core.import_batch_out(entry['batch']).parse_summary.get('rows', []))
                   for entry in coverage.batches(db, factory_id) if entry['batch'].status != 'REJECTED')
    reviews = coverage.source_reviews(db, factory_id)
    latest, seen = [], set()
    for batch_id, rows in sources:
        groups = defaultdict(list)
        for row in rows:
            if isinstance(row, dict) and row.get('schedule_customer_code') and identity(row):
                groups[row.get('schedule_identity') or identity(row)].append(row)
        for key, group in groups.items():
            if key in seen:
                continue
            seen.add(key)
            if batch_id and reviews.get(key, {}).get('status') == 'NO_LONGER_REQUIRED':
                continue
            latest.extend(dict(row, factory_id=factory_id) for row in group)
    fields = ('id', 'factory_id', 'customer_code', 'contract_no', 'item_no', 'customer_po', 'status', 'deleted_at')
    orders = [dict(row) for row in db.execute(select(*(getattr(CartonOrder, key) for key in fields)).where(
        CartonOrder.factory_id == factory_id, CartonOrder.deleted_at.is_(None), CartonOrder.status != 'CANCELLED')).mappings()]
    semantics = {}
    events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory_id,
        CartonAuditEvent.entity_type == 'schedule_order_link', CartonAuditEvent.event_type == 'SCHEDULE_ORDER_LINKED')
        .order_by(CartonAuditEvent.sequence))
    for event in events:
        try:
            detail = json.loads(event.detail_json or '{}')
        except (ValueError, TypeError):
            continue
        if isinstance(detail, dict) and detail.get('order_id'):
            semantics[detail['order_id']] = detail.get('po_semantics', '')
    for order in orders:
        order['source_po_semantics'] = semantics.get(order['id'], '')
    result = solve(latest, orders, core._schedule_order_links(db, factory_id), factory_id=factory_id)
    result['rows'] = latest
    return result
