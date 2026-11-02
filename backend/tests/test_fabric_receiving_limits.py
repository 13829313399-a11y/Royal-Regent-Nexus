"""Physical delivery limits are distinct from purchase chase and legacy retries."""
import copy
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from test_fabric_batch_receiving import warehouse, body


@pytest.fixture
def v2_receiving(warehouse):
    from test_fabric_procurement import book, row
    from app.services import fabric_procurement as source
    from app.services.fabric_procurement_parser import parse_workbook
    from app.models.warehouse_operations import WarehouseOperation
    engine, actor, _, receiving = warehouse
    WarehouseOperation.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        parsed = parse_workbook('v2.xlsx', book([row(订单号='V2', 订单数量=1000, 入库数量=0, 交货明细='', 采购明细ID='V2')]))
        token = source.preview(db, parsed, actor.id)['preview_token']
        source.apply(db, parsed, actor, 'v2.xlsx', str(uuid4()), token, confirmed=True, acknowledge_excluded=True)
        line = source.list_lines(db, search='V2')['items'][0]
    data = body([line])
    data['items'][0]['batches'][0].update(quantity='960', counted_quantity='980', rejected_quantity='20')
    return engine, actor, line, receiving, data


def test_v2_1000_delivered_980_counted_20_rejected_posts_960_and_owes_40(v2_receiving):
    from decimal import Decimal
    from sqlalchemy import select
    engine, actor, line, receiving, data = v2_receiving
    with Session(engine) as db:
        posted = receiving.receive(db, actor, line['id'], single(data))
        assert {key: posted[key] for key in ('delivered_quantity', 'counted_quantity', 'quantity', 'accepted_quantity', 'shortage_quantity', 'returned_to_supplier')} == {
            'delivered_quantity': '1000', 'counted_quantity': '980', 'quantity': '960', 'accepted_quantity': '960', 'shortage_quantity': '20', 'returned_to_supplier': '20'}
        assert posted['stock_posted'] is True
        assert [item['quantity'] for item in posted['batches']] == ['960']
        assert list(db.scalars(select(receiving.FabricInventoryMovement.quantity))) == ['960']
        evidence = posted['receipt_lines'][0]
        assert evidence['rejected_quantity'] == '20' and evidence['disposition'] == 'RETURNED_TO_SUPPLIER'
        assert evidence['batch_id'] == posted['batches'][0]['id'] and evidence['shortage_scope'] == 'RECEIPT'
        assert Decimal(receiving.receipt_progress(line['facts'], receiving.receipt_context(db)[line['id']])['warehouse_outstanding_quantity']) == 40
        assert receiving.receive(db, actor, line['id'], single(data)) == posted
        changed = copy.deepcopy(data)
        changed['items'][0]['batches'][0].update(quantity='950', rejected_quantity='30')
        with pytest.raises(HTTPException) as caught:
            receiving.receive(db, actor, line['id'], single(changed))
        assert caught.value.status_code == 409


def test_v2_all_unusable_keeps_evidence_count_and_no_stock(v2_receiving, monkeypatch):
    from sqlalchemy import select, func
    from app.services import fabric_receipt_corrections as corrections
    from app.api import fabric_procurement as endpoint
    from app.schemas.fabric_receiving import ReverseReceiptRequest
    engine, actor, line, receiving, data = v2_receiving
    data['items'][0]['batches'][0].update(quantity='0', counted_quantity='1000', rejected_quantity='970', damaged_quantity='20', other_unusable_quantity='10')
    with Session(engine) as db:
        posted = receiving.receive(db, actor, line['id'], single(data))
        assert posted['quantity'] == '0' and posted['stock_posted'] is False and posted['batches'] == []
        assert posted['returned_to_supplier'] == '1000' and posted['receipt_lines'][0]['batch_id'] is None
        assert db.scalar(select(func.count()).select_from(receiving.FabricReceipt)) == 1
        for model in (receiving.FabricStockBatch, receiving.FabricInventoryMovement):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        progress = receiving.receipt_progress(line['facts'], receiving.receipt_context(db)[line['id']])
        assert progress['warehouse_outstanding_quantity'] == '1000' and progress['receipt_count'] == 1
        assert receiving.receive(db, actor, line['id'], single(data)) == posted
        assert corrections.preview(db, posted['id'])['blocked_reason'] == corrections.ZERO_RECEIPT_MESSAGE
        db.rollback()
        # Keep permission tests in the existing API suite; exercise the real reversal endpoint guard here.
        monkeypatch.setattr(endpoint, 'authorize_receipt_reversal', lambda *args: None)
        reverse = ReverseReceiptRequest(factory_id='huakang-c', request_id=uuid4(), expected_revision=0,
            business_date='2026-10-10', reason='核对', confirmed=True)
        for _ in range(2):
            with pytest.raises(HTTPException) as caught:
                endpoint.reverse_receipt(posted['id'], reverse, db, actor)
            assert caught.value.status_code == 422 and caught.value.detail == corrections.ZERO_RECEIPT_MESSAGE
        duplicate = copy.deepcopy(data)
        duplicate['request_id'] = str(uuid4())
        duplicate['items'][0]['expected_receipt_count'] = 1
        with pytest.raises(HTTPException) as caught:
            receiving.receive(db, actor, line['id'], single(duplicate))
        assert caught.value.status_code == 409


def test_v2_split_rolls_bins_and_separate_damage_other_evidence(v2_receiving):
    engine, actor, line, receiving, data = v2_receiving
    item = data['items'][0]
    first = item['batches'][0]
    first.update(quantity='80.1', counted_quantity='100.1', damaged_quantity='10', rejected_quantity='0', other_unusable_quantity='10')
    item['batches'] = [first, {**first, 'location_id': 'fabric-A02', 'location': 'A02'},
        {**first, 'roll_no': '0003', 'quantity': '0', 'counted_quantity': '20'}]
    with Session(engine) as db:
        posted = receiving.receive(db, actor, line['id'], single(data))
        assert posted['quantity'] == '160.2' and posted['counted_quantity'] == '220.2'
        assert posted['damaged_quantity'] == posted['other_unusable_quantity'] == '30'
        assert posted['returned_to_supplier'] == '60' and posted['shortage_quantity'] == '779.8'
        assert len(posted['batches']) == 2 and len(posted['receipt_lines']) == 3


@pytest.mark.parametrize('change', [
    {'counted_quantity': '1001', 'quantity': '981'}, {'quantity': '959'},
    {'counted_quantity': '19', 'quantity': '0'}, {'damaged_quantity': '-1'},
    {'rejected_quantity': ''}, {'other_unusable_quantity': '1e1'}, {'counted_quantity': '0.0000001'},
    {'quantity': '-1'}, {'counted_quantity': 'NaN'},
])
def test_v2_invalid_quantities_leave_no_receipt(v2_receiving, change):
    engine, actor, line, receiving, data = v2_receiving
    data['items'][0]['batches'][0].update(change)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as caught:
            receiving.receive(db, actor, line['id'], single(data))
        assert caught.value.status_code == 422
        db.rollback()
        assert receiving.list_receipts(db)['total'] == 0


def test_v2_duplicates_and_only_accepted_overage_require_reason(v2_receiving):
    engine, actor, line, receiving, data = v2_receiving
    item = data['items'][0]
    item['batches'].append(copy.deepcopy(item['batches'][0]))
    with Session(engine) as db:
        with pytest.raises(HTTPException, match='同缸号'):
            receiving.receive(db, actor, line['id'], single(data))
        db.rollback()
        item['batches'].pop()
        item.update(delivery_quantity='1100')
        item['batches'][0].update(counted_quantity='1050', quantity='1001', rejected_quantity='49')
        with pytest.raises(HTTPException, match='超收说明'):
            receiving.receive(db, actor, line['id'], single(data))
        db.rollback()
        item['batches'][0].update(quantity='1000', rejected_quantity='50')
        assert receiving.receive(db, actor, line['id'], single(data))['quantity'] == '1000'


def test_v2_legacy_quantity_plus_losses_infers_counted(v2_receiving):
    engine, actor, line, receiving, data = v2_receiving
    data['items'][0]['batches'][0].update(counted_quantity='', quantity='10', damaged_quantity='2', rejected_quantity='3', other_unusable_quantity='4')
    with Session(engine) as db:
        posted = receiving.receive(db, actor, line['id'], single(data))
        assert posted['quantity'] == '10' and posted['counted_quantity'] == '19' and posted['returned_to_supplier'] == '9'


def test_v2_reversal_removes_only_accepted_stock_and_keeps_loss_evidence(v2_receiving, monkeypatch):
    from app.services import warehouse_operations as operations, auth
    from app.services import fabric_receipt_corrections as corrections
    from app.schemas.warehouse_operations import WarehouseDocumentRequest
    engine, actor, line, receiving, data = v2_receiving
    monkeypatch.setattr(auth, 'can', lambda *args: True)
    with Session(engine) as db:
        posted = receiving.receive(db, actor, line['id'], single(data))
        evidence = db.get(receiving.FabricReceipt, posted['id']).payload_json
        preview = corrections.preview(db, posted['id'])
        assert preview['can_reverse'] is True and preview['quantity'] == '960'
        request = WarehouseDocumentRequest(factory_id='huakang-c', request_id=uuid4(), expected_revision=preview['expected_revision'],
            kind='CORRECTION', business_date='2026-10-10', original_id='FR-' + posted['id'], reason='核对数量', confirmed=True)
        result = operations.post(db, actor, 'fabric', request)
        assert result['data']['quantity'] == '960'
        assert all(batch['quantity'] == '0' for batch in operations.projection(db, 'fabric')[0].values())
        assert db.get(receiving.FabricReceipt, posted['id']).payload_json == evidence
        reread = receiving.receipt_data(db, db.get(receiving.FabricReceipt, posted['id']))
        assert reread['quantity'] == '960' and reread['reversed'] is True and reread['receipt_lines'] == posted['receipt_lines']
        assert receiving.receipt_progress(line['facts'], receiving.receipt_context(db)[line['id']])['warehouse_outstanding_quantity'] == '1000'


def test_v2_zero_receipt_on_unupgraded_store_has_explicit_upgrade_message(v2_receiving):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from test_fabric_receipt_zero_migration import current
    engine, actor, line, receiving, data = v2_receiving
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            current.downgrade()
    data['items'][0]['batches'][0].update(quantity='0', rejected_quantity='980')
    with Session(engine) as db:
        with pytest.raises(HTTPException) as caught:
            receiving.receive(db, actor, line['id'], single(data))
        assert caught.value.status_code == 503 and '20261023_0176' in caught.value.detail
        db.rollback()
        assert receiving.list_receipts(db)['total'] == 0


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
        for part in old_body['batches']:
            for field in ('counted_quantity', 'damaged_quantity', 'rejected_quantity', 'other_unusable_quantity'):
                part.pop(field)
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
