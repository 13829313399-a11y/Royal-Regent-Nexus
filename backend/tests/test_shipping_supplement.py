from types import SimpleNamespace

from app.services.shipping_supplement import _line, compute_totals, render_supplement_xlsx


def test_supplement_line_math_and_totals():
    task = SimpleNamespace(container_type='1*40HQ', so_number='SZPM39654400', planned_ship_date='2026-06-16')
    line = _line({'product_code': '40624', 'product_name': 'PNP PUP TOTES', 'cartons': 1760,
                  'quantity': 5280, 'cbm': 24.64, 'gross_weight': 2604.8, 'customer_po': 'OE-1931976'},
                 {'contract_no': 'SE -1926407'}, task)
    assert line['size'] == '40HQ'
    assert line['ctns'] == 1760
    assert line['qty'] == 5280
    assert line['cbmPerCarton'] == 0.014
    assert line['cbm'] == 24.64
    assert line['gwPerCarton'] == 1.48
    assert line['gw'] == 2604.8
    totals = compute_totals([line])
    assert totals['ctns'] == 1760
    assert totals['qty'] == 5280
    assert totals['vgm'] == 2604.8


def test_supplement_export_is_xlsx():
    header = {
        'to': 'PLAYMATE', 'from': 'ROYAL REGENT', 'subject': 'SHIPMENT ADVICE', 'ref': '',
        'date': '2026-06-16', 'customerMarket': 'PLAYMATES-USA', 'vessel': 'MOL COURAGE/0067E',
        'portOfLoading': 'YANTIAN', 'portOfDischarge': 'USA', 'etd': '2026-06-21',
        'invoice': 'RPM00076', 'origin': 'CHINA', 'receipt': '',
    }
    task = SimpleNamespace(container_type='40HQ', so_number='SZPM39654400', planned_ship_date='2026-06-16')
    line = _line({'product_code': '40624', 'product_name': 'PNP PUP TOTES', 'cartons': 1760,
                  'quantity': 5280, 'cbm': 24.64, 'gross_weight': 2604.8}, {'contract_no': 'SE-1926407'}, task)
    content = render_supplement_xlsx({'header': header, 'lines': [line]})
    assert content[:2] == b'PK'
    assert len(content) > 4000
