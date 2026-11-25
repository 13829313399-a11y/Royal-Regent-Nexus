from app.services.shipping_zuru import _line, compute_totals, render_zuru_xlsx


def test_zuru_line_math_and_totals():
    line = _line({
        'product_code': '77903TQ1', 'quantity': 8352, 'cartons': 2088,
        'gross_weight': 5136.48, 'net_weight': 2764.5, 'customer_po': 'FB15423',
    }, '4500222023', 'UNITED KINGDOM')
    assert line['filingCode'] == '77903TQ1'
    assert line['coefficient'] == 4
    assert line['quantity'] == 8352
    assert line['grossPerCarton'] == 2.46
    assert line['netPerCarton'] == 1.324
    assert line['grossWeight'] == 5136.48
    assert line['po'] == 'FB15423'

    totals = compute_totals([line, {**line, 'quantity': 97, 'cartons': 97,
                                    'grossWeight': 100, 'netWeight': 50, 'cbm': 2}])
    assert totals['quantity'] == 8449
    assert totals['cartons'] == 2185


def test_zuru_export_is_xlsx():
    header = {
        'toNames': ['苏迪', '罗梓良'], 'fromName': '农建壮', 'sheetDate': '2026-11-09',
        'cutoff': '2026-11-10', 'number': 'W187', 'soNo': 'SZPE39988600',
        'vesselVoyage': 'CMA CGM TANYA 0R104W1MA', 'blNo': '', 'transportCompany': '建联',
        'containerType': '40HQ', 'tradeTerm': 'FOB', 'plate': '', 'containerNo': '',
        'sealNo': '', 'tareWeight': '', 'originPort': '盐田', 'destinationCountry': 'UNITED KINGDOM',
    }
    line = _line({'product_code': '77903TQ1', 'quantity': 8352, 'cartons': 2088,
                  'gross_weight': 5136.48, 'net_weight': 2764.5}, '4500222023', 'UNITED KINGDOM')
    content = render_zuru_xlsx({'header': header, 'lines': [line]})
    assert content[:2] == b'PK'
    assert len(content) > 4000
