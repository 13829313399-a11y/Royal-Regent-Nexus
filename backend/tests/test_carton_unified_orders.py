"""Combined pagination and authorization use existing real domain rows."""
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_supplier_portal import setup_portal, grant_supplier_permissions, supplier_login
from test_carton_special_requests import command, create_body, ok, BASE, FACTORY

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
        from unittest.mock import patch
        from app.services import carton_special_requests
        with patch.object(carton_special_requests, "detail", wraps=carton_special_requests.detail) as details:
            page = ok(client.get(ENDPOINT, params={"factory_id": FACTORY, "kind": "SAMPLE", "limit": 1,
                                                   "collaboration_filter": "NOT_ISSUED"}))
            assert page["total"] >= 55 and len(page["items"]) == details.call_count == 1
            board = ok(client.get("/api/carton-procurement/dashboard/workspace", params={"factory_id": FACTORY}))
            assert board["pending_order_count"] == 57 and details.call_count == 1
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


@pytest.mark.parametrize("kind", ["SAMPLE", "WORKSHOP_MISC"])
def test_special_follow_up_uses_current_supplier_response_and_dashboard_scope(monkeypatch, kind):
    # The restricted reader below receives their explicit factory permission through IAM overrides.
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        row = ok(client.post(BASE, json=create_body(kind)), 201)
        path = f"{BASE}/{row['id']}"
        scoped = {"factory_id": FACTORY, "search": row["request_no"], "responsibility_scope": "OWN"}

        def count(state):
            return ok(client.get(ENDPOINT, params={**scoped, "kind": kind, "collaboration_filter": state}))["total"]

        def assert_follow_up(expected):
            board = ok(client.get("/api/carton-procurement/dashboard/workspace", params=scoped))
            ledger = ok(client.get(ENDPOINT, params={**scoped, "status_filter": "FOLLOW_UP"}))
            assert board["pending_order_count"] == ledger["total"] == expected

        assert count("NOT_ISSUED") == 1
        assert_follow_up(1)
        row = ok(client.post(path + "/send", json=command(row)))
        assert count("AWAITING_ACCEPTANCE") == 1 and count("ACCEPTED") == 0
        supplier_login(client)
        ok(client.post("/api/carton-supplier/changes/respond", json={
            "factory_id": FACTORY, "source_kind": "SPECIAL", "source_id": row["current_version_id"],
            "expected_revision": row["revision"], "action": "ACCEPT", "promised_date": "2026-10-25",
            "request_id": uuid4().hex,
        }))
        login_as(client, "admin")
        assert count("AWAITING_ACCEPTANCE") == 0 and count("ACCEPTED") == count("LATE_PROMISE") == 1
        row = ok(client.get(path, params={"factory_id": FACTORY}))
        update = {**create_body(kind), **command(row), "reason": "采购调整需求数量"}
        update["lines"][0].update(id=row["lines"][0]["id"], quantity="110")
        revised = ok(client.post(path + "/adjust", json=update))
        assert revised["current_version_id"] != row["current_version_id"]
        assert count("AWAITING_ACCEPTANCE") == 1 and count("ACCEPTED") == count("LATE_PROMISE") == 0
        assert_follow_up(1)
        ensure_test_user("engineer")
        grant_supplier_permissions("user-engineer", permissions=("carton_procurement:read",))
        login_as(client, "engineer")
        scoped["responsibility_scope"] = "ALL"
        assert_follow_up(0)


def test_legacy_wrong_version_never_exposes_another_special_orders_acceptance(monkeypatch):
    from test_carton_special_requests import accept
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        orders = []
        for kind in ("SAMPLE", "WORKSHOP_MISC"):
            row = ok(client.post(BASE, json=create_body(kind)), 201)
            orders.append(ok(client.post(f"{BASE}/{row['id']}/send", json=command(row))))
        source, other = orders
        accept(client, source)
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialRequest
        with SessionLocal() as db:
            db.get(SpecialRequest, other["id"]).current_version_id = source["current_version_id"]
            db.commit()
        confirmed = ok(client.get(ENDPOINT, params={"factory_id": FACTORY, "collaboration_filter": "ACCEPTED"}))
        assert [e["special"]["id"] for e in confirmed["items"] if e["kind"] != "PURCHASE"] == [source["id"]]
        other_detail = ok(client.get(f"{BASE}/{other['id']}", params={"factory_id": FACTORY}))
        state = other_detail["supplier_confirmation"]
        assert state["status"] == "PENDING" and state["history"] == []
        assert not any(state[k] for k in ("promised_date", "acceptance_id", "responded_by", "version_id"))
