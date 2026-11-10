"""Combined pagination and authorization use existing real domain rows."""
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_supplier_portal import setup_portal, grant_supplier_permissions, supplier_login
from test_carton_special_requests import create_body, ok, BASE, FACTORY

ENDPOINT = '/api/carton-unified-orders'


@pytest.fixture(autouse=True)
def isolated_directory(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    # The synthetic native API fixture needs its own admin; workstation .env
    # may correctly disable default accounts for the running business service.
    monkeypatch.setenv('SEED_DEFAULT_ACCOUNTS', 'true')


def test_combined_page_filters_before_pagination_and_preserves_purchase_projection(monkeypatch):
    with make_client(monkeypatch) as client:
        purchase = setup_portal(client)
        login_as(client, 'admin')
        seed = ok(client.post(BASE, json=create_body()), 201)
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialRequest
        with SessionLocal() as db:
            original = db.get(SpecialRequest, seed['id'])
            for index in range(55):
                data = {column.name: getattr(original, column.name) for column in SpecialRequest.__table__.columns}
                data.update(id='TEST-' + uuid4().hex, request_no=f'SAMPLE-{index:03}',
                            required_date=f'2050-10-{index % 28 + 1:02}', current_version_id='', title=f'needle-{index}')
                db.add(SpecialRequest(**data))
            db.commit()
        first = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'limit': 50, 'sort': 'DUE_ASC'}))
        second = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'limit': 50, 'offset': 50, 'sort': 'DUE_ASC'}))
        assert first['total'] == second['total'] == 57
        assert len(first['items']) == 50 and len(second['items']) == 7
        all_items = first['items'] + second['items']
        identities = [item.get('order', item.get('special'))['id'] for item in all_items]
        assert len(set(identities)) == 57
        regular = [item['order'] for item in all_items if item['kind'] == 'PURCHASE']
        assert len(regular) == 1 and regular[0]['order_no'] == purchase['order_no'] and regular[0]['lines']
        filtered = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'kind': 'SAMPLE', 'search': 'SAMPLE-054', 'limit': 1}))
        assert filtered['total'] == 1 and filtered['items'][0]['special']['request_no'] == 'SAMPLE-054'
        assert ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'kind': 'PURCHASE'}))['total'] == 1
        assert ok(client.get(ENDPOINT, params={'factory_id': 'huakang-a'}))['total'] == 0
        submitted = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'status_filter': 'SUBMITTED', 'limit': 1}))
        assert submitted['total'] == 56 and submitted['items'][0]['kind'] == 'SAMPLE'
        for regular_state in ('CONFIRMED', 'PENDING_SUPPLIER'):
            exact = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'status_filter': regular_state}))
            assert all(item['kind'] == 'PURCHASE' for item in exact['items'])
        with SessionLocal() as db:
            db.get(SpecialRequest, seed['id']).status = 'SENT'
            db.commit()
        sent = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'kind': 'SAMPLE', 'status_filter': 'SENT'}))
        assert sent['total'] == 1 and sent['items'][0]['special']['id'] == seed['id']
        assert ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'kind': 'WORKSHOP_MISC', 'status_filter': 'SENT'}))['total'] == 0
        unlocked = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'status_filter': 'UNLOCKED', 'limit': 1, 'offset': 54}))
        assert unlocked['total'] == 55 and unlocked['items'][0]['special']['status'] == 'SUBMITTED'
        locked = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'status_filter': 'LOCKED'}))
        assert locked['total'] == 2
        assert {entry['kind'] for entry in locked['items']} == {'PURCHASE', 'SAMPLE'}


def test_awaiting_acceptance_groups_pending_and_partial_from_current_issue(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        portal = ok(client.get('/api/carton-supplier/workspace', params={'factory_id': FACTORY}))['orders'][0]
        params = {'factory_id': FACTORY, 'collaboration_filter': 'AWAITING_ACCEPTANCE'}
        for accepted, status in enumerate(('PENDING', 'PARTIAL', 'ACCEPTED')):
            if accepted:
                supplier_login(client)
                line = portal['lines'][accepted - 1]
                ok(client.put(f"/api/carton-supplier/papers/{line['id']}/commitment",
                    json={'factory_id': FACTORY, 'issue_id': portal['issue_id'], 'expected_revision': 0, 'promised_date': '2026-09-23'}))
            login_as(client, 'admin')
            filtered = ok(client.get(ENDPOINT, params=params))
            if status == 'ACCEPTED':
                assert filtered['total'] == 0
                filtered = ok(client.get(ENDPOINT, params={**params, 'collaboration_filter': 'ACCEPTED'}))
            assert filtered['total'] == 1
            assert filtered['items'][0]['order']['order_no'] == order['order_no']
            assert filtered['items'][0]['order']['supplier_acceptance']['status'] == status


def test_applicant_only_never_reads_purchase_or_other_employees_requests(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        ok(client.post(BASE, json=create_body()), 201)
        ensure_test_user('engineer')
        grant_supplier_permissions('user-engineer', permissions=('carton_procurement:special_request_submit',))
        login_as(client, 'engineer')
        own = ok(client.post(BASE, json=create_body()), 201)
        page = ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'responsibility_scope': 'ALL'}))
        assert page['can_create'] is True and page['total'] == 1
        assert page['items'][0]['special']['id'] == own['id']
        assert ok(client.get(ENDPOINT, params={'factory_id': FACTORY, 'kind': 'PURCHASE'}))['total'] == 0
        supplier_login(client)
        assert client.get(ENDPOINT, params={'factory_id': FACTORY}).status_code == 403
