from types import SimpleNamespace as NS

import pytest

from app.services.carton_schedule_marks import project


def source(**values):
    return dict(source_sheet='ITEM', source_row=4, schedule_customer_code='A', contract_no='SC-001',
                item_no='ITEM-1', customer_po='0001') | values


def file(**values):
    return NS(**(dict(id='FILE', contract_number='SC-001', recognition_source='filename', bound_order_id=None,
                     orders=[], file_name='唛头.pdf', workflow=NS(status='READY')) | values))


def order(**values):
    return NS(**(dict(id='ORDER', factory_id='huaxing', customer_code='A', contract_no='SC-001', item_no='ITEM-1',
                     customer_po='0001') | values))


def test_files_uploaded_before_orders_match_all_rows_of_one_customer_contract_without_writes():
    rows = [source(), source(source_row=5, item_no='ITEM-2', customer_po='0002')]
    asset = file()
    result, originals = project(rows, rows, [], [asset])
    assert [row['status'] for row in result] == ['UPLOADED', 'UPLOADED']
    assert len(originals) == 1 and originals[0]['usage_status'] == 'READY'
    assert asset.orders == [] and asset.bound_order_id is None


@pytest.mark.parametrize('other', [source(schedule_customer_code='B'), source(schedule_customer_code='')])
def test_contract_collision_with_another_or_unbound_customer_requires_review(other):
    result, originals = project([source()], [source(), other], [], [file()])
    assert result[0]['status'] == 'REVIEW' and not originals


def test_contract_numbers_match_completely_and_ignore_only_case_width_and_spacing():
    result, _ = project([source(contract_no=' ｓｃ－００１ ')], [source()], [], [file()])
    assert result[0]['status'] == 'UPLOADED'
    result, _ = project([source(contract_no='SC-0010')], [source()], [], [file()])
    assert result[0]['status'] == 'MISSING'


def test_explicit_binding_only_covers_its_customer_item_and_effective_po():
    row = source()
    asset = file(recognition_source='manual_orders', contract_number='', orders=[NS(id='ORDER')])
    placed = order()
    result, _ = project([row], [row, source(schedule_customer_code='B')], [placed], [asset])
    assert result[0]['status'] == 'UPLOADED'
    for changed in [source(item_no='OTHER'), source(customer_po='0002'), source(customer_po=''), source(schedule_customer_code='B')]:
        result, _ = project([changed], [changed], [placed], [asset])
        assert result[0]['status'] == 'MISSING'
    result, _ = project([row], [row], [], [asset])
    assert result[0]['status'] == 'MISSING'  # Deleted/manual selection never falls back to the contract.


def test_historical_versions_are_not_counted_and_ambiguous_sources_are_not_guessed():
    result, files = project([source()], [source()], [], [file(workflow=NS(status='HISTORY'))])
    assert result[0]['status'] == 'MISSING' and files == []
    result, _ = project([source(contract_no=''), source(schedule_customer_code='')], [], [], [file()])
    assert [row['status'] for row in result] == ['REVIEW', 'REVIEW']


@pytest.mark.parametrize('status', ['UNCLASSIFIED', 'DRAFT', 'PENDING', 'HISTORY'])
@pytest.mark.parametrize('manual', [False, True])
def test_only_ready_classification_is_counted_for_contract_and_explicit_order_links(status, manual):
    asset = file(workflow=NS(status=status), **(dict(recognition_source='manual_orders',
        contract_number='', orders=[NS(id='ORDER')]) if manual else {}))
    result, originals = project([source()], [source()], [order()], [asset])
    assert result[0]['status'] == 'MISSING' and result[0]['asset_ids'] == [] and originals == []


def test_mixed_classifications_count_only_confirmed_files():
    result, originals = project([source()], [source()], [], [file(), file(id='DRAFT', workflow=NS(status='DRAFT'))])
    assert result[0]['asset_ids'] == ['FILE'] and [item['id'] for item in originals] == ['FILE']


def test_uploaded_file_cannot_choose_between_customer_codes_on_existing_orders():
    result, files = project([source()], [source()], [order(), order(id='OTHER', customer_code='B')], [file()])
    assert result[0]['status'] == 'REVIEW' and files == []


def test_schedule_api_recognizes_preorder_files_and_rechecks_archive_factory_and_permissions(monkeypatch):
    import importlib
    import json
    from test_molding_sample_api import make_client, login_as
    from test_carton_mark_api import _workbook_bytes
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        db_module = importlib.import_module('app.db')
        model = importlib.import_module('app.models.carton_procurement')
        with db_module.SessionLocal() as db:
            db.add(model.CartonImportBatch(id='PREORDER', factory_id='huaxing', import_type='WEEKLY_SCHEDULE',
                original_filename='schedule.xlsx', source_sha256='s' * 64, status='REQUIRES_REVIEW',
                parse_summary_json=json.dumps({'schedule_customer': {'customer_code': 'A'}, 'rows': [source()]}),
                imported_by='admin', created_at='2026-10-27'))
            db.commit()
        url = '/api/carton-mark/assets/schedule'
        params = dict(factory_id='huaxing', batch_id='PREORDER')
        assert client.get(url, params=params).json()['rows'][0]['status'] == 'MISSING'
        # Contract text in a generically named file is recognized before any purchase exists.
        response = client.post('/api/carton-mark/assets/batch', data={'factory_id': 'huaxing'},
            files=[('files', ('资料.xlsx', _workbook_bytes('SC-001')))])
        assert response.status_code == 200, response.text
        asset = response.json()[0]['asset']
        assert asset and asset['contract_number'] == 'SC-001'
        assert client.get(url, params=params).json()['rows'][0]['status'] == 'MISSING'
        classification_url = f"/api/carton-mark/assets/{asset['id']}/classification"
        for classification, expected in [('READY', 'UPLOADED'), ('PENDING', 'MISSING'), ('READY', 'UPLOADED')]:
            saved = client.put(classification_url, params={'factory_id': 'huaxing'},
                json={'revision': asset['revision'], 'status': classification, 'note': '分类核对'})
            assert saved.status_code == 200, saved.text
            asset = saved.json()
            assert client.get(url, params=params).json()['rows'][0]['status'] == expected
        result = client.get(url, params=params)
        assert result.status_code == 200, result.text
        assert result.json()['rows'][0]['asset_ids'] == [asset['id']]
        assert client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['total'] == 0
        assert client.get(url, params={**params, 'factory_id': 'huakang-a'}).status_code == 404
        assert client.delete(f"/api/carton-mark/assets/{asset['id']}", params={'factory_id': 'huaxing', 'revision': asset['revision']}).status_code == 204
        assert client.get(url, params=params).json()['rows'][0]['status'] == 'MISSING'
        with db_module.SessionLocal() as db:
            db.get(model.CartonImportBatch, 'PREORDER').status = 'REJECTED'; db.commit()
        assert client.get(url, params=params).status_code == 404
        auth = importlib.import_module('app.services.auth')
        for permission in ('carton_mark:read', 'carton_procurement:read'):
            user = auth.AuthContext(id='mark-reader', username='mark-reader', display_name='资料读取',
                roles=('仓管',), role_codes=('carton_warehouse_keeper',), permissions=frozenset({permission}),
                factory_scopes=('huaxing',), department_scopes=('pmc-warehouse',))
            client.app.dependency_overrides[auth.get_current_user] = lambda: user
            assert client.get(url, params=params).status_code == 403
        client.app.dependency_overrides.clear()
