"""Missing commercial information is advisory; never invent values or approval."""
from io import BytesIO
import json

import openpyxl
import pytest
from sqlalchemy import select, func

from app.models.huakang_b_jp import JPCounter, JPExport, JPExportIdentity
from app.services.huakang_b_jp import intake
from test_huakang_b_jp import engine, db, client, api, mail, body, install, xlsx


BASE = '/api/huakang-b-jp'
SCOPE = {'factory_id': 'huakang-b'}


def generate(client, content, **extra):
    form = {**SCOPE, 'received_date': '2026-11-11', **extra}
    files = {'files': ('synthetic.eml', content, 'message/rfc822')}
    response = client.post(BASE + '/preview', data=form, files=files)
    assert response.status_code == 200, response.text
    preview = response.json()
    response = client.post(BASE + '/export', files=files, data={**form,
        'fingerprint': preview['fingerprint'], 'selected': json.dumps([r['id'] for r in preview['rows']])})
    assert response.status_code == 200, response.text
    saved = response.json()
    content = client.get(BASE + '/exports/' + saved['id'] + '/download', params=SCOPE).content
    return saved, openpyxl.load_workbook(BytesIO(content)), preview


def test_no_references_review_reason_or_merchandiser_can_generate_without_claiming_number_or_review(client, db):
    raw = mail(body().replace('<p>S/D 12/31/2026</p>', ''))
    saved, workbook, preview = generate(client, raw)
    row = list(workbook.active.values)[1]
    assert len(row) == 44
    assert saved['numbering_status'] == 'pending' and saved['first_number'] == saved['last_number'] == 0
    assert row[0] is None and row[17] is None and row[19] is None
    assert row[20] is None and row[23] is None and row[39] is None
    assert row[38] == '待核对' and row[12] == 648
    record = db.get(JPExport, saved['id'])
    assert record.data['reason'] == '' and record.data['review_status'] == 'pending'
    assert record.data['generation_reminders'] and any('未上传' in w for w in preview['warnings'])
    assert db.get(JPCounter, 'huakang-b') is None
    assert db.scalar(select(func.count()).select_from(JPExportIdentity)) == 0
    again, _, _ = generate(client, raw)
    assert again['id'] == saved['id']
    assert client.get(BASE + '/exports/' + saved['id'] + '/clipboard', params=SCOPE).status_code == 200

    # Adding an authoritative baseline allows the same enquiry to be numbered;
    # its previous unnumbered immutable file is still downloadable unchanged.
    old_bytes = record.content
    install(db)
    allocated, _, _ = generate(client, raw)
    assert allocated['first_number'] == 21615 and allocated['numbering_status'] == 'allocated'
    assert client.get(BASE + '/exports/' + saved['id'] + '/download', params=SCOPE).content == old_bytes
    assert db.scalar(select(func.count()).select_from(JPExportIdentity)) == 1


def test_missing_prices_carton_customer_and_dates_export_as_blanks_with_numbered_history(client, db):
    install(db)
    raw = mail(body())
    form = {**SCOPE, 'received_date': '2026-11-11'}
    files = {'files': ('synthetic.eml', raw)}
    preview = client.post(BASE + '/preview', data=form, files=files).json()
    fields = ['customer', 'carton_t', 'ship_date', 'cutoff_date', 'price_t', 'factory_price_t']
    changes = [{'id': preview['rows'][0]['id'], 'field': field, 'value': ''} for field in fields]
    result = client.post(BASE + '/export', data={**form, 'fingerprint': preview['fingerprint'],
        'selected': json.dumps([preview['rows'][0]['id']]), 'overrides': json.dumps(changes)}, files=files)
    assert result.status_code == 200, result.text
    record = db.get(JPExport, result.json()['id'])
    sheet = openpyxl.load_workbook(BytesIO(record.content)).active
    assert sheet.cell(2, 1).value.endswith('-21615')
    assert all(sheet.cell(2, index).value is None for index in (2, 15, 18, 20, 21, 24))
    assert sheet.cell(2, 39).value == '待核对'
    assert record.data['generation_reminders'] and not record.data['rows'][0]['manual_price_review']


def test_unrecognized_extra_source_is_visible_and_saved_without_blocking_recognized_rows(client, db):
    install(db)
    saved, workbook, preview = generate(client, mail(), html='This extra body has no order table')
    assert preview['failed_sources'] == ['粘贴正文'] and saved['row_count'] == 1
    assert workbook.active.max_row == 2
    assert db.get(JPExport, saved['id']).data['failed_sources'] == ['粘贴正文']


def test_schedule_only_and_previous_counter_still_supply_monotonic_numbering(client, db):
    api.transaction(db, lambda: intake.save_reference(db, 'schedule', 'schedule.xlsx', xlsx('schedule'), 0, '测试'))
    first, sheet, _ = generate(client, mail())
    assert first['first_number'] == 21615 and sheet.active.cell(2, 21).value is None
    # A missing price table must not suppress the existing numbering baseline.
    second, _, _ = generate(client, mail(body(po='0000000002')))
    assert second['first_number'] == 21616


@pytest.mark.parametrize('field,value', [('qty', '-1'), ('qty', '0'), ('price_t', '-1'), ('ship_date', '2027/2/30')])
def test_actual_invalid_values_still_reject_without_reserving_numbers(client, db, field, value):
    install(db)
    form = {**SCOPE, 'received_date': '2026-11-11'}
    files = {'files': ('synthetic.eml', mail())}
    preview = client.post(BASE + '/preview', data=form, files=files).json()
    response = client.post(BASE + '/export', files=files, data={**form, 'fingerprint': preview['fingerprint'],
        'selected': json.dumps([preview['rows'][0]['id']]),
        'overrides': json.dumps([{'id': preview['rows'][0]['id'], 'field': field, 'value': value}])})
    assert response.status_code == 400
    assert db.get(JPCounter, 'huakang-b') is None
