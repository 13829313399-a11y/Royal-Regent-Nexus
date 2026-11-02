"""Receipt originals remain immutable while Sales corrects private, unposted source rows."""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.indonesia_materials import IndonesiaMaterialRecord as Record
from app.services.indonesia_warehouse_import import parse_warehouse_receipts
from test_indonesia_materials import client, command, workspace, BASE
from test_indonesia_warehouse_import import catalog, source, content, preview, choose, confirm
from test_indonesia_material_ownership import accounts, login
from test_indonesia_warehouse_packing import setup_mixed, mixed_rows, shipment_for


def correct(client, row, values, index=0, **kwargs):
    return command(client, 'warehouse_import_correct', dict(index=index, values=values), row, **kwargs)


@pytest.mark.parametrize('value,expected', [('2026-11-2', '2026-11-02'), ('2026/1/2', '2026-01-02'),
    ('2026-11-02', '2026-11-02'), ('2024-2-29', '2024-02-29'), ('2026-2-29', None), ('2/11/2026', None), ('', None)])
def test_optional_voucher_and_unambiguous_calendar_dates(value, expected):
    parsed = parse_warehouse_receipts(content([source(receipt_no='', actual_date=value)]), 'input.csv')[0]
    assert not any('收料单号' in error for error in parsed['source_issues'])
    if expected:
        assert parsed['source']['actual_date'] == expected and not parsed['source_issues']
    else:
        assert any('实收日期' in error for error in parsed['source_issues'])


def test_no_voucher_posts_once_across_accounts_and_different_upload_context(client, accounts):
    catalog(client)
    raw = source(receipt_no='', actual_date='2026-11-2')
    first = preview(client, raw)
    login(client, accounts, 'bob')
    second = preview(client, raw, warehouse='备用上传上下文')
    assert first['id'] != second['id']
    login(client, accounts, 'alice')
    posted = confirm(client, first)
    assert posted['data']['status'] == 'confirmed'
    login(client, accounts, 'bob')
    current = next(r for r in workspace(client)['records'] if r['id'] == second['id'])
    assert current['data']['rows'][0]['blocked']
    confirm(client, second, [choose(second)], status=409)
    supplies = [r for r in workspace(client)['records'] if r['kind'] == 'supply']
    assert len(supplies) == 1 and supplies[0]['data']['warehouse_source']['receipt_no'] == ''


def test_no_voucher_mixed_carton_is_one_physical_package_and_exportable(client):
    setup_mixed(client)
    rows = [dict(row, receipt_no='', actual_date='2026-11-2') for row in mixed_rows()]
    original = preview(client, *rows)
    group = original['data']['rows'][0]['packing_group']
    assert not group['issues'] and group['row_count'] == 2
    result = confirm(client, original, [choose(original, i) for i in range(2)])
    shipment = shipment_for(client, result)
    assert len(shipment['data']['packages']) == 1
    confirmed = command(client, 'shipment_confirm', {}, shipment)
    assert client.get(BASE + f"/shipments/{confirmed['id']}/export", params={'factory_id': 'huaxing'}).status_code == 200


def test_existing_bad_preview_revalidates_without_reupload_or_database_rewrite(client):
    catalog(client)
    row = preview(client, source(receipt_no='', actual_date='2026-11-2'))
    with Session(client.engine) as db:
        entity = db.get(Record, row['id']); legacy = deepcopy(entity.data)
        legacy.pop('source_sha256', None)
        legacy['rows'][0]['source']['actual_date'] = '2026-11-2'
        legacy['rows'][0].pop('formula_fields', None)
        legacy['rows'][0]['source_issues'] = ['缺少收料单号', '实收日期须为明确的年月日']
        entity.data = legacy; db.commit()
    refreshed = next(r for r in workspace(client)['records'] if r['id'] == row['id'])
    assert not refreshed['data']['rows'][0]['blocked']
    assert refreshed['data']['rows'][0]['source']['actual_date'] == '2026-11-02'
    with Session(client.engine) as db:
        assert db.get(Record, row['id']).data == legacy


def test_correction_retains_original_bytes_history_and_other_rows_then_posts(client):
    catalog(client)
    raw = source(receipt_no='', actual_date='bad-date', material_name='错误名称')
    other = source(receipt_no='SECOND', receipt_line='2')
    original = preview(client, raw, other)
    before = deepcopy(original['data']['rows'][1])
    key = uuid4().hex
    fixed = correct(client, original, dict(actual_date='2026-11-2', material_name='合成螺丝'), operation_id=key)
    assert correct(client, original, dict(actual_date='2026-11-2', material_name='合成螺丝'), operation_id=key) == fixed
    assert fixed['version'] == original['version'] + 1
    assert fixed['data']['rows'][0]['source']['actual_date'] == '2026-11-02'
    assert not fixed['data']['rows'][0]['blocked']
    assert fixed['data']['rows'][0]['original_source']['actual_date'] == 'bad-date'
    assert fixed['data']['rows'][1] == before
    assert len(fixed['data']['source_corrections']) == 1
    assert fixed['data']['source_corrections'][0]['changes']['material_name'] == {'before': '错误名称', 'after': '合成螺丝'}
    response = client.get(BASE + '/assets/' + original['data']['asset_id'], params={'factory_id': 'huaxing'})
    assert response.content == content([raw, other])
    assert not any(r['kind'] in {'supply', 'allocation', 'shipment'} for r in workspace(client)['records'])
    posted = confirm(client, fixed)
    correct(client, posted, {'normal_quantity': '10'}, status=409)
    correct(client, original, {'normal_quantity': '10'}, status=409)
    # Partial imports may still correct their unposted remainder.
    remaining = correct(client, posted, {'warehouse': '来料仓'}, index=1)
    assert remaining['data']['rows'][0]['imported_supply_id']


@pytest.mark.parametrize('values', [{'_file_row_identity': 'fake'}, {'customer': 'another'}, {'factory': 'huadeng'}, {'recipient': 'RRM'}, {'normal_quantity': 12}])
def test_correction_rejects_scope_internal_fields_and_numeric_coercion(client, values):
    catalog(client); row = preview(client)
    correct(client, row, values, status=422)
    current = next(r for r in workspace(client)['records'] if r['id'] == row['id'])
    assert current['version'] == row['version']


def test_invalid_corrections_remain_reviewable_and_cannot_post(client):
    catalog(client); row = preview(client)
    bad = correct(client, row, {'normal_quantity': '-1', 'actual_date': '2026-2-30'})
    assert bad['data']['rows'][0]['blocked'] and len(bad['data']['rows'][0]['issues']) >= 2
    confirm(client, bad, [choose(row)], status=409)


def test_formula_problem_requires_explicit_field_correction_and_keeps_original(client):
    catalog(client)
    row = preview(client, source(actual_date='bad', price='=1/0'))
    date_fixed = correct(client, row, {'actual_date': '2026-11-2'})
    assert any('公式' in issue for issue in date_fixed['data']['rows'][0]['issues'])
    fixed = correct(client, date_fixed, {'price': '0.12345678'})
    assert not fixed['data']['rows'][0]['blocked']
    assert fixed['data']['rows'][0]['original_source']['price'] == '=1/0'
    assert fixed['data']['rows'][0]['source']['price'] == '0.12345678'
    confirm(client, fixed)


def test_source_corrections_obey_ownership_transfer_and_replay_access(client, accounts):
    catalog(client); row = preview(client, source(actual_date='bad'))
    login(client, accounts, 'bob')
    correct(client, row, {'actual_date': '2026-11-2'}, status=404)
    login(client, accounts, 'manager')
    key = uuid4().hex
    updated = correct(client, row, {'actual_date': '2026-11-2'}, operation_id=key)
    assert updated['data']['source_corrections'][0]['actor'] == 'manager'
    moved = command(client, 'draft_transfer', dict(assignee_id='bob', reason='接手核对'), updated)
    login(client, accounts, 'alice')
    correct(client, moved, {'warehouse': '新仓库'}, status=404)
    login(client, accounts, 'bob')
    assert correct(client, moved, {'warehouse': '新仓库'})['version'] == moved['version'] + 1
