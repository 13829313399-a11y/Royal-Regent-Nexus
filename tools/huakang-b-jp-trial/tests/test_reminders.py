"""The delivered Windows adapter uses the same reminder-only generation flow."""
from io import BytesIO
import json
import sqlite3

import openpyxl
from test_standalone import BASE, SCOPE, client_for, mail, install


def test_unreferenced_unconfirmed_export_and_copy_survive_restart_then_accept_numbering_baseline(tmp_path):
    raw = mail()
    form = {**SCOPE, 'received_date': '2026-11-11', 'html': 'Extra text without a table'}
    files = {'files': ('synthetic.eml', raw)}
    with client_for(tmp_path) as client:
        preview = client.post(BASE + '/preview', data=form, files=files)
        assert preview.status_code == 200, preview.text
        parsed = preview.json()
        assert parsed['failed_sources'] == ['粘贴正文']
        payload = {**form, 'fingerprint': parsed['fingerprint'], 'selected': json.dumps([parsed['rows'][0]['id']])}
        generated = client.post(BASE + '/export', data=payload, files=files)
        assert generated.status_code == 200, generated.text
        result = generated.json()
        assert result['numbering_status'] == 'pending' and result['first_number'] == 0
        path = BASE + '/exports/' + result['id']
        content = client.get(path + '/download', params=SCOPE).content
        sheet = openpyxl.load_workbook(BytesIO(content)).active
        assert sheet.cell(2, 1).value is None and sheet.cell(2, 21).value is None
        assert sheet.cell(2, 39).value == '待核对'
        assert sheet.cell(2, 40).value is None
        copied = client.get(path + '/clipboard', params=SCOPE).json()
        assert copied['row_count'] == 1 and copied['column_count'] == 44
        assert client.post(BASE + '/export', data=payload, files=files).json()['id'] == result['id']
    with sqlite3.connect(tmp_path / 'jp-trial.sqlite3') as connection:
        assert connection.execute('SELECT count(*) FROM jp_intake_counters').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM jp_intake_export_identities').fetchone()[0] == 0
    with client_for(tmp_path) as client:
        assert client.get(path + '/download', params=SCOPE).content == content
        assert client.get(path + '/clipboard', params=SCOPE).json() == copied
        install(client)
        parsed = client.post(BASE + '/preview', data=form, files=files).json()
        payload.update(fingerprint=parsed['fingerprint'], selected=json.dumps([parsed['rows'][0]['id']]))
        numbered = client.post(BASE + '/export', data=payload, files=files)
        assert numbered.status_code == 200 and numbered.json()['first_number'] == 21615
