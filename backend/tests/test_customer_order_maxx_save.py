"""MAXX save regression using constructed PO and disposable SQLite only."""
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from test_customer_order_ledger import engine, db, client, user
from test_customer_order_regional import template
from app.api import customer_order as mapping
from app.services import customer_order_unified as service
from app.services.auth import get_current_user


def arguments():
    lines = ['MAXX MARKETING', 'P.O. NO. PO-HK-260999 (REVISION NO. 0)',
             'P.O. DATE 14/4/2026', 'TERMS OF DELIVERY FCA HK', 'DELIVERY 6/7/2026',
             'S.C. NO. SC-HK-260999', 'Project# 260999 Test Project',
             'ITEM NO. ITEM DESCRIPTION QUANTITY U/M USD UNIT PRICE USD AMOUNT',
             '260999-001 Test Item 6000 Pieces 2.2700 13,620.00']
    writer = PdfWriter()
    page = writer.add_blank_page(width=900, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    escaped = [s.replace('(', r'\(').replace(')', r'\)') for s in lines]
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 9 Tf 12 TL 30 760 Td ' + ' T* '.join(f'({s}) Tj' for s in escaped) + ' ET').encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return dict(customer_code='maxx', factory_id='huakang-d', received_date='2026-10-08',
                po_files=[('test-maxx.pdf', output.getvalue())], schedule_file_name='test.xlsx', schedule_content=template())


@pytest.mark.parametrize('authorized', [True, False])
def test_maxx_http_save_missing_cartons_nonblocking_and_permissions(client, db, authorized):
    args = arguments()
    identity = user(['read', 'write'] if authorized else ['read'], factory='huakang-d')
    client.test_app.dependency_overrides[get_current_user] = lambda: identity
    preview = service.create_unified_customer_preview(**args)
    assert preview['summary']['blocked'] == 0
    assert preview['rows'][0]['units_per_carton'] == preview['rows'][0]['carton_count'] == ''
    mapping._finalize_preview(preview, received_date=args['received_date'], current_user=identity, factory_id='huakang-d')
    form = dict(factory_id='huakang-d', received_date=args['received_date'], confirmed='true',
                source_kind='formal', preview_fingerprint=preview['preview_fingerprint'], confirmation_reason='合成订单测试核对')
    files = [('po_files', (n, c, 'application/pdf')) for n, c in args['po_files']]
    files.append(('schedule_file', (args['schedule_file_name'], args['schedule_content'],
                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')))
    response = client.post('/api/customer-order-ledger/imports/maxx', data=form, files=files)
    assert response.status_code == (200 if authorized else 403), response.text
    if authorized:
        assert response.json()['created_count'] == 1
        retry = client.post('/api/customer-order-ledger/imports/maxx', data=form, files=files)
        assert retry.status_code == 200, retry.text
        assert retry.json()['created_count'] == 0
        assert retry.json()['existing_count'] == 1
