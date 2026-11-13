"""Full rejection observations and warehouse follow-up on the original delivery."""
import json
from collections import Counter, defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.material_handover import HandoverEvent
from app.services import material_handover as handover


FOLLOWUP = 'REJECTION_FOLLOWUP'


def project_observation(detail, followups=None):
    observation = detail.get('receipt_observation')
    if not observation:
        return None
    followups = followups or {}
    splits_per_line = Counter(part['line_id'] for part in detail['selections']['lines'])
    lines = []
    for line in observation['lines']:
        parts = line['parts']
        line_id = line['line_id']
        # A direct net receipt may have no observation for its split.
        if len(parts) == splits_per_line[line_id]:
            counted = sum(Decimal(part['counted_quantity']) for part in parts)
            rejected = sum(Decimal(part['rejected_quantity']) for part in parts)
            if counted > 0 and counted == rejected:
                line = {**line, 'full_rejection': {
                    'rejected_quantity': handover.inventory.text(rejected),
                    'followup': followups.get((observation['request_id'], line_id)),
                }}
        lines.append(line)
    return {**observation, 'lines': lines}


def observations_by_document(db, document_ids):
    observations = defaultdict(list)
    if not document_ids:
        return observations
    rows = db.execute(select(HandoverEvent.document_id, HandoverEvent.kind, HandoverEvent.detail_json).where(
        HandoverEvent.factory_id == handover.FACTORY,
        HandoverEvent.document_id.in_(document_ids),
        HandoverEvent.kind.in_(('POST', FOLLOWUP)),
    ).order_by(HandoverEvent.document_id, HandoverEvent.revision.desc()))
    followups = defaultdict(dict)
    for document_id, kind, raw in rows:
        detail = json.loads(raw)
        if kind == FOLLOWUP:
            key = (detail['observation_request_id'], detail['line_id'])
            followups[document_id].setdefault(key, detail['followup'])
        elif observation := project_observation(detail, followups[document_id]):
            observations[document_id].append(observation)
    return observations


def rejection_summary(observations):
    resolved = None
    for observation in observations:
        for line in observation['lines']:
            rejection = line.get('full_rejection')
            if not rejection:
                continue
            status = (rejection['followup'] or {}).get('status')
            summary = {'rejected_quantity': rejection['rejected_quantity'], 'unit': line['unit'], 'status': status}
            if status != 'RESOLVED':
                return summary
            resolved = resolved or summary
    return resolved


def add_summaries(db, items):
    by_document = observations_by_document(db, [item['id'] for item in items
        if item['status'] == 'CONFIRMED' and item['data']['kind'] == 'DELIVERY'])
    for item in items:
        if summary := rejection_summary(by_document.get(item['id'], [])):
            item['receipt_rejection'] = summary


def add_observations(result, observations):
    if observations:
        result['receipt_observations'] = observations
    if summary := rejection_summary(observations):
        result['receipt_rejection'] = summary


def record_followup(db, actor, identifier, payload):
    from app.services.material_handover_receipts import can_review

    access = handover.staff(actor, 'operate')
    handover.ensure_schema(db)
    handover.inventory.procurement.lock_factory(db)
    signature = handover.request_signature(FOLLOWUP, identifier, payload)
    previous = handover.replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous

    row = handover.document(db, access, identifier, lock=True)
    handover.check_revision(row, payload.expected_revision)
    if row.status != 'CONFIRMED' or json.loads(row.data_json)['kind'] != 'DELIVERY':
        raise HTTPException(409, '只能处理已确认送货单的全拒收记录')
    observations = observations_by_document(db, [identifier])[identifier]
    observation_id = str(payload.observation_request_id)
    rejection = next((line.get('full_rejection') for observation in observations
                      if observation['request_id'] == observation_id for line in observation['lines']
                      if line['line_id'] == payload.line_id), None)
    if rejection is None:
        raise HTTPException(422, '未找到本单的全拒收记录，请刷新后核对')

    row.revision += 1
    row.updated_at = handover.business_now().isoformat()
    followup = {'status': payload.status, 'reason': payload.reason, 'actor_name': access.name, 'recorded_at': row.updated_at}
    rejection['followup'] = followup
    detail = {'observation_request_id': observation_id, 'line_id': payload.line_id, 'followup': followup}
    db.flush()
    result = handover.output(db, row, with_receipt_review=can_review(actor))
    add_observations(result, observations)
    handover.event(db, access, row, FOLLOWUP, payload.request_id, signature, detail, result)
    db.commit()
    return result
