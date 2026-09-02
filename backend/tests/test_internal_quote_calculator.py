import pytest

from app.services.internal_quote_calculator import CalculationInputError, DEFAULT_MACHINE_PRICES, calculate_section, resolve_sales_cartons


SNAPSHOT = {
    "fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8", "rmb_usd": "7.75"},
    "material_prices": {"ABS|750SW": "8.50"},
    "legacy_material_prices": {},
    "machine_prices": [
        {"range": "4A-6A", "machine": "80T", "shift_price_hkd": "940"},
    ],
    "paper_price_factor": "2.75",
    "injection_loss_rate_percent": "3",
    "blow_profit_multiplier": "1.05",
    "electronic_profit_rate_percent": "10",
    "assembly_labor_base_hkd": "260",
    "tax_rates": {"carton": "0.10"},
    "freight_share": "0.48",
    "lift_share": "0.52",
    "markup": "1.2",
    "settlement": "0.98",
}


def calculate(section_code: str, payload: dict, **context):
    return calculate_section(
        section_code,
        payload,
        SNAPSHOT,
        "IQREF-TEST",
        context=context,
    )


@pytest.mark.parametrize("unit", ["inch", "cm"])
@pytest.mark.parametrize("color_field", ["color_box_size_in", "color_box_size_cm"])
def test_justplay_carton_uses_color_box_dimensions_not_submitted_manual_values(unit, color_field):
    payload = {
        "pricing_mode": "component", "color_box_size_unit": unit,
        color_field: {"length": 10, "width": 5, "height": 4},
        "cartons": [{"item": "主纸箱", "size_unit": unit, "length_in": 99, "width_in": 99, "height_in": 99, "qty_per_carton": 6}],
    }
    result = calculate("sales", payload)
    carton = next(row for row in result["line_breakdown"] if row["kind"] == "carton")
    assert carton["carton_price_hkd"] == "1.1956"  # 18.5 * 11.75 * 2 * 2.75 / 1000
    assert carton["per_piece_hkd"] == "0.1993"
    assert carton["cuft"] == "0.1789"
    pallet = next(row for row in result["line_breakdown"] if row.get("formula_code") == "paper_pallet")
    assert (pallet["carton_length_in"], pallet["carton_width_in"], pallet["carton_height_in"]) == ("10.7500", "5.7500", "5.0000")
    assert pallet["cartons_per_pallet"] == "210.0000"
    assert payload["cartons"][0]["length_in"] == 99  # Pure calculation never rewrites the input audit payload.
    inner = {"item": "内箱", "length_in": 4, "width_in": 3, "height_in": 2, "qty_per_carton": 2}
    assert resolve_sales_cartons({**payload, "cartons": [*payload["cartons"], inner]})[1] == inner
    ordinary = {**payload, "pricing_mode": "standard"}
    assert resolve_sales_cartons(ordinary) == payload["cartons"]


@pytest.mark.parametrize("color_box", [None, {}, {"length": 10, "width": 0, "height": 4}, {"length": 10, "width": 5, "height": -1}])
def test_justplay_carton_requires_complete_positive_color_box_dimensions(color_box):
    with pytest.raises(CalculationInputError, match="彩盒"):
        calculate("sales", {"pricing_mode": "component", "color_box_size_in": color_box,
                            "cartons": [{"length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 24}]})


def test_justplay_color_box_changes_also_update_freight_capacity():
    result = calculate_section("sales", {
        "pricing_mode": "component", "color_box_size_in": {"length": 17.25, "width": 11.25, "height": 9},
        "cartons": [{"item": "主纸箱", "length_in": 1, "width_in": 1, "height_in": 1, "qty_per_carton": 24}],
        "freight_calc": {"cap_40": 1980},
    }, {**SNAPSHOT, "freight": {"routes": [{"route_key": "hk40", "route_name": "港柜", "capacity_key": "cap_40",
                                           "freight_hkd": 8000, "lifting_hkd": 1200}]}}, "TEST-JP-COLOR-BOX")
    freight = result["totals"]["freight_options"][0]
    assert freight["carton_cuft"] == "1.2500"
    assert freight["total_cartons"] == "1584.0000"
    assert freight["freight_per_piece_hkd"] == "0.2104"
    assert freight["lifting_per_piece_hkd"] == "0.0316"


@pytest.mark.parametrize(("parameters", "amounts", "total"), [
    ({"adhesive_extra_hkd": "0.12", "cartons_per_pallet": "40", "paper_pallet_extra_hkd": "0.07"}, ["0.2075", "0.8617"], "1.0692"),
    ({"adhesive_extra_hkd": 0, "cartons_per_pallet": 24, "paper_pallet_extra_hkd": 0}, ["0.0875", "0.7917"], "0.8792"),
])
def test_justplay_packaging_uses_editable_parameters(parameters, amounts, total):
    result = calculate("sales", {
        "pricing_mode": "component",
        "justplay_packaging": parameters,
        "color_box_size_in": {"length": 23, "width": 10, "height": 14.5},
        "cartons": [{"item": "主纸箱", "length_in": "23.75", "width_in": "10.75", "height_in": "15.5", "qty_per_carton": "2"}],
    })
    rows = [row for row in result["line_breakdown"] if row["kind"] == "justplay_fixed_packaging"]
    assert [row["amount_hkd"] for row in rows] == amounts
    assert result["totals"]["packaging_material_hkd"] == total
    assert rows[0]["adhesive_extra_hkd"] == f"{float(parameters['adhesive_extra_hkd']):.4f}"
    assert rows[1]["cartons_per_pallet"] == "12.0000"  # 4 wide * 1 long * 3 high; ignore legacy manual count
    assert rows[1]["paper_pallet_extra_hkd"] == f"{float(parameters['paper_pallet_extra_hkd']):.4f}"


@pytest.mark.parametrize("parameters", [
    {"adhesive_extra_hkd": -1}, {"paper_pallet_extra_hkd": -1},
    {"adhesive_extra_hkd": ""}, {"paper_pallet_extra_hkd": None},
    {"adhesive_extra_hkd": "Infinity"}, [], None,
])
def test_justplay_packaging_rejects_invalid_parameters(parameters):
    with pytest.raises(CalculationInputError):
        calculate("sales", {"pricing_mode": "component", "justplay_packaging": parameters})
    ordinary = calculate("sales", {"justplay_packaging": parameters})
    assert ordinary["totals"]["packaging_material_hkd"] == "0.0000"


def test_justplay_pallet_count_is_derived_and_oversize_cartons_cannot_be_priced():
    payload = {"pricing_mode": "component", "justplay_packaging": {
        "adhesive_extra_hkd": 0, "cartons_per_pallet": 0, "paper_pallet_extra_hkd": 0,
    }}
    assert calculate("sales", payload)["totals"]["packaging_material_hkd"] == "0.0000"
    payload["cartons"] = [{"item": "主纸箱", "length_in": 18, "width_in": 12, "height_in": 10, "qty_per_carton": 24}]
    payload["color_box_size_in"] = {"length": 17.25, "width": 11.25, "height": 9}
    result = calculate("sales", payload)
    pallet = next(row for row in result["line_breakdown"] if row.get("formula_code") == "paper_pallet")
    assert pallet["cartons_per_pallet"] == "30.0000"  # 3 * 2 * 5
    assert pallet["amount_hkd"] == "0.0264"
    payload["justplay_packaging"]["paper_pallet_extra_hkd"] = "0.049"
    result = calculate("sales", payload)
    pallet = next(row for row in result["line_breakdown"] if row.get("formula_code") == "paper_pallet")
    assert pallet["paper_pallet_extra_hkd"] == "0.0500"
    assert pallet["amount_hkd"] == "0.0764"
    payload["color_box_size_in"]["width"] = 50
    with pytest.raises(CalculationInputError, match="超出纸托板可装范围"):
        calculate("sales", payload)


def test_engineering_electronic_and_molding_decimal_vectors():
    engineering = calculate(
        "engineering",
        {
            "materials": [
                {
                    "item": "五金件",
                    "category": "hardware",
                    "quantity": "2",
                    "unit_price_rmb": "8.5",
                }
            ],
            "molds": [{"item": "主模", "quantity": "1", "cost_rmb": "1000"}],
            "amortization_qty": "100",
            "customer_mold_subsidy_usd": "5",
            "cartons": [
                {
                    "item": "外箱",
                    "length_in": "10",
                    "width_in": "5",
                    "height_in": "4",
                    "qty_per_carton": "10",
                    "flat_cards": [
                        {"length_in": "8", "width_in": "4", "quantity": "2"}
                    ],
                }
            ],
        },
    )
    assert engineering["status"] == "valid"
    assert engineering["line_breakdown"][0]["unit_price_hkd"] == "10.0000"
    assert engineering["line_breakdown"][0]["auxiliary_category"] == "五金"
    assert engineering["line_breakdown"][0]["tax_rate_percent"] == "13.0000"
    assert engineering["line_breakdown"][0]["formula"].startswith("用量 × 原单价 RMB × 损耗率")
    assert engineering["totals"] == {
        "hardware_hkd": "20.0000",
        "auxiliary_hkd": "0.0000",
        "packaging_hkd": "0.0000",
        "carton_hkd": "0.1111",
        "carton_cuft": "0.1157",
        "mold_quote_total_rmb": "1000.0000",
        "mold_quote_total_hkd": "1176.4706",
        "mold_total_rmb": "1000.0000",
        "mold_fx_rmb_usd": "7.7500",
        "mold_share_rmb": "10.0000",
        "mold_share_usd": "1.2403",
        "prototype_share_rmb": "0.0000",
        "prototype_share_usd": "0.0000",
        "testing_share_rmb": "0.0000",
        "testing_share_usd": "0.0000",
        "mold_amortization_rmb": "10.0000",
        "mold_amortization_usd": "1.2403",
        "total_hkd": "20.1111",
    }
    electronic = calculate(
        "electronic",
        {
            "components": [
                {
                    "item": "主件",
                    "quantity": "2",
                    "unit_price_hkd": "3",
                    "children": [
                        {"item": "子件", "quantity": "4", "unit_price_hkd": "1.5"}
                    ],
                }
            ],
            "bonding_hkd": "1",
            "smt_hkd": "2",
            "labor_hkd": "3",
            "testing_hkd": "4",
            "packaging_hkd": "5",
            "profit_rate_percent": "10",
            "tax_credit_difference_hkd": "10",
        },
    )
    assert electronic["totals"]["component_hkd"] == "12.0000"
    assert electronic["totals"]["pre_tax_hkd"] == "27.0000"
    assert electronic["totals"]["tax_payable_hkd"] == "1.0000"
    assert electronic["totals"]["total_hkd"] == "40.7000"

    molding = calculate(
        "molding",
        {
            "injection_lines": [
                {
                    "item": "主壳",
                    "material": "ABS",
                    "grade": "750SW",
                    "net_weight_g": "454",
                    "machine_code": "5A",
                    "sets": "2",
                    "target_output": "100",
                    "quantity": "2",
                }
            ],
            "blow_lines": [
                {
                    "item": "吹气件",
                    "material": "ABS",
                    "grade": "750SW",
                    "estimated_weight_g": "454",
                    "labor_hkd": "1",
                    "burr_hkd": "0.5",
                }
            ],
        },
    )
    assert molding["status"] == "valid"
    assert molding["totals"] == {
        "injection_hkd": "26.9100",
        "injection_material_hkd": "17.5100",
        "injection_imported_material_hkd": "17.5100",
        "injection_domestic_material_hkd": "0.0000",
        "injection_labor_hkd": "9.4000",
        "blow_hkd": "10.5000",
        "total_hkd": "37.4100",
    }
    injection_line = molding["line_breakdown"][0]
    assert injection_line["loss_weight_g"] == "467.6200"
    assert injection_line["material_price_hkd_g"] == "0.0187"
    assert injection_line["material_cost_hkd"] == "8.7550"
    assert injection_line["material_amount_hkd"] == "17.5100"
    assert injection_line["material_origin"] == "imported"
    assert injection_line["molding_cost_hkd"] == "4.7000"
    assert injection_line["molding_amount_hkd"] == "9.4000"
    assert injection_line["unit_amount_hkd"] == "13.4550"
    assert "台班价 ÷ 套数 ÷ 目标数" in injection_line["formula"]
    blow_line = molding["line_breakdown"][1]
    assert blow_line["subtotal_hkd"] == "10.0000"
    assert blow_line["unit_amount_hkd"] == "10.5000"
    assert "吹工 + 披锋" in blow_line["formula"]


def test_molding_totals_keep_domestic_material_split_without_mixing_in_process_cost():
    result = calculate_section(
        "molding",
        {
            "injection_lines": [
                {
                    "item": "齿轮",
                    "material": "POM",
                    "grade": "F3003/M9044",
                    "net_weight_g": "454",
                    "machine_code": "5A",
                    "sets": "1",
                    "target_output": "100",
                    "quantity": "2",
                }
            ]
        },
        {
            **SNAPSHOT,
            "material_prices": {
                **SNAPSHOT["material_prices"],
                "POM|F3003/M9044": "16.50",
            },
        },
        "IQREF-TEST",
    )

    assert result["status"] == "valid"
    line = result["line_breakdown"][0]
    assert line["material_origin"] == "domestic"
    assert line["material_amount_hkd"] == "33.9900"
    assert line["molding_amount_hkd"] == "18.8000"
    assert result["totals"]["injection_material_hkd"] == "33.9900"
    assert result["totals"]["injection_imported_material_hkd"] == "0.0000"
    assert result["totals"]["injection_domestic_material_hkd"] == "33.9900"
    assert result["totals"]["injection_labor_hkd"] == "18.8000"


def test_electronic_rmb_contract_recalculates_tax_and_hkd_quote_from_snapshot():
    electronic = calculate(
        "electronic",
        {
            "pricing_currency": "RMB",
            "components": [
                {
                    "item": "IC",
                    "specification": "A1",
                    "quantity": "2",
                    "unit_price_rmb": "0.45",
                    "tax_rate_percent": "13",
                    "children": [
                        {
                            "item": "",
                            "specification": "A2",
                            "quantity": "18",
                            "unit_price_rmb": "0.002",
                            "tax_rate_percent": "13",
                        }
                    ],
                }
            ],
            "bonding_rmb": "0",
            "smt_rmb": "0.496",
            "labor_rmb": "0.6925",
            "testing_rmb": "0.14",
            "packaging_rmb": "0.023",
            "profit_rate_percent": "10",
        },
    )

    assert electronic["status"] == "valid"
    assert electronic["currency_totals"] == {"HKD": "3.2443", "RMB": "2.7576", "USD": "0.0000"}
    assert electronic["totals"]["component_rmb"] == "0.9360"
    assert electronic["totals"]["pre_tax_rmb"] == "2.2875"
    assert electronic["totals"]["deductible_input_tax_rmb"] == "0.1077"
    assert electronic["totals"]["tax_credit_difference_rmb"] == "0.2194"
    assert electronic["totals"]["tax_payable_rmb"] == "0.0219"
    assert electronic["totals"]["total_hkd"] == "3.2443"


def test_electronic_quick_quote_uses_requested_fields_and_ignores_detail_rows():
    electronic = calculate(
        "electronic",
        {
            "quote_mode": "quick",
            "quick_quotes": [
                {"item": "主控板", "unit_price_rmb": "10", "tax_rate_percent": "13", "remark": "含税"},
                {"item": "喇叭", "unit_price_rmb": "5", "tax_rate_percent": "0", "remark": "不含税"},
            ],
            "components": [
                {"item": "保留明细", "quantity": "1", "unit_price_rmb": "999", "tax_rate_percent": "13"},
            ],
            "profit_rate_percent": "10",
        },
    )

    assert electronic["status"] == "valid"
    assert electronic["currency_totals"] == {"HKD": "20.6988", "RMB": "17.5940", "USD": "0.0000"}
    assert electronic["totals"]["component_rmb"] == "15.0000"
    assert [row["item"] for row in electronic["line_breakdown"]] == ["主控板", "喇叭"]
    assert electronic["line_breakdown"][0]["unit_price_hkd"] == "11.7647"
    assert electronic["line_breakdown"][0]["quantity"] == "1.0000"


def test_painting_slush_sewing_and_assembly_decimal_vectors():
    painting = calculate(
        "painting",
        {
            "rows": [
                {
                    "name": "主壳",
                    "position": "正面",
                    "image_reference": "主壳.png",
                    "remark": "对色板",
                    "operations": {
                        "clamp": {"quantity": "2", "unit_price_hkd": "1.5"},
                        "pad_print": {"quantity": "1", "unit_price_hkd": "2"},
                        "pp_water": {"quantity": "2", "unit_price_hkd": "0.25"},
                    },
                }
            ]
        },
    )
    assert painting["totals"]["total_hkd"] == "5.5000"
    assert painting["line_breakdown"][0]["operations"]["pp_water"] == "0.5000"
    assert painting["line_breakdown"][0]["name"] == "主壳"
    assert painting["line_breakdown"][0]["position"] == "正面"

    slush = calculate(
        "slush",
        {"lines": [{"product_code": "RC-01", "item": "软胶件", "material": "PVC", "weight_g": "35", "daily_output_24h": "8000", "quantity": "2", "unit_price_hkd": "3.6", "remark": "透明"}]},
    )
    assert slush["totals"]["total_hkd"] == "7.2000"
    assert slush["totals"]["total_rmb"] == "6.1200"
    assert slush["currency_totals"]["RMB"] == "6.1200"
    assert slush["line_breakdown"][0]["product_code"] == "RC-01"
    assert slush["line_breakdown"][0]["weight_g"] == "35.0000"
    assert slush["line_breakdown"][0]["formula"] == "quantity * unit_price_hkd"

    hair = calculate(
        "hair",
        {
            "lines": [
                {
                    "name": "公仔头发",
                    "craft": "植发",
                    "weight_g": "18.5",
                    "unit_price_hkd": "2.35",
                    "unit": "PCS",
                    "remark": "棕色",
                },
                {
                    "name": "尾巴毛",
                    "craft": "车发",
                    "weight_g": "3",
                    "unit_price_hkd": "0.65",
                    "unit": "PCS",
                    "remark": "",
                },
            ]
        },
    )
    assert hair["status"] == "valid"
    assert hair["totals"] == {"total_hkd": "3.0000"}
    assert hair["currency_totals"]["HKD"] == "3.0000"
    assert hair["line_breakdown"][0] == {
        "kind": "hair",
        "item": "公仔头发",
        "craft": "植发",
        "weight_g": "18.5000",
        "unit_price_hkd": "2.3500",
        "unit": "PCS",
        "remark": "棕色",
        "formula": "unit_price_hkd",
        "amount_hkd": "2.3500",
    }

    sewing = calculate(
        "sewing",
        {
            "groups": [
                {
                    "name": "外套",
                    "category": "clothes",
                    "materials": [
                        {"item": "布料", "part": "身体", "craft": "电绣", "pieces": "4", "usage": "1.2", "unit_price_rmb": "28", "markup": "1.05", "remark": "红色"}
                    ],
                    "labor_rmb": "12",
                },
                {
                    "name": "发套",
                    "category": "hair",
                    "materials": [
                        {"item": "人工车缝", "usage": "1", "unit_price_rmb": "5", "markup": "1"}
                    ],
                    "labor_rmb": "100",
                },
            ]
        },
    )
    assert sewing["totals"]["clothes_rmb"] == "47.2800"
    assert sewing["totals"]["hair_rmb"] == "5.0000"
    assert sewing["totals"]["clothes_material_rmb"] == "35.2800"
    assert sewing["totals"]["clothes_labor_rmb"] == "12.0000"
    assert sewing["totals"]["hair_material_rmb"] == "0.0000"
    assert sewing["totals"]["hair_labor_rmb"] == "5.0000"
    assert sewing["totals"]["material_rmb"] == "35.2800"
    assert sewing["totals"]["labor_rmb"] == "17.0000"
    assert sewing["totals"]["clothes_material_hkd"] == "41.5059"
    assert sewing["totals"]["clothes_labor_hkd"] == "14.1176"
    assert sewing["totals"]["hair_material_hkd"] == "0.0000"
    assert sewing["totals"]["hair_labor_hkd"] == "5.8824"
    assert sewing["totals"]["material_hkd"] == "41.5059"
    assert sewing["totals"]["labor_hkd"] == "20.0000"
    assert sewing["totals"]["total_rmb"] == "52.2800"
    assert sewing["totals"]["total_hkd"] == "61.5059"
    sewing_line = sewing["line_breakdown"][0]
    assert sewing_line["cost_kind"] == "material"
    assert sewing_line["amount_hkd"] == "41.5059"
    assert sewing_line["part"] == "身体"
    assert sewing_line["craft"] == "电绣"
    assert sewing_line["pieces"] == "4.0000"
    assert sewing_line["price_rmb"] == "33.6000"
    assert sewing_line["amount_rmb"] == "35.2800"
    assert sewing_line["formula"] == "usage * unit_price_rmb / exchange_rate * markup"

    assembly = calculate(
        "assembly",
        {
            "groups": [
                {
                    "name": "组装",
                    "category": "assembly",
                    "processes": [
                        {"name": "锁螺丝", "persons": "4", "teams": "2", "production_qty": "800"}
                    ],
                },
                {
                    "name": "包装",
                    "category": "packaging",
                    "processes": [
                        {"name": "装箱", "persons": "3", "teams": "2", "production_qty": "800"}
                    ],
                },
            ]
        },
    )
    assert assembly["totals"] == {
        "assembly_hkd": "2.6000",
        "packaging_hkd": "1.9500",
        "total_hkd": "4.5500",
    }
    assert assembly["group_summaries"][0] == {
        "category": "assembly",
        "group": "组装",
        "standard_work_hours": "11.0000",
        "labor_base_hkd": "260.0000",
        "production_qty": "800.0000",
        "teams": "2.0000",
        "total_persons": "4.0000",
        "amount_hkd_pcs": "2.6000",
        "formula": "人工基数 × 总人数 × 小组数 ÷ 生产量",
    }


def test_painting_and_sewing_quick_quotes_are_authoritative_hkd_totals():
    painting = calculate(
        "painting",
        {
            "quote_mode": "quick",
            "quick_quote": {"spray_labor_hkd": "2", "paint_hkd": "3"},
            "rows": [{"name": "历史明细不应重复计价", "operations": {"spray": {"quantity": 99, "unit_price_hkd": 99}}}],
        },
    )
    assert painting["status"] == "valid"
    assert painting["totals"] == {
        "quote_mode": "quick",
        "painting_labor_hkd": "2.0000",
        "paint_base_hkd": "3.0000",
        "paint_tax_hkd": "0.3900",
        "paint_material_hkd": "3.3900",
        "total_hkd": "5.3900",
    }
    assert [row["amount_hkd"] for row in painting["line_breakdown"]] == ["2.0000", "3.0000", "0.3900"]

    sewing = calculate(
        "sewing",
        {
            "quote_mode": "quick",
            "quick_quotes": [
                {"doll_name": "公仔 A", "unit_price_hkd": "4.25"},
                {"doll_name": "公仔 B", "unit_price_hkd": "5.75"},
            ],
            "groups": [{"name": "历史明细不应重复计价", "category": "clothes", "materials": [{"item": "布", "usage": 10, "unit_price_rmb": 10}]}],
        },
    )
    assert sewing["status"] == "valid"
    assert sewing["totals"]["total_hkd"] == "10.0000"
    assert sewing["totals"]["total_rmb"] == "8.5000"
    assert sewing["totals"]["clothes_hkd"] == "10.0000"
    assert sewing["totals"]["clothes_material_hkd"] == "0.0000"
    assert sewing["totals"]["clothes_labor_hkd"] == "10.0000"
    assert sewing["totals"]["material_hkd"] == "0.0000"
    assert sewing["totals"]["labor_hkd"] == "10.0000"
    assert [row["item"] for row in sewing["line_breakdown"]] == ["公仔 A", "公仔 B"]


def test_sewing_tax_basis_splits_material_rows_labor_rows_and_legacy_group_labor():
    sewing = calculate(
        "sewing",
        {
            "groups": [
                {
                    "name": "布衣",
                    "category": "clothes",
                    "materials": [
                        {"item": "棉布", "part": "身体", "usage": "1", "unit_price_rmb": "8.5", "markup": "1"},
                        {"item": "人工车缝", "part": "", "usage": "1", "unit_price_rmb": "1.7", "markup": "1"},
                    ],
                    # An explicit labor detail line suppresses this legacy fallback.
                    "labor_rmb": "99",
                },
                {
                    "name": "帽子",
                    "category": "clothes",
                    "materials": [
                        {"item": "绒布", "part": "外层", "usage": "1", "unit_price_rmb": "4.25", "markup": "1"},
                    ],
                    "labor_rmb": "0.85",
                },
            ]
        },
    )

    assert sewing["totals"]["clothes_material_rmb"] == "12.7500"
    assert sewing["totals"]["clothes_labor_rmb"] == "2.5500"
    assert sewing["totals"]["clothes_material_hkd"] == "15.0000"
    assert sewing["totals"]["clothes_labor_hkd"] == "3.0000"
    assert sewing["totals"]["material_hkd"] == "15.0000"
    assert sewing["totals"]["labor_hkd"] == "3.0000"
    assert sewing["totals"]["clothes_hkd"] == "18.0000"
    assert sewing["totals"]["total_hkd"] == "18.0000"
    assert [row["cost_kind"] for row in sewing["line_breakdown"]] == ["material", "labor", "material"]


def test_sewing_detail_uses_row_exchange_rate_for_authoritative_hkd_amounts():
    sewing = calculate(
        "sewing",
        {
            "groups": [{
                "name": "土豆蝙蝠",
                "category": "clothes",
                "materials": [
                    {
                        "item": "莱卡布",
                        "part": "前身",
                        "usage": "0.084",
                        "unit_price_rmb": "93.2",
                        "exchange_rate": "0.8",
                        "markup": "1.1",
                    },
                    {
                        "item": "车缝人工",
                        "usage": "1",
                        "unit_price_rmb": "1.7",
                        "markup": "1",
                    },
                ],
            }],
        },
    )

    material, labor = sewing["line_breakdown"]
    assert material["exchange_rate"] == "0.8000"
    assert material["cost_rmb"] == "7.8288"
    assert material["cost_hkd"] == "9.7860"
    assert material["amount_hkd"] == "10.7646"
    assert material["formula"] == "usage * unit_price_rmb / exchange_rate * markup"
    assert labor["exchange_rate"] == "0.8500"
    assert labor["amount_hkd"] == "2.0000"
    assert sewing["totals"]["clothes_material_hkd"] == "10.7646"
    assert sewing["totals"]["clothes_labor_hkd"] == "2.0000"
    assert sewing["totals"]["total_hkd"] == "12.7646"
    assert sewing["totals"]["total_rmb"] == "10.3117"


def test_incomplete_quick_quotes_can_be_saved_but_block_submission():
    empty_painting = calculate("painting", {"quote_mode": "quick", "quick_quote": {}})
    assert empty_painting["status"] == "blocked"
    assert "painting_quick_quote_empty" in {warning["code"] for warning in empty_painting["warnings"]}

    incomplete_sewing = calculate("sewing", {"quote_mode": "quick", "quick_quotes": [{"doll_name": "", "unit_price_hkd": 2}]})
    assert incomplete_sewing["status"] == "blocked"
    assert incomplete_sewing["warnings"][0]["code"] == "sewing_quick_quote_incomplete"


def test_incomplete_hair_rows_can_be_saved_but_block_submission():
    result = calculate(
        "hair",
        {
            "lines": [
                {
                    "name": "",
                    "craft": "植发",
                    "weight_g": "0",
                    "unit_price_hkd": "2",
                    "unit": "",
                }
            ]
        },
    )
    assert result["status"] == "blocked"
    assert result["warnings"][0]["code"] == "hair_line_incomplete"


def test_assembly_group_inputs_follow_reference_summary_formula():
    assembly = calculate(
        "assembly",
        {
            "labor_base_hkd": "260",
            "standard_work_hours": "10.5",
            "groups": [{
                "name": "成品组装",
                "category": "assembly",
                "production_qty": "100",
                "teams": "2",
                "processes": [
                    {"name": "锁螺丝", "persons": "3", "remark": "电批"},
                    {"name": "组装", "persons": "2", "remark": ""},
                ],
            }],
        },
    )

    assert assembly["totals"]["assembly_hkd"] == "26.0000"
    assert assembly["group_summaries"][0]["standard_work_hours"] == "10.5000"
    assert assembly["group_summaries"][0]["total_persons"] == "5.0000"
    assert [row["amount_hkd_pcs"] for row in assembly["line_breakdown"]] == ["15.6000", "10.4000"]


def test_assembly_manual_total_persons_is_authoritative_only_without_process_rows():
    manual = calculate(
        "assembly",
        {
            "labor_base_hkd": "260",
            "standard_work_hours": "11",
            "groups": [{
                "name": "成品组装",
                "category": "assembly",
                "production_qty": "100",
                "teams": "2",
                "total_persons": "6",
                "processes": [],
            }],
        },
    )

    assert manual["status"] == "valid"
    assert manual["totals"]["assembly_hkd"] == "31.2000"
    assert manual["group_summaries"][0]["total_persons"] == "6.0000"
    assert manual["line_breakdown"][0]["kind"] == "assembly_manual_total"

    missing = calculate(
        "assembly",
        {
            "groups": [{
                "name": "成品组装",
                "category": "assembly",
                "production_qty": "100",
                "teams": "1",
                "processes": [],
            }],
        },
    )
    assert missing["status"] == "blocked"
    assert missing["warnings"][0]["code"] == "assembly_total_persons_missing"

    empty_process = calculate(
        "assembly",
        {
            "groups": [{
                "name": "成品组装",
                "category": "assembly",
                "production_qty": "100",
                "teams": "1",
                "total_persons": "99",
                "processes": [{"name": "装配", "persons": "0"}],
            }],
        },
    )
    assert empty_process["status"] == "blocked"
    assert empty_process["totals"]["assembly_hkd"] == "0.0000"
    assert empty_process["warnings"][0]["code"] == "assembly_process_persons_missing"


def test_engineering_mold_detail_and_production_allocations_follow_rr2_fields_and_formulas():
    engineering = calculate(
        "engineering",
        {
            "materials": [],
            "molds": [
                {
                    "item": "主体模",
                    "mold_no": "M-01",
                    "mold_base_type": "CI 3040",
                    "quantity": "2",
                    "cost_rmb": "5000",
                    "net_weight_g": "120",
                    "cycle_time_seconds": "35",
                }
            ],
            "production_mold_costs": [
                {"item": "模具费用", "cost_rmb": "1000"},
                {"item": "超声模费用", "cost_rmb": "550"},
            ],
            "mold_fx_rmb_usd": "7.75",
            "customer_mold_subsidy_usd": "10",
            "amortization_qty": "100",
            "prototype_total_usd": "500",
            "prototype_amortization_qty": "50000",
            "testing_total_usd": "100",
            "testing_amortization_qty": "2000",
        },
    )

    assert engineering["status"] == "valid"
    assert engineering["totals"]["mold_quote_total_rmb"] == "5000.0000"
    assert engineering["totals"]["mold_quote_total_hkd"] == "5882.3529"
    assert engineering["totals"]["mold_total_rmb"] == "1550.0000"
    assert engineering["totals"]["mold_share_rmb"] == "15.5000"
    assert engineering["totals"]["mold_share_usd"] == "1.9000"
    assert engineering["totals"]["prototype_share_rmb"] == "0.0775"
    assert engineering["totals"]["prototype_share_usd"] == "0.0100"
    assert engineering["totals"]["testing_share_rmb"] == "0.3875"
    assert engineering["totals"]["testing_share_usd"] == "0.0500"
    assert engineering["totals"]["mold_amortization_rmb"] == "15.9650"
    assert engineering["totals"]["mold_amortization_usd"] == "1.9600"
    assert [row["item"] for row in engineering["line_breakdown"] if row["kind"] == "mold_allocation"] == [
        "生产模费分摊",
        "手板费分摊",
        "测试费分摊",
    ]

    allocation_disabled = calculate(
        "engineering",
        {
            "materials": [],
            "molds": [{"item": "主体模", "quantity": "1", "cost_rmb": "5000"}],
            "mold_allocation_enabled": False,
            "production_mold_costs": [{"item": "模具费用", "cost_rmb": "1000"}],
            "mold_fx_rmb_usd": "7.75",
            "amortization_qty": "100",
            "prototype_total_usd": "500",
            "prototype_amortization_qty": "50000",
            "testing_total_usd": "100",
            "testing_amortization_qty": "2000",
        },
    )
    assert allocation_disabled["totals"]["mold_total_rmb"] == "0.0000"
    assert allocation_disabled["totals"]["mold_amortization_rmb"] == "0.0000"
    assert allocation_disabled["totals"]["mold_amortization_usd"] == "0.0000"
    assert not any(row["kind"] in {"production_mold_cost", "mold_allocation"} for row in allocation_disabled["line_breakdown"])
    assert any(row["kind"] == "mold_quote" for row in allocation_disabled["line_breakdown"])

    with pytest.raises(CalculationInputError, match="客户模费补贴不能大于"):
        calculate(
            "engineering",
            {
                "materials": [],
                "molds": [],
                "production_mold_costs": [{"item": "模具费用", "cost_rmb": "7.75"}],
                "mold_fx_rmb_usd": "7.75",
                "customer_mold_subsidy_usd": "2",
                "amortization_qty": "100",
            },
        )

    adjusted_assembly = calculate(
        "assembly",
        {
            "labor_base_hkd": "310",
            "groups": [
                {
                    "name": "组装",
                    "category": "assembly",
                    "processes": [
                        {"name": "锁螺丝", "persons": "4", "teams": "2", "production_qty": "800"}
                    ],
                }
            ],
        },
    )
    assert adjusted_assembly["totals"]["assembly_hkd"] == "3.1000"


def test_sales_owns_carton_flat_card_and_cuft_calculation():
    sales = calculate(
        "sales",
        {
            "paper_price_factor": "2.75",
            "packaging_materials": [{
                "item": "彩盒",
                "specification": "四彩印刷",
                "category": "color_box_inner_card",
                "quantity": "2",
                "unit_price_rmb": "3.4",
                "tax_rate_percent": "10",
                "remark": "FSC",
            }],
            "product_size_in": {"length": "12", "width": "8", "height": "4"},
            "color_box_size_in": {"length": "13", "width": "9", "height": "5"},
            "cartons": [
                {
                    "item": "主纸箱",
                    "length_in": "10",
                    "width_in": "5",
                    "height_in": "4",
                    "qty_per_carton": "10",
                    "flat_cards": [
                        {"name": "主平卡", "length_in": "8", "width_in": "4", "quantity": "2"}
                    ],
                }
            ],
        },
        factory_price_hkd="20",
        mold_amortization_usd="0",
    )
    assert sales["status"] == "valid"
    assert sales["totals"]["base_factory_price_hkd"] == "20.0000"
    assert sales["totals"]["packaging_material_hkd"] == "8.0000"
    assert sales["totals"]["packaging_material_rmb"] == "6.8000"
    assert sales["totals"]["carton_hkd"] == "0.1111"
    assert sales["totals"]["carton_cuft"] == "0.1157"
    assert sales["totals"]["factory_price_hkd"] == "28.1111"
    assert sales["totals"]["total_hkd"] == "8.1111"
    assert sales["line_breakdown"][0] == {
        "kind": "packaging_material",
        "owner": "sales",
        "item": "彩盒",
        "specification": "四彩印刷",
        "category": "color_box_inner_card",
        "quantity": "2.0000",
        "base_unit_price_rmb": "3.4000",
        "base_unit_price_hkd": "4.0000",
        "loss_rate": "1.0000",
        "unit_price_rmb": "3.4000",
        "unit_price_hkd": "4.0000",
        "unit_price_source_currency": "RMB",
        "tax_rate_percent": "10.0000",
        "amount_rmb": "6.8000",
        "amount_hkd": "8.0000",
        "remark": "FSC",
        "formula": "用量 × 原单价 RMB × 损耗率 ÷ 冻结 RMB→HKD 汇率（税点仅记录，不重复加价）",
    }
    assert sales["line_breakdown"][1] == {
        "kind": "carton",
        "owner": "sales",
        "item": "主纸箱",
        "paper_price_factor": "2.7500",
        "flat_card_price_factor": "2.7500",
        "carton_price_hkd": "0.9350",
        "flat_card_price_hkd": "0.1760",
        "per_piece_hkd": "0.1111",
        "cuft": "0.1157",
        "qty_per_carton": "10.0000",
    }

    justplay = calculate(
        "sales",
        {
            "pricing_mode": "component",
            "paper_price_factor": "2.75",
            "color_box_size_in": {"length": 23, "width": 10, "height": 14.5},
            "cartons": [{
                "item": "主纸箱",
                "length_in": "23.75",
                "width_in": "10.75",
                "height_in": "15.5",
                "qty_per_carton": "2",
                "flat_cards": [],
            }],
        },
        factory_price_hkd="20",
    )
    fixed_lines = [
        row for row in justplay["line_breakdown"]
        if row["kind"] == "justplay_fixed_packaging"
    ]
    assert [row["item"] for row in fixed_lines] == ["胶纸/胶水/胶针", "纸托板成本"]
    assert [row["formula_code"] for row in fixed_lines] == ["adhesive", "paper_pallet"]
    assert [row["amount_hkd"] for row in fixed_lines] == ["0.0875", "0.7917"]
    assert justplay["totals"]["packaging_material_hkd"] == "0.8792"
    assert justplay["totals"]["packaging_material_rmb"] == "0.0000"

    adjusted = calculate(
        "sales",
        {
            "paper_price_factor": "2.75",
            "flat_card_price_factor": "1.5",
            "product_size_cm": {"length": "12", "width": "8", "height": "4"},
            "color_box_size_cm": {"length": "13", "width": "9", "height": "5"},
            "cartons": [{
                "item": "主纸箱", "length_in": "10", "width_in": "5", "height_in": "4",
                "qty_per_carton": "10",
                "flat_cards": [{"name": "主平卡", "length_in": "8", "width_in": "4", "quantity": "2"}],
            }],
        },
        factory_price_hkd="20",
    )
    assert adjusted["line_breakdown"][0]["flat_card_price_factor"] == "1.5000"
    assert adjusted["line_breakdown"][0]["flat_card_price_hkd"] == "0.0960"
    assert adjusted["totals"]["carton_hkd"] == "0.1031"

    with pytest.raises(CalculationInputError, match="平卡第 1 行用量 必须大于 0"):
        calculate(
            "sales",
            {
                "paper_price_factor": "2.75",
                "cartons": [{
                    "item": "主纸箱",
                    "length_in": "10",
                    "width_in": "5",
                    "height_in": "4",
                    "qty_per_carton": "10",
                    "flat_cards": [{
                        "name": "主平卡",
                        "length_in": "8",
                        "width_in": "4",
                        "quantity": "0",
                    }],
                }],
            },
            factory_price_hkd="20",
        )

    optional_product_dimensions = calculate(
        "sales",
        {
            "paper_price_factor": "2.7",
            "flat_card_price_factor": "2.7",
            "freight_calc": {
                "cap_10t": "1166", "cap_5t": "750", "cap_40": "1980", "cap_20": "883",
                "hk40": "8000", "hk20": "7100", "yt40": "7200", "yt20": "6000",
                "hk10t": "14900", "yt10t": "11500", "hk5t": "12500", "yt5t": "11000",
            },
            "product_size_cm": {"length": 0, "width": 0, "height": 0},
            "color_box_size_cm": {"length": "13.375", "width": "13.375", "height": "4.25"},
            "cartons": [{
                "item": "主纸箱", "length_in": "14", "width_in": "9.25", "height_in": "23.875",
                "qty_per_carton": "2",
                "flat_cards": [{"name": "平卡1", "length_in": "14", "width_in": "9.25", "quantity": "1"}],
            }],
        },
        factory_price_hkd="0",
    )
    assert optional_product_dimensions["status"] == "valid"
    assert optional_product_dimensions["totals"]["carton_hkd"] == "2.5013"
    assert optional_product_dimensions["line_breakdown"][0]["per_piece_hkd"] == "2.5013"
    freight_options = optional_product_dimensions["totals"]["freight_options"]
    assert len(freight_options) == 8
    assert freight_options[0]["kind"] == "freight_reference"
    assert freight_options[0]["reference_only"] is True
    assert freight_options[0]["item"] == "HK 40 柜"
    assert freight_options[0]["capacity_cuft"] == "1980"
    assert freight_options[0]["carton_cuft"] == "1.7892"
    assert freight_options[0]["qty_per_carton"] == "2.0000"
    assert freight_options[0]["total_cartons"] == "1107.0000"
    assert freight_options[0]["freight_per_piece_hkd"] == "3.6134"
    assert freight_options[0]["lifting_cost_hkd"] == "0.0000"
    assert freight_options[0]["lifting_per_piece_hkd"] == "0.0000"
    assert freight_options[0]["per_piece_hkd"] == "3.6134"
    assert freight_options[-1]["item"] == "YT 5 吨车"
    assert optional_product_dimensions["totals"]["total_hkd"] == "2.5013"
    assert len(optional_product_dimensions["line_breakdown"]) == 9

    baseline_freight = calculate_section(
        "sales",
        {
            "freight_calc": {"cap_40": "1980"},
            "cartons": [{
                "item": "主纸箱", "length_in": "14", "width_in": "9.25", "height_in": "23.875",
                "qty_per_carton": "2", "flat_cards": [],
            }],
        },
        {
            **SNAPSHOT,
            "freight": {
                "capacity_cuft": {"container_40": "1980"},
                "routes": [{
                    "route_key": "sz40",
                    "route_name": "深圳 40 柜",
                    "capacity_key": "cap_40",
                    "freight_hkd": "6500",
                    "lifting_hkd": "1100",
                }],
            },
        },
        "IQREF-FREIGHT-BASELINE",
        context={"factory_price_hkd": "0"},
    )
    assert len(baseline_freight["totals"]["freight_options"]) == 1
    baseline_sz40 = baseline_freight["totals"]["freight_options"][0]
    assert baseline_sz40["route_key"] == "sz40"
    assert baseline_sz40["item"] == "深圳 40 柜"
    assert baseline_sz40["freight_cost_hkd"] == "6500.0000"
    assert baseline_sz40["lifting_cost_hkd"] == "1100.0000"
    assert baseline_sz40["has_lifting_fee"] is True
    assert baseline_sz40["freight_per_piece_hkd"] == "2.9359"
    assert baseline_sz40["lifting_per_piece_hkd"] == "0.4968"
    assert baseline_sz40["per_piece_hkd"] == "3.4327"
    assert baseline_sz40["formula"] == "已启用的运费与吊柜费分别 ÷ ROUND(柜/车容量 ÷ 主纸箱 CUFT) ÷ 每箱数量；未启用项按 0 计算"

    selected_freight = calculate_section(
        "sales",
        {
            "freight_calc": {"cap_40": "1980", "cap_20": "883", "selected_route_keys": ["sz20"]},
            "cartons": [{
                "item": "主纸箱", "length_in": "14", "width_in": "9.25", "height_in": "23.875",
                "qty_per_carton": "2", "flat_cards": [],
            }],
        },
        {
            **SNAPSHOT,
            "freight": {
                "routes": [
                    {"route_key": "sz40", "route_name": "深圳 40 柜", "capacity_key": "cap_40", "freight_hkd": "6500", "lifting_hkd": "1100"},
                    {"route_key": "sz20", "route_name": "深圳 20 柜", "capacity_key": "cap_20", "freight_hkd": "4200", "lifting_hkd": "700"},
                ],
            },
        },
        "IQREF-FREIGHT-SELECTED",
        context={"factory_price_hkd": "0"},
    )
    assert [row["route_key"] for row in selected_freight["totals"]["freight_options"]] == ["sz20"]

    custom_capacity_freight = calculate_section(
        "sales",
        {
            "freight_calc": {"8 吨车容量": "1200"},
            "cartons": [{
                "item": "主纸箱", "length_in": "12", "width_in": "12", "height_in": "12",
                "qty_per_carton": "10", "flat_cards": [],
            }],
        },
        {
            **SNAPSHOT,
            "freight": {
                "routes": [{
                    "route_key": "hk8t",
                    "route_name": "HK 8 吨车",
                    "capacity_key": "8 吨车容量",
                    "freight_hkd": "6000",
                    "lifting_hkd": "800",
                }],
            },
        },
        "IQREF-FREIGHT-CUSTOM-CAPACITY",
        context={"factory_price_hkd": "0"},
    )
    custom_capacity_option = custom_capacity_freight["totals"]["freight_options"][0]
    assert custom_capacity_option["route_key"] == "hk8t"
    assert custom_capacity_option["capacity_cuft"] == "1200"
    assert custom_capacity_option["total_cartons"] == "1200.0000"
    assert custom_capacity_option["per_piece_hkd"] == "0.5667"

    freight_only = calculate_section(
        "sales",
        {
            "freight_calc": {
                "enabled": True,
                "freight_enabled": True,
                "lifting_enabled": False,
                "cap_40": "1980",
            },
            "cartons": [{
                "item": "主纸箱", "length_in": "14", "width_in": "9.25", "height_in": "23.875",
                "qty_per_carton": "2", "flat_cards": [],
            }],
        },
        {
            **SNAPSHOT,
            "freight": {
                "capacity_cuft": {"container_40": "1980"},
                "routes": [{
                    "route_key": "sz40",
                    "route_name": "深圳 40 柜",
                    "capacity_key": "cap_40",
                    "freight_hkd": "6500",
                    "lifting_hkd": "1100",
                }],
            },
        },
        "IQREF-FREIGHT-ONLY",
        context={"factory_price_hkd": "0"},
    )
    freight_only_sz40 = freight_only["totals"]["freight_options"][0]
    assert freight_only_sz40["freight_enabled"] is True
    assert freight_only_sz40["lifting_enabled"] is False
    assert freight_only_sz40["freight_per_piece_hkd"] == "2.9359"
    assert freight_only_sz40["lifting_cost_hkd"] == "0.0000"
    assert freight_only_sz40["lifting_per_piece_hkd"] == "0.0000"
    assert freight_only_sz40["per_piece_hkd"] == "2.9359"

    self_pickup = calculate(
        "sales",
        {
            "paper_price_factor": "2.7",
            "freight_calc": {"enabled": False},
            "product_size_cm": {"length": 0, "width": 0, "height": 0},
            "color_box_size_cm": {"length": 0, "width": 0, "height": 0},
            "cartons": [{
                "item": "主纸箱", "length_in": "14", "width_in": "9.25", "height_in": "23.875",
                "qty_per_carton": "2", "flat_cards": [],
            }],
        },
        factory_price_hkd="0",
    )
    assert self_pickup["totals"]["freight_options"] == []
    assert len(self_pickup["line_breakdown"]) == 1

    with pytest.raises(CalculationInputError, match="容量必须为整数"):
        calculate(
            "sales",
            {
                "paper_price_factor": "2.7",
                "freight_calc": {"enabled": True, "cap_40": "1980.5"},
                "product_size_cm": {"length": 0, "width": 0, "height": 0},
                "color_box_size_cm": {"length": 0, "width": 0, "height": 0},
                "cartons": [{
                    "item": "主纸箱", "length_in": "14", "width_in": "9.25", "height_in": "23.875",
                    "qty_per_carton": "2", "flat_cards": [],
                }],
            },
            factory_price_hkd="0",
        )

    missing = calculate(
        "sales",
        {
            "paper_price_factor": "2.75",
            "product_size_cm": {"length": 0, "width": 0, "height": 0},
            "color_box_size_cm": {"length": 0, "width": 0, "height": 0},
            "cartons": [],
        },
        factory_price_hkd="20",
    )
    assert missing["status"] == "blocked"
    assert missing["warnings"][0]["code"] == "sales_carton_missing"


def test_sales_uses_separate_main_and_inner_carton_factors_with_legacy_fallback():
    cartons = [
        {
            "item": "主纸箱",
            "length_in": "10",
            "width_in": "5",
            "height_in": "4",
            "qty_per_carton": "10",
            "flat_cards": [],
        },
        {
            "item": "内纸箱 1",
            "length_in": "8",
            "width_in": "4",
            "height_in": "3",
            "qty_per_carton": "2",
            "flat_cards": [],
        },
    ]
    separated = calculate(
        "sales",
        {
            "paper_price_factor": "2.75",
            "inner_paper_price_factor": "1.5",
            "freight_calc": {"enabled": False},
            "cartons": cartons,
        },
        factory_price_hkd="0",
    )
    separated_lines = [row for row in separated["line_breakdown"] if row["kind"] == "carton"]
    assert [row["paper_price_factor"] for row in separated_lines] == ["2.7500", "1.5000"]
    assert [row["carton_price_hkd"] for row in separated_lines] == ["0.9350", "0.3360"]
    assert [row["per_piece_hkd"] for row in separated_lines] == ["0.0935", "0.1680"]
    assert separated["totals"]["carton_hkd"] == "0.2615"
    assert separated["totals"]["carton_cuft"] == "0.1713"

    legacy = calculate(
        "sales",
        {
            "paper_price_factor": "2.75",
            "freight_calc": {"enabled": False},
            "cartons": cartons,
        },
        factory_price_hkd="0",
    )
    legacy_lines = [row for row in legacy["line_breakdown"] if row["kind"] == "carton"]
    assert [row["paper_price_factor"] for row in legacy_lines] == ["2.7500", "2.7500"]
    assert [row["carton_price_hkd"] for row in legacy_lines] == ["0.9350", "0.6160"]
    assert legacy["totals"]["carton_hkd"] == "0.4015"

    with pytest.raises(CalculationInputError, match="内纸箱纸价系数 必须大于 0"):
        calculate(
            "sales",
            {
                "paper_price_factor": "2.75",
                "inner_paper_price_factor": "0",
                "freight_calc": {"enabled": False},
                "cartons": cartons,
            },
            factory_price_hkd="0",
        )

    main_only = calculate(
        "sales",
        {
            "paper_price_factor": "2.75",
            "inner_paper_price_factor": "0",
            "freight_calc": {"enabled": False},
            "cartons": cartons[:1],
        },
        factory_price_hkd="0",
    )
    assert main_only["totals"]["carton_hkd"] == "0.0935"


def test_auxiliary_and_packaging_materials_accept_hkd_source_prices():
    engineering = calculate(
        "engineering",
        {
            "materials": [{
                "item": "胶袋",
                "category": "auxiliary",
                "auxiliary_category": "胶袋",
                "quantity": "3",
                "unit_price_rmb": "999",
                "unit_price_hkd": "2",
                "unit_price_source_currency": "HKD",
                "loss_rate": "1.02",
                "tax_rate_percent": "13",
            }],
            "molds": [],
        },
    )
    material = engineering["line_breakdown"][0]
    assert material["unit_price_source_currency"] == "HKD"
    assert material["base_unit_price_hkd"] == "2.0000"
    assert material["base_unit_price_rmb"] == "1.7000"
    assert material["loss_rate"] == "1.0200"
    assert material["unit_price_hkd"] == "2.0400"
    assert material["unit_price_rmb"] == "1.7340"
    assert material["amount_hkd"] == "6.1200"
    assert material["amount_rmb"] == "5.2020"
    assert engineering["totals"]["auxiliary_hkd"] == "6.1200"
    assert material["formula"].startswith("用量 × 原单价 HKD × 损耗率")

    hardware = calculate(
        "engineering",
        {
            "materials": [{
                "item": "螺丝",
                "category": "hardware",
                "quantity": "2",
                "unit_price_rmb": "8.5",
                "loss_rate": "1.02",
            }],
            "molds": [],
        },
    )["line_breakdown"][0]
    assert hardware["base_unit_price_rmb"] == "8.5000"
    assert hardware["loss_rate"] == "1.0200"
    assert hardware["unit_price_rmb"] == "8.6700"
    assert hardware["unit_price_hkd"] == "10.2000"
    assert hardware["amount_hkd"] == "20.4000"

    sales = calculate(
        "sales",
        {
            "packaging_materials": [{
                "item": "吸塑罩",
                "category": "blister",
                "quantity": "2",
                "unit_price_hkd": "4",
                "loss_rate": "1.05",
                "tax_rate_percent": "6",
            }],
        },
        factory_price_hkd="20",
        mold_amortization_usd="0",
    )
    packaging = sales["line_breakdown"][0]
    assert packaging["unit_price_source_currency"] == "HKD"
    assert packaging["base_unit_price_hkd"] == "4.0000"
    assert packaging["base_unit_price_rmb"] == "3.4000"
    assert packaging["loss_rate"] == "1.0500"
    assert packaging["unit_price_hkd"] == "4.2000"
    assert packaging["unit_price_rmb"] == "3.5700"
    assert packaging["amount_hkd"] == "8.4000"
    assert sales["totals"]["packaging_material_hkd"] == "8.4000"
    assert sales["totals"]["packaging_material_rmb"] == "7.1400"

    with pytest.raises(CalculationInputError, match="输入币种必须是 RMB 或 HKD"):
        calculate(
            "sales",
            {
                "packaging_materials": [{
                    "item": "彩盒",
                    "category": "color_box_inner_card",
                    "quantity": "1",
                    "unit_price_rmb": "3.4",
                    "unit_price_source_currency": "USD",
                }],
            },
            factory_price_hkd="20",
            mold_amortization_usd="0",
        )

    with pytest.raises(CalculationInputError, match="损耗率 必须大于 0"):
        calculate(
            "engineering",
            {
                "materials": [{
                    "item": "螺丝",
                    "category": "hardware",
                    "quantity": "1",
                    "unit_price_rmb": "1",
                    "loss_rate": "0",
                }],
                "molds": [],
            },
        )


def test_sales_testing_fee_calculates_multiple_moq_unit_prices_without_changing_hkd_cost():
    payload = {
        "testing_fee_total_usd": "1250",
        "testing_fee_moqs": ["5000", "10000"],
        "freight_calc": {"enabled": False},
        "cartons": [{
            "item": "主纸箱",
            "length_in": "10",
            "width_in": "5",
            "height_in": "4",
            "qty_per_carton": "10",
            "flat_cards": [],
        }],
    }
    sales = calculate("sales", payload, factory_price_hkd="20")
    baseline = calculate(
        "sales",
        {**payload, "testing_fee_total_usd": "0", "testing_fee_moqs": ["0"]},
        factory_price_hkd="20",
    )

    assert sales["status"] == "valid"
    assert sales["currency_totals"]["USD"] == "0.2500"
    assert sales["currency_totals"]["HKD"] == baseline["currency_totals"]["HKD"]
    assert sales["totals"]["testing_fee_total_usd"] == "1250.0000"
    assert sales["totals"]["testing_fee_moqs"] == ["5000.0000", "10000.0000"]
    assert sales["totals"]["testing_fee_tiers"] == [
        {"moq": "5000.0000", "unit_price_usd": "0.2500"},
        {"moq": "10000.0000", "unit_price_usd": "0.1250"},
    ]
    assert sales["totals"]["testing_fee_moq"] == "5000.0000"
    assert sales["totals"]["testing_fee_unit_usd"] == "0.2500"
    assert sales["totals"]["factory_price_hkd"] == baseline["totals"]["factory_price_hkd"]
    assert sales["line_breakdown"][0] == {
        "kind": "sales_testing_fee",
        "owner": "sales",
        "item": "测试费",
        "total_usd": "1250.0000",
        "moq": "5000.0000",
        "unit_price_usd": "0.2500",
        "tiers": [
            {"moq": "5000.0000", "unit_price_usd": "0.2500"},
            {"moq": "10000.0000", "unit_price_usd": "0.1250"},
        ],
        "formula": "测试费用 USD ÷ MOQ 数量",
        "reference_only": True,
    }

    legacy = calculate(
        "sales",
        {**payload, "testing_fee_moqs": None, "testing_fee_moq": "5000"},
        factory_price_hkd="20",
    )
    assert legacy["totals"]["testing_fee_moqs"] == ["5000.0000"]
    assert legacy["totals"]["testing_fee_unit_usd"] == "0.2500"

    disabled = calculate(
        "sales",
        {**payload, "testing_fee_enabled": False, "testing_fee_moqs": ["保留但不校验"]},
        factory_price_hkd="20",
    )
    assert disabled["currency_totals"]["USD"] == "0.0000"
    assert disabled["totals"]["testing_fee_enabled"] is False
    assert disabled["totals"]["testing_fee_total_usd"] == "0.0000"
    assert disabled["totals"]["testing_fee_tiers"] == []
    assert all(row.get("kind") != "sales_testing_fee" for row in disabled["line_breakdown"])

    with pytest.raises(CalculationInputError, match="第 2 档 MOQ 必须大于 0"):
        calculate(
            "sales",
            {
                "testing_fee_total_usd": "1250",
                "testing_fee_moqs": ["5000", "0"],
                "freight_calc": {"enabled": False},
                "cartons": payload["cartons"],
            },
            factory_price_hkd="20",
        )

    with pytest.raises(CalculationInputError, match="MOQ 不能重复"):
        calculate(
            "sales",
            {
                "testing_fee_total_usd": "1250",
                "testing_fee_moqs": ["5000", "5000"],
                "freight_calc": {"enabled": False},
                "cartons": payload["cartons"],
            },
            factory_price_hkd="20",
        )


def test_sales_scenario_and_blocking_reference_warnings():
    sales = calculate(
        "sales",
        {
            "additional_tax_hkd": "2",
            "tax_categories": [{"code": "carton", "amount_hkd": "20"}],
            "scenarios": [
                {
                    "name": "盐田测试场景",
                    "capacity_cuft": "100",
                    "freight_cost_hkd": "100",
                    "carton_cuft": "10",
                    "qty_per_carton": "2",
                }
            ],
        },
        factory_price_hkd="10",
        mold_amortization_usd="1",
    )
    assert sales["totals"]["tax_deduction_hkd"] == "0.0000"
    assert sales["totals"]["after_tax_cost_hkd"] == "10.0000"
    carton_tax_line = next(
        row for row in sales["line_breakdown"]
        if row.get("kind") == "tax" and row.get("code") == "carton"
    )
    assert carton_tax_line["rate"] is None
    assert carton_tax_line["deduction_hkd"] is None
    assert sales["totals"]["scenarios"][0]["total_usd"] == "3.6688"

    misc_ratio = calculate(
        "sales",
        {"shipping": {"misc_ratio": "0.035"}, "freight_calc": {"enabled": False}},
        factory_price_hkd="10",
    )
    assert misc_ratio["totals"]["misc_ratio"] == "0.0350"

    tiered_markup = calculate(
        "sales",
        {
            "shipping": {
                "markup_x": "1.20",
                "markup_tiers": [
                    {"moq": 3000, "markup_x": "1.30"},
                    {"moq": 5000, "markup_x": "1.25"},
                    {"moq": 10000, "markup_x": "1.15"},
                ],
                "selected_markup_moq": 5000,
            },
            "freight_calc": {"enabled": False},
        },
        factory_price_hkd="10",
    )
    assert tiered_markup["totals"]["total_hkd"] == "0.0000"

    selective_tiers = calculate(
        "sales",
        {
            "shipping": {
                "markup_tiers": [
                    {"moq": 3000, "markup_x": "1.30", "include_in_output": False},
                    {"moq": 5000, "markup_x": "1.25", "include_in_output": True},
                ],
                "selected_markup_moq": 5000,
            },
            "freight_calc": {"enabled": False},
        },
        factory_price_hkd="10",
    )
    assert selective_tiers["status"] == "valid"

    with pytest.raises(CalculationInputError, match="至少要输出一个 MOQ"):
        calculate(
            "sales",
            {
                "shipping": {
                    "markup_tiers": [
                        {"moq": 3000, "markup_x": "1.30", "include_in_output": False},
                        {"moq": 5000, "markup_x": "1.25", "include_in_output": False},
                    ],
                },
                "freight_calc": {"enabled": False},
            },
            factory_price_hkd="10",
        )

    with pytest.raises(CalculationInputError, match="MOQ 必须由小到大排列"):
        calculate(
            "sales",
            {
                "shipping": {
                    "markup_tiers": [
                        {"moq": 5000, "markup_x": "1.20"},
                        {"moq": 3000, "markup_x": "1.30"},
                    ],
                },
                "freight_calc": {"enabled": False},
            },
            factory_price_hkd="10",
        )

    with pytest.raises(CalculationInputError, match="本单采用的 MOQ 必须来自分段码数档位"):
        calculate(
            "sales",
            {
                "shipping": {
                    "markup_tiers": [
                        {"moq": 3000, "markup_x": "1.30"},
                        {"moq": 5000, "markup_x": "1.20"},
                    ],
                    "selected_markup_moq": 10000,
                },
                "freight_calc": {"enabled": False},
            },
            factory_price_hkd="10",
        )

    historical_empty_shipping = calculate(
        "sales",
        {"shipping": None, "freight_calc": {"enabled": False}},
        factory_price_hkd="10",
    )
    assert historical_empty_shipping["totals"]["misc_ratio"] == "0.0200"

    for invalid_misc_ratio in ("1", "1.01"):
        with pytest.raises(CalculationInputError, match="杂项系数必须在 0% 至 100% 之间"):
            calculate(
                "sales",
                {
                    "shipping": {"misc_ratio": invalid_misc_ratio},
                    "freight_calc": {"enabled": False},
                },
                factory_price_hkd="10",
            )

    missing_reference = calculate(
        "molding",
        {
            "injection_lines": [
                {
                    "material": "UNKNOWN",
                    "grade": "NONE",
                    "net_weight_g": "10",
                    "machine_code": "999A",
                    "sets": "1",
                    "target_output": "1",
                }
            ]
        },
    )
    assert missing_reference["status"] == "blocked"
    assert {warning["code"] for warning in missing_reference["warnings"]} == {
        "material_price_missing",
        "machine_price_missing",
    }


@pytest.mark.parametrize(
    ("shipping", "legacy_settlement", "expected_misc", "expected_after_settlement"),
    [
        ({"misc_ratio": "0.03", "divisor": "0.80"}, "0.70", "0.0300", "18.5567"),
        ({"divisor": "0.96"}, "0.70", "0.0400", "18.7500"),
        ({}, "0.95", "0.0500", "18.9474"),
        ({}, None, "0.0200", "18.3673"),
    ],
)
def test_sales_scenario_settlement_is_always_derived_from_resolved_misc_ratio(
    shipping: dict,
    legacy_settlement: str | None,
    expected_misc: str,
    expected_after_settlement: str,
):
    scenario = {
        "name": "兼容场景",
        "capacity_cuft": "100",
        "freight_cost_hkd": "100",
        "carton_cuft": "10",
        "qty_per_carton": "2",
    }
    if legacy_settlement is not None:
        scenario["settlement"] = legacy_settlement

    result = calculate(
        "sales",
        {"shipping": shipping, "scenarios": [scenario]},
        factory_price_hkd="10",
    )

    assert result["totals"]["misc_ratio"] == expected_misc
    assert result["totals"]["scenarios"][0]["after_settlement_hkd"] == expected_after_settlement


def test_real_buzzbee_18a_machine_code_is_present_in_the_authoritative_reference_table():
    snapshot = {
        **SNAPSHOT,
        "machine_prices": [
            {"range": machine_range, "machine": machine, "shift_price_hkd": price}
            for machine_range, machine, price in DEFAULT_MACHINE_PRICES
        ],
    }
    result = calculate_section(
        "molding",
        {
            "injection_lines": [{
                "item": "下---大身面壳+底壳",
                "material": "ABS",
                "grade": "750SW",
                "net_weight_g": "135",
                "machine_code": "18A",
                "sets": "1",
                "target_output": "2800",
                "quantity": "1",
            }],
            "blow_lines": [],
        },
        snapshot,
        "IQREF-BUZZBEE-L5-1",
    )
    assert result["status"] == "valid"
    assert result["line_breakdown"][0]["machine_shift_price_hkd"] == "1890.0000"

    bare_code_result = calculate_section(
        "molding",
        {
            "injection_lines": [{
                "item": "导入模具行",
                "material": "ABS",
                "grade": "750SW",
                "net_weight_g": "135",
                "machine_code": "18",
                "sets": "1",
                "target_output": "2800",
                "quantity": "1",
            }],
            "blow_lines": [],
        },
        snapshot,
        "IQREF-BARE-A-CODE",
    )
    assert bare_code_result["status"] == "valid"
    assert bare_code_result["line_breakdown"][0]["machine_shift_price_hkd"] == "1890.0000"


def test_caixing_tool_plan_is_validated_and_audited_without_changing_internal_cost():
    result = calculate(
        "molding",
        {
            "injection_lines": [],
            "blow_lines": [],
            "caixing_tool_plan_rows": [{
                "ref_no": "B1",
                "process_type": "BL",
                "tool_no": "",
                "tooling_cost_hkd": "5000",
                "description": "剑身",
                "sku_no": "68963",
                "cavities": "1",
                "up": "1",
                "net_weight_g": "50",
                "material_code": "11",
                "material": "LDPE",
                "color": "透明",
                "material_cost_hkd": "0.722",
                "machine_size": "BL",
                "cycle_time_seconds": "45",
                "process_cost_hkd": "0.718",
            }],
        },
    )

    assert result["status"] == "valid"
    assert result["warnings"] == []
    assert result["totals"]["total_hkd"] == "0.0000"
    assert result["line_breakdown"] == [{
        "kind": "caixing_tool_plan",
        "customer_only": True,
        "ref_no": "B1",
        "process_type": "BL",
        "item": "剑身",
        "sku_no": "68963",
        "cavities": "1.0000",
        "up": "1.0000",
        "net_weight_g": "50.0000",
        "material_code": "11.0000",
        "material": "LDPE",
        "machine_size": "BL",
        "cycle_time_seconds": "45.0000",
        "tooling_cost_hkd": "5000.0000",
        "material_cost_hkd": "0.7220",
        "process_cost_hkd": "0.7180",
        "amount_hkd": "0.0000",
    }]
