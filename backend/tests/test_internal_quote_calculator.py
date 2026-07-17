from app.services.internal_quote_calculator import DEFAULT_MACHINE_PRICES, calculate_section


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
    "assembly_labor_base_hkd": "310",
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
    assert engineering["totals"] == {
        "hardware_hkd": "20.0000",
        "auxiliary_hkd": "0.0000",
        "packaging_hkd": "0.0000",
        "carton_hkd": "0.1115",
        "carton_cuft": "0.1157",
        "mold_total_rmb": "1000.0000",
        "mold_amortization_rmb": "10.0000",
        "mold_amortization_usd": "1.2403",
        "total_hkd": "20.1115",
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
        "blow_hkd": "10.5000",
        "total_hkd": "37.4100",
    }


def test_painting_slush_sewing_and_assembly_decimal_vectors():
    painting = calculate(
        "painting",
        {
            "rows": [
                {
                    "item": "主壳",
                    "operations": {
                        "clamp": {"quantity": "2", "unit_price_hkd": "1.5"},
                        "pad_print": {"quantity": "1", "unit_price_hkd": "2"},
                    },
                }
            ]
        },
    )
    assert painting["totals"]["total_hkd"] == "5.0000"

    slush = calculate(
        "slush",
        {"lines": [{"item": "软胶件", "quantity": "2", "unit_price_hkd": "3.6"}]},
    )
    assert slush["totals"]["total_hkd"] == "7.2000"

    sewing = calculate(
        "sewing",
        {
            "groups": [
                {
                    "name": "外套",
                    "category": "clothes",
                    "materials": [
                        {"item": "布料", "usage": "1.2", "unit_price_rmb": "28", "markup": "1.05"}
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
    assert sewing["totals"]["total_hkd"] == "61.5059"

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
        "assembly_hkd": "3.1000",
        "packaging_hkd": "2.3250",
        "total_hkd": "5.4250",
    }


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
    assert sales["totals"]["tax_deduction_hkd"] == "2.0000"
    assert sales["totals"]["after_tax_cost_hkd"] == "8.0000"
    assert sales["totals"]["scenarios"][0]["total_usd"] == "3.6688"

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
