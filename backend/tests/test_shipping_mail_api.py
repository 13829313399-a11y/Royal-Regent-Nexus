from email.message import EmailMessage

import pytest

from test_identity_changes import client  # noqa: F401 - shared authenticated TestClient fixture

BOOKING_BODY = """\
Booking Amendment
ROSS 700149016
From: Yantian, Guangdong, China
To: Houston, Texas, US
Customer: BuShipping (Shenzhen)
SI Cut Off(截补料时间): 10 月 26, 2026 20:30
CY Cut Off: 10/28/2026 12:00
1*40HQ
"""


def booking_email(body: str = BOOKING_BODY, subject: str = 'BN Amendment') -> bytes:
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = 'booking@maersk.example'
    message['Date'] = 'Thu, 16 Oct 2026 09:05:18 +0800'
    message.set_content(body)
    return bytes(message)


def scan_pdf() -> bytes:
    canvas = pytest.importorskip('reportlab.pdfgen.canvas')
    import io

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.rect(40, 40, 400, 400, fill=1)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def upload(client, factory_id: str, filename: str, data: bytes):
    return client.post(
        '/api/shipping/mail/batches',
        data={'factory_id': factory_id},
        files=[('files', (filename, data, 'message/rfc822'))],
    )


def test_mail_preview_import_confirm_and_factory_isolation(client):  # noqa: F811
    preview = client.post(
        '/api/shipping/mail/preview',
        data={'factory_id': 'huaxing'},
        files={'file': ('booking.eml', booking_email(), 'message/rfc822')},
    )
    assert preview.status_code == 200, preview.text
    fields = preview.json()['fields']
    assert fields['so_number'] == '700149016'
    assert fields['si_deadline'] == '2026-10-26T20:30'
    assert fields['planned_ship_date'] == '2026-10-27'

    created = upload(client, 'huaxing', 'booking.eml', booking_email())
    assert created.status_code == 200, created.text
    body = created.json()
    batch_id = body['batch']['id']
    item_id = body['items'][0]['id']
    assert body['items'][0]['status'] == 'pending'

    detail = client.get(f'/api/shipping/mail/batches/{batch_id}', params={'factory_id': 'huaxing'})
    assert detail.status_code == 200
    assert detail.json()['items'][0]['fields']['so_number'] == '700149016'
    assert client.get(f'/api/shipping/mail/batches/{batch_id}',
                      params={'factory_id': 'huadeng'}).status_code == 404
    assert upload(client, 'huakang-c', 'booking.eml', booking_email()).status_code == 422

    confirmed = client.post(
        f'/api/shipping/mail/batches/{batch_id}/confirm',
        json={'factory_id': 'huaxing', 'item_ids': [item_id]},
    )
    assert confirmed.status_code == 200, confirmed.text
    task = confirmed.json()['tasks'][0]
    assert task['so_number'] == '700149016'
    assert task['planned_ship_date'] == '2026-10-27'
    assert task['status'] == 'review'

    again = client.post(
        f'/api/shipping/mail/batches/{batch_id}/confirm',
        json={'factory_id': 'huaxing', 'item_ids': [item_id]},
    )
    assert again.status_code == 409

    tasks = client.get('/api/shipping/tasks', params={'factory_id': 'huaxing'}).json()['tasks']
    assert [row['id'] for row in tasks] == [task['id']]


def test_scanned_and_incomplete_mail_need_manual_entry(client):  # noqa: F811
    scanned = upload(client, 'huaxing', 'scan.pdf', scan_pdf())
    assert scanned.status_code == 200, scanned.text
    scanned_body = scanned.json()
    item = scanned_body['items'][0]
    assert item['status'] == 'needs_ocr'
    assert any('扫描件' in warning for warning in item['warnings'])
    blocked = client.post(
        f"/api/shipping/mail/batches/{scanned_body['batch']['id']}/confirm",
        json={'factory_id': 'huaxing', 'item_ids': [item['id']]},
    )
    assert blocked.status_code == 409

    plain = upload(client, 'huaxing', 'plain.eml', booking_email('请查收附件，谢谢。', subject='请查收'))
    plain_body = plain.json()
    missing_so = client.post(
        f"/api/shipping/mail/batches/{plain_body['batch']['id']}/confirm",
        json={'factory_id': 'huaxing', 'item_ids': [plain_body['items'][0]['id']]},
    )
    assert missing_so.status_code == 422
    assert 'SO/BN' in missing_so.text


def test_manual_entry_validation_and_task_state(client):  # noqa: F811
    payload = {
        'factory_id': 'huaxing',
        'fields': {'so_number': '4501234567', 'cutoff_date': '2026-11-20T17:00', 'shipment_mode': 'warehouse'},
        'items': [{'key': '1', 'cbm': 40, 'product_code': 'A-1'}],
        'warehouse_trips': [{'warehouse': '裕泰仓', 'cargo_keys': ['1'], 'vehicle_type': '1*3T'}],
    }
    over_cap = client.post('/api/shipping/tasks', json=payload)
    assert over_cap.status_code == 422
    assert '35 CBM' in over_cap.text

    payload['items'] = [{'key': '1', 'cbm': 20, 'product_code': 'A-1'}]
    created = client.post('/api/shipping/tasks', json=payload)
    assert created.status_code == 200, created.text
    task = created.json()['task']
    assert task['planned_ship_date'] == '2026-11-19'

    no_date = client.post('/api/shipping/tasks', json={
        'factory_id': 'huaxing', 'fields': {'so_number': '4509999999'}, 'items': [],
    })
    assert no_date.status_code == 422
    assert '出货日' in no_date.text

    assert client.post(f"/api/shipping/tasks/{task['id']}/status",
                       json={'factory_id': 'huaxing', 'status': 'shipment'}).status_code == 200
    assert client.post(f"/api/shipping/tasks/{task['id']}/status",
                       json={'factory_id': 'huaxing', 'status': 'waiting'}).status_code == 409
    assert client.post(f"/api/shipping/tasks/{task['id']}/status",
                       json={'factory_id': 'huaxing', 'status': 'completed'}).status_code == 200
