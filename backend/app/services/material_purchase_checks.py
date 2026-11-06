"""Read-only, version-bound preparation checks; never net demand or reservations."""
from collections import defaultdict
import json
from fastapi import HTTPException
from sqlalchemy import and_, select
from app.core.time import business_now
from app.models.material_purchase import MaterialPurchase, MaterialPurchaseEvent
from app.services import material_purchase as purchase
from app.services.material_purchase_comparison import latest_comparison
from app.services.transaction_lock import lock_transaction


def summarize(documents, demand_id):
    groups, occurrences = {}, defaultdict(set)
    cancelled = 0
    for doc in documents:
        if doc['data']['demand_id'] != demand_id:
            continue
        if doc['status'] == purchase.CANCELLED:
            cancelled += 1
            continue
        basis = {g['source_key']: g for g in doc['source']['groups']}
        for line in doc['data']['lines']:
            source = basis[line['source_key']]
            source_id = (doc['data']['demand_version'], line['source_key'])
            occurrences[source_id].add(doc['id'])
            change = doc.get('pending_change')
            before_status = change.get('before_status', purchase.APPROVED) if change else None
            # Empty units cannot be assumed identical/comparable across documents.
            key = (*source_id, line['purchase_unit'], doc['status'], before_status or '', '' if line['purchase_unit'] else doc['id'])
            group = groups.setdefault(key, dict(demand_version=source_id[0], source_key=source_id[1], code=source['code'],
                name=source['name'], attribute=source['attribute'], material_version=source['material_version'], source_unit=source['unit'],
                purchase_unit=line['purchase_unit'], status=doc['status'], before_status=before_status, known_quantity=0, missing_quantity_count=0, documents=[]))
            if line['quantity'] is None: group['missing_quantity_count'] += 1
            else: group['known_quantity'] += line['quantity']
            group['documents'].append(dict(id=doc['id'], version=doc['version'], supplier_reference=doc['data']['supplier_reference'],
                quantity=line['quantity'], pending_kind=change['kind'] if change else None,
                proposed_quantity=change['quantities'].get(line['source_key']) if change and change['kind'] == 'QUANTITY' else None))
    rows = []
    for key, group in sorted(groups.items()):
        group['complete_quantity'] = str(group['known_quantity']) if not group['missing_quantity_count'] and group['purchase_unit'] else None
        group['known_quantity'] = str(group['known_quantity'])
        group['related_document_count'] = len(occurrences[key[:2]])
        group['possible_duplicate'] = group['related_document_count'] > 1
        rows.append(group)
    return dict(groups=rows, cancelled_document_count=cancelled)


def read(db, identity, expected_version):
    lock_transaction(db, 'engineering-bom', purchase.FACTORY)
    lock_transaction(db, 'material-plan', purchase.FACTORY)
    lock_transaction(db, 'material-purchase', purchase.FACTORY)
    doc = purchase.view(db, purchase.record(db, identity))
    purchase.trial.bom.require(doc['version'] == expected_version, '采购准备单已更新，请刷新当前版本再核对', 409)
    issue = None
    try:
        purchase.source(db, doc['data']['demand_id'], doc['data']['demand_version'])
    except HTTPException as error:
        if error.status_code not in (404, 409, 422, 503): raise
        issue = error.detail
    # Only current snapshots; historical events must not multiply quantities.
    query = select(MaterialPurchaseEvent).join(MaterialPurchase, and_(MaterialPurchaseEvent.entity_id == MaterialPurchase.id,
        MaterialPurchaseEvent.factory_id == MaterialPurchase.factory_id, MaterialPurchaseEvent.version == MaterialPurchase.version)).where(
        MaterialPurchase.factory_id == purchase.FACTORY)
    summary = summarize([json.loads(e.result_json) for e in db.scalars(query)], doc['data']['demand_id'])
    result = dict(document_id=doc['id'], document_version=doc['version'], demand_id=doc['data']['demand_id'],
        bound_demand_version=doc['data']['demand_version'], checked_at=business_now().isoformat(), source_current=issue is None,
        source_issue=issue, can_release=False, source_comparison=latest_comparison(db, doc), **summary)
    db.rollback()  # release snapshot locks without creating any business evidence
    return result
