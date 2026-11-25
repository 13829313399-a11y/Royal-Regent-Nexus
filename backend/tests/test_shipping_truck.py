from app.services.shipping_truck import _line, compute_totals, render_truck_xls


def test_truck_line_math_and_totals():
    line = _line({
        'product_code': '67771-2', 'product_name': '塑胶玩具子弹枪5个/箱',
        'quantity': 860, 'cartons': 172, 'gross_weight': 516, 'net_weight': 412.8,
        'customer_po': '0968136498',
    }, '加拿大')
    assert line['coefficient'] == 5
    assert line['pieces'] == 172
    assert line['grossPerCarton'] == 3
    assert line['netPerCarton'] == 2.4
    assert line['grossWeight'] == 516
    assert line['netWeight'] == 412.8
    totals = compute_totals([line])
    assert totals == {'quantity': 860, 'pieces': 172, 'grossWeight': 516, 'netWeight': 412.8, 'cbm': 0}


def test_truck_workbook_is_non_empty_xls():
    header = {
        'shipper': '华兴玩具制品（河源）有限公司', 'consignee': '华登玩具制品有限公司',
        'reference': 'PXR8V6T2F2ZD', 'toName': '罗梓良', 'vehicle': 'W15',
        'cfs': '02月26日 入盐港2号仓 1只3吨车如下', 'tradeTerm': 'EXW', 'cc': 'PAT',
        'tableName': '入盐港2号仓客上车W15车', 'consolidator': '华兴与新际拼车',
        'scheduleText': '2/26装车，2/27交仓', 'brandNote': '1票ADVENTURE FORCE品牌',
        'plate': '粤BE7959', 'cutoff': '2026-02-27T15:00', 'sheetDate': '2026-02-10',
        'preparer': '农建壮',
    }
    line = _line({'product_code': '67771', 'product_name': '塑胶玩具子弹枪5个/箱',
                  'quantity': 860, 'cartons': 172, 'gross_weight': 516, 'net_weight': 412.8}, '加拿大')
    content = render_truck_xls({'header': header, 'lines': [line]})
    assert content[:4] == b'\xd0\xcf\x11\xe0'
    assert len(content) > 4000
