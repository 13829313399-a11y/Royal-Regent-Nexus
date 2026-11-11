"""Library read cost and freshness; disposable databases, no production writes."""
from unittest.mock import Mock

import pytest

from test_carton_asset_quick import BASE, F, enable, ok, schedule, upload
from test_carton_item_schedule import _prepare_schedule_customer, source_row
from test_molding_sample_api import make_client, login_as


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (tmp_path / 'bootstrap.db').as_posix())
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    for name in ('TEMP', 'TMP', 'TMPDIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setenv(name, str(directory))


def test_unassociated_library_and_detail_do_not_scan_schedules(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin'); enable(monkeypatch)
        originals = [ok(upload(client, text=f'unassociated {index}', association='NONE')) for index in range(4)]
        from app.services import carton_asset_targets as targets
        scan = Mock(side_effect=AssertionError('Unassociated sources must not scan factory schedules'))
        monkeypatch.setattr(targets, 'schedules', scan)
        result = ok(client.get(BASE, params=F))
        assert result['total'] == len(originals)
        assert {row['id'] for row in result['items']} == {row['id'] for row in originals}
        assert all(row['targets'] == [] for row in result['items'])
        assert ok(client.get(BASE + '/' + originals[0]['id'], params=F)) == originals[0]
        scan.assert_not_called()


def test_library_reuses_one_scan_and_refreshes_after_reimport(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        original_batch = schedule(client, [source_row(contract='LIB-READ', item='LIB-ITEM')])
        login_as(client, 'admin'); enable(monkeypatch)
        originals = [ok(upload(client, text=f'linked {index}', contract_number='LIB-READ')) for index in range(3)]
        unassociated = ok(upload(client, association='NONE'))
        from app.services import carton_asset_targets as targets
        scan = Mock(wraps=targets.schedules)
        monkeypatch.setattr(targets, 'schedules', scan)

        def listing():
            scan.reset_mock()
            result = ok(client.get(BASE, params=F))
            assert result['total'] == 4
            assert scan.call_count == 1
            assert scan.call_args.args[1] == F['factory_id']
            return {row['id']: row for row in result['items']}

        first = listing()
        for asset in [*originals, unassociated]:
            assert first[asset['id']] == asset
        assert first[originals[0]['id']]['targets'][0]['id'] == original_batch['id']
        # A new HTTP read must not reuse the previous read's schedule snapshot.
        new_batch = schedule(client, [source_row(contract='OTHER', item='OTHER'),
                                      source_row(contract='LIB-READ', item='LIB-ITEM')])
        assert new_batch['id'] != original_batch['id']
        fresh = listing()
        assert all(fresh[asset['id']]['targets'][0]['id'] == new_batch['id'] for asset in originals)
        # Cross-import ambiguity retains the canonical rejection, not stale links.
        schedule(client, [source_row(contract='LIB-READ', item='LIB-ITEM'), source_row(contract='LIB-READ', item='LIB-ITEM')])
        ambiguous = listing()
        assert all(row['targets'] == [] for row in ambiguous.values())


def test_regular_order_library_does_not_scan_schedules(monkeypatch):
    from test_carton_supplier_portal import setup_portal
    from test_carton_supplier_asset_status import internal_asset
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        asset = internal_asset(client, order)
        from app.services import carton_asset_targets as targets
        scan = Mock(side_effect=AssertionError('Purchase-order sources must not scan factory schedules'))
        monkeypatch.setattr(targets, 'schedules', scan)
        row = next(row for row in ok(client.get(BASE, params=F))['items'] if row['id'] == asset['id'])
        assert any(target['kind'] == 'REGULAR' and target['id'] == order['id'] for target in row['targets'])
        scan.assert_not_called()


def test_supplier_list_reuses_order_choices_and_refreshes_after_revocation(monkeypatch):
    from uuid import uuid4
    from test_carton_supplier_portal import setup_portal, supplier_login, revoke_supplier_permission
    with make_client(monkeypatch) as client:
        from app.services import carton_asset_targets as targets, carton_procurement as core
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        choices = ok(client.get(BASE + '/candidates', params={**F, 'owner_department': 'sales-business'}))['items']
        chosen = next(row for row in choices if row['id'] == order['id'])
        ref = {key: chosen[key] for key in ('kind', 'id', 'sheet', 'row', 'fingerprint')}
        sources = [ok(upload(client, text=f'linked {i}', association='MANUAL', targets=[ref], sharing_mode='SUPPLIER')) for i in range(3)]
        sources.append(ok(upload(client, text='unassociated', association='NONE', sharing_mode='SUPPLIER')))
        ok(upload(client, text='internal', association='NONE', sharing_mode='INTERNAL'))
        supplier_login(client)
        candidates = Mock(wraps=targets.candidates)
        monkeypatch.setattr(targets, 'candidates', candidates)
        schedule_state = Mock(side_effect=AssertionError('No schedule targets in these originals'))
        monkeypatch.setattr(core, 'schedule_order_state', schedule_state)
        listed = ok(client.get(BASE, params={**F, 'owner_department': 'supplier'}))['items']
        assert {row['id'] for row in listed} == {row['id'] for row in sources}
        assert candidates.call_count == 1
        schedule_state.assert_not_called()
        # Standalone details remain fresh and byte-for-byte equal to list items.
        for row in listed:
            assert ok(client.get(BASE + '/' + row['id'], params={**F, 'supplier_view': True})) == row
        login_as(client, 'admin')
        for asset in sources:
            ok(client.post(BASE + '/' + asset['id'] + '/audience', params=F, json=dict(
                revision=asset['revision'], request_id=uuid4().hex, sharing_mode='INTERNAL')))
        supplier_login(client)
        candidates.reset_mock()
        assert ok(client.get(BASE, params={**F, 'owner_department': 'supplier'}))['items'] == []
        candidates.assert_not_called()
        assert client.get(BASE + '/' + sources[0]['id'], params={**F, 'supplier_view': True}).status_code == 404
        assert client.get(BASE + '/' + sources[0]['id'], params={'factory_id': 'huadeng', 'supplier_view': True}).status_code in {403, 404}
        revoke_supplier_permission()
        supplier_login(client, expect_read=False)
        assert client.get(BASE, params={**F, 'owner_department': 'supplier'}).status_code == 403


def test_supplier_list_with_empty_order_choices_builds_once_per_request(monkeypatch):
    from test_carton_supplier_portal import setup_portal, supplier_login
    with make_client(monkeypatch) as client:
        from app.services import carton_asset_targets as targets
        setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        sources = [ok(upload(client, text=f'unbound {i}', association='NONE', sharing_mode='SUPPLIER')) for i in range(3)]
        supplier_login(client)
        # No eligible order choices is a legitimate result, not a cache miss.
        choices = Mock(return_value=[])
        monkeypatch.setattr(targets, 'candidates', choices)
        for _ in range(2):
            choices.reset_mock()
            rows = ok(client.get(BASE, params={**F, 'owner_department': 'supplier'}))['items']
            assert {row['id'] for row in rows} == {row['id'] for row in sources}
            assert all(row['targets'] == [] for row in rows)
            assert choices.call_count == 1


def test_schedule_source_still_resolves_its_explicit_purchase(monkeypatch):
    from test_carton_supplier_portal import setup_portal, supplier_login
    from test_carton_procurement_api import _order_payload, _submit_order
    with make_client(monkeypatch) as client:
        unrelated = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        batch = schedule(client, [source_row()])
        row = next(x for x in ok(client.get(BASE + '/candidates', params={**F,
            'owner_department': 'sales-business', 'target_scope': 'PENDING_SCHEDULE'}))['items'] if x['kind'] == 'SCHEDULE')
        asset = ok(upload(client, contract_number='53135', target_scope='PENDING_SCHEDULE'))
        payload = {**_order_payload(), 'contract_no': '53135', 'item_no': '0040220-1', 'customer_po': '0989551378',
            'product_order_quantity': 360, 'customer_due_date': '2026-09-17',
            'schedule_source': {'batch_id': batch['id'], 'source_sheet': row['sheet'], 'source_row': row['row']}}
        order = _submit_order(client, ok(client.post('/api/carton-procurement/orders', json=payload)))
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.services import carton_asset_targets as targets, carton_procurement as core
        evidence = Mock(wraps=core._schedule_order_link_evidence)
        monkeypatch.setattr(core, '_schedule_order_link_evidence', evidence)
        with SessionLocal() as db:
            assert targets.source_purchase_order_ids(db, db.get(CartonMarkAsset, asset['id'])) == {order['id']}
        assert evidence.call_count == 1
        supplier_login(client)
        result = next(x for x in ok(client.get(BASE, params={**F, 'owner_department': 'supplier'}))['items'] if x['id'] == asset['id'])
        assert {x['id'] for x in result['targets']} == {order['id']}
        assert unrelated['id'] not in {x['id'] for x in result['targets']}
