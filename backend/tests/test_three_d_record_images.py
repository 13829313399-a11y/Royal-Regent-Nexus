from io import BytesIO

from PIL import Image
from test_three_d_ledger_snapshots import client, stock, create, edit, dashboard, BASE, FACTORY
from test_three_d_printing_api import jpeg_bytes


def test_record_photo_persists_through_cost_edits_without_touching_other_records(client):
    stock(client)
    row = create(client)
    other = create(client)
    before = dashboard(client)
    url = f"{BASE}/records/{row['id']}/image"
    params = {"factory_id": FACTORY, "revision": row['revision'], "idempotency_key": "record-image-retry"}
    uploaded = client.post(url, params=params, files={"file": ("paste.png", jpeg_bytes(), "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    photo = uploaded.json()
    assert photo['revision'] == row['revision'] + 1
    assert photo['frozen_totals'] == row['frozen_totals']
    # A lost successful response replays the same result without another revision or write.
    replay = client.post(url, params=params, files={"file": ("paste.png", jpeg_bytes(), "image/png")})
    assert replay.status_code == 200, replay.text
    assert replay.json() == photo
    response = client.get(photo['record_image_url'])
    assert response.status_code == 200
    assert Image.open(BytesIO(response.content)).format == 'JPEG'
    after = dashboard(client)
    assert after['inventory'] == before['inventory']
    assert after['inventory_movements'] == before['inventory_movements']
    assert next(x for x in after['records'] if x['id'] == other['id'])['record_image_url'] == ''
    assert client.post(url, params={**params, 'idempotency_key': 'another-image-key'}, files={"file": ('x.jpg', jpeg_bytes(), 'image/jpeg')}).status_code == 409
    changed = edit(client, photo, quoted_price=51)
    assert changed['record_image_url'] == photo['record_image_url']
    items = client.get(BASE+'/collections/records', params={'factory_id': FACTORY}).json()['items']
    assert next(x for x in items if x['id'] == row['id'])['record_image_url'] == photo['record_image_url']
    assert client.get(url, params={'factory_id': 'huaxing'}).status_code == 400
    assert client.post(url, params={'factory_id': FACTORY, 'revision': changed['revision'], 'idempotency_key': 'invalid-image-key'}, files={'file': ('bad.png', b'broken', 'image/png')}).status_code == 422
    assert client.get(photo['record_image_url']).content == response.content
    client.post('/api/auth/logout')
    assert client.get(photo['record_image_url']).status_code == 401
