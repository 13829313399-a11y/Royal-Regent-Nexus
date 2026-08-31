import pytest

from app.services.internal_quote_excel import _engineering_mold_parts, _split_engineering_mold_part_names


@pytest.mark.parametrize("source,expected", [
    ("粉色蝴蝶结前后", ["粉色蝴蝶结前", "粉色蝴蝶结后"]),
    ("粉色蝴蝶结前/后", ["粉色蝴蝶结前", "粉色蝴蝶结后"]),
    ("黑色前／后壳", ["黑色前壳", "黑色后壳"]),
    ("前后壳", ["前壳", "后壳"]),
    ("前/后壳（黑色）", ["前壳（黑色）", "后壳（黑色）"]),
    ("前后壳（红/蓝）", ["前壳（红/蓝）", "后壳（红/蓝）"]),
    ("前/后壳（红/蓝）", ["前壳（红/蓝）", "后壳（红/蓝）"]),
    ("外壳(红/蓝)/支架【黑/白】", ["外壳(红/蓝)", "支架【黑/白】"]),
    ("前壳/后盖", ["前壳", "后盖"]),
    ("黑色前壳/白色后壳", ["黑色前壳", "白色后壳"]),
    ("左右前枪身（橙色）", ["左前枪身（橙色）", "右前枪身（橙色）"]),
    ("左/右手", ["左手", "右手"]),
    ("泵杆/击锤/扣机/配件(7件)", ["泵杆", "击锤", "扣机", "配件(7件)"]),
    ("前后左右壳", ["前后左右壳"]),
    (" 黑色前/后壳 / 黑色眼睛 / ", ["黑色前壳", "黑色后壳", "黑色眼睛"]),
    ("", []),
])
def test_export_part_names_match_frontend_contract(source, expected):
    assert _split_engineering_mold_part_names(source) == expected
    assert [part["name"] for part in _engineering_mold_parts({"item": source})] == expected


def test_export_keeps_saved_manual_child_names_and_values():
    parts = _engineering_mold_parts({
        "item": "粉色蝴蝶结前后",
        "parts": [{"name": "手工改名后件", "color": "粉色", "process": "电镀", "process_unit_price_hkd": "2.5", "unit_net_weight_g": "15", "output_count": "2", "quantity": "1"}],
    })
    assert parts == [{"name": "手工改名后件", "color": "粉色", "process": "电镀", "process_unit_price_hkd": 2.5, "unit_net_weight_g": 15.0, "output_count": 2.0, "quantity": 1.0}]
