from copy import deepcopy
from io import BytesIO
import importlib

import openpyxl
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from test_customer_order_ledger import db, engine
from test_customer_order_zuru_unified import args, po_book, data
from app.services.auth import AuthContext, AuthGrantContext


def actor(*, read=True, export=True, factory='huaxing', department='sales-business'):
    codes = frozenset(f'customer_order:{key}' for key, enabled in [('read', read), ('export', export)] if enabled)
    return AuthContext(id='local-test', username='local-test', display_name='测试业务员', roles=('test',), role_codes=('test',),
        permissions=codes, factory_scopes=(factory,), department_scopes=(department,),
        grants=(AuthGrantContext(role_id='test', role_name='test', factory_id=factory, department=department, permissions=codes),))


@pytest.fixture
def client(monkeypatch):
    api = importlib.import_module('app.api.customer_order')
    auth = importlib.import_module('app.services.auth')
    authz = importlib.import_module('app.services.business_authz')
    get_db = importlib.import_module('app.db').get_db
    audit = importlib.import_module('app.models.customer_order').CustomerOrderExportAudit
    monkeypatch.setattr(authz.settings, 'authz_mode', 'enforce')
    monkeypatch.setattr(authz, 'add_auth_audit', lambda *a, **k: None)
    database = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    audit.__table__.create(database)
    app = FastAPI()
    app.include_router(api.router)
    with Session(database) as session:
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[auth.get_current_user] = lambda: actor(factory='huaxing')
        with TestClient(app) as c:
            c.test_app = app
            yield c
    database.dispose()


def uploads(book=None):
    p = args(book)
    return [('po_files', p['po_files'][0]), ('schedule_file', (p['schedule_file_name'], p['schedule_content']))]


def test_real_worker_http_preview_export_audit_and_stale_source(client):
    fields = dict(factory_id='huaxing', received_date='2026-10-29')
    files = uploads()
    response = client.post('/api/customer-orders/zuru/preview-batch', data=fields, files=files)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['customer_code'] == 'zuru' and preview['summary']['total'] == 2
    export = dict(fields, confirmed='true', preview_fingerprint=preview['preview_fingerprint'])
    response = client.post('/api/customer-orders/zuru/export-batch', data=export, files=files)
    assert response.status_code == 200, response.text
    assert response.headers['x-export-audit-id'].startswith('customer-order-export-')
    workbook = openpyxl.load_workbook(BytesIO(response.content))
    assert workbook['ITEM表']['E5'].value == '4500999001-10'
    changed = po_book()
    changed.active['AE15'] = 'OTHER-TERMINAL'
    response = client.post('/api/customer-orders/zuru/export-batch', data=export, files=uploads(changed))
    assert response.status_code == 409, response.text


@pytest.mark.parametrize('user,route', [
    (actor(factory='huaxing', read=False), 'preview'), (actor(factory='huakang-a'), 'preview'),
    (actor(factory='huaxing', department='pmc-warehouse'), 'preview'), (actor(factory='huaxing', export=False), 'export'),
])
def test_real_api_respects_scope_and_permission(client, user, route):
    auth = importlib.import_module('app.services.auth')
    client.test_app.dependency_overrides[auth.get_current_user] = lambda: user
    response = client.post(f'/api/customer-orders/zuru/{route}-batch',
        data=dict(factory_id='huaxing', received_date='2026-10-29', confirmed='true'), files=uploads())
    assert response.status_code == 403, response.text


def test_real_api_rejects_invalid_source_with_client_error(client):
    book = po_book()
    book.active['A16'] = 10
    response = client.post('/api/customer-orders/zuru/preview-batch',
        data=dict(factory_id='huaxing', received_date='2026-10-29'), files=uploads(book))
    assert response.status_code == 400 and '重复' in response.text


def test_zuru_ledger_import_is_idempotent_preserves_identity_and_rejects_conflicts(db):
    unified = importlib.import_module('app.services.customer_order_unified')
    ledger = importlib.import_module('app.services.customer_order_ledger')
    p = unified.create_unified_customer_preview(**args())
    def save(preview):
        return ledger.import_preview(db, preview=preview, files=[('PO.xlsx', data(po_book()), 'formal')],
            source_kind='formal', actor='synthetic-test', reason='已核对订单', controls={})
    first = save(p)
    db.commit()
    assert first['created_count'] == 2
    assert {r['product_no'] for r in first['items']} == {'9560-S001', '9560-S004-MB'}
    assert {r['factory_id'] for r in first['items']} == {'huaxing'}
    assert save(p)['existing_count'] == 2
    changed = deepcopy(p)
    changed['rows'][0]['quantity'] = '104'
    with pytest.raises(HTTPException) as error:
        save(changed)
    assert error.value.status_code == 409


@pytest.mark.parametrize('route', ['preview', 'export'])
def test_huakang_a_cannot_use_zuru_unified_entry(client, route):
    auth = importlib.import_module('app.services.auth')
    client.test_app.dependency_overrides[auth.get_current_user] = lambda: actor(factory='huakang-a')
    response = client.post(f'/api/customer-orders/zuru/{route}-batch',
        data=dict(factory_id='huakang-a', received_date='2026-11-04', confirmed='true'), files=uploads())
    assert response.status_code == 400, response.text
    assert '华兴' in response.text
