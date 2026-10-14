"""Scoped fixtures only; never touch business files or an existing store."""
from decimal import Decimal
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import openpyxl
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text, inspect
from app.db import get_db
from app.services.auth import get_current_user
from app.services import customer_order_products as products, customer_order_unified as unified, customer_order_dickie as dickie
from app.services.customer_order_manual import decorate_manual_resolution_policy
from app.schemas.customer_order_products import ProductSave
from app.models.customer_order_products import OrderProductChange as Change, OrderProductExportEvidence as Evidence
from app.models.customer_order import CustomerOrderExportAudit as Audit
from app.models.customer_order_ledger import OrderLedgerLine as Line
from app.api import customer_order as orders, customer_order_ledger as ledger, customer_order_products as api
from test_customer_order_ledger import engine, db, user
from test_customer_order_huaxing_unified import template, data
TEST_SCHEDULE = data(template('dickie'))


def migration():
    path = Path(__file__).parents[1] / 'alembic/versions/20261014_0161_customer_order_products.py'
    spec = importlib.util.spec_from_file_location('product_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def store(db):
    with Operations.context(MigrationContext.configure(db.connection())):
        migration().upgrade()
    db.execute(text('CREATE TABLE auth_users (id VARCHAR(64) PRIMARY KEY)'))
    db.execute(text("INSERT INTO auth_users VALUES ('test-user')"))
    Audit.__table__.create(db.connection())
    db.commit()
    return db


def choice(**changes):
    out = dict(product_no='000123', item_sheet_name='ITEM表', product_name_zh='测试产品',
               product_name_en='DEFAULT NAME', default_pack='24', reason='业务确认分类正确')
    out.update(changes); return out


def save(db, **changes):
    item = choice(); item.update(expected_revision=products.snapshot(db)['revision'], active=True); item.update(changes)
    return ledger.transaction(db, lambda: products.save(db, ProductSave(**item), '业务员 (test-user)'))


def args(wb=None):
    return dict(customer_code='dickie', factory_id='huaxing', received_date='2026-10-14',
                po_files=[('PO.pdf', b'%PDF-test')], schedule_file_name='schedule.xlsx', schedule_content=data(wb or template('dickie')))


@pytest.fixture
def po(monkeypatch):
    monkeypatch.setattr(dickie, 'parse_dickie_pdf_orders', lambda *a, **k: [dickie.DickieParsedOrder(
        reference_no='SC700123456-1000', master_contract='500056789-10', po_no='300012345-10', product_no='000123',
        product_name_en='CURRENT PO NAME', quantity=Decimal('480'), unit_price_hkd=Decimal('24.10'), packing='0/12',
        ship_date='2027-06-14', source_date='2026-10-02', customer_name='TEST BUYER', country='德国')])


@pytest.fixture
def client(store, monkeypatch, po):
    from app.services import business_authz
    monkeypatch.setattr(business_authz.settings, 'authz_mode', 'enforce')
    monkeypatch.setattr(business_authz, 'add_auth_audit', lambda *a, **k: None)
    app = FastAPI(); app.include_router(api.router); app.include_router(orders.router); app.include_router(ledger.router)
    app.dependency_overrides[get_db] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: user(['read', 'write', 'export', 'audit_read'])
    monkeypatch.setattr(orders, 'refresh_product_user', lambda req, db: app.dependency_overrides[get_current_user]())
    async def job(fn, *a, db=None, **k):
        if db is not None: db.rollback()
        return fn(*a, **k)
    monkeypatch.setattr(orders, 'run_order_job', job); monkeypatch.setattr(ledger, 'run_order_job', job)
    with TestClient(app) as client:
        client.test_app = app
        yield client


def form(choices=None):
    return dict(factory_id='huaxing', received_date='2026-10-14', product_choices=json.dumps(choices or [], ensure_ascii=False))


def files():
    return [('po_files', ('PO.pdf', b'%PDF-test', 'application/pdf')),
            ('schedule_file', ('schedule.xlsx', TEST_SCHEDULE, 'application/octet-stream'))]


def test_additive_migration_immutable_rule_history_and_safe_downgrade(store):
    assert products.TABLES.issubset(inspect(store.bind).get_table_names())
    assert store.scalar(select(func.count()).select_from(Line)) == 0
    save(store)
    with pytest.raises(Exception, match='immutable'):
        store.execute(text('DELETE FROM customer_order_product_changes'))
    store.rollback()
    with Operations.context(MigrationContext.configure(store.connection())):
        with pytest.raises(RuntimeError, match='Retained'): migration().downgrade()


def test_updating_cannot_overwrite_another_version_or_old_order(store):
    save(store)
    with pytest.raises(HTTPException) as exc: save(store, expected_revision=0, product_name_zh='不能覆盖')
    assert exc.value.status_code == 409
    assert products.snapshot(store)['products']['000123']['product_name_zh'] == '测试产品'
    save(store, product_name_zh='修订产品'); save(store, active=False)
    events = store.scalars(select(Change).order_by(Change.revision)).all()
    assert len(events) == 3 and events[1].data['before']['product_name_zh'] == '测试产品'
    assert not events[2].data['after']['active']
    assert store.scalar(select(func.count()).select_from(Line)) == 0


def test_one_off_classification_three_sheet_links_and_PO_priority(store, po):
    a = args(); original = a['schedule_content']; registry = products.snapshot(store)
    initial = unified.create_unified_customer_preview(**a, product_registry=registry)
    assert initial['summary']['blocked'] == 1
    decorate_manual_resolution_policy(initial)
    assert not next(i for i in initial['rows'][0]['issues'] if i['code'] == 'unmapped_item_sheet')['can_skip']
    output, _, parsed = unified.export_unified_customer_schedule(**a, product_registry=registry, product_choices=[choice()])
    assert parsed['summary']['blocked'] == 0
    row = parsed['rows'][0]
    assert row['product_name_en'] == 'CURRENT PO NAME' and row['units_per_carton'] == '12'
    assert row['quantity'] == '480' and row['requested_ship_date'] == '2027-06-14'
    assert row['unit_price_hkd'] == '24.1' and row['product_name_zh'] == '测试产品'
    book = openpyxl.load_workbook(BytesIO(output))
    assert book['ITEM表']['H4'].value == '000123'
    assert any('ITEM表' in str(c.value) for c in book['接单表']['J'])
    assert any('ITEM表' in str(c.value) for c in book['正单评审表']['J'])
    assert openpyxl.load_workbook(BytesIO(original))['ITEM表']['H4'].value is None
    assert products.snapshot(store)['revision'] == 0


def test_saved_rule_matches_next_batch_and_disabled_rule_stops_matching(store, po):
    save(store)
    parsed = unified.create_unified_customer_preview(**args(), product_registry=products.snapshot(store))
    assert parsed['summary']['blocked'] == 0
    assert parsed['product_registration']['applied'][0]['origin'] == '已保存货号规则'
    save(store, active=False)
    assert unified.create_unified_customer_preview(**args(), product_registry=products.snapshot(store))['summary']['blocked'] == 1


def test_updated_defaults_can_replace_history_fallback_not_explicit_PO_fields(store, po, monkeypatch):
    original = dickie.parse_dickie_pdf_orders('PO.pdf', b'%PDF-test')[0]
    original.packing = ''; original.product_name_en = ''
    monkeypatch.setattr(dickie, 'parse_dickie_pdf_orders', lambda *a, **k: [original])
    wb = template('dickie'); s = wb['ITEM表']
    s['H4'], s['I4'], s['J4'], s['L4'] = '000123', '旧中文', 'OLD ENGLISH', 12
    save(store)
    row = unified.create_unified_customer_preview(**args(wb), product_registry=products.snapshot(store))['rows'][0]
    assert row['product_name_zh'] == '测试产品' and row['product_name_en'] == 'DEFAULT NAME'
    assert row['units_per_carton'] == '24'
    assert row['quantity'] == '480' and row['requested_ship_date'] == '2027-06-14'
    assert s['I4'].value == '旧中文' and s['L4'].value == 12


def test_conflicting_or_missing_classification_cannot_be_skipped(store, po):
    save(store)
    wb = template('dickie'); wb['恐龙蛋口水车Iteam表']['H4'] = '000123'; a = args(wb)
    parsed = unified.create_unified_customer_preview(**a, product_registry=products.snapshot(store))
    assert any(i['code'] == 'product_rule_conflict' for i in parsed['rows'][0]['issues'])
    decorate_manual_resolution_policy(parsed)
    keys = {i['skip_key'] for i in parsed['rows'][0]['issues']}
    with pytest.raises(unified.CustomerOrderUnifiedError, match='分类'):
        unified.export_unified_customer_schedule(**a, product_registry=products.snapshot(store), skipped_issue_keys=keys)
    assert unified.create_unified_customer_preview(**a, product_registry=products.snapshot(store),
        product_choices=[choice(item_sheet_name='恐龙蛋口水车Iteam表')])['summary']['blocked'] == 0
    wb = template('dickie'); wb.remove(wb['恐龙蛋口水车Iteam表'])
    assert unified.create_unified_customer_preview(**args(wb), product_registry=products.snapshot(store),
        product_choices=[choice(item_sheet_name='恐龙蛋口水车Iteam表')])['summary']['blocked'] == 1


@pytest.mark.parametrize('bad', [dict(default_pack='0'), dict(default_pack='2.5'), dict(product_name_zh='=WEBSERVICE("x")'),
    dict(item_sheet_name='其他客户页'), dict(reason='  '), dict(product_no='=SUM(A1)')])
def test_invalid_rule_values_do_not_write(store, bad):
    body = choice(); body.update(bad)
    with pytest.raises(Exception): products.choices(json.dumps([body]))
    assert products.snapshot(store)['revision'] == 0


def test_inputs_not_current_product_and_duplicate_choices_are_rejected(store, po):
    with pytest.raises(ValueError, match='不属于'):
        unified.create_unified_customer_preview(**args(), product_registry=products.snapshot(store),
                                               product_choices=[choice(product_no='ANOTHER')])
    with pytest.raises(HTTPException): products.choices(json.dumps([choice(), choice()]))


def test_api_permissions_scope_header_and_read_only_no_write(client, store):
    scope = '?factory_id=huaxing&customer_code=dickie'
    assert client.get('/api/customer-order-product-rules' + scope).status_code == 200
    payload = {**choice(), 'expected_revision':0, 'active':True}
    assert client.post('/api/customer-order-product-rules' + scope, json=payload).status_code == 403
    client.headers['X-Order-Product-Rules'] = '1'
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'export'])
    assert client.post('/api/customer-order-product-rules' + scope, json=payload).status_code == 403
    assert not client.get('/api/customer-order-product-rules' + scope).json()['can_write']
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'write'], factory='huakang-a')
    assert client.get('/api/customer-order-product-rules' + scope).status_code == 403
    assert client.get('/api/customer-order-product-rules?factory_id=huakang-a&customer_code=green-toys').status_code == 400
    assert products.snapshot(store)['revision'] == 0


def test_export_only_account_cannot_read_rules_even_via_file_worker(client, monkeypatch):
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['export'])
    async def unexpected(*a, **k):
        raise AssertionError('Must deny before loading rules or running the file worker')
    monkeypatch.setattr(orders, 'run_order_job', unexpected)
    response = client.post('/api/customer-orders/dickie/export-batch', data={**form(), 'confirmed':'true'}, files=files())
    assert response.status_code == 403


def test_http_preview_export_and_ledger_share_rule_controls(client, store):
    controls = form([choice()])
    response = client.post('/api/customer-orders/dickie/preview-batch', data=controls, files=files())
    assert response.status_code == 200, response.text
    p = response.json(); assert p['summary']['blocked'] == 0
    body = {**controls, 'confirmed':'true','preview_fingerprint':p['preview_fingerprint']}
    out = client.post('/api/customer-orders/dickie/export-batch', data=body, files=files())
    assert out.status_code == 200, out.text
    proof = store.get(Evidence, out.headers['X-Export-Audit-ID'])
    assert proof.data['applied'][0]['rule']['item_sheet_name'] == 'ITEM表'
    assert store.scalar(select(func.count()).select_from(Line)) == 0
    result = client.post('/api/customer-order-ledger/imports/dickie', data=body, files=files())
    assert result.status_code == 200, result.text
    assert store.scalar(select(func.count()).select_from(Line)) == 1
    line = store.scalar(select(Line))
    assert line.data['import_controls']['product_registration']['choices'][0]['product_no'] == '000123'
    assert products.snapshot(store)['revision'] == 0


def test_rule_change_invalidates_old_preview_without_saving_or_exporting(client, store):
    controls = form([choice()])
    p = client.post('/api/customer-orders/dickie/preview-batch', data=controls, files=files()).json()
    save(store, default_pack='48')
    body = {**controls, 'confirmed':'true','preview_fingerprint':p['preview_fingerprint']}
    for path in ('/api/customer-orders/dickie/export-batch', '/api/customer-order-ledger/imports/dickie'):
        response = client.post(path, data=body, files=files())
        assert response.status_code == 409, response.text
    assert store.scalar(select(func.count()).select_from(Audit)) == 0
    assert store.scalar(select(func.count()).select_from(Line)) == 0


def test_unmigrated_old_reads_work_but_one_off_cannot_bypass(db, po):
    assert not products.snapshot(db)['available']
    assert unified.create_unified_customer_preview(**args(), product_registry=products.snapshot(db))['summary']['blocked'] == 1
    with pytest.raises(ValueError, match='迁移'):
        unified.create_unified_customer_preview(**args(), product_registry=products.snapshot(db), product_choices=[choice()])


def test_update_during_export_rejected_before_new_order_write(store):
    snap = products.snapshot(store); save(store)
    with pytest.raises(HTTPException) as exc:
        ledger.transaction(store, lambda: products.ensure_current(store, snap))
    assert exc.value.status_code == 409
    assert store.scalar(select(func.count()).select_from(Line)) == 0


def test_existing_order_data_and_versions_are_unchanged_when_catalog_changes(store):
    from test_customer_order_ledger import ingest
    from app.models.customer_order_ledger import OrderLedgerVersion
    line = ingest(store)
    original = json.dumps(line.data, sort_keys=True)
    versions = store.scalar(select(func.count()).select_from(OrderLedgerVersion))
    save(store)
    store.expire_all()
    assert json.dumps(store.get(Line, line.id).data, sort_keys=True) == original
    assert store.scalar(select(func.count()).select_from(OrderLedgerVersion)) == versions


def test_permissions_revoked_during_file_job_prevent_export_and_order_save(client, store, monkeypatch):
    async def revoke(fn, *a, db=None, **k):
        db.rollback()
        result = fn(*a, **k)
        client.test_app.dependency_overrides[get_current_user] = lambda: user(['read'])
        return result
    p = client.post('/api/customer-orders/dickie/preview-batch', data=form([choice()]), files=files()).json()
    body = {**form([choice()]), 'confirmed':'true', 'preview_fingerprint':p['preview_fingerprint']}
    monkeypatch.setattr(orders, 'run_order_job', revoke)
    assert client.post('/api/customer-orders/dickie/export-batch', data=body, files=files()).status_code == 403
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'write', 'export'])
    monkeypatch.setattr(ledger, 'run_order_job', revoke)
    assert client.post('/api/customer-order-ledger/imports/dickie', data=body, files=files()).status_code == 403
    assert store.scalar(select(func.count()).select_from(Audit)) == 0
    assert store.scalar(select(func.count()).select_from(Line)) == 0


def test_two_connections_cannot_overwrite_catalog_with_same_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine('sqlite:///' + str(tmp_path / 'rules.db'), connect_args={'check_same_thread':False})
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)): migration().upgrade()
    barrier = Barrier(2)
    def write(name):
        with Session(engine) as db:
            barrier.wait()
            try:
                ledger.transaction(db, lambda: products.save(db, ProductSave(**choice(product_name_zh=name), expected_revision=0, active=True), name))
                return 'saved'
            except HTTPException as exc: return exc.status_code
    try:
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(write, ['甲产品', '乙产品']))
        assert sorted(str(r) for r in results) == ['409', 'saved']
        with Session(engine) as db:
            assert products.snapshot(db)['revision'] == 1
            assert db.scalar(select(func.count()).select_from(Change)) == 1
    finally: engine.dispose()
