"""Read-only contract hints for schedule rows, including demand before purchase creation."""
import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonImportBatch
from app.services import carton_mark_assets as assets, carton_mark_sharing as sharing
from app.services.carton_schedule_tracking import effective_po


def schedule_sources(db, factory):
    batches = db.execute(select(CartonImportBatch.id, CartonImportBatch.parse_summary_json).where(
        CartonImportBatch.factory_id == factory, CartonImportBatch.import_type == 'WEEKLY_SCHEDULE',
        CartonImportBatch.status != 'REJECTED')).all()
    result = {}
    for identifier, content in batches:
        summary = json.loads(content or '{}')
        code = (summary.get('schedule_customer') or {}).get('customer_code', '')
        result[identifier] = [{**row, 'schedule_customer_code': row.get('schedule_customer_code') or code}
                              for row in summary.get('rows', []) if isinstance(row, dict)]
    return result


def known_schedule_contracts(db, factory, user):
    from app.services.auth import has_permission_in_scope
    if not any(has_permission_in_scope(user, 'carton_procurement:read', factory, dep)
               for dep in ('carton', 'pmc-warehouse')):
        return set()
    from app.services.carton_customer_assignment import ensure_customer_operation
    result = set()
    for rows in schedule_sources(db, factory).values():
        for row in rows:
            code = row.get('schedule_customer_code')
            if not code:
                continue
            try:
                ensure_customer_operation(db, user, factory, code)
            except HTTPException:
                continue
            if row.get('contract_no'):
                result.add(row['contract_no'])
    return result


def project(rows, sources, orders, files):
    """Explicit order bindings never widen into automatic contract bindings."""
    normalize = lambda value: assets.identity(str(value or ''))
    owners = defaultdict(set)
    for source in sources:
        owners[normalize(source.get('contract_no'))].add(normalize(source.get('schedule_customer_code')))
    for order in orders:
        owners[normalize(order.contract_no)].add(normalize(order.customer_code))
    order_index = {order.id: order for order in orders}
    automatic, explicit = defaultdict(list), []
    for file in files:
        # Upload alone is not confirmation; this hint counts only usable-classified originals.
        if file.workflow.status != 'READY':
            continue
        if file.recognition_source in {'manual_order', 'manual_orders'} or file.bound_order_id:
            explicit.append(file)
        elif file.contract_number:
            automatic[normalize(file.contract_number)].append(file)
    output, selected = [], {}
    for row in rows:
        contract, code = normalize(row.get('contract_no')), normalize(row.get('schedule_customer_code'))
        matched = []
        review = not contract or not code
        candidates = automatic.get(contract, [])
        if candidates:
            if code and owners[contract] == {code}:
                matched.extend(candidates)
            else:
                review = True
        for file in explicit:
            for link in file.orders:
                order = order_index.get(link.id)
                if order and normalize(order.customer_code) == code and normalize(order.contract_no) == contract \
                        and normalize(order.item_no) == normalize(row.get('item_no')) \
                        and (row.get('order_id') == order.id or effective_po(row) == effective_po({'customer_po': order.customer_po})):
                    matched.append(file)
                    break
        identifiers = list(dict.fromkeys(file.id for file in matched))
        selected.update({file.id: file for file in matched})
        output.append(dict(source_sheet=row.get('source_sheet') or '', source_row=row.get('source_row') or 0,
                           status='UPLOADED' if identifiers else 'REVIEW' if review else 'MISSING', asset_ids=identifiers))
    return output, [dict(id=file.id, file_name=file.file_name, usage_status=file.workflow.status)
                    for file in selected.values()]


def workspace(db, user, factory, batch_id):
    sources = schedule_sources(db, factory)
    if batch_id not in sources:
        raise HTTPException(404, '有效的本厂业务排期不存在')
    from app.services.carton_customer_assignment import ensure_customer_operation
    rows = sources[batch_id]
    permitted, restricted = [], []
    for row in rows:
        try:
            if row.get('schedule_customer_code'):
                ensure_customer_operation(db, user, factory, row['schedule_customer_code'])
            permitted.append(row)
        except HTTPException:
            restricted.append(dict(source_sheet=row.get('source_sheet') or '', source_row=row.get('source_row') or 0,
                                   status='RESTRICTED', asset_ids=[]))
    files = sharing.filter_internal(db, user, assets.list_assets(db, factory))
    result, files = project(permitted, [row for rows in sources.values() for row in rows],
                            assets.available_orders(db, factory), files)
    return dict(factory_id=factory, batch_id=batch_id, rows=result + restricted, assets=files)
