from types import SimpleNamespace

from app.services import file_open, shipping_bulk_truck, shipping_loading, shipping_supplement


def test_supplement_xlsx_preview_preserves_merges_fills_borders_and_dates():
    header = {
        'to': 'PLAYMATE', 'from': 'ROYAL REGENT', 'subject': 'SHIPMENT ADVICE', 'ref': '',
        'date': '2026-11-24', 'customerMarket': 'GERMANY', 'vessel': 'HMM SOUTHAMPTON',
        'portOfLoading': 'YANTIAN', 'portOfDischarge': 'GERMANY', 'etd': '2026-11-24',
        'invoice': 'HAMN00411A', 'origin': 'CHINA', 'receipt': 'CHINA',
    }
    task = SimpleNamespace(container_type='40HQ', so_number='HKGGC6501802', planned_ship_date='2026-11-24')
    line = shipping_supplement._line(
        {'product_code': 'TRICYCLE-6501802', 'product_name': '三轮车', 'cartons': 5, 'quantity': 5, 'cbm': 0.5, 'gross_weight': 10},
        {'contract_no': 'HAMN00411A'}, task,
    )
    content = shipping_supplement.render_supplement_xlsx({'header': header, 'lines': [line]})
    sheets = file_open.workbook_preview('TRICYCLE-6501802.xlsx', content)

    assert len(sheets) == 1
    sheet = sheets[0]
    assert sheet['colWidths']
    assert sheet['rowHeights']
    cells = sheet['cells']
    assert cells

    flat = [cell for row in cells for cell in row]
    assert any(cell.get('bg') == '#ffff00' for cell in flat)
    assert any(cell.get('bg') == '#92d050' for cell in flat)
    assert any(cell.get('cs', 1) > 1 or cell.get('rs', 1) > 1 for cell in flat)
    assert any(cell.get('skip') for cell in flat)
    assert any(cell.get('border') for cell in flat)
    assert not any('00:00:00' in cell.get('v', '') for cell in flat)


def test_loading_xls_preview_preserves_merges_fills_borders_and_dates():
    header = {
        'shipper': '华兴玩具制品（河源）有限公司', 'consignee': 'ROSS', 'soNo': '279188253',
        'vessel': 'ONE', 'voyage': '101E', 'containerType': '40HQ',
        'cutoff': '2026-10-27T17:00', 'sheetDate': '2026-11-24', 'number': 'W1',
        'originPort': '盐田', 'destinationCountry': '美国', 'preparer': '农建壮', 'photoNote': '注，要照相',
    }
    line = shipping_loading._line_from_item({
        'product_code': 'ROSS-279188253', 'product_name': 'TOY',
        'quantity': 1200, 'cartons': 100, 'gross_weight': 500, 'net_weight': 400, 'cbm': 10,
    }, {'contract_no': '298379137'})
    content = shipping_loading.render_xls({'header': header, 'lines': [line]})
    sheets = file_open.workbook_preview('ROSS-279188253.xls', content)

    assert len(sheets) == 1
    sheet = sheets[0]
    assert sheet['colWidths']
    assert sheet['rowHeights']
    flat = [cell for row in sheet['cells'] for cell in row]
    photo = next((cell for cell in flat if '注，要照相' in cell.get('v', '')), None)
    assert photo is not None
    assert photo.get('bg') == '#ffcc00'
    assert any(cell.get('cs', 1) > 1 or cell.get('rs', 1) > 1 for cell in flat)
    assert any(cell.get('border') for cell in flat)
    assert any(cell.get('v') == '11/24' for cell in flat)


def test_bulk_truck_ole2_bytes_with_xlsx_name_uses_xls_parser():
    header = {
        'toNames': ['苏迪', '罗梓良'], 'fromName': '农建壮', 'sheetDate': '2026-10-31',
        'vehicle': 'W218', 'transport': '建联派', 'truckType': '3T', 'tradeTerm': 'FOB',
        'tableName': '建联派运输，出盐田', 'cutoff': '2026-10-31T18:00', 'originPort': '盐田',
    }
    line = shipping_bulk_truck._line(
        {'product_code': 'GDSM-HKGM002686', 'quantity': 2400, 'cartons': 150,
         'gross_weight': 861, 'net_weight': 578, 'cbm': 4.77},
        'US2625089', 'HKGM00268600',
    )
    content = shipping_bulk_truck.render_bulk_xlsx({'header': header, 'lines': [line]})
    assert content[:4] == b'\xd0\xcf\x11\xe0'
    sheets = file_open.workbook_preview('GDSM-HKGM002686.xlsx', content)

    assert len(sheets) == 1
    flat = [cell for row in sheets[0]['cells'] for cell in row]
    assert any(cell.get('bg') == '#ffcc00' for cell in flat)
    assert any(cell.get('cs', 1) > 1 or cell.get('rs', 1) > 1 for cell in flat)
    assert any(cell.get('border') for cell in flat)
