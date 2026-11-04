"""Sanitized reproductions of forwarding, item and pricing failures; no real mail fixtures."""
from datetime import date, datetime
from email.message import EmailMessage
from io import BytesIO
from hashlib import sha256
import json

import openpyxl
import pytest
from fastapi import HTTPException

from app.services.huakang_b_jp import intake, parser
from test_huakang_b_jp import db, engine, client, api, install, preview, export, mail, body, user


def table(headers, rows):
    return '<table><tr>' + ''.join(f'<th>{v}</th>' for v in headers) + '</tr>' + ''.join(
        '<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows) + '</table>'


def forwarding(content, cover='婷，请查看以下问单'):
    return (f'<div>{cover}</div><div><strong>发件人：</strong>业务员</div>'
            '<div><strong>发送时间：</strong>2026-10-28&nbsp;15:32</div>'
            '<div><strong>主题：</strong>Re: enquiry</div>'
            '<div><strong>收件人：</strong>跟单员</div><div>&nbsp;</div>' + content)


def farmers():
    return forwarding(
        '<p>Hi Elmond,</p><p>DDD 11/6,请看以下回复.</p>'
        '<p>#25314 All componnet 在1/4送到.</p><p>Shipment surcharge USD380x2.</p>'
        + table(['LOI#', 'JP Item #', 'Description', 'QTY', 'Factory Ship Date', 'PKG', 'Remark'], [
            ['27SSF028', '25273-000-1A-002-OB0', 'Toy A', '240', '1/20', '8L pkg + sound only IC', 'Embargo until 05/01/2027'],
            ['27SSF028', '25314-000-1A-004-SWG', 'Toy B', '320', '2/26', '3L', 'Embargo until 05/01/2027'],
        ]) + '<p>发件人：较旧询问</p>' + body(qty='999'))


def minnie():
    return forwarding(
        '<p>Dear Cynthia,</p><p>DDD/11/06 S/D 1/15</p>'
        '<p>#89374 tag on Neco order no MOQ issue</p><p>#88329 / #38441 NO MOQ issue</p>'
        '<p>#89902 MOQ 5K</p><p>#89902 申请MA/MO失败，是否需要重新申请，谢谢！</p>'
        + table(['Item No.', 'Description', 'IC', 'Pkg', 'Qty'], [
            ['38441 -000-3A-006-BC0', 'Toy C', 'x', '8L', '600'],
            ['88329-INT-1B-002-CB0', 'Toy D', 'Sound Only', '8L CB0', '120'],
            ['89374-000-1A-002-HT0', 'Toy E', 'x', '8L', '240'],
            ['89902-000-1B-002-OTP', 'Toy F', 'x', '/', '240'],
        ]) + '<p>---- Replied Message ----</p>' + body(qty='999'))


def feedback_files():
    return [
        ('farmers.eml', mail(farmers(), 'Fw: Re: Farmers (NZ) - 27SSF028 - Royal Regent')),
        ('minnie.eml', mail(minnie(), 'Fw: Re: Minnie new order for Imexporta / Chile --- Royal Regent')),
    ]


def test_forwarded_current_orders_keep_customers_dates_and_business_notes():
    parsed = []
    for name, content in feedback_files():
        html, _, subject, stamp = parser.parse_eml(content)
        parsed.append(parser.parse_order_email(html, subject, stamp, name))
    f, m = parsed
    assert len(f['orders']) == 2 and len(m['orders']) == 4
    assert f['meta']['order_date'] == m['meta']['order_date'] == '2026/10/28'
    assert f['meta']['ddd'] == 'DDD 11/6'
    assert f['meta']['global_note'] == 'Shipment surcharge USD380x2'
    assert [(r['customer'], r['country']) for r in f['orders']] == [('Farmers', '新西兰')] * 2
    assert [(r['ship_date'], r['cutoff_date']) for r in f['orders']] == [
        ('2027/1/12', '2027/1/20'), ('2027/2/19', '2027/2/26')]
    assert '散件1/4送到' in f['orders'][1]['item_note']
    assert 'Embargo until 05/01/2027' in f['orders'][0]['item_note']
    assert not any('版本不一致' in w for w in f['warnings'])
    assert [(r['customer'], r['country']) for r in m['orders']] == [('Imexporta', '智利')] * 4
    assert all(r['cutoff_date'] == '2027/1/15' and r['ship_date'] == '2027/1/8' for r in m['orders'])
    assert m['orders'][0]['baby_item'] == '38441'
    assert m['orders'][0]['long_code'] == '38441-000-3A-006-BC0'
    assert m['orders'][0]['item_note'] == 'NO MOQ issue'
    assert m['orders'][2]['item_note'] == 'tag on Neco order no MOQ issue'
    assert m['orders'][3]['item_note'] == 'MOQ 5K，申请MA/MO失败，是否需要重新申请'
    assert m['orders'][3]['pkg'] == '/'


@pytest.mark.parametrize('cover', ['FYI', '仅供参考', '取消此单，请查看以下问单'])
def test_generic_or_cancelled_forward_does_not_revive_history(cover):
    result = parser.parse_order_email(forwarding(body(), cover), 'Fw: enquiry', date(2026, 10, 30))
    assert result['orders'] == []


def test_forwarding_unwraps_only_one_message_and_requires_complete_header():
    old = '<p>发件人：旧邮件</p>' + body()
    assert not parser.parse_order_email(forwarding('<p>Thanks</p>' + old), 'Fw: enquiry')['orders']
    partial = '<p>请查看以下问单</p><p>发件人：旧邮件</p>' + body()
    assert not parser.parse_order_email(partial, 'Fw: enquiry')['orders']


def test_forwarding_cover_with_its_own_update_remains_the_newest_reply():
    html = forwarding(body(), '<p>请查看以下问单</p><p>S/D 1/22. 8L pkg.</p>')
    result = parser.parse_order_email(html, 'Fw: WMUS', date(2026, 10, 30))
    assert not result['meta']['forwarded_enquiry']
    assert result['orders'][0]['cutoff_date'] == '2027/1/22'
    assert result['orders'][0]['pkg'] == '8L'


def test_single_spaced_long_item_is_recognized_and_canonicalized():
    html = table(['Item No.', 'Qty'], [['38441 -000-3A-006-BC0', '600']])
    result = parser.parse_order_email(html, 'Imexporta', date(2026, 10, 30))
    assert [(r['baby_item'], r['long_code']) for r in result['orders']] == [('38441', '38441-000-3A-006-BC0')]


def test_quoted_header_table_cannot_leak_old_reply_dates():
    html = body() + '<table><tr><td>发件人：历史邮件</td></tr></table><p>S/D 1/15. 8L pkg.</p>'
    result = parser.parse_order_email(html, 'WMUS', date(2026, 10, 30))
    assert result['orders'][0]['cutoff_date'] == '2026/12/31'
    assert result['orders'][0]['pkg'] == ''


def test_attached_order_mail_is_never_used_as_the_current_body():
    old = EmailMessage()
    old.set_content('old enquiry')
    old.add_alternative(body(qty='999'), subtype='html')
    outer = EmailMessage()
    outer['Subject'] = 'Fw: current enquiry'
    outer.make_mixed()
    outer.add_attachment(old)
    current = EmailMessage()
    current.set_content('current notice only')
    outer.attach(current)
    html, text, _, _ = parser.parse_eml(outer.as_bytes())
    assert html is None and text.strip() == 'current notice only'


def test_feedback_preview_and_44_column_export_use_exact_variant_prices(db):
    install(db)
    files = feedback_files()
    w = openpyxl.Workbook()
    s = w.active
    s.append(['货号编码', '产品货号', '客货价(HK$)', '货运类别', '长货号', '货价日期', '外箱-装箱数'])
    codes = ['25273-000-1A-002-OB0', '25314-000-1A-004-SWG', '38441-000-3A-006-BC0',
             '88329-INT-1B-002-CB0', '89374-000-1A-002-HT0', '89902-000-1B-002-OTP']
    for code in codes:
        for category, value in [('柜货', 25), ('出厂价', 20)]:
            s.append([code + category, code[:5], value, category, code, date(2026, 1, 1), int(code.split('-')[3])])
    # A newer different variant must not override this order's exact long code.
    s.append(['different-variant', '89374', 40.872, '柜货', '89374-000-1A-002-HT9', date(2026, 10, 31), 2])
    b = BytesIO(); w.save(b)
    api.transaction(db, lambda: intake.save_reference(db, 'price', 'synthetic-price.xlsx', b.getvalue(), 1, '测试'))
    p = preview(db, files)
    assert len(p['rows']) == 6 and p['failed_sources'] == []
    assert [r['carton_t'] for r in p['rows']] == ['2', '4', '6', '2', '2', '2']
    assert all(r['price_t'] == '25' and r['factory_price_t'] == '20' and not r['price_confirm'] for r in p['rows'])
    record = export(db, p, files=files)
    out = openpyxl.load_workbook(BytesIO(record.content)).active
    assert out.max_row == 7 and out.max_column == 44
    assert [out.cell(i, 2).value for i in range(2, 8)] == ['Farmers'] * 2 + ['Imexporta'] * 4
    assert out.cell(4, 11).value == '38441'
    assert out.cell(2, 18).value == datetime(2027, 1, 12)
    assert out.cell(2, 20).value == datetime(2027, 1, 20)
    assert out.cell(6, 21).value == 25 and out.cell(6, 24).value == 20
    assert all(out.cell(i, 22).value is None and out.cell(i, 23).value is None for i in range(2, 8))
    assert 'DDD 11/6' in out.cell(2, 28).value and 'Shipment surcharge USD380x2' in out.cell(2, 28).value
    assert 'MOQ 5K' in out.cell(7, 28).value and '申请MA/MO失败' in out.cell(7, 28).value


def test_fallback_variant_price_requires_recorded_review_before_export(db):
    install(db)
    files = [('other-variant.eml', mail(body().replace('2B-003', '2C-003')))]
    p = preview(db, files)
    row = p['rows'][0]
    assert row['price_confirm'] and row['price_t'] == '12.5'
    with pytest.raises(HTTPException, match='货价未精确匹配'):
        export(db, p, files=files)
    changes = [{'id': row['id'], 'field': f, 'value': row[f]} for f in ('price_t', 'factory_price_t')]
    record = export(db, p, overrides=changes, files=files)
    assert record.data['rows'][0]['manual_price_review'] is True


def test_current_package_is_not_replaced_by_schedule_history(db):
    install(db)
    html = body().replace('<th>Customer PO</th>', '<th>Customer PO</th><th>Pkg</th>').replace(
        '<td>0117978388</td>', '<td>0117978388</td><td>/</td>')
    p = preview(db, [('package.eml', mail(html))])
    assert p['rows'][0]['pkg'] == '/'
    assert any('当前邮件包装 / 与排期历史 3L 不同，保留当前邮件' in w for w in p['warnings'])


def test_exact_customer_price_does_not_approve_another_variants_factory_price(db):
    install(db)
    w = openpyxl.Workbook()
    s = w.active
    s.append(['货号编码', '产品货号', '客货价(HK$)', '货运类别', '长货号', '货价日期', '外箱-装箱数'])
    s.append(['current', '67053', 12.5, '柜货', '67053-000-2B-003-WB0', date(2026, 1, 1), 3])
    s.append(['other', '67053', 10, '出厂价', '67053-000-2C-003-WB0', date(2026, 1, 1), 3])
    b = BytesIO(); w.save(b)
    api.transaction(db, lambda: intake.save_reference(db, 'price', 'synthetic-price.xlsx', b.getvalue(), 1, '测试'))
    p = preview(db)
    assert p['rows'][0]['price_confirm']
    assert '出厂价未按本单' in p['rows'][0]['price_note']
    with pytest.raises(HTTPException, match='货价未精确匹配'):
        export(db, p)


@pytest.mark.parametrize('category,long_code', [
    ('柜货', '67053-000-2B-003-WB0'),
    ('客派车', '67053-000-2C-003-WB0'),
])
def test_amazon_category_or_variant_fallback_requires_price_review(db, category, long_code):
    install(db)
    w = openpyxl.Workbook()
    s = w.active
    s.append(['货号编码', '产品货号', '客货价(HK$)', '货运类别', '长货号', '货价日期', '外箱-装箱数'])
    s.append(['customer-price', '67053', 12.5, category, long_code, date(2026, 1, 1), 3])
    s.append(['factory-price', '67053', 10, '出厂价', '67053-000-2B-003-WB0', date(2026, 1, 1), 3])
    b = BytesIO(); w.save(b)
    api.transaction(db, lambda: intake.save_reference(db, 'price', 'synthetic-price.xlsx', b.getvalue(), 1, '测试'))
    files = [('amazon.eml', mail(body(), 'Amazon order inquiry'))]
    p = preview(db, files)
    row = p['rows'][0]
    assert row['price_confirm'] and row['price_t'] == '12.5' and row['factory_price_t'] == '10'
    with pytest.raises(HTTPException, match='货价未精确匹配'):
        export(db, p, files=files)


def test_preview_semantic_version_changes_fingerprint_without_changing_inputs(db, monkeypatch):
    install(db)
    files = [('versioned.eml', mail())]
    current = preview(db, files)
    assert current['preview_schema_version'] == 'huakang-b-jp-preview-v2'
    with monkeypatch.context() as ctx:
        ctx.setattr(intake, 'PREVIEW_SCHEMA_VERSION', 'huakang-b-jp-preview-v1')
        old = preview(db, files)
    assert old['fingerprint'] != current['fingerprint']
    assert old['rows'] == current['rows']
    assert old['inputs'] == current['inputs']


def test_api_rejects_pre_upgrade_fingerprint_even_with_identical_files_and_references(client, db):
    install(db)
    content = mail()
    form = {'factory_id': 'huakang-b', 'received_date': '2026-10-13', 'merchandiser': '测试跟单'}
    files = [('files', ('test.eml', content, 'message/rfc822'))]
    response = client.post('/api/huakang-b-jp/preview', data=form, files=files)
    assert response.status_code == 200, response.text
    current = response.json()
    actor = user(['read', 'write', 'export'], factory='huakang-b')
    legacy = intake.digest({'files': [('test.eml', sha256(content).hexdigest())],
        'html': '', 'subject': '', 'received': '2026-10-13', 'choices': [],
        'references': [(k, m['id'], m['revision']) for k, m, _ in intake.snapshots(db)],
        'actor': actor.id, 'merchandiser': '测试跟单'})
    form.update(fingerprint=legacy, selected=json.dumps([r['id'] for r in current['rows']]),
                confirmed=True, reason='逐项核对正确')
    response = client.post('/api/huakang-b-jp/export', data=form, files=files)
    assert response.status_code == 409 and '解析规则' in response.text
    form['fingerprint'] = current['fingerprint']
    response = client.post('/api/huakang-b-jp/export', data=form, files=files)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('nested', [False, True])
def test_current_layout_table_instructions_survive_order_table_filtering(nested):
    instructions = table(['Current reply'], [['DDD 11/6 S/D 1/15. 8L pkg.'], ['Shipment surcharge USD380x2.']])
    orders = table(['Item No.', 'Qty'], [['38441-000-3A-006-BC0', '600']])
    html = instructions + orders
    if nested:
        # Layout content before and after an inner order table must survive;
        # the inner </table> must not terminate the outer layout prematurely.
        html = '<table><tr><td>' + instructions + orders + '</td></tr><tr><td>MOQ 5K</td></tr></table>'
    result = parser.parse_order_email(html, 'Imexporta', date(2026, 10, 30))
    assert len(result['orders']) == 1
    assert result['meta']['ddd'] == 'DDD 11/6'
    assert result['meta']['sd'] == '2027/1/15'
    assert 'Shipment surcharge USD380x2' in result['meta']['global_note']
    if nested:
        assert 'MOQ 5K' in result['meta']['global_note']
    assert result['orders'][0]['cutoff_date'] == '2027/1/15'
    assert result['orders'][0]['pkg'] == '8L'


def test_order_table_packaging_stays_row_specific_with_layout_instructions():
    instructions = table(['Current reply'], [['DDD 11/6 S/D 1/15.']])
    orders = table(['Item No.', 'Qty', 'Pkg'], [
        ['25273-000-1A-002-OB0', '240', '8L pkg + sound only IC'],
        ['25314-000-1A-004-SWG', '320', '3L'],
        ['38441-000-3A-006-BC0', '600', ''],
    ])
    result = parser.parse_order_email(instructions + orders, 'Farmers', date(2026, 10, 30))
    assert [row['pkg'] for row in result['orders']] == ['8L pkg + sound only IC', '3L', '']
    assert all(row['cutoff_date'] == '2027/1/15' for row in result['orders'])
    assert result['meta']['ddd'] == 'DDD 11/6'
    assert not any('版本不一致' in warning for warning in result['warnings'])
