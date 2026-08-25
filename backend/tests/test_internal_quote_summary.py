import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.internal_quote import InternalQuoteCreateRequest
from app.services.internal_quote import _initial_section_payloads, _rr2_cost_summary


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
    "fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8"},
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


def create_request(**overrides):
    values = {
        "factory_id": "huakang-b",
        "quote_no": "IQ-JP-001",
        "product_name": "JustPlay 套装",
        "customer": "JustPlay",
        "qty": 10000,
        "initiator_department": "sales-business",
        "business_owner_id": "owner-1",
        "business_owner_name": "业务员",
        "pricing_components": ["主体", "镜子"],
    }
    values.update(overrides)
    return InternalQuoteCreateRequest(**values)


def test_justplay_components_are_created_only_for_huakang_b_and_seed_sales_payload():
    payload = create_request()
    seeded = json.loads(_initial_section_payloads(payload)["sales"])
    assert seeded == {
        "pricing_mode": "component",
        "pricing_components": [
            {"id": "component-01", "name": "主体"},
            {"id": "component-02", "name": "镜子"},
        ],
    }
    with pytest.raises(ValidationError, match="只有华康B JustPlay"):
        create_request(factory_id="huaxing")


def test_rr2_standard_detail_multiplier_detaches_from_main_multiplier_pool():
    sections = [
        section(
            "sales",
            {"shipping": {"markup_x": "1.16", "misc_ratio": "0.02"}},
            {},
        ),
        section(
            "engineering",
            {"materials": [{"item": "车衣", "category": "hardware"}]},
            {"hardware_hkd": "12.66", "auxiliary_hkd": "0", "packaging_hkd": "0", "carton_hkd": "0", "total_hkd": "12.66"},
            [{"kind": "material", "item": "车衣", "category": "hardware", "amount_hkd": "12.66", "markup_override": "1.03"}],
        ),
    ]

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("14.79"), "carton_hkd": Decimal("0")},
        SNAPSHOT,
    )

    pricing = result["shipping_pricing"]
    assert pricing["pricing_mode"] == "standard"
    assert pricing["pricing_groups"] == [
        {
            "id": "main",
            "name": "主倍率汇总",
            "cost_hkd": "2.1300",
            "pricing_base_hkd": "2.1300",
            "markup": "1.1600",
            "settlement": "0.9800",
            "quoted_hkd": "2.5212",
            "inherits_main_markup": "true",
        },
        {
            "id": "detail-01",
            "name": "车衣",
            "cost_hkd": "12.6600",
            "pricing_base_hkd": "12.6600",
            "markup": "1.0300",
            "settlement": "0.9800",
            "quoted_hkd": "13.3059",
            "inherits_main_markup": "false",
        },
    ]
    assert rows_by_key(result["t1"])["base_price"]["value"] == "15.8271"


def test_rr2_justplay_component_multipliers_group_department_costs_once():
    sections = [
        section(
            "sales",
            {
                "pricing_mode": "component",
                "pricing_components": [
                    {"id": "component-01", "name": "主体", "markup_x": "1.15"},
                    {"id": "component-02", "name": "镜子", "markup_x": "1.05"},
                ],
                "shipping": {"markup_x": "1.15", "misc_ratio": "0.03"},
            },
            {},
        ),
        section(
            "engineering",
            {"materials": []},
            {"hardware_hkd": "10", "auxiliary_hkd": "0", "packaging_hkd": "0", "carton_hkd": "0", "total_hkd": "10"},
            [
                {"kind": "material", "item": "主体件", "category": "hardware", "amount_hkd": "6", "pricing_component_id": "component-01"},
                {"kind": "material", "item": "镜子件", "category": "hardware", "amount_hkd": "4", "pricing_component_id": "component-02"},
            ],
        ),
    ]

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("10"), "carton_hkd": Decimal("0")},
        SNAPSHOT,
        factory_id="huakang-b",
    )

    pricing = result["shipping_pricing"]
    assert pricing["pricing_mode"] == "component"
    assert [(row["name"], row["cost_hkd"], row["markup"]) for row in pricing["pricing_groups"]] == [
        ("主体", "6.0000", "1.1500"),
        ("镜子", "4.0000", "1.0500"),
    ]
    assert rows_by_key(result["t1"])["base_price"]["value"] == "11.4433"


def test_rr2_justplay_pricing_entries_keep_assembly_formula_inputs():
    sections = [
        section(
            "sales",
            {
                "pricing_mode": "component",
                "pricing_components": [
                    {"id": "component-01", "name": "主体", "markup_x": "1.15"},
                ],
                "shipping": {"markup_x": "1.15", "misc_ratio": "0.03"},
            },
            {},
        ),
        section(
            "assembly",
            {"labor_base_hkd": "260"},
            {"assembly_hkd": "0.52", "packaging_hkd": "0", "total_hkd": "0.52"},
            [
                {
                    "kind": "assembly_process",
                    "group": "主体组装",
                    "process": "锁螺丝",
                    "persons": "7",
                    "teams": "1",
                    "production_qty": "3500",
                    "amount_hkd_pcs": "0.52",
                    "pricing_component_id": "component-01",
                }
            ],
        ),
    ]

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("0.52"), "assembly_hkd": Decimal("0.52")},
        SNAPSHOT,
        factory_id="huakang-b",
    )

    entry = next(
        row
        for row in result["shipping_pricing"]["pricing_entries"]
        if row["section"] == "assembly"
    )
    assert entry["persons"] == "7"
    assert entry["teams"] == "1"
    assert entry["production_qty"] == "3500"
    assert entry["formula_allocation_factor"] == "1.0000"


def test_rr2_justplay_keeps_packaging_global_and_prices_it_once_with_main_markup():
    sections = [
        section(
            "sales",
            {
                "pricing_mode": "component",
                "pricing_components": [
                    {"id": "component-01", "name": "主体", "markup_x": "1.15"},
                    {"id": "component-02", "name": "镜子", "markup_x": "1.05"},
                ],
                "shipping": {"markup_x": "1.15", "misc_ratio": "0.03"},
                "packaging_materials": [{"item": "彩盒"}],
                "cartons": [{"item": "外箱"}],
            },
            {"packaging_material_hkd": "3", "carton_hkd": "1"},
            [
                {"kind": "packaging_material", "item": "彩盒", "category": "color_box_inner_card", "amount_hkd": "3"},
                {"kind": "carton", "item": "外箱", "per_piece_hkd": "1"},
            ],
        ),
        section(
            "engineering",
            {"materials": []},
            {"hardware_hkd": "10", "auxiliary_hkd": "0", "packaging_hkd": "0", "carton_hkd": "0", "total_hkd": "10"},
            [
                {"kind": "material", "item": "主体件", "category": "hardware", "amount_hkd": "6", "pricing_component_id": "component-01"},
                {"kind": "material", "item": "镜子件", "category": "hardware", "amount_hkd": "4", "pricing_component_id": "component-02"},
            ],
        ),
    ]

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("14"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
        factory_id="huakang-b",
    )

    pricing = result["shipping_pricing"]
    assert [(row["name"], row["cost_hkd"], row["pricing_base_hkd"]) for row in pricing["pricing_groups"]] == [
        ("主体", "6.0000", "10.0000"),
        ("镜子", "4.0000", "4.0000"),
    ]
    assert pricing["global_pricing"]["cost_hkd"] == "4.0000"
    assert [row["label"] for row in pricing["global_pricing"]["entries"]] == ["彩盒", "外箱"]
    assert rows_by_key(result["t1"])["base_price"]["value"] == "16.1856"


@pytest.mark.parametrize(
    ("factory_id", "expected_rate", "expected_deduction"),
    [
        ("huaxing", None, None),
        ("huadeng", None, None),
        ("huakang-a", None, None),
        ("huakang-b", None, None),
        ("huakang-c", "11.5000", "1.7250"),
        ("huakang-d", "11.5000", "1.7250"),
    ],
)
def test_rr2_sewing_tax_refund_is_material_only_and_limited_to_huakang_c_d(
    factory_id: str,
    expected_rate: str | None,
    expected_deduction: str | None,
):
    sections = summary_sections(freight_enabled=False)
    sewing = next(item for item in sections if item.department == "sewing")
    sewing.calculation_json = json.dumps(
        {
            "totals": {
                "quote_mode": "detail",
                "clothes_material_hkd": "15",
                "clothes_labor_hkd": "3",
                "clothes_hkd": "18",
                "hair_hkd": "0",
                "total_hkd": "18",
            },
            "line_breakdown": [],
        },
        ensure_ascii=False,
    )

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
        factory_id=factory_id,
    )

    assert rows_by_key(result["t1"])["sewing_cloth"]["value"] == "18.0000"
    tax_row = rows_by_key(result["t4"])["sewcloth13"]
    assert tax_row == {
        "key": "sewcloth13",
        "label": "车衣物料退税（仅华康C/D）",
        "amount_hkd": "15.0000",
        "rate_percent": expected_rate,
        "deduction_hkd": expected_deduction,
    }


def test_rr2_sewing_tax_refund_rebuilds_material_only_basis_from_legacy_lines():
    sections = summary_sections(freight_enabled=False)
    sewing = next(item for item in sections if item.department == "sewing")
    sewing.calculation_json = json.dumps(
        {
            "totals": {"clothes_hkd": "18", "hair_hkd": "0", "total_hkd": "18"},
            "line_breakdown": [
                {
                    "kind": "sewing_material",
                    "category": "clothes",
                    "item": "棉布",
                    "part": "身体",
                    "amount_rmb": "12.75",
                },
                {
                    "kind": "sewing_material",
                    "category": "clothes",
                    "item": "车缝人工",
                    "part": "",
                    "amount_rmb": "1.70",
                },
            ],
        },
        ensure_ascii=False,
    )

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
        factory_id="huakang-c",
    )

    tax_row = rows_by_key(result["t4"])["sewcloth13"]
    assert tax_row["amount_hkd"] == "15.0000"
    assert tax_row["deduction_hkd"] == "1.7250"


def test_rr2_sewing_quick_quote_never_assumes_an_unknown_total_is_refundable_material():
    sections = summary_sections(freight_enabled=False)
    sewing = next(item for item in sections if item.department == "sewing")
    sewing.calculation_json = json.dumps(
        {
            "totals": {
                "quote_mode": "quick",
                "clothes_material_hkd": "0",
                "clothes_labor_hkd": "18",
                "clothes_hkd": "18",
                "hair_hkd": "0",
                "total_hkd": "18",
            },
            "line_breakdown": [{"kind": "sewing_quick", "category": "clothes", "amount_hkd": "18"}],
        },
        ensure_ascii=False,
    )

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
        factory_id="huakang-d",
    )

    tax_row = rows_by_key(result["t4"])["sewcloth13"]
    assert tax_row["amount_hkd"] == "0.0000"
    assert tax_row["rate_percent"] == "11.5000"
    assert tax_row["deduction_hkd"] == "0.0000"


def test_rr2_cost_summary_keeps_exact_four_table_fields_and_reference_tax_columns():
    result = _rr2_cost_summary(
        summary_sections(freight_enabled=False),
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
    )

    assert [row["label"] for row in result["t1"] if row.get("display", True)] == [
        "货价", "料价", "吹气", "搪胶", "车发", "车衣", "五金", "电子", "马达", "吸塑", "胶袋",
    ]
    hidden_material_rows = [row for row in result["t1"] if row.get("display") is False]
    assert [(row["key"], row["value"]) for row in hidden_material_rows] == [
        ("imp_mat", "0.0000"),
        ("dom_mat", "2.0000"),
    ]
    assert result["molding_material_breakdown"] == {
        "total_hkd": "2.0000",
        "imported_hkd": "0.0000",
        "domestic_hkd": "2.0000",
    }
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
    assert tax_rows["carton"]["rate_percent"] is None
    assert tax_rows["carton"]["deduction_hkd"] is None
    assert tax_rows["tax1"]["rate_percent"] == "0.9900"
    assert tax_rows["freight9"]["amount_hkd"] == "0.0000"
    assert rows_by_key(result["t1"])["base_price"]["value"] == "61.8367"
    assert rows_by_key(result["t3"])["painting_labor"]["value"] == "7.0000"
    assert rows_by_key(result["t3"])["paint_material"]["value"] == "3.0000"
    assert result["shipping_pricing"]["enabled"] is False
    assert result["shipping_pricing"]["rows"] == []


def test_rr2_material_price_uses_authoritative_molding_totals_and_keeps_purchase_split_internal():
    def build(imported: str, domestic: str, material_total: str = "5"):
        sections = summary_sections(freight_enabled=False)
        molding = next(item for item in sections if item.department == "molding")
        molding.calculation_json = json.dumps(
            {
                "totals": {
                    "injection_hkd": "8",
                    "injection_material_hkd": material_total,
                    "injection_imported_material_hkd": imported,
                    "injection_domestic_material_hkd": domestic,
                    "injection_labor_hkd": "3",
                    "blow_hkd": "1",
                    "total_hkd": "9",
                },
                # Deliberately inconsistent legacy evidence proves that the
                # current calculator totals, rather than another department or
                # an obsolete browser formula, are authoritative.
                "line_breakdown": [
                    {
                        "kind": "injection",
                        "material": "POM",
                        "quantity": "100",
                        "material_cost_hkd": "100",
                        "molding_cost_hkd": "100",
                    },
                    {"kind": "blow", "material_cost_hkd": "999"},
                ],
            },
            ensure_ascii=False,
        )
        return _rr2_cost_summary(
            sections,
            {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
            SNAPSHOT,
        )

    imported_result = build("5", "0")
    domestic_result = build("0", "5")

    for result in (imported_result, domestic_result):
        t1 = rows_by_key(result["t1"])
        assert t1["material"]["value"] == "5.0000"
        assert t1["blow"]["value"] == "1.0000"
        assert rows_by_key(result["t3"])["injection_labor"]["value"] == "3.0000"
        assert result["molding_material_breakdown"]["total_hkd"] == "5.0000"

    # Reclassifying the same HKD 5 material does not change cost, but domestic
    # resin remains in the RMB-purchase and 13%-tax bases used by exports.
    assert (
        rows_by_key(imported_result["t3"])["total_cost"]["value"]
        == rows_by_key(domestic_result["t3"])["total_cost"]["value"]
    )
    assert (
        Decimal(domestic_result["totals"]["rmb_purchase_cost_hkd"])
        - Decimal(imported_result["totals"]["rmb_purchase_cost_hkd"])
    ) == Decimal("5.0000")
    assert (
        Decimal(rows_by_key(domestic_result["t4"])["tax13"]["amount_hkd"])
        - Decimal(rows_by_key(imported_result["t4"])["tax13"]["amount_hkd"])
    ) == Decimal("5.0000")

    # The combined total is authoritative even if a future/legacy origin is
    # not represented by either tax bucket.  Tax and RMB purchase still use
    # only the explicit domestic split.
    unclassified_result = build("3", "2", material_total="7")
    assert rows_by_key(unclassified_result["t1"])["material"]["value"] == "7.0000"
    assert unclassified_result["molding_material_breakdown"] == {
        "total_hkd": "7.0000",
        "imported_hkd": "3.0000",
        "domestic_hkd": "2.0000",
    }


@pytest.mark.parametrize(
    ("misc_ratio", "expected_base_price", "expected_misc", "expected_total_cost", "expected_rmb_purchase"),
    [
        ("0", "60.6000", "0.0000", "46.5000", "28.5000"),
        ("0.02", "61.8367", "1.2367", "47.7367", "29.7367"),
        ("0.03", "62.4742", "1.8742", "48.3742", "30.3742"),
        ("0.035", "62.7979", "2.1979", "48.6979", "30.6979"),
    ],
)
def test_rr2_cost_summary_books_misc_as_a_share_of_the_grossed_up_quote(
    misc_ratio: str,
    expected_base_price: str,
    expected_misc: str,
    expected_total_cost: str,
    expected_rmb_purchase: str,
):
    sections = summary_sections(freight_enabled=False)
    sales = next(item for item in sections if item.department == "sales")
    sales_payload = json.loads(sales.payload_json)
    sales_payload["shipping"] = {"misc_ratio": misc_ratio}
    sales.payload_json = json.dumps(sales_payload, ensure_ascii=False)

    result = _rr2_cost_summary(
        sections,
        {
            "factory_price_hkd": Decimal("50"),
            "carton_hkd": Decimal("1"),
            "indonesia_freight_hkd": Decimal("1"),
        },
        SNAPSHOT,
    )

    t1 = rows_by_key(result["t1"])
    t2 = rows_by_key(result["t2"])
    t3 = rows_by_key(result["t3"])
    assert t1["base_price"]["value"] == expected_base_price
    assert t2["misc"]["value"] == expected_misc
    assert t3["total_cost"]["value"] == expected_total_cost
    assert result["totals"]["rmb_purchase_cost_hkd"] == expected_rmb_purchase

    # The settlement gross-up only finances the misc share.  It must not alter
    # the pre-misc gross margin or profit.
    assert Decimal(t1["base_price"]["value"]) - Decimal(t2["misc"]["value"]) == Decimal("60.6000")
    assert t3["gross"]["value"] == "29.1000"
    assert t3["profit"]["value"] == "14.1000"


def test_rr2_cost_summary_keeps_direct_misc_costs_once_when_percentage_misc_is_zero():
    with_direct_sections = summary_sections(freight_enabled=False)
    with_direct_sales = next(item for item in with_direct_sections if item.department == "sales")
    with_direct_payload = json.loads(with_direct_sales.payload_json)
    with_direct_payload["shipping"] = {"misc_ratio": "0"}
    with_direct_sales.payload_json = json.dumps(with_direct_payload, ensure_ascii=False)
    with_direct = _rr2_cost_summary(
        with_direct_sections,
        {
            "factory_price_hkd": Decimal("50"),
            "carton_hkd": Decimal("1"),
            "indonesia_freight_hkd": Decimal("1"),
        },
        SNAPSHOT,
    )

    without_direct_sections = summary_sections(freight_enabled=False)
    without_direct_sales = next(item for item in without_direct_sections if item.department == "sales")
    without_direct_payload = json.loads(without_direct_sales.payload_json)
    without_direct_payload.update({
        "indonesia_freight_hkd": "0",
        "additional_tax_hkd": "0",
        "shipping": {"misc_ratio": "0"},
    })
    without_direct_sales.payload_json = json.dumps(without_direct_payload, ensure_ascii=False)
    without_direct = _rr2_cost_summary(
        without_direct_sections,
        # The normal cost context already contains Indonesia freight, so remove
        # the fixture's HKD 1 when its source payload is removed.
        {
            "factory_price_hkd": Decimal("49"),
            "carton_hkd": Decimal("1"),
            "indonesia_freight_hkd": Decimal("0"),
        },
        SNAPSHOT,
    )

    with_t2 = rows_by_key(with_direct["t2"])
    without_t2 = rows_by_key(without_direct["t2"])
    assert with_t2["misc"]["value"] == "0.0000"
    assert without_t2["misc"]["value"] == "0.0000"
    assert (
        Decimal(rows_by_key(with_direct["t3"])["total_cost"]["value"])
        - Decimal(rows_by_key(without_direct["t3"])["total_cost"]["value"])
    ) == Decimal("1.5000")
    assert (
        Decimal(with_direct["totals"]["rmb_purchase_cost_hkd"])
        - Decimal(without_direct["totals"]["rmb_purchase_cost_hkd"])
    ) == Decimal("1.5000")


def test_rr2_cost_summary_prefers_standalone_hair_and_falls_back_to_legacy_sewing_hair():
    legacy_sections = summary_sections(freight_enabled=False)
    legacy_sections.append(
        SimpleNamespace(
            department="hair",
            is_required=False,
            calculation_status="pending",
            payload_json="{}",
            calculation_json="{}",
        )
    )
    legacy = _rr2_cost_summary(
        legacy_sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
    )
    assert rows_by_key(legacy["t1"])["sewing_hair"]["value"] == "4.0000"

    standalone_sections = summary_sections(freight_enabled=False)
    standalone_sections.append(
        section(
            "hair",
            {"lines": [{"name": "公仔头发", "craft": "植发", "weight_g": 18.5, "unit_price_hkd": 2.35, "unit": "PCS"}]},
            {"total_hkd": "2.35"},
            [{"kind": "hair", "item": "公仔头发", "amount_hkd": "2.35"}],
        )
    )
    standalone = _rr2_cost_summary(
        standalone_sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
    )
    assert rows_by_key(standalone["t1"])["sewing_hair"]["value"] == "2.3500"


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
    assert shipping["misc_ratio"] == "0.0200"
    assert shipping["settlement"] == "0.9800"
    assert [row["name"] for row in shipping["rows"]] == ["出厂价", "YT 40 柜"]
    yt40 = shipping["rows"][1]
    assert yt40["freight_hkd"] == "4.8000"
    assert yt40["lift_hkd"] == "5.2000"
    assert yt40["with_freight_hkd"] == "60.5000"
    assert yt40["after_markup_hkd"] == "72.6000"
    assert yt40["after_settlement_hkd"] == "74.0816"
    assert yt40["total_with_mold_usd"] == "9.7476"


def test_rr2_shipping_price_uses_explicit_freight_and_lifting_baseline_amounts():
    sections = summary_sections(freight_enabled=True)
    sales = next(item for item in sections if item.department == "sales")
    calculation = json.loads(sales.calculation_json)
    calculation["totals"]["freight_options"][0].update({
        "has_lifting_fee": True,
        "freight_per_piece_hkd": "6",
        "lifting_per_piece_hkd": "4",
        "per_piece_hkd": "10",
    })
    sales.calculation_json = json.dumps(calculation, ensure_ascii=False)

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
    )

    t2 = rows_by_key(result["t2"])
    assert t2["freight"]["value"] == "6.0000"
    assert t2["cabinet"]["value"] == "4.0000"
    assert rows_by_key(result["t4"])["freight9"]["amount_hkd"] == "6.0000"
    yt40 = result["shipping_pricing"]["rows"][1]
    assert yt40["freight_hkd"] == "6.0000"
    assert yt40["lift_hkd"] == "4.0000"
    assert yt40["with_freight_hkd"] == "60.5000"


def test_rr2_shipping_price_uses_markup_and_misc_ratio_saved_in_the_sales_section():
    sections = summary_sections(freight_enabled=True)
    sales = next(item for item in sections if item.department == "sales")
    sales_payload = json.loads(sales.payload_json)
    sales_payload["shipping"] = {
        "markup_x": "1.15",
        "misc_ratio": "0.035",
        "divisor": "0.80",
    }
    sales_payload["scenarios"] = [{"settlement": "0.70"}]
    sales.payload_json = json.dumps(sales_payload, ensure_ascii=False)

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
    )

    shipping = result["shipping_pricing"]
    assert shipping["markup"] == "1.1500"
    assert shipping["misc_ratio"] == "0.0350"
    assert shipping["settlement"] == "0.9650"
    assert shipping["rows"][1]["after_markup_hkd"] == "69.5750"
    assert shipping["rows"][1]["after_settlement_hkd"] == "72.0984"


@pytest.mark.parametrize(
    ("shipping_payload", "legacy_scenarios", "expected_misc", "expected_settlement"),
    [
        ({"divisor": "0.96"}, [{"settlement": "0.70"}], "0.0400", "0.9600"),
        ({}, [{"settlement": "0.95"}], "0.0500", "0.9500"),
        ({}, [], "0.0200", "0.9800"),
    ],
)
def test_rr2_shipping_price_reverse_derives_misc_from_legacy_settlement_only_when_missing(
    shipping_payload: dict,
    legacy_scenarios: list[dict],
    expected_misc: str,
    expected_settlement: str,
):
    sections = summary_sections(freight_enabled=True)
    sales = next(item for item in sections if item.department == "sales")
    sales_payload = json.loads(sales.payload_json)
    sales_payload["shipping"] = shipping_payload
    sales_payload["scenarios"] = legacy_scenarios
    sales.payload_json = json.dumps(sales_payload, ensure_ascii=False)

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1")},
        SNAPSHOT,
    )

    shipping = result["shipping_pricing"]
    assert shipping["misc_ratio"] == expected_misc
    assert shipping["settlement"] == expected_settlement


def test_rr2_shipping_price_selects_the_highest_moq_tier_reached_by_quote_quantity():
    sections = summary_sections(freight_enabled=True)
    sales = next(item for item in sections if item.department == "sales")
    sales_payload = json.loads(sales.payload_json)
    sales_payload["shipping"] = {
        "markup_x": "1.99",
        "markup_tiers": [
            {"moq": 3000, "markup_x": "1.30"},
            {"moq": 5000, "markup_x": "1.25"},
            {"moq": 10000, "markup_x": "1.15"},
        ],
    }
    sales.payload_json = json.dumps(sales_payload, ensure_ascii=False)

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
        7000,
    )

    shipping = result["shipping_pricing"]
    assert shipping["markup"] == "1.2500"
    assert shipping["active_markup_moq"] == "5000.0000"
    assert shipping["markup_tiers"] == [
        {"moq": "3000.0000", "markup": "1.3000", "is_active": False, "include_in_output": True},
        {"moq": "5000.0000", "markup": "1.2500", "is_active": True, "include_in_output": True},
        {"moq": "10000.0000", "markup": "1.1500", "is_active": False, "include_in_output": True},
    ]
    assert shipping["rows"][1]["after_markup_hkd"] == "75.6250"


def test_rr2_shipping_price_uses_the_manually_selected_tier_instead_of_quantity_default():
    sections = summary_sections(freight_enabled=True)
    sales = next(item for item in sections if item.department == "sales")
    sales_payload = json.loads(sales.payload_json)
    sales_payload["shipping"] = {
        "markup_x": "1.99",
        "markup_tiers": [
            {"moq": 3000, "markup_x": "1.30"},
            {"moq": 5000, "markup_x": "1.25"},
            {"moq": 10000, "markup_x": "1.15"},
        ],
        "selected_markup_moq": 3000,
    }
    sales.payload_json = json.dumps(sales_payload, ensure_ascii=False)

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
        10000,
    )

    shipping = result["shipping_pricing"]
    assert shipping["markup"] == "1.3000"
    assert shipping["active_markup_moq"] == "3000.0000"
    assert shipping["markup_tiers"][0]["is_active"] is True
    assert shipping["markup_tiers"][2]["is_active"] is False


def test_rr2_cost_summary_uses_quick_painting_labor_and_tax_inclusive_paint_exactly():
    sections = summary_sections(freight_enabled=False)
    painting = next(item for item in sections if item.department == "painting")
    painting.calculation_json = json.dumps(
        {
            "totals": {
                "quote_mode": "quick",
                "painting_labor_hkd": "2.0000",
                "paint_base_hkd": "3.0000",
                "paint_tax_hkd": "0.3900",
                "paint_material_hkd": "3.3900",
                "total_hkd": "5.3900",
            },
            "line_breakdown": [],
        },
        ensure_ascii=False,
    )

    result = _rr2_cost_summary(
        sections,
        {"factory_price_hkd": Decimal("50"), "carton_hkd": Decimal("1"), "mold_amortization_usd": Decimal("0.25")},
        SNAPSHOT,
    )

    labor_rows = rows_by_key(result["t3"])
    assert labor_rows["painting_labor"]["value"] == "2.0000"
    assert labor_rows["paint_material"]["value"] == "3.3900"
