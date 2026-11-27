import io

from openpyxl import Workbook

from app.services.shipping_product_history import parse_products


def workbook_bytes(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_parse_products_extracts_history_columns():
    data = workbook_bytes([
        ['柜单资料'],
        ['货号', '货名', '玩具类别', '每箱毛重', '每箱净重'],
        ['119118', '单款猫头鹰套18/箱', '塑胶', 4.989, 4.165],
        ['125160-KP1', '125160-20个装箱打...', '纸箱', 4.654, 4.132],
        ['合计', '', '', '', ''],
    ])
    products = parse_products(data, 'daily.xlsx')
    assert len(products) == 2
    assert products[0]['product_code'] == '119118'
    assert products[0]['product_name'] == '单款猫头鹰套18/箱'
    assert products[0]['category'] == '塑胶'
    assert products[0]['gross_per_carton'] == '4.989'
    assert products[0]['net_per_carton'] == '4.165'
    assert products[1]['product_code'] == '125160-KP1'


def test_parse_products_supports_so_sheet_headers():
    data = workbook_bytes([
        ['序号', '洋行', '合约', '工厂备案货号', '出货申报货号', '品牌', '数量', '箱数',
         '毛重', '净重', 'CBM', '出口国家', '品牌', '每箱毛重', '每箱净重', '每箱体积', '备注', 'PO'],
        [1, 'Zuru', '4500222023', '77903TQ1', 77903, 'Zuru', 8352, 2088, 5136, 2764, 3, 'UK',
         'Zuru MINI BRANDS', 2.46, 1.324, 0.756, '', 'FB15423'],
    ])
    products = parse_products(data, 'zuru.xlsx')
    assert products[0]['product_code'] == '77903TQ1'
    assert products[0]['gross_per_carton'] == '2.46'
    assert products[0]['net_per_carton'] == '1.324'
