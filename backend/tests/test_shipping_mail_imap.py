from datetime import datetime
from types import SimpleNamespace

from test_shipping_mail_api import booking_email
from test_identity_changes import client  # noqa: F401 - shared authenticated TestClient fixture


def test_mail_account_configuration_test_and_sync(client, monkeypatch):  # noqa: F811
    from app.services import shipping_mail_account_service as accounts

    monkeypatch.setattr(accounts, 'encrypt_password', lambda password: f'enc:{password}')
    monkeypatch.setattr(accounts, 'decrypt_password', lambda value: value.removeprefix('enc:'))
    monkeypatch.setattr(accounts, 'test_connection', lambda *args, **kwargs: None)

    saved = client.put('/api/shipping/mail/account', json={
        'factory_id': 'huaxing', 'host': 'imap.example.com', 'port': 993,
        'username': 'shipping@example.com', 'password': 'secret', 'use_ssl': True,
        'folder': 'INBOX', 'enabled': True,
    })
    assert saved.status_code == 200, saved.text
    account = saved.json()['account']
    assert account['configured'] is True
    assert account['has_password'] is True
    assert 'password' not in account

    fetched = client.get('/api/shipping/mail/account', params={'factory_id': 'huaxing'})
    assert fetched.status_code == 200
    assert fetched.json()['account']['username'] == 'shipping@example.com'

    tested = client.post('/api/shipping/mail/account/test', json={'factory_id': 'huaxing'})
    assert tested.status_code == 200, tested.text
    assert tested.json()['ok'] is True

    monkeypatch.setattr(accounts, 'fetch_recent', lambda *args, **kwargs: [
        ('10', 'mail-10.eml', booking_email()),
    ])
    synced = client.post('/api/shipping/mail/account/sync', params={'factory_id': 'huaxing'})
    assert synced.status_code == 200, synced.text
    run = synced.json()['run']
    assert run['status'] == 'ok'
    assert run['fetched'] == 1
    assert run['imported'] == 1
    assert run['confirmed'] == 1

    tasks = client.get('/api/shipping/tasks', params={'factory_id': 'huaxing'})
    assert tasks.status_code == 200
    assert tasks.json()['tasks'][0]['so_number'] == '700149016'

    batches = client.get('/api/shipping/mail/batches', params={'factory_id': 'huaxing'}).json()['batches']
    assert any(batch['source'] == 'imap' for batch in batches)

    runs = client.get('/api/shipping/mail/account/runs', params={'factory_id': 'huaxing'})
    assert runs.status_code == 200
    assert runs.json()['runs'][0]['imported'] == 1


def test_mail_account_rejects_unsupported_factory_and_missing_password(client):  # noqa: F811
    bad_factory = client.put('/api/shipping/mail/account', json={
        'factory_id': 'huakang-c', 'host': 'imap.example.com', 'username': 'a@example.com',
        'password': 'secret',
    })
    assert bad_factory.status_code == 422

    missing = client.put('/api/shipping/mail/account', json={
        'factory_id': 'huadeng', 'host': 'imap.example.com', 'username': 'a@example.com', 'password': '',
    })
    assert missing.status_code == 422


def test_hourly_sync_gate_runs_once_per_hour_and_stops_after_midnight(monkeypatch):
    from app.core.config import settings
    from app.services.shipping_mail_account_service import due_for_sync

    now = datetime.now()
    monkeypatch.setattr(settings, 'shipping_mail_imap_weekdays', '0,1,2,3,4,5,6')
    monkeypatch.setattr(settings, 'shipping_mail_imap_hour', 0)
    monkeypatch.setattr(settings, 'shipping_mail_imap_end_hour', 23)
    assert due_for_sync(SimpleNamespace(enabled=True, last_sync_at=''), now) is True
    same_hour = datetime(now.year, now.month, now.day, now.hour, 0, 0).isoformat(timespec='seconds')
    assert due_for_sync(SimpleNamespace(enabled=True, last_sync_at=same_hour), now) is False
    if now.hour > 0:
        previous_hour = datetime(now.year, now.month, now.day, now.hour - 1, 30, 0).isoformat(timespec='seconds')
        assert due_for_sync(SimpleNamespace(enabled=True, last_sync_at=previous_hour), now) is True
    assert due_for_sync(SimpleNamespace(enabled=False, last_sync_at=''), now) is False

    midnight = datetime(2026, 11, 13, 0, 30)
    monkeypatch.setattr(settings, 'shipping_mail_imap_hour', 8)
    monkeypatch.setattr(settings, 'shipping_mail_imap_end_hour', 23)
    assert due_for_sync(SimpleNamespace(enabled=True, last_sync_at=''), midnight) is False


def test_default_auto_collection_covers_all_five_factories():
    from app.services.shipping_mail_account_service import configured_factories

    assert configured_factories() == ['huaxing', 'huadeng', 'huakang-a', 'huakang-b', 'huakang-d']
