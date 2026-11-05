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
        new_batch = schedule(client, [source_row(contract='LIB-READ', item='LIB-ITEM')])
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
