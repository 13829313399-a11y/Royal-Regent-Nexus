"""Public synthetic converted-PO samples for scoped offline delivery."""
from io import BytesIO
import openpyxl
import pytest
from app.services import customer_order_unified as service
from test_customer_order_unified import _template_bytes

TRIAL_TEXT = {
    'spin': '''SPIN MASTER PURCHASE ORDER
NUMBER: 4500000123
DATE 01/11/2026
1 1000 PC 12345678
Synthetic Toy
Sales Material: 87654321 1250 USD Per 01/12/2026 1250
Material Group: 67750 1000 PC
Sales Order: 123456 Line Item: 10
Customer PO: DEMO-SPIN-001
Customer: DEMO US
''',
    'simba': '''Release Order
Reference: SC700144914/800
Date of creation: 01.NOV.2026
Mat. No.: 109491008
Synthetic Plush Toy
Packing: 0 PC / 12 PC
Quantity Master Contract No. PO Contract No. Unit Price Delivery Date
264 PC 500055145/10 300493420/10 40.45 HKD 01.DEC.2026
Total CTN: 22
Port of discharge: MELBOURNE
''',
}


def converted_po(customer):
    book = openpyxl.Workbook()
    for line in TRIAL_TEXT[customer].splitlines():
        book.active.append([line])
    stream = BytesIO(); book.save(stream); book.close()
    return stream.getvalue()


@pytest.mark.parametrize('customer', ('spin', 'simba'))
def test_synthetic_scoped_demo_uses_actual_parser_and_export(customer):
    output, _, preview = service.export_unified_customer_schedule(factory_id='huadeng',
        customer_code=customer, received_date='2026-11-19',
        po_files=[('DEMO_PO.xlsx', converted_po(customer))],
        schedule_file_name='DEMO.xlsx', schedule_content=_template_bytes())
    assert len(preview['rows']) == 1
    assert preview['summary']['blocked'] == 0
    book = openpyxl.load_workbook(BytesIO(output))
    assert preview['rows'][0]['product_no'] in [c.value for c in book['ITEM表']['H']]
    assert float(preview['rows'][0]['unit_price_usd' if customer == 'spin' else 'unit_price_hkd']) > 0
