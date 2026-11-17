"""Clipboard endpoint against the exact staged standalone API and worker."""
import csv
from io import StringIO
import sqlite3

from test_standalone import BASE, SCOPE, client_for, install, parsed, exported, mail, MANIFEST


def test_copy_exact_export_survives_restart_without_allocating_numbers(tmp_path):
    assert any(item['target'].endswith('/clipboard.py') for item in MANIFEST['unchanged_business_sources'])
    with client_for(tmp_path) as client:
        install(client)
        raw, form, preview = parsed(client)
        generated = exported(client, raw, form, preview)
        assert generated.status_code == 200, generated.text
        record = generated.json(); route = BASE + '/exports/' + record['id']
        original = client.get(route + '/download', params=SCOPE).content
        first = client.get(route + '/clipboard', params=SCOPE)
        assert first.status_code == 200, first.text
        result = first.json(); row, = list(csv.reader(StringIO(result['text'], newline=''), delimiter='\t'))
        assert result['column_count'] == 44 and result['row_count'] == 1 and len(row) == 44
        assert row[0].endswith('-21615') and row[2] == "'0117978388"
        assert row[12] == '648' and row[20] == '12.5' and row[-3:] == ['', '', '']
        assert client.get(route + '/clipboard', params=SCOPE).json() == result
        assert client.get(route + '/clipboard', params={'factory_id': 'huaxing'}).status_code == 400
        assert client.get(BASE + '/exports/not-found/clipboard', params=SCOPE).status_code == 404
    with client_for(tmp_path) as restarted:
        assert restarted.get(route + '/clipboard', params=SCOPE).json() == result
        assert restarted.get(route + '/download', params=SCOPE).content == original
        raw, form, preview = parsed(restarted, mail('0117978389'))
        next_export = exported(restarted, raw, form, preview)
        assert next_export.status_code == 200 and next_export.json()['first_number'] == 21616
    with sqlite3.connect(tmp_path / 'jp-trial.sqlite3') as database:
        assert database.execute('SELECT content FROM jp_intake_exports WHERE id=?', (record['id'],)).fetchone()[0] == original
        assert database.execute('SELECT count(*) FROM jp_intake_exports').fetchone()[0] == 2
