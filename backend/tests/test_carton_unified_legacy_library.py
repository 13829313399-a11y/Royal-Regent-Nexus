"""Legacy library compatibility on isolated, disposable SQLite stores."""
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select

from test_molding_sample_api import make_client, login_as
from test_carton_asset_quick import BASE, F, enable, ok, upload, action
from test_carton_supplier_portal import setup_portal, supplier_login, grant_supplier_permissions


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for name in ('TEMP', 'TMP', 'TMPDIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setenv(name, str(directory))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (tmp_path / 'bootstrap.db').as_posix())
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('QC_DEPARTMENT_MANAGED', 'false')


def legacy(identifier, order, mode, *, bound=False):
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset, CartonMarkAssetOrderBinding
    content = ('legacy synthetic ' + identifier).encode()
    with SessionLocal() as db:
        row = CartonMarkAsset(id=identifier, factory_id='huaxing', owner_department=None,
            owner_supplier_id=None, asset_purpose='MATERIAL', file_name=identifier+'.pdf', kind='pdf',
            content_type='application/pdf', content=content, size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(), contract_number=order['contract_no'],
            recognition_source=mode, candidates_json='[]', warning='', revision=1, is_archived=False,
            created_by='user-admin', created_by_name='admin', created_at='2026-01-01', updated_at='2026-01-01')
        if bound:
            row.order_bindings.append(CartonMarkAssetOrderBinding(asset_id=identifier,
                factory_id='huaxing', order_id=order['id']))
        db.add(row)
        db.commit()


def raw(identifier):
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset
    with SessionLocal() as db:
        row = db.get(CartonMarkAsset, identifier)
        return (row.id, row.owner_department, row.owner_supplier_id, row.content, row.sha256,
                row.recognition_source, row.contract_number, row.bound_order_id,
                tuple(sorted(x.order_id for x in row.order_bindings)))


def associate(client, asset):
    return client.post(BASE + '/' + asset['id'] + '/associations', params=F,
        json=dict(revision=asset['revision'], request_id=uuid4().hex, targets=[]))


def audience(client, asset, mode):
    return client.post(BASE + '/' + asset['id'] + '/audience', params=F,
        json=dict(revision=asset['revision'], request_id=uuid4().hex, sharing_mode=mode))


def test_legacy_read_through_and_guard_preserve_automatic_and_manual_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        for identifier, mode, bound in [('legacy-auto', 'order_contract', False),
                                        ('legacy-manual', 'manual_orders', True),
                                        ('legacy-empty', 'manual_orders', False)]:
            legacy(identifier, order, mode, bound=bound)
        before = {identifier: raw(identifier) for identifier in ('legacy-auto', 'legacy-manual', 'legacy-empty')}
        rows = {row['id']: row for row in ok(client.get(BASE, params=F))['items']}
        for identifier in before:
            row = rows[identifier]
            assert row['legacy_source'] is True
            assert row['can_manage_original'] is True
            assert row['can_associate'] is False and row['association_blocker']
            assert {target['id'] for target in row['targets']} == ({order['id']} if identifier != 'legacy-empty' else set())
            assert associate(client, row).status_code == 409
            assert raw(identifier) == before[identifier]


def test_legacy_named_supplier_sharing_revocation_and_write_denial(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        legacy('legacy-shared', order, 'manual_orders')
        original = raw('legacy-shared')
        row = ok(client.get(BASE + '/legacy-shared', params=F))
        shared = ok(audience(client, row, 'SUPPLIER'))
        assert raw('legacy-shared') == original
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        supplier_row = ok(client.get(BASE + '/legacy-shared', params={**F, 'supplier_view': True}))
        assert supplier_row['targets'] == [] and not supplier_row['can_associate']
        assert client.get(BASE + '/legacy-shared/document', params={**F, 'supplier_view': True}).content == original[3]
        assert associate(client, supplier_row).status_code in (403, 404, 409)
        assert raw('legacy-shared') == original
        login_as(client, 'admin')
        revoked = ok(audience(client, shared, 'INTERNAL'))
        assert raw('legacy-shared') == original
        supplier_login(client)
        assert client.get(BASE + '/legacy-shared', params={**F, 'supplier_view': True}).status_code == 404
        assert revoked['sharing_mode'] == 'INTERNAL'


def test_quick_association_rejects_group_and_history_without_mutation(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        grouped = ok(upload(client, association='NONE'))
        history = ok(upload(client, association='NONE', text='historical source'))
        history = ok(action(client, history, 'HISTORY'))
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        with SessionLocal() as db:
            row = db.get(CartonMarkAsset, grouped['id'])
            row.kind = 'image'
            row.photo_group_id = 'synthetic-group'
            db.commit()
        for row in (grouped, history):
            before = raw(row['id'])
            current = ok(client.get(BASE + '/' + row['id'], params=F))
            assert not current['can_associate'] and current['association_blocker']
            assert associate(client, current).status_code == 409
            assert raw(row['id']) == before


def test_legacy_named_audience_excludes_other_supplier_and_explicit_deny(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        legacy('legacy-audience', order, 'manual_orders')
        before = raw('legacy-audience')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id='legacy-other-supplier', factory_id='huaxing', supplier_code='OTHER',
                supplier_name='Other', status='ACTIVE', created_at='2026-01-01', updated_at='2026-01-01'))
            db.commit()
        response = client.put('/api/carton-mark/assets/legacy-audience/sharing', params=F,
            json=dict(revision=1, sharing_mode='SUPPLIER', supplier_id='legacy-other-supplier'))
        assert response.status_code == 200, response.text
        supplier_login(client)
        assert client.get(BASE + '/legacy-audience', params={**F, 'supplier_view': True}).status_code == 404
        login_as(client, 'admin')
        current = ok(client.get(BASE + '/legacy-audience', params=F))
        shared = ok(audience(client, current, 'SUPPLIER'))
        supplier_login(client)
        assert client.get(BASE + '/legacy-audience', params={**F, 'supplier_view': True}).status_code == 200
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        with SessionLocal() as db:
            permission = db.scalar(select(AuthPermission).where(AuthPermission.code == 'carton_asset:read'))
            db.add(AuthUserPermissionOverride(id='legacy-explicit-deny', user_id='supplier-test',
                permission_id=permission.id, factory_id='huaxing', department='supplier', effect='deny',
                status='active', reason='synthetic deny regression'))
            db.commit()
        supplier_login(client)
        assert client.get(BASE + '/legacy-audience', params={**F, 'supplier_view': True}).status_code == 404
        assert shared['sharing_mode'] == 'SUPPLIER' and raw('legacy-audience') == before


def test_ambiguous_legacy_auto_contract_does_not_infer_cross_customer_links(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        legacy('legacy-ambiguous', order, 'order_contract')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            db.add(CartonOrder(id='ambiguous-order', factory_id='huaxing', order_no='ambiguous-order',
                customer_code='OTHER', customer_name='Other', supplier_id=order['supplier_id'],
                supplier_name_snapshot='Synthetic supplier', contract_no=order['contract_no'], item_no='other-item',
                quantity_basis='EXPLICIT', product_order_quantity=None, order_date='2026-01-01', due_date='2026-01-02',
                status='DRAFT', created_by='seed', created_by_name='seed', updated_by='seed', updated_by_name='seed',
                created_at='2026-01-01', updated_at='2026-01-01'))
            db.commit()
        before = raw('legacy-ambiguous')
        row = ok(client.get(BASE + '/legacy-ambiguous', params=F))
        assert row['targets'] == []
        assert raw('legacy-ambiguous') == before


def test_legacy_revision_preserves_null_owner_matching_and_original_bytes(monkeypatch):
    import json
    from test_carton_mark_api import _pdf_bytes
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        legacy('legacy-revision-parent', order, 'manual_orders', bound=True)
        before = raw('legacy-revision-parent')
        response = client.post('/api/carton-mark/assets/batch',
            data={**F, 'options_json': json.dumps([dict(status='PENDING',
                previous_asset_id='legacy-revision-parent', previous_revision=1)])},
            files=[('files', ('synthetic-revision.pdf', _pdf_bytes(), 'application/pdf'))])
        assert response.status_code == 200, response.text
        result = response.json()[0]
        assert result['status'] == 'created', result
        child = result['asset']
        child_raw = raw(child['id'])
        assert child_raw[1:3] == (None, None)
        assert child_raw[5:] == before[5:]
        assert raw('legacy-revision-parent') == before
        projected = ok(client.get(BASE + '/' + child['id'], params=F))
        assert projected['legacy_source'] and {x['id'] for x in projected['targets']} == {order['id']}


def test_legacy_creator_or_admin_required_for_original_audience(monkeypatch):
    from test_carton_asset_quick import grant
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        legacy('legacy-owner-guard', order, 'manual_orders')
        before = raw('legacy-owner-guard')
        grant('engineer_peer', 'pmc-warehouse')
        login_as(client, 'engineer_peer')
        row = ok(client.get(BASE + '/legacy-owner-guard', params=F))
        assert not row['can_manage_original'] and not row['can_change_audience']
        assert audience(client, row, 'SUPPLIER').status_code == 403
        assert raw('legacy-owner-guard') == before


def test_ambiguous_auto_regular_match_keeps_independent_special_link(monkeypatch):
    from types import SimpleNamespace
    from app.services import carton_asset_targets as targets, carton_mark_assets as assets, carton_mark_sharing as sharing
    asset = SimpleNamespace(owner_department=None, recognition_source='order_contract', bound_order_id=None,
        factory_id='huaxing')
    orders = [SimpleNamespace(customer_code='A'), SimpleNamespace(customer_code='B')]
    monkeypatch.setattr(assets, 'available_orders', lambda db, factory: orders)
    monkeypatch.setattr(assets, 'matching_asset_orders', lambda source, values: values)
    monkeypatch.setattr(sharing, 'current', lambda db, source: {'special_orders': [dict(
        order_kind='SAMPLE', order_id='explicit-sample', customer_code='A', supplier_id='supplier', line_id='line')]})
    rows = targets.legacy_targets(None, asset)
    assert [(row['kind'], row['id'], row['line_id']) for row in rows] == [('SAMPLE', 'explicit-sample', 'line')]
