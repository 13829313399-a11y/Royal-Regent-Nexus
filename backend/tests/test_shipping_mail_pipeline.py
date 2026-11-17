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
