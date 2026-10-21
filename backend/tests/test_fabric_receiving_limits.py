"""Physical delivery limits are distinct from purchase chase and legacy retries."""
import copy
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from test_fabric_batch_receiving import warehouse, body


def single(data):
    from app.schemas.fabric_receiving import ReceiveSourceRequest
    return ReceiveSourceRequest(**{key: value for key, value in data.items() if key != 'items'},
        **{key: value for key, value in data['items'][0].items() if key != 'source_line_id'})


def test_split_total_cannot_exceed_delivery_even_with_difference_reason(warehouse):
    engine, actor, lines, receiving = warehouse
    data = body(lines)
    item = data['items'][0]
    item.update(delivery_quantity='0.3', difference_reason='供应商多送')
    part = item['batches'][0]
    item['batches'] = [{**part, 'quantity': '0.1'}, {**part, 'location_id': 'fabric-A02', 'location': 'A02', 'quantity': '0.200001'}]
    with Session(engine) as db:
        with pytest.raises(HTTPException) as caught:
            receiving.receive(db, actor, lines[0]['id'], single(data))
        assert caught.value.status_code == 422 and '到货量' in caught.value.detail
        db.rollback()
        assert receiving.list_stock(db)['total'] == 0
        item['batches'][1]['quantity'] = '0.2'
        posted = receiving.receive(db, actor, lines[0]['id'], single(data))
        assert posted['quantity'] == '0.3' and posted['delivery_quantity'] == '0.3'
        assert len(posted['batches']) == 2
        assert receiving.receive(db, actor, lines[0]['id'], single(data)) == posted


def test_legacy_committed_request_replays_without_new_limit_or_current_zone(warehouse):
    from app.services.fabric_procurement_parser import digest, dump
    from app.models.fabric_master import FabricMasterRecord
    engine, actor, lines, receiving = warehouse
    data = body(lines)
    with Session(engine) as db:
        posted = receiving.receive(db, actor, lines[0]['id'], single(data))
        legacy = copy.deepcopy(data)
        legacy['items'][0].pop('delivery_quantity')
        request = single(legacy)
        old_body = request.model_dump(mode='json')
        for key in ('delivery_quantity', 'unit_price', 'price_unit', 'currency'):
            old_body.pop(key)
        # Represent an already committed pre-upgrade request in this isolated DB.
        record = db.get(receiving.FabricReceipt, posted['id'])
        record.request_hash = digest([actor.id, lines[0]['id'], old_body])
        evidence = json.loads(record.payload_json)
        evidence.pop('delivery_quantity')
        record.payload_json = dump(evidence)
        place = db.get(FabricMasterRecord, 'fabric-A01')
        place.data_json = dump({'warehouse': '布料一仓', 'category': ''})
        db.commit()
        replayed = receiving.receive(db, actor, lines[0]['id'], request)
        assert replayed['id'] == posted['id'] and 'delivery_quantity' not in replayed
        assert receiving.list_stock(db)['total'] == 1
        legacy['request_id'] = str(uuid4())
        legacy['delivery_reference'] = 'NEW-NOTE'
        legacy['items'][0]['expected_receipt_count'] = 1
        legacy['items'][0]['batches'][0].update(location_id='fabric-A02', location='A02')
        with pytest.raises(HTTPException) as caught:
            receiving.receive(db, actor, lines[0]['id'], single(legacy))
        assert caught.value.status_code == 422 and '到货量' in caught.value.detail
        db.rollback()
        assert receiving.list_stock(db)['total'] == 1
