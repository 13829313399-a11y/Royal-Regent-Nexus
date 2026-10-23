import json
from test_molding_sample_api import make_client, login_as

BASE = '/api/carton-procurement'


def test_history_summaries_details_pagination_and_factory_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonImportBatch, CartonAuditEvent, CartonReceipt
        with SessionLocal() as db:
            for index in range(11):
                factory = 'huaxing' if index < 10 else 'huakang-a'
                db.add(CartonImportBatch(id=f'B-{index:02}', factory_id=factory, import_type='INSPECTION_SCHEDULE',
                    original_filename=f'排期-{index:02}.xlsx', source_sha256=f'{index:064}', import_profile='',
                    parse_summary_json=json.dumps({'row_count': 500, 'schedule_customer': {'customer_code': 'C1'},
                        'rows': [{'source': 'large-original-' * 1000}], 'private_snapshot': 'snapshot-' * 1000}),
                    imported_by='admin', imported_by_name='管理员', created_at=f'2026-10-{index+1:02}T08:00:00+08:00'))
                db.add(CartonAuditEvent(id=f'CAE-REQ-{index:02}', factory_id=factory, event_type='ORDER_CREATED', entity_type='carton_order',
                    entity_id=f'O-{index}', detail_json=json.dumps({'request': {'secret': 'transport'}, 'note': 'detail-' * 1000}),
                    actor_user_id='admin', actor_name='管理员', created_at=f'2026-10-{index+1:02}T08:00:00+08:00'))
                db.add(CartonReceipt(id=f'R-{index:02}', factory_id=factory, receipt_no=f'CR-{index}', delivery_note_no=f'DN-{index}',
                    delivery_date=f'2026-10-{index+1:02}', acceptance_date=f'2026-10-{index+1:02}', supplier_id='test-supplier',
                    supplier_name_snapshot='测试供应商', status='POSTED', created_by='admin', created_by_name='管理员',
                    created_at=f'2026-10-{index+1:02}', updated_at=f'2026-10-{index+1:02}'))
            db.commit()
        params = {'factory_id': 'huaxing', 'summary_only': True, 'limit': 3}
        response = client.get(BASE + '/imports', params={**params, 'import_type': 'INSPECTION_SCHEDULE', 'customer_code': 'C1'})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['total'] == 10 and len(data['items']) == 3
        assert len(response.content) < 5000
        assert data['items'][0]['id'] == 'B-09'
        assert data['items'][0]['detail_loaded'] is False
        assert 'rows' not in data['items'][0]['parse_summary']
        second = client.get(BASE + '/imports', params={**params, 'import_type': 'INSPECTION_SCHEDULE', 'offset': 3}).json()
        assert not set(x['id'] for x in data['items']) & set(x['id'] for x in second['items'])
        detail = client.get(BASE + '/imports/B-09', params={'factory_id': 'huaxing'}).json()
        assert detail['parse_summary']['rows'] and detail['detail_loaded']
        assert client.get(BASE + '/imports/B-10', params={'factory_id': 'huaxing'}).status_code == 404
        assert client.get(BASE + '/imports', params={**params, 'search': '排期-03'}).json()['total'] == 1
        assert client.get(BASE + '/imports', params={**params, 'customer_code': 'missing'}).json()['total'] == 0

        response = client.get(BASE + '/audit-events', params={**params, 'event_type': 'ORDER_CREATED'})
        assert response.status_code == 200, response.text
        assert len(response.content) < 5000
        assert all(item['detail'] == {} and item['detail_loaded'] is False for item in response.json()['items'])
        detail = client.get(BASE + '/audit-events/CAE-REQ-09', params={'factory_id': 'huaxing'}).json()
        assert detail['detail']['note'] and 'request' not in detail['detail']
        assert client.get(BASE + '/audit-events/CAE-REQ-10', params={'factory_id': 'huaxing'}).status_code == 404

        response = client.get(BASE + '/receipt-history', params={'factory_id': 'huaxing', 'limit': 3})
        assert response.status_code == 200, response.text
        assert response.json()['total'] == 10
        assert len(response.json()['items']) == 3 and 'lines' not in response.json()['items'][0]
        assert client.get(BASE + '/receipt-history', params={'factory_id': 'huaxing', 'date_from': '2026-10-09'}).json()['total'] == 2
        assert client.get(BASE + '/receipts/R-09', params={'factory_id': 'huaxing'}).status_code == 200
        assert client.get(BASE + '/receipts/R-10', params={'factory_id': 'huaxing'}).status_code == 404
        assert client.get(BASE + '/receipt-history', params={'factory_id': 'huaxing', 'date_from': 'bad'}).status_code == 422


def test_import_history_filters_by_types_status_and_business_date(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonImportBatch
        with SessionLocal() as db:
            for identifier, kind, status, created_at in [
                ('W-1', 'WEEKLY_SCHEDULE', 'REQUIRES_REVIEW', '2026-09-01T08:00:00+08:00'),
                ('W-2', 'WEEKLY_SCHEDULE', 'REJECTED', '2026-09-05T08:00:00+08:00'),
                ('I-1', 'INSPECTION_SCHEDULE', 'REQUIRES_REVIEW', '2026-09-03T08:00:00+08:00'),
            ]:
                db.add(CartonImportBatch(id=identifier, factory_id='huaxing', import_type=kind,
                    original_filename=f'{identifier}.xlsx', source_sha256=(identifier * 24)[:64], import_profile='',
                    status=status, imported_by='admin', imported_by_name='管理员', created_at=created_at,
                    parse_summary_json=json.dumps({'row_count': 1, 'review_count': 2, 'change_counts': {'NEW': 1},
                        'schedule_customer': {'customer_code': 'C1', 'customer_name': '客户一'}, 'rows': []})))
            db.commit()

        base = {'factory_id': 'huaxing', 'summary_only': True}
        both = client.get(BASE + '/imports', params={**base, 'import_types': 'WEEKLY_SCHEDULE,INSPECTION_SCHEDULE'})
        assert both.status_code == 200, both.text
        assert both.json()['total'] == 3
        assert [item['id'] for item in both.json()['items']] == ['W-2', 'I-1', 'W-1']
        summary = both.json()['items'][1]['parse_summary']
        assert summary['review_count'] == 2 and summary['change_counts'] == {'NEW': 1}
        assert client.get(BASE + '/imports', params={**base, 'import_types': 'WEEKLY_SCHEDULE'}).json()['total'] == 2
        assert client.get(BASE + '/imports', params={**base, 'import_types': 'WEEKLY_SCHEDULE', 'status': 'ACTIVE'}).json()['total'] == 1
        rejected = client.get(BASE + '/imports', params={**base, 'import_types': 'WEEKLY_SCHEDULE', 'status': 'REJECTED'}).json()
        assert [item['id'] for item in rejected['items']] == ['W-2']
        ranged = client.get(BASE + '/imports', params={**base, 'import_types': 'WEEKLY_SCHEDULE,INSPECTION_SCHEDULE',
            'date_from': '2026-09-02', 'date_to': '2026-09-04'}).json()
        assert [item['id'] for item in ranged['items']] == ['I-1']
        assert client.get(BASE + '/imports', params={**base, 'import_types': 'UNKNOWN'}).status_code == 422
        assert client.get(BASE + '/imports', params={**base, 'status': 'UNKNOWN'}).status_code == 422
        assert client.get(BASE + '/imports', params={**base, 'date_from': '2026-9-1'}).status_code == 422
        assert client.get(BASE + '/imports', params={**base, 'date_from': '2026-09-05', 'date_to': '2026-09-01'}).status_code == 422
