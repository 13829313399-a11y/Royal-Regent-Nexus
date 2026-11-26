from email.message import EmailMessage

from test_identity_changes import client  # noqa: F401 - shared authenticated TestClient fixture


def build_email() -> bytes:
    message = EmailMessage()
    message['Subject'] = 'Re:DK盐田W62柜 (1)出货资料/通关一体化资料'
    message['From'] = 'shipping@example.com'
    message.set_content('请查收柜装箱单。')
    message.add_attachment(b'PK\x03\x04fake-xls', maintype='application',
                           subtype='vnd.ms-excel', filename='华兴DKW62柜装箱单.xls')
    return bytes(message)


def test_upload_stores_customs_documents_and_unread_count(client):  # noqa: F811
    created = client.post(
        '/api/shipping/mail/batches',
        data={'factory_id': 'huaxing'},
        files=[('files', ('customs.eml', build_email(), 'message/rfc822'))],
    )
    assert created.status_code == 200, created.text

    docs = client.get('/api/shipping/customs-docs', params={'factory_id': 'huaxing'})
    assert docs.status_code == 200, docs.text
    body = docs.json()
    assert body['unread'] == 1
    assert body['docs'][0]['filename'] == '华兴DKW62柜装箱单.xls'
    assert '通关一体化资料' in body['docs'][0]['subject']

    download = client.get(f"/api/shipping/customs-docs/{body['docs'][0]['id']}/download",
                          params={'factory_id': 'huaxing'})
    assert download.status_code == 200
    assert download.content.startswith(b'PK')

    marked = client.post('/api/shipping/customs-docs/read', json={'factory_id': 'huaxing'})
    assert marked.status_code == 200
    assert marked.json()['marked'] == 1
    assert client.get('/api/shipping/customs-docs', params={'factory_id': 'huaxing'}).json()['unread'] == 0
