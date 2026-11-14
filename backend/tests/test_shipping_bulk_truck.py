from app.services.shipping_bulk_truck import _line, compute_totals, render_bulk_xlsx


def test_bulk_truck_line_math():
    line = _line({'product_code': '77794UQ1', 'quantity': 2400, 'cartons': 150,
                  'gross_weight': 861, 'net_weight': 578, 'cbm': 4.77}, '4500218843', '280386965')
    assert line['coefficient'] == 16
    assert line['quantity'] == 2400
    assert line['cartons'] == 150
    assert line['grossPerCarton'] == 5.74
    assert line['netPerCarton'] == 3.853
    assert line['grossWeight'] == 861
    assert line['netWeight'] == 578
    assert line['cbmPerCarton'] == 1.126
    assert line['cbm'] == 4.77
    totals = compute_totals([line])
    assert totals['quantity'] == 2400
    assert totals['cartons'] == 150


def test_bulk_truck_workbook_is_xlsx():
    header = {
        'toNames': ['苏迪', '罗梓良'], 'fromName': '农建壮', 'sheetDate': '2026-10-31',
        'vehicle': 'W218', 'transport': '建联派', 'truckType': '3T', 'tradeTerm': 'FOB',
        'tableName': '2026年盐田散货W218车', 'cutoff': '2026-10-31T18:00', 'originPort': '盐田',
    }
    line = _line({'product_code': '77794UQ1', 'quantity': 2400, 'cartons': 150,
                  'gross_weight': 861, 'net_weight': 578, 'cbm': 4.77}, '4500218843', '280386965')
    content = render_bulk_xlsx({'header': header, 'lines': [line]})
    assert content[:2] == b'PK'
    assert len(content) > 4000
