"""Coverage is a free authorization check, never proof of business acceptance."""
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from test_assistant_api import env


def items(response):
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    return {row['module_id']: row for row in response.json()['items']}


def test_authenticated_bounded_and_does_not_create_a_session_or_call_provider(env):
    client, dbm, calls, patch = env
    from app.services.assistant import business
    def no_business_query(*args, **kwargs):
        raise AssertionError('coverage must not read business records')
    patch.setattr(business, 'query', no_business_query)
    writes = []
    def capture(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER')):
            writes.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        response = client.get('/api/assistant/coverage', params={'factory_id': 'huaxing', 'module_id': 'unregistered'})
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    rows = items(response)
    assert rows['work-center']['state'] == 'business_read'
    assert rows['customer-orders']['state'] == 'forbidden'
    assert rows['uv-operations']['state'] == 'not_connected'
    assert rows['unregistered']['state'] == 'not_connected'
    assert all(row['verification'] != 'connected' for row in rows.values())
    assert not any('nexus_assistant_' in sql for sql in writes)
    assert not calls
    assert client.get('/api/assistant/coverage', params={'factory_id': 'x' * 33}).status_code == 422
    client.cookies.clear()
    assert client.get('/api/assistant/coverage', params={'factory_id': 'huaxing'}).status_code == 401


def test_native_spray_authority_matches_factory_flag_and_schema_states(env):
    from test_assistant_v3_spray import setup
    from test_spray_ops import user_with
    from app.services.assistant import runtime
    from app.core.config import settings
    from app.services import auth
    client, dbm, calls, actor = setup(env)
    patch = env[3]
    current = {'actor': user_with('read', factory='huaxing')}
    patch.setattr(runtime, 'authenticate', lambda request: current['actor'])
    client.app.dependency_overrides[auth.get_current_user] = lambda: current['actor']
    def compare(factory, state, status):
        assert items(client.get('/api/assistant/coverage', params={'factory_id': factory}))['spray-production']['state'] == state
        assert client.get('/api/spray-operations/demands', params={'factory_id': factory}).status_code == status
    compare('huaxing', 'business_read', 200)
    compare('huakang-b', 'forbidden', 403)
    compare('group', 'not_connected', 422)
    patch.setattr(settings, 'spray_ops_enabled', False)
    compare('huaxing', 'disabled', 503)
    compare('huakang-b', 'forbidden', 403)
    patch.setattr(settings, 'spray_ops_enabled', True)
    current['actor'] = user_with(factory='huaxing')
    compare('huaxing', 'forbidden', 403)
    assert not calls


def test_guide_coverage_requires_current_audience_factory_and_verified_source(env):
    from app.services.assistant import help_registry
    client, _, _, patch = env
    def article(ident, **changes):
        return SimpleNamespace(module_id=ident, title=ident, kind='overview', audience='internal',
                               factory_ids=changes.get('factories', []), status=changes.get('status', 'verified'))
    patch.setattr(help_registry, 'articles', lambda: [article('guide'), article('stale', status='needs_review'),
        article('elsewhere', factories=['huakang-a']), SimpleNamespace(module_id='supplier', title='Supplier',
        kind='overview', audience='supplier', factory_ids=[], status='verified')])
    rows = items(client.get('/api/assistant/coverage', params={'factory_id': 'huaxing'}))
    assert rows['guide']['state'] == 'guide_only' and rows['guide']['guide_count'] == 1
    assert rows['stale']['state'] == rows['elsewhere']['state'] == 'not_connected'
    assert rows['stale']['guide_count'] == rows['elsewhere']['guide_count'] == 0
    assert rows['supplier']['state'] == 'forbidden'


def test_one_failed_domain_preserves_others_and_hides_internal_exception(env):
    from app.services.assistant import business
    client, _, _, patch = env
    original = business.authorize
    def failed(db, user, name, factory):
        if name == 'get_injection_overview':
            raise OperationalError('PRIVATE_SQL', {}, RuntimeError('PRIVATE_DATABASE_PATH'))
        return original(db, user, name, factory)
    patch.setattr(business, 'authorize', failed)
    response = client.get('/api/assistant/coverage', params={'factory_id': 'huaxing'})
    rows = items(response)
    assert rows['injection-scheduling']['state'] == 'not_connected'
    assert rows['work-center']['state'] == 'business_read'
    assert 'PRIVATE_' not in response.text


def test_global_disable_cannot_advertise_callable_modules(env):
    from app.core.config import settings
    client, _, _, patch = env
    patch.setattr(settings, 'assistant_enabled', False)
    rows = items(client.get('/api/assistant/coverage', params={'factory_id': 'huaxing'}))
    assert rows['work-center']['state'] == 'disabled'
    assert all(row['state'] not in {'business_read', 'guide_only'} for row in rows.values())
