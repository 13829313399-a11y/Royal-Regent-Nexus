import json
from decimal import Decimal
from types import SimpleNamespace

from app.services.internal_quote import _rr2_cost_summary


def section(code: str, payload: dict, totals: dict, lines: list[dict] | None = None):
    return SimpleNamespace(
        department=code,
        is_required=True,
        calculation_status="valid",
        payload_json=json.dumps(payload, ensure_ascii=False),
        calculation_json=json.dumps({"totals": totals, "line_breakdown": lines or []}, ensure_ascii=False),
    )


def summary_sections(*, freight_enabled: bool):
    return [
        section(
            "sales",
            {
                "indonesia_freight_hkd": "1",
                "additional_tax_hkd": "0.5",
                "freight_calc": {"enabled": freight_enabled},
            },
            {
                "freight_options": ([{
                    "key": "yt40",
                    "item": "YT 40 柜",
                    "per_piece_hkd": "10",
                    "total_cartons": "100",
                }] if freight_enabled else []),
            },
            [{"kind": "packaging_material", "item": "吸塑罩", "category": "blister", "amount_hkd": "2"}],
        ),
        section(
            "engineering",
            {
                "materials": [
                    {"item": "小马达", "category": "hardware", "auxiliary_category": "其他外购"},
                    {"item": "彩盒", "category": "auxiliary", "auxiliary_category": "彩盒/内卡"},
                ],
            },
            {"hardware_hkd": "5", "auxiliary_hkd": "3", "total_hkd": "8"},
            [
                {"kind": "material", "item": "小马达", "category": "hardware", "auxiliary_category": "其他外购", "amount_hkd": "5"},
                {"kind": "material", "item": "彩盒", "category": "auxiliary", "auxiliary_category": "彩盒/内卡", "amount_hkd": "3"},
            ],
        ),
        section(
            "electronic",
            {},
            {"total_hkd": "6"},
            [{"kind": "electronic_component", "item": "马达线", "amount_hkd": "1"}],
        ),
        section(
            "molding",
            {},
            {"blow_hkd": "1", "total_hkd": "4"},
            [{
                "kind": "injection",
                "material": "POM",
                "quantity": "2",
                "material_cost_hkd": "1",
                "molding_cost_hkd": "0.5",
            }],
        ),
        section("painting", {}, {"total_hkd": "10"}),
        section("slush", {}, {"total_hkd": "2"}),
        section("sewing", {}, {"hair_hkd": "4", "clothes_hkd": "3", "total_hkd": "7"}),
        section("assembly", {}, {"assembly_hkd": "3", "packaging_hkd": "2", "total_hkd": "5"}),
    ]


SNAPSHOT = {
    "fx": {"hkd_usd": "7.8"},
    "freight_share": "0.48",
    "tax_rates": {
        "carton": "0.10",
        "tax_1_percent": "0.0099",
        "slush": "0.03",
        "sewing_hair": "0.115",
        "sewing_clothes": "0.115",
        "blister": "0.06",
        "freight_tax_9": "0.0826",
        "tax_13_percent": "0.115",
    },
}


def rows_by_key(rows: list[dict]):
    return {row["key"]: row for row in rows}


def test_rr2_cost_summary_keeps_exact_four_table_fields_and_reference_tax_columns():
    result = _rr2_cost_summary(
        summary_sections(freight_enabled=False),
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
    )

    assert [row["label"] for row in result["t1"]] == [
        "货价", "进口料", "国内料", "吹气", "搪胶", "车发", "车衣", "五金", "电子", "马达", "吸塑", "胶袋",
    ]
    assert [row["label"] for row in result["t2"]] == [
        "彩盒/内咭", "未减税前码数", "减税后码数", "电池", "利宝", "电镀", "其他外购", "纸箱", "运费", "吊柜费", "杂项",
    ]
    assert [row["label"] for row in result["t3"]] == [
        "啤工", "喷油工", "油漆", "装配工", "不含人工成本", "人工比例", "毛利", "毛利率", "利润", "利润率", "总成本",
    ]
    tax_rows = rows_by_key(result["t4"])
    assert tax_rows["tax13"]["rate_percent"] is None
    assert tax_rows["tax13"]["deduction_hkd"] is None
    assert tax_rows["labor13"]["rate_percent"] is None
    assert tax_rows["carton"]["rate_percent"] == "10.0000"
    assert tax_rows["tax1"]["rate_percent"] == "0.9900"
    assert tax_rows["freight9"]["amount_hkd"] == "0.0000"
    assert rows_by_key(result["t1"])["base_price"]["value"] == "60.0000"
    assert rows_by_key(result["t3"])["painting_labor"]["value"] == "7.0000"
    assert rows_by_key(result["t3"])["paint_material"]["value"] == "3.0000"
    assert result["shipping_pricing"]["enabled"] is False
    assert result["shipping_pricing"]["rows"] == []


def test_rr2_shipping_price_uses_48_52_markup_settlement_and_mold_share_when_enabled():
    result = _rr2_cost_summary(
        summary_sections(freight_enabled=True),
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
    )

    shipping = result["shipping_pricing"]
    assert shipping["enabled"] is True
    assert shipping["freight_share_percent"] == "48.0000"
    assert shipping["lift_share_percent"] == "52.0000"
    assert [row["name"] for row in shipping["rows"]] == ["出厂价", "YT 40 柜"]
    yt40 = shipping["rows"][1]
    assert yt40["freight_hkd"] == "4.8000"
    assert yt40["lift_hkd"] == "5.2000"
    assert yt40["with_freight_hkd"] == "60.5000"
    assert yt40["after_markup_hkd"] == "72.6000"
    assert yt40["after_settlement_hkd"] == "74.0816"
    assert yt40["total_with_mold_usd"] == "9.7476"
