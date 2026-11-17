"""Immutable exported-workbook clipboard contract; all inputs are synthetic."""
from datetime import datetime
import csv
from hashlib import sha256
from io import BytesIO, StringIO

import openpyxl
import pytest
from sqlalchemy import select, func

from app.services.huakang_b_jp import clipboard as service
from app.services.huakang_b_jp.intake import COLUMNS, MAX_ROWS
from app.models.huakang_b_jp import JPCounter, JPExport
from test_huakang_b_jp import engine, db, client, install, preview, export, api, user, get_current_user

BASE = '/api/huakang-b-jp'


def document(values=None, change=None):
    book = openpyxl.Workbook(); sheet = book.active
    sheet.append(COLUMNS)
    sheet.append(values or ['0126-0001'] + [''] * 43)
    for cell in sheet[2]:
        if isinstance(cell.value, str): cell.data_type = 's'
    if change: change(book)
    output = BytesIO(); book.save(output); book.close()
    return output.getvalue()


def fields(text):
    return list(csv.reader(StringIO(text, newline=''), delimiter='\t'))


def test_tsv_preserves_44_cells_types_quotes_blank_tail_and_safe_text():
    values = ['0126-0001', 'ACME', '001234567890123456', datetime(2026, 11, 11)] + [''] * 40
    values[12], values[20], values[23] = 123, 12.5, 0
    values[27] = '=HYPERLINK("https://example.invalid","mail")'
    values[28] = 'note\twith tab\nand "quotes"'
    values[29] = '  +SUM(1,2)'
    values[30] = "'literal"
    values[31] = '12345678901234567890'
    result = service.export_clipboard(document(values))
    row, = fields(result['text'])
    assert result['column_count'] == 44 and result['row_count'] == 1 and len(row) == 44
    assert row[:4] == ['0126-0001', 'ACME', "'001234567890123456", '2026/11/11']
    assert (row[12], row[20], row[23]) == ('123', '12.5', '0')
    assert row[27] == "'" + values[27] and row[28] == values[28]
    assert row[29] == "'" + values[29] and row[30] == "''literal"
    assert row[31] == "'12345678901234567890" and row[41:] == ['', '', '']
    assert result['text'].endswith('\t\t\t\r\n')
    assert not any(value.startswith('="') for value in row)


@pytest.mark.parametrize('change', [
    lambda b: setattr(b.active['AB2'], 'value', '=1+1'),
    lambda b: setattr(b.active['A1'], 'value', 'wrong'),
    lambda b: b.active.cell(2, 45, 'extra'),
    lambda b: b.active.cell(MAX_ROWS + 2, 1, 'too many'),
    lambda b: b.create_sheet('extra'),
])
def test_unexpected_or_formula_exports_are_rejected(change):
    with pytest.raises(ValueError): service.export_clipboard(document(change=change))


@pytest.mark.parametrize('content', [b'', b'not an xlsx'])
def test_invalid_workbook_is_rejected(content):
    with pytest.raises(ValueError): service.export_clipboard(content)


def test_stream_closes_even_if_formula_error_traceback_is_retained(monkeypatch):
    handles = []
    def stream(content):
        result = BytesIO(content); handles.append(result); return result
    monkeypatch.setattr(service, 'BytesIO', stream)
    with pytest.raises(ValueError, match='公式') as error:
        service.export_clipboard(document(change=lambda b: setattr(b.active['AB2'], 'value', '=1+1')))
    assert error.traceback and handles and all(handle.closed for handle in handles)


def test_clipboard_reads_exact_export_without_renumbering_or_mutating_record(client, db):
    install(db); record = export(db, preview(db))
    original = bytes(record.content); before_hash = sha256(original).hexdigest()
    counter = [(r.factory_id, r.last_number) for r in db.scalars(select(JPCounter))]
    route = f'{BASE}/exports/{record.id}/clipboard'
    first = client.get(route, params={'factory_id': 'huakang-b'})
    assert first.status_code == 200, first.text
    assert first.headers['cache-control'] == 'no-store'
    assert first.json() == service.export_clipboard(original)
    assert client.get(route, params={'factory_id': 'huakang-b'}).json() == first.json()
    assert fields(first.json()['text'])[0][2] == "'0117978388"
    assert db.scalar(select(func.count()).select_from(JPExport)) == 1
    assert [(r.factory_id, r.last_number) for r in db.scalars(select(JPCounter))] == counter
    db.expire(record)
    assert sha256(record.content).hexdigest() == before_hash
    assert client.get(f'{BASE}/exports/{record.id}/download', params={'factory_id': 'huakang-b'}).content == original


@pytest.mark.parametrize('permissions,factory', [(['read'], 'huakang-b'), (['export'], 'huakang-b'), (['read', 'export'], 'huakang-a')])
def test_clipboard_requires_both_read_export_and_factory_scope(client, db, permissions, factory):
    install(db); record = export(db, preview(db))
    client.test_app.dependency_overrides[get_current_user] = lambda: user(permissions, factory=factory)
    assert client.get(f'{BASE}/exports/{record.id}/clipboard', params={'factory_id': 'huakang-b'}).status_code == 403


def test_clipboard_rejects_wrong_factory_missing_id_and_invalid_export(client, db):
    assert client.get(f'{BASE}/exports/absent/clipboard', params={'factory_id': 'huakang-a'}).status_code == 400
    assert client.get(f'{BASE}/exports/absent/clipboard', params={'factory_id': 'huakang-b'}).status_code == 404
    record = JPExport(id='bad', factory_id='huakang-b', request_hash='bad', actor='test', created_at='2026-11-11',
        first_number=1, last_number=1, data={'rows': [{}], 'prefix': '0126'}, content=b'bad')
    db.add(record); db.commit()
    result = client.get(f'{BASE}/exports/{record.id}/clipboard', params={'factory_id': 'huakang-b'})
    assert result.status_code == 422
    assert bytes(record.content) == b'bad'


@pytest.mark.parametrize('hidden_cell', ['A3', 'AT2'])
def test_incorrect_dimension_cannot_hide_extra_rows_or_columns(hidden_cell):
    from zipfile import ZipFile
    import re
    source = document(change=lambda b: setattr(b.active[hidden_cell], 'value', 'hidden'))
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, 'w') as updated:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                data = re.sub(rb'<dimension ref="[^"]+"', b'<dimension ref="A1:AR2"', data)
            updated.writestr(item, data)
    with pytest.raises(ValueError, match='范围'):
        service.export_clipboard(output.getvalue())
