from io import BytesIO

from openpyxl import Workbook
import pytest

from app.services.carton_packaging_adapter import adapt_carton_sheets, adapt_carton_workbook


@pytest.mark.parametrize('quality_column', [26, 255])
def test_wide_generic_header_and_short_rows_keep_missing_dimensions_pending(quality_column):
    header = ['货号', '装箱数'] + [None] * (quality_column - 2) + ['做箱SIZE']
    result = adapt_carton_sheets({'其他客户': [header, ['00123', '0/12']]})
    rows = result['sheets'][0]['rows']
    assert len(rows) == 2
    assert rows[1][0] == '00123' and rows[1][10] == 12
    assert rows[1][5:8] == [None, None, None]
    assert '做箱长宽高缺失' in rows[1][16] and '缺纸质' in rows[1][16]
    assert rows[1][17] == '其他客户!2'
    assert any('A=00123' in str(row) for row in result['sheets'][1]['rows'])


def test_size_table_stages_names_blank_and_cards_in_notes():
    result = adapt_carton_sheets({"测试": [
        ["货号", "装箱数", "做箱SIZE inch", None, None, None, "CUFT", "毛重", "净重", "外箱唛CM", None, None, "CBM", "啤卡"],
        [None, None, "纸质", "L", "W", "H"],
        ["00123", "0/4", "A=B", 12, 10, 8, None, 2.3, 1.8, 31, 26, 21, None, "B3B 11.5*9.5，1配2"],
    ]})
    row = result["sheets"][0]["rows"][1]
    assert row[0] == "00123" and row[1] is None
    assert row[5:11] == [12, 10, 8, "inch", "个", 4]
    assert row[12] == "停用"
    assert "啤卡：B3B 11.5*9.5，1配2" in row[13]
    assert row[14:16] == [1.8, 2.3]


def test_conflicting_cm_header_never_silently_converts_dimensions():
    result = adapt_carton_sheets({"Magic Box": [
        ["货号", "装箱数", "做箱SIZECM", None, None, None, "CUFT", "毛重", "净重", "外箱唛CM"], [],
        ["ABC1", 4, "A=B", 13, 7.125, 8.75, None, 1.71, 1.42, 33.655, 18.7325, 23.495],
    ]})
    row = result["sheets"][0]["rows"][1]
    assert row[5:8] == [13, 7.125, 8.75]
    assert row[8] is None and "疑似英寸" in row[16]


def test_shipping_sizes_are_not_ordering_sizes_and_weights_not_swapped():
    source = [[], [], [], ["9251UQ1-S001", "A=B", "6PCS/箱", 43.8, "X", 21.9, "X", 21, 1.29, None, 1.61]]
    row = adapt_carton_sheets({"9251更新-0309": source})["sheets"][0]["rows"][1]
    assert row[5:8] == [None, None, None]
    assert row[14:16] == [1.61, 1.29]
    assert "未自动对调" in row[16]
    assert "43.8" in row[13]


def test_block_accessories_stay_with_explicit_product_without_invented_sku():
    data = [[], [], [],
            [1, "9459-S004", "4个魔法兔子装1箱", "K4K 150LBS", "英寸INCH", 19, 10, 16],
            [None, None, "装箱尺寸（箱唛尺寸）", None, "厘米CM", 49, 26, 42, 4.34, 3.65],
            [None, None, "左右折卡", "L3H", "(40+30)*406MM", None, None, None, None, None, None, None, "1*2"]]
    rows = adapt_carton_sheets({"9549魔法兔东莞": data})["sheets"][0]["rows"]
    assert len(rows) == 2 and rows[1][0] == "9459-S004"
    assert "左右折卡" in rows[1][13] and "1*2" in rows[1][13]
    assert rows[1][14:16] == [3.65, 4.34]
    assert "未擅自改号" in rows[1][16]


def test_hunan_material_strength_and_ratios_never_become_packing_count():
    rows = adapt_carton_sheets({"湖南转-77351": [
        ["合同号", "货号", "装箱数", "订箱尺寸"],
        [None, "001", "K3K850/3800", "30cm", "20cm", "10cm"],
        [None, "002", "1/44", "30cm", "20cm", "10cm"],
        [None, None, "平卡B3B 1配2", "29cm", "19cm"],
    ]})["sheets"][0]["rows"]
    assert len(rows) == 3
    assert rows[1][10] is None and rows[2][10] is None
    assert "平卡B3B 1配2" in rows[2][13]


def test_real_workbook_loader_uses_actual_bounds_and_preserves_padded_identifiers():
    book = Workbook()
    sheet = book.active
    sheet.title = "测试"
    sheet.append(["货号", "装箱数", "做箱SIZE inch"])
    sheet.append([None, None, "纸质", "L", "W", "H"])
    sheet.append([123, 4, "A=B", 12, 10, 8])
    sheet['A3'].number_format = '000000'
    sheet['XFD1048576'].number_format = '@'
    output = BytesIO()
    book.save(output)
    result = adapt_carton_workbook(output.getvalue())
    assert result['sheets'][0]['rows'][1][0] == '000123'
    assert len(result['sheets'][0]['rows']) == 2


def test_missing_sku_is_not_filled_from_previous_row():
    result = adapt_carton_sheets({"测试": [
        ["货号", "装箱数", "做箱SIZE inch"], [],
        ["ABC1", 4, "A=B", 12, 10, 8],
        [None, 6, "A=B", 15, 10, 8],
    ]})
    rows = result['sheets'][0]['rows']
    assert rows[2][0] is None and '未从上一行继承' in rows[2][16]


def test_one_header_row_does_not_swallow_first_product():
    result = adapt_carton_sheets({"测试": [
        ["货号", "装箱数", "做箱SIZE inch"],
        ["ABC1", 4, "A=B", 12, 10, 8],
    ]})
    assert result['sheets'][0]['rows'][1][0] == 'ABC1'


def test_mixed_units_in_text_spec_are_flagged_without_wrong_conversion():
    result = adapt_carton_sheets({"Zuru清溪": [
        ["ITEM", "规格", "单坑(内箱)", "订箱尺码双坑(外箱)"],
        ["ABC1", 4, None, "A=B 100mm x 20cm x 3inch", 2, 1.5],
    ]})
    row = result['sheets'][0]['rows'][1]
    assert row[5:8] == [100, 20, 3] and row[8] is None
    assert "单位不一致" in row[16]
