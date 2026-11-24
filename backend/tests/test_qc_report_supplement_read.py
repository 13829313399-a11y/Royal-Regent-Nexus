"""Saved workbook values and audit history reach one isolated inspection, not its neighbours."""
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import qc_dossier_read as dossier
from app.services import qc_daily_report as daily
from app.services import qc_inspection_sheet as sheet, qc_inspection_summary as summary
from app.services import qc_monthly_templates as monthly, qc_weekly_templates as weekly
from app.services import qc_report_workbook as workbook
from app.services.qc_report_supplement_read import FIELD_LABELS
from test_qc_approved_statistics import approval, db, engine, hashes, isolated, transition
from test_qc_monthly_templates import issue
from test_qc_report_workbook import save_request
from test_qc_workflow import ACTOR

FACTORY = 'huaxing'
DAY = '2026-11-03'


def dossier_id(entry):
    return summary.sha256((FACTORY + '\0entry:' + entry['id']).encode()).hexdigest()[:32]


def report_write(kind, entry, field, value):
    data = workbook.projection(FACTORY, kind, DAY, '', 'ALL')
    needle = f'detail:{entry["id"]}:{field}'
    cell = next((cell for cell in workbook.writable_cells(kind, data).values() if cell['field'] == needle), None)
    assert cell, (kind, field)
    if 'writeRevision' in cell:
        body = save_request(cell, value)
        save = lambda: workbook.save_record(FACTORY, ACTOR, kind, DAY, '', 'ALL', body)
    else:
        body = dict(customerKey=cell['customerKey'], field=cell['field'], value=value,
                    baseVersion=cell['version'], date=DAY, sourceRevision=data['sourceRevision'], requestKey=uuid4().hex)
        if kind == 'quality':
            body.update(template='overview', customer='')
        target = weekly if kind == 'detail' else monthly
        save = lambda: target.save(FACTORY, ACTOR, body)
    result = save()
    assert save() == result
    return result


def test_all_eight_workbooks_share_the_correct_record_and_keep_audit(db):
    entry = issue(db, 1, result='FAIL')
    entry = transition(entry, 'revoke')
    with sheet.store(True) as conn:
        # The annual statistics permits an agency supplement only if the
        # synthetic approval has no third-party institution or agency value.
        base = json.loads(sheet.get(conn, FACTORY, entry['id'])['base'])
        base['agency'] = ''
        conn.execute('UPDATE entries SET base=? WHERE id=?',(summary.dump(base),entry['id']))
    entry = transition(entry)
    other = issue(db, 2, result='FAIL')  # Same factory, customer and PO, different entry.
    across = approval(db, 3, 'FAIL', factory='huadeng', customer=entry['customer'])
    rows = [
        ('daily', 'traderQDate', '2026-11-26'),
        ('detail', 'contractNo', '000017'),
        ('issues', 'analysisReason', '周图文补录原因'),
        ('orders', 'contractNo', '000018'),
        ('tracking', 'improvement', '月整改补录'),
        ('quality', 'returnReason', '本单专属退货原因'),
        ('annual-stats', 'institution', '年度补录机构'),
        ('annual-issues', 'correctiveCompletion', '待复核'),
    ]
    assert {kind for kind, *_ in rows} == workbook.KINDS
    original = hashes()
    for kind, field, value in rows:
        report_write(kind, entry, field, value)
    # An unrelated record can be written independently without crossing the same PO.
    report_write('daily', other, 'traderQDate', '2026-11-28')
    data = weekly.query(FACTORY, DAY)
    scope = dict(date=DAY, customerKey=data['customers'][0]['key'], sourceRevision=data['sourceRevision'])
    weekly.save(FACTORY, ACTOR, dict(**scope, field='weeklyRemark', value='整份周报备注不归单笔', baseVersion=0, requestKey=uuid4().hex))
    data = monthly.query(FACTORY, DAY, include_overview=True)
    row = data['overview']['signatures']
    monthly.save(FACTORY, ACTOR, dict(date=DAY, customerKey=row['customerKey'], field='overview:preparer',
        value='月报制表人不归单笔', baseVersion=0, sourceRevision=data['sourceRevision'],
        requestKey=uuid4().hex, template='overview', customer=''))
    assert monthly.query(FACTORY, DAY, include_overview=True)['overview']['signatures']['values'][0] == '月报制表人不归单笔'
    assert weekly.query(FACTORY, DAY)['fields'][scope['customerKey']]['weeklyRemark']['value'] == '整份周报备注不归单笔'

    after_writes = hashes()
    detail = dossier.detail(FACTORY, dossier_id(entry))
    report = detail['reportSupplements']
    assert report['status'] == 'ok' and len(report['items']) == len(report['changes']) == len(rows)
    assert {(row['field'], row['value']) for row in report['items']} == {(field,value) for _,field,value in rows}
    assert all(row['current'] and row['version'] == 1 and row['actor']['id'] == ACTOR['id'] for row in report['changes'])
    assert all(row['before'] == '' and row['after'] and row['at'] for row in report['changes'])
    assert {row['value'] for row in dossier.detail(FACTORY, dossier_id(other))['reportSupplements']['items']} == {'2026-11-28'}
    with pytest.raises(HTTPException) as exc:
        dossier.detail('huadeng', dossier_id(entry))
    assert exc.value.status_code == 404
    east = summary.sha256(('huadeng\0entry:' + across['id']).encode()).hexdigest()[:32]
    assert dossier.detail('huadeng', east)['reportSupplements']['items'] == []
    assert not detail['qc'].get('contractNo') and detail['qc']['result'] == 'FAIL'
    assert hashes() == after_writes and all(after_writes[k] == v for k,v in original.items())


def test_saved_clears_and_reapproved_period_are_not_confused_with_current_qc_data(db):
    entry = approval(db, 1)
    key = dossier_id(entry)
    assert dossier.detail(FACTORY, key)['reportSupplements']['items'] == []
    assert not weekly._path().exists() and not monthly._path().exists()
    report_write('daily', entry, 'traderQDate', '2026-11-21')
    report_write('daily', entry, 'traderQDate', '')
    report_write('daily', entry, 'thirdPartyQDate', '2026-11-22')

    entry = transition(entry, 'revoke')
    with pytest.raises(HTTPException) as exc:
        dossier.detail(FACTORY, key)
    assert exc.value.status_code == 404
    entry = sheet.save(FACTORY, entry['id'], dict(revision=entry['revision'], result='PASS', remark='',
        inspectionExecution={'actualDate':'2026-12-05', 'analysisReason':'待审核填写的原始分析'}), ACTOR, review=True)
    entry = transition(entry)
    detail = dossier.detail(FACTORY, key)
    assert detail['qc']['inspectionExecution']['analysisReason'] == '待审核填写的原始分析'
    assert any(event['changes'].get('inspectionExecution.analysisReason', {}).get('after') == '待审核填写的原始分析'
               for event in detail['changes'])
    report = detail['reportSupplements']
    assert [(r['value'], r['periodStart'], r['current']) for r in report['items']] == [('2026-11-22', '2026-11-01', False)]
    assert {(r['before'], r['after']) for r in report['changes']} == {('', '2026-11-21'), ('2026-11-21', ''), ('', '2026-11-22')}
    assert not any(r['current'] for r in report['changes'])


def test_report_read_failure_is_not_silent_and_does_not_hide_approval(db):
    entry = approval(db, 1)
    report_write('detail', entry, 'contractNo', '00123')
    path = monthly._path()
    path.parent.mkdir(parents=True)
    path.write_text('not a database')
    before = hashes()
    detail = dossier.detail(FACTORY, dossier_id(entry))
    assert detail['reportSupplements']['status'] == 'unavailable'
    assert detail['reportSupplements']['items'][0]['value'] == '00123'
    assert detail['qc']['result'] == 'PASS' and hashes() == before


def test_field_labels_cover_every_record_field_and_no_group_keys():
    required = set(monthly.DETAIL_FIELDS.values()) | set(daily.SUPPLEMENT_COLUMNS.values())
    assert set(FIELD_LABELS) == required
    assert not {'returns','overviewRemark','weeklyRemark'} & set(FIELD_LABELS)
