from app.services.shipping_loading import _hq_payload, _line_from_item, compute_totals, render_xls
import xlrd


def test_line_math_and_totals():
    fields = {'contract_no': 'SC700140332-1000'}
    line = _line_from_item({
        'product_code': '20 374 2018', 'product_name': '线控垃圾车',
        'quantity': 600, 'cartons': 50, 'gross_weight': 201, 'net_weight': 138, 'cbm': 1.55,
    }, fields)
    assert line['contract'] == 'SC700140332-1000'
    assert line['quantity'] == 600
    assert line['cartons'] == 50
    assert line['grossPerCarton'] == 4.02
    assert line['netPerCarton'] == 2.76
    assert line['grossWeight'] == 201
    assert line['netWeight'] == 138
    assert line['department'] == 'W'

    totals = compute_totals([line, {**line, 'id': 'b', 'quantity': 2075, 'cartons': 75,
                                    'grossWeight': 500, 'netWeight': 400, 'cbm': 2}])
    assert totals == {'quantity': 2675, 'cartons': 125, 'grossWeight': 701, 'netWeight': 538, 'cbm': 3.55}


def test_workbook_is_a_non_empty_xls():
    header = {
        'shipper': '华兴玩具制品（河源）有限公司', 'consignee': '测试收货商', 'soNo': 'GGZ2947883',
        'vessel': 'CMA CGM TANYA', 'voyage': '0R104W1MA', 'containerType': '40HQ',
        'cutoff': '2026-04-24T06:00', 'sheetDate': '2026-04-13', 'number': 'W11',
        'originPort': '盐田', 'destinationCountry': '德国', 'preparer': '农建壮',
    }
    lines = [_line_from_item({'product_code': '203742018', 'product_name': '线控垃圾车',
                              'quantity': 600, 'cartons': 50, 'gross_weight': 201,
                              'net_weight': 138, 'cbm': 1.55}, {})]
    content = render_xls({'header': header, 'lines': lines})
    assert content[:4] == b'\xd0\xcf\x11\xe0'
    assert len(content) > 4000


def test_pallet_count_is_not_written_into_exported_xls_or_hq():
    header = {
        'shipper': '华兴玩具制品（河源）有限公司', 'consignee': '测试收货商', 'soNo': 'GGZ2947883',
        'vessel': 'CMA CGM TANYA', 'voyage': '0R104W1MA', 'containerType': '40HQ',
        'cutoff': '2026-04-24T06:00', 'sheetDate': '2026-04-13', 'number': 'W11',
        'originPort': '盐田', 'destinationCountry': '德国', 'preparer': '农建壮',
    }
    line = _line_from_item({
        'product_code': '203742018', 'product_name': '线控垃圾车',
        'quantity': 600, 'cartons': 50, 'gross_weight': 201,
        'net_weight': 138, 'cbm': 1.55,
    }, {})
    assert line['pallet'] is None
    line['pallet'] = 987

    content = render_xls({'header': header, 'lines': [line]})
    book = xlrd.open_workbook(file_contents=content)
    for sheet in book.sheets():
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                val = sheet.cell_value(r, c)
                text = str(val)
                assert '987' not in text
                assert '卡板' not in text

    hq_payload = _hq_payload(header, [line])
    assert 'pallet' not in hq_payload['lines'][0]
