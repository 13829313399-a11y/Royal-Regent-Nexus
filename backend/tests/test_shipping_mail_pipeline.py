import io
import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from app.services.shipping_mail.documents import DocumentText
from app.services.shipping_mail.fields import extract_fields
from app.services.shipping_mail.pipeline import parse_shipping_document, parse_shipping_email

BOOKING_BODY = """\
Booking Amendment
ROSS 700149016
16 OCT 2026

From: Yantian, Guangdong, China
To: Houston, Texas, US
Customer: BuShipping (Shenzhen)
Commodity: Toys (With Non-Lithium Batteries)

SI Cut Off(截补料时间): 10 月 26, 2026 20:30
CY Cut Off: 10/28/2026 12:00
"""

REAL_SAMPLE = Path(
    r'C:\Users\Administrator\xwechat_files\wxid_xoqqshfub67c22_1c96\msg\file\2026-11\2622_001.pdf'
)


def build_email(body: str, attachments: list[tuple[str, bytes]] | None = None,
                subject: str = 'BN Amendment - ROSS 700149016') -> bytes:
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = 'booking@maersk.example'
    message['To'] = 'shipping@royalregent.example'
    message['Date'] = 'Thu, 16 Oct 2026 09:05:18 +0800'
    message.set_content(body)
    for filename, data in attachments or []:
        maintype, subtype = ('application', 'pdf') if filename.endswith('.pdf') else (
            'application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return bytes(message)


def text_pdf(lines: list[str]) -> bytes:
    canvas = pytest.importorskip('reportlab.pdfgen.canvas')
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 780
    for line in lines:
        pdf.drawString(40, y, line)
        y -= 18
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def packing_workbook(rows: list[list]) -> bytes:
    openpyxl = pytest.importorskip('openpyxl')
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_booking_email_fields():
    result = parse_shipping_email(build_email(BOOKING_BODY), 'booking.eml')
    fields = result['fields']
    assert fields['so_number'] == '700149016'
    assert fields['si_deadline'] == '2026-10-26T20:30'
    assert fields['cutoff_date'] == '2026-10-28T12:00'
    assert fields['port'] == '盐田'
    assert fields['destination_country'] == '美国'
    assert fields['customer'] == 'BuShipping (Shenzhen)'
    # 截关 10-28 前一天
    assert fields['planned_ship_date'] == '2026-10-27'
    assert result['rule_trace'], '规则执行必须有轨迹'


def test_contract_route_voyage_booking_date_and_terminal_fields():
    body = """\
Booking Confirmation
Booking No: SHZ8265013
Booking Date: 11/13/2026
Terminal: YICT
Contract No: CT-100/200/300
Voyage No: 123E
From: Shekou, China
To: Manila, Philippines
SI Cut Off: 11/20/2026 18:00
CY Cut Off: 11/21/2026 12:00
"""
    result = parse_shipping_email(build_email(body, subject='Booking confirmation'), 'booking.eml')
    fields = result['fields']
    assert fields['booking_no'] == 'SHZ8265013'
    assert fields['contract_no'] == 'CT-100/200/300'
    assert fields['contract_tails'] == ['100', '200', '300']
    assert fields['from_port'] == 'Shekou, China'
    assert fields['to_port'] == 'Manila, Philippines'
    assert fields['destination_country'] == '菲律宾'
    assert fields['voyage_no'] == '123E'
    assert fields['booking_date'] == '2026-11-13'
    assert fields['terminal'] == '盐田国际码头'
    assert fields['table_name'] == '盐田国际码头SO排期表'


def test_email_without_so_or_deadlines_warns_instead_of_guessing():
    result = parse_shipping_email(build_email('请查收附件，谢谢。', subject='请查收'), 'plain.eml')
    assert result['fields']['so_number'] == ''
    assert result['fields']['planned_ship_date'] == ''
    assert any('SO/BN' in warning for warning in result['warnings'])
    assert any('SI' in warning for warning in result['warnings'])


def test_multiple_si_candidates_take_earliest_and_warn():
    text = (
        'SI Cut Off: 10/30/2026 18:00\n'
        'SI Cut Off(截补料时间): 10/26/2026 20:30\n'
    )
    extraction = extract_fields(text, received_at='2026-10-16')
    assert extraction.fields['si_deadline'] == '2026-10-26T20:30'
    assert any('多个 SI' in warning for warning in extraction.warnings)


def test_text_pdf_booking_is_parsed():
    data = text_pdf([
        'BOOKING CONFIRMATION',
        'SO# 4501234567',
        '1*40HQ',
        'From: Shekou, China',
        'To: Los Angeles, CA, US',
        'CY Cut Off: 11/05/2026 17:00',
    ])
    result = parse_shipping_document(data, 'booking.pdf')
    assert result['status'] == 'parsed'
    assert result['fields']['so_number'] == '4501234567'
    assert result['fields']['container_type'] == '1*40HQ'
    assert result['fields']['port'] == '蛇口'
    assert result['fields']['planned_ship_date'] == '2026-11-04'


def test_scanned_pdf_requires_manual_entry(monkeypatch):
    monkeypatch.setattr('app.services.shipping_mail.pipeline.read_pdf_ocr_text', lambda data: DocumentText('', 1, False))
    canvas = pytest.importorskip('reportlab.pdfgen.canvas')
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.rect(40, 40, 400, 400, fill=1)
    pdf.showPage()
    pdf.save()
    result = parse_shipping_document(buffer.getvalue(), 'scan.pdf')
    assert result['status'] == 'needs_ocr'
    assert result['kind'] == 'scanned_document'
    assert any('扫描件' in warning for warning in result['warnings'])


def test_email_attachment_scan_warns_and_body_fields_survive(monkeypatch):
    monkeypatch.setattr('app.services.shipping_mail.pipeline.read_pdf_ocr_text', lambda data: DocumentText('', 1, False))
    canvas = pytest.importorskip('reportlab.pdfgen.canvas')
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.rect(40, 40, 400, 400, fill=1)
    pdf.showPage()
    pdf.save()
    result = parse_shipping_email(
        build_email(BOOKING_BODY, [('booking-amendment.pdf', buffer.getvalue())]),
        'with-scan.eml',
    )
    attachment = result['attachments'][0]
    assert attachment['status'] == 'needs_ocr'
    assert result['fields']['so_number'] == '700149016'
    assert any('扫描件' in warning for warning in result['warnings'])


def test_packing_list_workbook_becomes_items():
    data = packing_workbook([
        ['货号', '品名', '客户PO', '数量', '箱数', 'CBM', '毛重', '净重'],
        ['A-1001', '遥控车', 'PO-77', 1200, 100, 6.5, 850, 780],
        ['A-1002', '积木', 'PO-77', 600, 50, 3.25, 420, 380],
        ['合计', '', '', 1800, 150, 9.75, 1270, 1160],
    ])
    result = parse_shipping_document(data, 'packing-list.xlsx')
    assert result['kind'] == 'packing_list'
    assert [item['product_code'] for item in result['items']] == ['A-1001', 'A-1002']
    first = result['items'][0]
    assert first['quantity'] == 1200 and first['cartons'] == 100 and first['cbm'] == 6.5
    assert first['customer_po'] == 'PO-77'
    assert first['source_file'] == 'packing-list.xlsx'


def test_email_with_packing_list_attachment_collects_items():
    data = packing_workbook([
        ['货号', '数量', '箱数'],
        ['B-2001', 300, 25],
    ])
    result = parse_shipping_email(
        build_email(BOOKING_BODY, [('packing-list.xlsx', data)]), 'with-pl.eml',
    )
    assert len(result['items']) == 1
    assert result['items'][0]['product_code'] == 'B-2001'
    assert result['fields']['cargo_source'] == 'attachment'


def test_unsupported_attachment_is_reported_not_fatal():
    result = parse_shipping_email(
        build_email(BOOKING_BODY, [('note.txt', b'hello')]), 'with-txt.eml',
    )
    assert result['attachments'][0]['status'] == 'ignored'
    assert any('未解析附件类型' in warning for warning in result['warnings'])
    assert result['fields']['so_number'] == '700149016'


@pytest.mark.skipif(not REAL_SAMPLE.is_file(), reason='本机真实扫描样本不存在')
def test_real_scanned_booking_sample_is_ocr_parsed():
    result = parse_shipping_document(REAL_SAMPLE.read_bytes(), REAL_SAMPLE.name)
    assert result['status'] == 'parsed'
    assert result['fields']['so_number']
    assert result['fields']['port']


def test_booking_confirmation_carrier_layout_fields():
    text = """Booking Confirmation Update (2)
Booking Number:
48420550
Quotation/Contract No.:
AND INSURANCE BUILDING NO.5013 Customer Reference:CCN4047078-V1
166636625
Request Booking Date:
From To Vessel
21-NOV-2026 00:01 29-DEC-2026 23:00 MANILA EXPRESS 19-OCT-2026
CNYTN YANTIAN DEHAM HAMBURG DP Voyage: 207677
Voy. No: 646W
1 x 42GP, 1 x 45GP
Shipping instruction closing CNYTN 18-NOV-2026 12:00
VGM cut off CNYTN 19-NOV-2026 10:00
GERMANY HAMBURG"""
    fields = extract_fields(text, received_at='2026-11-16').fields
    assert fields['so_number'] == '48420550'
    assert fields['contract_no'] == '166636625'
    assert fields['vessel_name'] == 'MANILA EXPRESS'
    assert fields['voyage_no'] == '646W'
    assert fields['container_type'] == '1*42GP, 1*45GP'
    assert fields['from_port'] == '盐田'
    assert fields['to_port'] == 'DEHAM HAMBURG'
    assert fields['destination_country'] == '德国'
    assert fields['si_deadline'] == '2026-11-18T12:00'
    assert fields['cutoff_date'] == '2026-11-19T10:00'
    assert fields['booking_date'] == '2026-10-19'


def test_maersk_booking_amendment_scanned_layout():
    text = """BOOKING AMENDMENT
Booking No.: 279188253
From:
Yantian,Guangdong,China
To:
Houston,Texas,United States
Service Contract:
298379137
SI Cut Off(截补料时间):星期一，10月 26,2026 20:30
CY Closing - Latest Return Container Date(截重柜时间-最晚还柜时间):星期二， 10月 27, 2026 17:00
Vessel
Voy No.
MVS
MAERSK SALTORO
643E
2026-10-29
40 DRY
1"""
    fields = extract_fields(text, received_at='2026-10-16').fields
    assert fields['so_number'] == '279188253'
    assert fields['contract_no'] == '298379137'
    assert fields['vessel_name'] == 'MAERSK SALTORO'
    assert fields['voyage_no'] == '643E'
    assert fields['container_type'] == '1*40GP'
    assert fields['from_port'] == '盐田'
    assert fields['destination_country'] == '美国'
    assert fields['si_deadline'] == '2026-10-26T20:30'
    assert fields['cutoff_date'] == '2026-10-27T17:00'


def test_cma_cgm_email_cover_page_does_not_override_p2_p3_pol_pod_and_country():
    padding = ('Terms and conditions notice line for CMA CGM cover page.\n' * 85)
    text = f"""From: no-reply.bkgdesk@cma-cgm.com
To: idun.zheng@fms-logistics.com
Subject: Booking Confirmation SHZ8356199

{padding}
BOOKING CONFIRMATION
Booking Reference: SHZ8356199
Service Contract: YFRMS0000003
Vessel: CMA CGM TANYA
Voyage: 0R10UW1MA
2*40HQ
Terminal: YICT
POL = CNYTN (YANTIAN)
POD = DEHAM (HAMBURG)
SI Cut Off: 2026-07-17 07:00
CY Cut Off: 2026-07-17 16:00
"""
    fields = extract_fields(text, received_at='2026-07-10').fields
    assert fields['so_number'] == 'SHZ8356199'
    assert '@' not in fields['from_port']
    assert '@' not in fields['to_port']
    assert '@' not in fields['destination']
    assert fields['from_port'] == '盐田'
    assert fields['port'] == '盐田'
    assert 'DEHAM' in fields['to_port'] and 'HAMBURG' in fields['to_port']
    assert fields['destination_country'] == '德国'


def test_cma_cgm_port_of_loading_and_discharge_with_email_headers():
    text = """From: no-reply.bkgdesk@cma-cgm.com
To: idun.zheng@fms-logistics.com
CMA CGM
Booking No.: SHZ8356199
Port of Loading:
CNYTN (YANTIAN)
Port of Discharge:
DEHAM (HAMBURG)
CY Cut Off: 2026-07-17 16:00
"""
    fields = extract_fields(text, received_at='2026-07-10').fields
    assert fields['from_port'] == '盐田'
    assert fields['to_port'] == 'DEHAM (HAMBURG)'
    assert fields['destination_country'] == '德国'


def test_chinese_so_fullwidth_colons_no_vessel_slash_or_shipper_contract():
    text = """订舱确认书
S/O No.：HLCUSZX26070901
Contract No.:
Shipper
服务合同号/运价协议号：SC-2026-9988
船名/航次：
EVER GIVEN / 088E
装货港：盐田 YICT
卸货港：HAMBURG 汉堡
客户PO：PO-88210
1*40HQ
截补料时间：2026-07-08 12:00
截关时间：2026-07-09 17:00
"""
    fields = extract_fields(text, received_at='2026-07-01').fields
    assert fields['so_number'] == 'HLCUSZX26070901'
    assert fields['booking_no'] == 'HLCUSZX26070901'
    assert fields['contract_no'] == 'SC-2026-9988'
    assert fields['vessel_name'] == 'EVER GIVEN'
    assert fields['voyage_no'] == '088E'
    assert fields['po_no'] == 'PO-88210'
    assert fields['from_port'] == '盐田'
    assert fields['destination_country'] == '德国'
    assert fields['container_type'] == '1*40HQ'
    assert fields['si_deadline'] == '2026-07-08T12:00'
    assert fields['cutoff_date'] == '2026-07-09T17:00'


def test_gbk_chinese_email_and_legacy_xls_attachment_are_parsed():
    xlwt = pytest.importorskip('xlwt')
    book = xlwt.Workbook(encoding='utf-8')
    sheet = book.add_sheet('Packing')
    for col, title in enumerate(['货号', '品名', '数量', '箱数', 'CBM']):
        sheet.write(0, col, title)
    for col, val in enumerate(['SKU-901', '积木套装', 600, 50, 2.5]):
        sheet.write(1, col, val)
    buf = io.BytesIO()
    book.save(buf)

    msg = EmailMessage()
    msg['Subject'] = '订舱通知 S/O：OOLU26071188'
    msg['From'] = 'ops@forwarder.example'
    msg['To'] = 'shipping@huaxing.example'
    msg['Date'] = 'Thu, 02 Jul 2026 10:00:00 +0800'
    body_gbk = (
        '订仓号：OOLU26071188\n'
        '合同号：CT-2026-0711\n'
        '船名/航次：OOCL HONG KONG / 112E\n'
        '装货港：盐田\n'
        '目的港：HAMBURG\n'
        '1*40HQ\n'
        '截补料时间：2026-07-09 12:00\n'
        '截关时间：2026-07-10 17:00\n'
    ).encode('gb18030')
    msg.set_content(body_gbk, maintype='text', subtype='plain', params={'charset': 'gb2312'})
    msg.add_attachment(buf.getvalue(), maintype='application', subtype='vnd.ms-excel', filename='packing.xls')

    result = parse_shipping_email(bytes(msg), 'gbk-so.eml')
    fields = result['fields']
    assert fields['so_number'] == 'OOLU26071188'
    assert fields['contract_no'] == 'CT-2026-0711'
    assert fields['vessel_name'] == 'OOCL HONG KONG'
    assert fields['voyage_no'] == '112E'
    assert fields['destination_country'] == '德国'
    assert len(result['items']) == 1
    assert result['items'][0]['product_code'] == 'SKU-901'
    assert result['items'][0]['cartons'] == 50.0


