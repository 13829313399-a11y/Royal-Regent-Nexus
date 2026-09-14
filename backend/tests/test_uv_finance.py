"""Synthetic UV ledger/API tests. PostgreSQL runs use an explicitly isolated database."""
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api import uv_finance as api, uv_printing as core_api
from app.models import uv_finance as m, uv_printing as cm
from app.models import uv_handover, uv_ingest  # noqa: F401: complete UV FK graph for standalone test runs
from app.services import uv_finance as f, uv_printing as core
from app.services.auth import AuthContext, AuthGrantContext, get_current_user
from app.services.permission_codes import UV_PRINTING_PERMISSION_CODES


def user(*permissions):
    codes = frozenset('uv_printing:' + p for p in permissions)
    grant = AuthGrantContext(role_id='synthetic', role_name='Synthetic', factory_id='huakang-a', department='production', permissions=codes)
    return AuthContext(id='uv-finance-test', username='uv-finance-test', display_name='Synthetic', roles=('synthetic',),
          role_codes=('synthetic',), permissions=codes, factory_scopes=('huakang-a',), department_scopes=('production',),
          grants=(grant,), active_permission_codes=frozenset(UV_PRINTING_PERMISSION_CODES))


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = os.environ.get('UV_FINANCE_TEST_DATABASE_URL', f'sqlite:///{tmp_path / "finance.db"}')
    if not url.startswith('sqlite:'):
        assert url == 'postgresql+psycopg://uv_dev@127.0.0.1:55432/rr_uv_finance'
    engine = create_engine(url)
    tables = [t for t in m.Base.metadata.sorted_tables if t.name.startswith('uv_')]
    m.Base.metadata.drop_all(engine, tables=tables)
    m.Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(api.settings, 'uv_printing_enabled', True)
    monkeypatch.setattr(api.settings, 'authz_mode', 'enforce')
    app = FastAPI()
    app.include_router(core_api.router)
    app.include_router(api.router)
    identity = {'user': user(*(p.split(':')[1] for p in UV_PRINTING_PERMISSION_CODES))}
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[api.get_db] = db
    app.dependency_overrides[get_current_user] = lambda: identity['user']
    with TestClient(app) as c:
        c.engine, c.identity = engine, identity
        yield c
    engine.dispose()


def post(c, path, payload, status=200, operation=None):
    r = c.post('/api/uv-printing' + path, json={'factory_id': 'huakang-a', 'operation_id': operation or uuid4().hex,
               'expected_version': 0, **payload})
    assert r.status_code == status, r.text
    return r.json()['data'] if status == 200 else r.json()


def get(c, path, **scope):
    r = c.get('/api/uv-printing' + path, params={'factory_id': 'huakang-a', **scope})
    assert r.status_code == 200, r.text
    return r.json()['data']


def sku(c, supplier='Supplier A'):
    return post(c, '/ink-skus', {'supplier': supplier, 'material': 'hard', 'color': 'White', 'package_ml': '500', 'threshold_ml': '200'})['entity']


def movement(c, ident, kind='purchase_in', qty='1000', **overrides):
    payload = dict(sku_id=ident, kind=kind, quantity_ml=qty, bottle_input=None, occurred_on='2026-09-13', machine_id=None,
                   purpose='Synthetic test', source_doc='SYNTHETIC', created_by_name='ignored client actor')
    if kind == 'purchase_in':
        payload.update(unit_cost='0.01', currency='HKD')
    payload.update(overrides)
    return post(c, '/ink-movements', payload)['entity']


def test_t28_t29_package_and_sku_dimension(client):
    a, b = sku(client), sku(client, 'Supplier B')
    movement(client, a['id'], bottle_input='2')
    movement(client, a['id'], 'issue_out', '1000', bottle_input='2')
    assert D(get(client, '/ink-balances')['items'][0]['available_ml']) >= 0
    post(client, '/ink-movements', dict(sku_id=b['id'], kind='issue_out', quantity_ml='1', occurred_on='2026-09-13', purpose='x'), 409)
    post(client, '/ink-movements', dict(sku_id=a['id'], kind='purchase_in', quantity_ml='2000', bottle_input='2', occurred_on='2026-09-13', purpose='x'), 422)


def test_t09_t10_retry_and_same_key_conflict(client):
    record = sku(client)
    p = dict(sku_id=record['id'], kind='purchase_in', quantity_ml='1000', occurred_on='2026-09-13', purpose='x', unit_cost='0', currency='HKD')
    first = post(client, '/ink-movements', p, operation='repeat')
    for _ in range(10):
        replay = post(client, '/ink-movements', p, operation='repeat')
        assert replay['entity']['id'] == first['entity']['id'] and replay['replayed']
    post(client, '/ink-movements', {**p, 'quantity_ml': '10'}, 409, operation='repeat')
    assert len(get(client, '/ink-movements')['items']) == 1
    assert D(get(client, '/ink-skus')['items'][0]['unit_cost']) == 0


def test_t31_reversal_preserves_evidence_and_cost(client):
    record = sku(client)
    movement(client, record['id'])
    issued = movement(client, record['id'], 'issue_out', '600')
    reversed_row = post(client, f'/ink-movements/{issued["id"]}/reverse', {'target_id': issued['id'], 'expected_version': 1, 'reason': 'returned'})['entity']
    assert reversed_row['reverses_movement_id'] == issued['id']
    assert D(get(client, '/ink-balances')['items'][0]['available_ml']) == 1000
    assert len(get(client, '/ink-movements')['items']) == 3
    with Session(client.engine) as db:
        costs = f.day_costs(db, 'huakang-a', '2026-09-13')
        assert D(costs['ink_cost']['amount']) == 0


def test_partial_return_and_no_duplicate_return(client):
    record = sku(client)
    movement(client, record['id'])
    issued = movement(client, record['id'], 'issue_out', '600')
    movement(client, record['id'], 'return_in', '200', source_movement_id=issued['id'])
    assert D(get(client, '/ink-balances')['items'][0]['available_ml']) == 600
    post(client, '/ink-movements', dict(sku_id=record['id'], kind='return_in', quantity_ml='401', occurred_on='2026-09-13', purpose='x', source_movement_id=issued['id']), 409)


def test_t05_sensitive_fields_never_returned_in_read_or_replay(client):
    record = sku(client)
    movement(client, record['id'])
    p = dict(sku_id=record['id'], kind='issue_out', quantity_ml='10', occurred_on='2026-09-13', purpose='x')
    post(client, '/ink-movements', p, operation='issue-replay')
    client.identity['user'] = user('read', 'ink_write', 'export')
    for path in ('/ink-skus', '/ink-movements'):
        for item in get(client, path)['items']:
            assert not {'unit_cost', 'amount', 'currency', 'stock_value', 'cost_value'} & item.keys()
    replay = post(client, '/ink-movements', p, operation='issue-replay')
    assert not {'unit_cost', 'amount', 'currency'} & replay['entity'].keys()
    download = client.get('/api/uv-printing/exports/ink_movements', params={'factory_id': 'huakang-a'})
    assert download.status_code == 200
    assert 'unit_cost' not in download.text and 'amount' not in download.text
    assert client.get('/api/uv-printing/expenses', params={'factory_id': 'huakang-a'}).status_code == 403


@pytest.mark.parametrize('authz_mode', ['legacy', 'shadow', 'enforce'])
def test_t03_permissions_and_disabled_switch(client, monkeypatch, authz_mode):
    monkeypatch.setattr(api.settings, 'authz_mode', authz_mode)
    client.identity['user'] = user('read')
    post(client, '/ink-skus', {'supplier': 'A', 'material': 'hard', 'color': 'W', 'package_ml': '500'}, 403)
    assert client.get('/api/uv-printing/ink-skus').status_code == 422
    assert client.get('/api/uv-printing/ink-skus', params={'factory_id': 'huakang-b'}).status_code == 403
    monkeypatch.setattr(api.settings, 'uv_printing_enabled', False)
    assert client.get('/api/uv-printing/ink-skus', params={'factory_id': 'huakang-a'}).status_code == 503


def test_t33_month_allocation_exact_and_history_preserved(client):
    p = dict(month='2026-09', working_days=['2026-09-01', '2026-09-02', '2026-09-03'], allocation_method='working_days',
             rent={'currency': 'HKD', 'amount': '100.00'}, utilities=None, management_wage=None, note='Explicit test dates')
    original = post(client, '/monthly-policies/2026-09', p)['entity']
    with Session(client.engine) as db:
        rows = list(db.scalars(select(m.UvPolicyAllocation).where(m.UvPolicyAllocation.policy_id == original['id']).order_by(m.UvPolicyAllocation.business_date)))
        assert [v.amount for v in rows] == [D('33.34'), D('33.33'), D('33.33')]
    post(client, '/monthly-policies/2026-09', {**p, 'expected_version': 1, 'rent': {'currency': 'HKD', 'amount': '0'}})
    with Session(client.engine) as db:
        assert len(list(db.scalars(select(m.UvMonthlyPolicy)))) == 2


def test_t35_mixed_currency_and_missing_cost_not_zero(client):
    for code in ('HKD', 'CNY'):
        post(client, '/expenses', dict(category='tooling', occurred_on='2026-09-13', period='2026-09', currency=code,
                 amount='100', evidence='synthetic-' + code, note=''))
    with Session(client.engine) as db:
        costs = f.day_costs(db, 'huakang-a', '2026-09-13')
        assert costs['expense_amount'] is None and costs['ink_cost'] is None
        assert set(costs['by_currency']) == {'HKD', 'CNY'}


def test_t27_pricing_formula_and_zero_uncomputable(client):
    p = dict(currency='HKD', daily_hours='10', board_hours='0.5', pieces_per_board='20', labor_cost_per_day='200',
             ink_cost_per_day='80', markup_rate='0.4', target_margin_rate='0.4', loss_rate=None)
    result = post(client, '/pricing/preview', p)
    assert D(result['pieces_per_day']) == 400
    assert D(result['direct_unit_cost']) == D('.7')
    assert D(result['markup_price']) == D('.98')
    assert D(result['target_margin_price']) == D('1.166667')
    assert post(client, '/pricing/preview', {**p, 'board_hours': '0'})['direct_unit_cost'] is None


def test_t40_closed_period_rejects_backdated_writes(client):
    with Session(client.engine) as db:
        db.add(m.UvPeriod(**f.base('huakang-a', 'synthetic', period='2026-09', reason='synthetic closure', snapshot={})))
        db.commit()
    post(client, '/expenses', dict(category='tooling', occurred_on='2026-09-13', period='2026-09', currency='HKD',
         amount='100', evidence='synthetic', note=''), 409)


def test_t38_import_preview_atomic_apply_and_retry(client):
    content = b'product_no,name\n000123,Synthetic UV\n'
    r = client.post('/api/uv-printing/imports', data={'factory_id': 'huakang-a', 'kind': 'products'}, files={'file': ('test.csv', content, 'text/csv')})
    assert r.status_code == 200, r.text
    batch = r.json()['data']
    assert get(client, '/products')['total'] == 0
    mapped = post(client, f'/imports/{batch["id"]}/mapping', dict(expected_version=1, mapping={'product_no': 'product_no', 'name': 'name'}))['entity']
    assert mapped['errors'] == []
    applied = post(client, f'/imports/{batch["id"]}/apply', {'expected_version': 2})['entity']
    assert applied['status'] == 'applied'
    post(client, f'/imports/{batch["id"]}/apply', {'expected_version': 2})
    assert get(client, '/products')['items'][0]['product_no'] == '000123'
    assert get(client, '/products')['total'] == 1


def test_t38_invalid_row_rolls_back_whole_import(client):
    content = b'product_no,name\n000123,Synthetic UV\n000123,Duplicate conflict\n'
    r = client.post('/api/uv-printing/imports', data={'factory_id': 'huakang-a', 'kind': 'products'}, files={'file': ('bad.csv', content, 'text/csv')})
    batch = r.json()['data']
    post(client, f'/imports/{batch["id"]}/mapping', dict(expected_version=1, mapping={'product_no': 'product_no', 'name': 'name'}))
    post(client, f'/imports/{batch["id"]}/apply', {'expected_version': 2}, 409)
    assert get(client, '/products')['total'] == 0


def test_t30_real_postgres_concurrent_issue(client):
    if client.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL concurrency proof requires UV_FINANCE_TEST_DATABASE_URL')
    record = sku(client)
    movement(client, record['id'])
    def issue(index):
        with Session(client.engine) as db:
            try:
                result = core.execute(db, 'huakang-a', 'concurrent', 'ink-movement-create', dict(factory_id='huakang-a',
                    operation_id=f'concurrent-{index}', sku_id=record['id'], kind='issue_out', quantity_ml='600', occurred_on='2026-09-13', purpose='synthetic concurrency'))
                db.commit()
                return result
            except f.HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, [1, 2]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert results.count(409) == 1
    assert D(get(client, '/ink-balances')['items'][0]['available_ml']) == 400


def test_reversal_after_currency_change_rejected_and_reverse_order_allowed(client):
    record = sku(client)
    purchase = movement(client, record['id'], qty='100', unit_cost='1')
    issue = movement(client, record['id'], 'issue_out', '100')
    movement(client, record['id'], qty='100', unit_cost='2', currency='CNY')
    post(client, f'/ink-movements/{issue["id"]}/reverse', {'expected_version': 1, 'reason': 'different currency'}, 409)
    assert D(get(client, '/ink-balances')['items'][0]['available_ml']) == 100
    other = sku(client, 'Supplier reverse sequence')
    original = movement(client, other['id'])
    issued = movement(client, other['id'], 'issue_out', '100')
    post(client, f'/ink-movements/{issued["id"]}/reverse', {'expected_version': 1, 'reason': 'undo issue'})
    post(client, f'/ink-movements/{original["id"]}/reverse', {'expected_version': 1, 'reason': 'undo purchase'})
    balances = {r['sku_id']: r['available_ml'] for r in get(client, '/ink-balances')['items']}
    assert D(balances[other['id']]) == 0


def test_quote_adoption_is_commercial_only_and_zero_version(client):
    product = post(client, '/products', {'product_no': 'quote-only', 'name': 'Synthetic quote'})['entity']
    p = dict(currency='HKD', daily_hours='10', board_hours='0.5', pieces_per_board='20', labor_cost_per_day='200',
             ink_cost_per_day='80', markup_rate='0.4', target_margin_rate='0.4', loss_rate=None)
    quote = post(client, '/pricing-quotes', {'label': 'Synthetic', 'product_id': product['id'], 'input': p, 'note': ''})['entity']
    post(client, f'/pricing-quotes/{quote["id"]}/adopt', dict(expected_version=1, rate_kind='piece_wage', effective_from='2026-09-14'), 422)
    rate = post(client, f'/pricing-quotes/{quote["id"]}/adopt', dict(expected_version=1, rate_kind='commercial', effective_from='2026-09-14'))['entity']
    assert D(rate['unit_price']) == D('.98')


def test_reversed_manual_fixed_expense_can_be_replaced_by_policy(client):
    row = post(client, '/expenses', dict(category='rent', occurred_on='2026-09-13', period='2026-09', currency='HKD',
              amount='100', evidence='synthetic rent', note=''))['entity']
    p = dict(month='2026-09', working_days=['2026-09-13'], allocation_method='working_days', rent={'amount': '100', 'currency': 'HKD'}, utilities=None, management_wage=None)
    post(client, '/monthly-policies/2026-09', p, 409)
    post(client, f'/expenses/{row["id"]}/reverse', dict(expected_version=1, reason='moved to monthly policy'))
    assert post(client, '/monthly-policies/2026-09', p)['entity']['rent']['amount'] == '100.00'


def test_pg_two_actors_import_same_preloaded_batch_once(client):
    if client.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL interleaving required')
    from threading import Barrier
    record = sku(client)
    content = f'sku_id,kind,quantity_ml,occurred_on,purpose\n{record["id"]},purchase_in,1000,2026-09-13,Synthetic\n'.encode()
    response = client.post('/api/uv-printing/imports', data={'factory_id': 'huakang-a', 'kind': 'ink_movements'}, files={'file': ('atomic.csv', content, 'text/csv')})
    batch = response.json()['data']
    mapping = {k: k for k in ('sku_id', 'kind', 'quantity_ml', 'occurred_on', 'purpose')}
    post(client, f'/imports/{batch["id"]}/mapping', dict(expected_version=1, mapping=mapping))
    barrier = Barrier(2)
    def apply_as(index):
        with Session(client.engine) as db:
            stale = db.get(m.UvImportBatch, batch['id'])
            assert stale.status == 'previewed'
            barrier.wait(timeout=10)
            result = core.execute(db, 'huakang-a', f'actor-{index}', 'import-apply', dict(factory_id='huakang-a',
                 operation_id=f'apply-{index}', expected_version=2, target_id=batch['id']))
            db.commit()
            return result['entity']['applied_ids']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply_as, [1, 2]))
    assert results[0] == results[1]
    assert get(client, '/ink-movements')['total'] == 1
    assert D(get(client, '/ink-balances')['items'][0]['available_ml']) == 1000


def test_payroll_confirmation_freezes_sources_and_adjustments_count_once(client):
    from test_uv_printing import masters, rate, report
    refs = masters(client)
    rate(client, refs, 'commercial', '1')
    rate(client, refs, 'piece_wage', '.2')
    source = report(client, refs)
    batch = post(client, '/payroll-batches', dict(date_from='2026-09-13', date_to='2026-09-13', reason='synthetic payroll'))['entity']
    assert batch['snapshot']['batch_total']['amount'] == '20.00'
    post(client, f'/payroll-batches/{batch["id"]}/confirm', dict(expected_version=1, reason='confirmed synthetic'))
    post(client, f'/payroll-batches/{batch["id"]}/adjustments', dict(expected_version=2, business_date='2026-09-14', reason='invalid nested input', lines=['bad']), 422)
    post(client, f'/production-reports/{source["id"]}/void', dict(report_id=source['id'], expected_version=source['version'], reason='cannot rewrite salary'), 409)
    post(client, f'/payroll-batches/{batch["id"]}/adjustments', dict(expected_version=2, business_date='2026-09-14', reason='explicit extra amount',
         lines=[dict(worker_id=refs['worker_ids'][0], currency='HKD', amount='3')]))
    preview = get(client, '/payroll/preview', date_from='2026-09-14', date_to='2026-09-14')
    assert preview['batch_total']['amount'] == '3.00'
    assert preview['lines'][0]['state'] == 'adjusted'
    post(client, '/payroll-batches', dict(date_from='2026-09-14', date_to='2026-09-14'), 409)


def test_policy_nested_invalid_inputs_are_422(client):
    payload = dict(month='2026-09', working_days=[{}], allocation_method='working_days', rent=None, utilities=None, management_wage=None)
    post(client, '/monthly-policies/2026-09', payload, 422)
    post(client, '/monthly-policies/2026-09', {**payload, 'working_days': ['2026-09-13'], 'rent': []}, 422)
    assert get(client, '/monthly-policies/2026-09') is None
    post(client, '/exports/reports', {'scope': []}, 422)
    post(client, '/exports/reports', {'scope': {'factory_id': 'huakang-a', 'date_from': 'not-a-date'}}, 422)


def test_purchase_only_dates_do_not_pollute_operating_totals(client):
    from test_uv_printing import masters, rate, report
    refs = masters(client)
    rate(client, refs, 'commercial', '1')
    rate(client, refs, 'piece_wage', '.2')
    report(client, refs)
    stock = sku(client)
    opening = movement(client, stock['id'], occurred_on='2026-09-14')
    daily = get(client, '/reports/daily-projection', date_from='2026-09-01', date_to='2026-09-30')['items']
    assert [v['business_date'] for v in daily] == ['2026-09-13']
    month = get(client, '/reports/monthly', date_from='2026-09-01', date_to='2026-09-30')['months'][0]
    assert month['output_value']['amount'] == '100.00' and month['payroll_amount']['amount'] == '20.00'
    post(client, f'/ink-movements/{opening["id"]}/reverse', dict(expected_version=1, reason='synthetic purchase reversal'))
    assert len(get(client, '/reports/daily-projection')['items']) == 1


def test_sunday_production_survives_explicit_nonworking_calendar(client):
    from test_uv_printing import masters, report
    refs = masters(client)
    report(client, refs)
    post(client, '/monthly-policies/2026-09', dict(month='2026-09', working_days=['2026-09-14'],
         allocation_method='working_days', rent=None, utilities=None, management_wage=None))
    sunday = get(client, '/reports/daily-projection', business_date='2026-09-13')['items'][0]
    assert sunday['good_qty'] == 100 and sunday['planned_day_off'] and sunday['off_plan_production']


def test_import_source_arrays_preview_uses_business_validation_without_writes(client):
    import csv, io, json
    from test_uv_printing import masters
    refs = masters(client)
    with Session(client.engine) as db:
        job = cm.UvJob(factory_id='huakang-a', machine_id=refs['machine_id'], product_id=refs['product_id'],
             process_version_id=refs['process_version_id'], source_job_id='import-source', source_event_id='import-event',
             connector_id='synthetic', generation='1', raw_task_name='Synthetic', state='completed', raw_count=100,
             raw_unit='piece', suggested_piece_qty=100)
        db.add(job); db.commit(); job_id = job.id
    payload = {**refs, 'business_date': '2026-09-13', 'shift': 'day', 'reported_qty': 60, 'good_qty': 60,
               'defective_qty': 0, 'pending_qty': 0, 'semi_finished_qty': 0,
               'source_allocations': [{'job_id': job_id, 'piece_qty': 60, 'job_version': 1}], 'evidence_job_ids': []}
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(payload)); writer.writeheader()
    writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in payload.items()})
    upload = client.post('/api/uv-printing/imports', data={'factory_id': 'huakang-a', 'kind': 'production_reports'},
             files={'file': ('source.csv', output.getvalue().encode(), 'text/csv')}).json()['data']
    mapped = post(client, f'/imports/{upload["id"]}/mapping', dict(expected_version=1, mapping={k: k for k in payload}))['entity']
    assert mapped['errors'] == []
    assert get(client, '/production-reports')['total'] == 0
    assert get(client, '/jobs')['items'][0]['available_piece_qty'] == 100
    post(client, f'/imports/{upload["id"]}/apply', dict(expected_version=2))
    draft = get(client, '/production-reports')['items'][0]
    assert draft['status'] == 'draft' and draft['source_allocations'][0]['piece_qty'] == 60
    assert get(client, '/jobs')['items'][0]['available_piece_qty'] == 100
