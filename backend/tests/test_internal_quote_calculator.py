from app.schemas.internal_quote import InternalQuoteSectionPayload
from app.services.internal_quote_calculator import calculate_section, default_reference_snapshot


def payload(rows, *, parameters=None, loss_pct=0):
    return InternalQuoteSectionPayload(
        rows=rows,
        parameters=parameters or {},
        loss_pct=loss_pct,
        reference_snapshot=default_reference_snapshot(),
    )


def row(line_id, item_name, *, quantity=0, unit_price_hkd=0, fields=None):
    return {
        "id": line_id,
        "item_name": item_name,
        "quantity": quantity,
        "unit_price_hkd": unit_price_hkd,
        "fields": fields or {},
    }


def test_molding_injection_uses_frozen_material_and_machine_reference_prices():
    source = payload([row("inj", "ABS外壳", fields={
        "mode": "injection",
        "material": "ABS",
        "material_grade": "抽粒料",
        "weight_g": 100,
        "loss_pct": 3,
        "machine_model": "4A",
        "sets": 2,
        "target": 1000,
    })])

    normalized, calculation = calculate_section("molding", source)

    assert calculation.formula_version == "department-formulas-v1"
    assert calculation.total_hkd == 1.51
    assert calculation.line_breakdown[0].formula == "克重 × (1+损耗%) × HK$/Lb ÷ 454 + 啤价"
    assert normalized.rows[0].amount_hkd == 1.51
    assert normalized.reference_snapshot["version"] == "rr2-2026-v1"


def test_molding_blow_formula_and_painting_no_loss():
    blow = payload([row("blow", "吹气件", fields={
        "mode": "blow",
        "weight_g": 100,
        "material_price_hkd_lb": 4.6,
        "blow_labor_hkd": 1,
        "flash_hkd": 0.5,
        "profit_multiplier": 1.2,
    })])
    painting = payload(
        [row("paint", "喷油", quantity=2, unit_price_hkd=3, fields={"mode": "operation"})],
        loss_pct=10,
    )

    assert calculate_section("molding", blow)[1].total_hkd == 3.02
    assert calculate_section("painting", painting)[1].total_hkd == 6
    assert calculate_section("painting", painting)[1].loss_amount_hkd == 0


def test_electronic_formula_applies_extras_profit_and_tax_difference():
    source = payload(
        [row("part", "IC", quantity=2, fields={"unit_price_rmb": 10})],
        parameters={
            "bonding_cost_rmb": 1,
            "smt_cost_rmb": 1,
            "labor_cost_rmb": 1,
            "test_repair_rmb": 1,
            "packing_shipping_rmb": 1,
            "profit_pct": 10,
            "tax_diff_rmb": 2,
        },
    )

    calculation = calculate_section("electronic", source)[1]

    assert calculation.total_hkd == 34.94
    assert calculation.total_rmb == 29.7
    assert calculation.total_usd == 4.48


def test_sewing_does_not_double_add_labor_and_assembly_uses_process_formula():
    sewing_with_labor_line = payload(
        [row("labor", "车缝人工", fields={"usage": 2, "material_price_hkd": 3, "markup": 1})],
        parameters={"labor_hkd": 10},
    )
    sewing_without_labor_line = payload(
        [row("cloth", "布料", fields={"usage": 2, "material_price_hkd": 3, "markup": 1})],
        parameters={"labor_hkd": 10},
    )
    assembly = payload([row("process", "组装", fields={
        "mode": "process",
        "base_rate_hkd": 310,
        "people_count": 4,
        "team_count": 2,
        "production_qty": 1000,
    })])

    assert calculate_section("sewing", sewing_with_labor_line)[1].total_hkd == 6
    assert calculate_section("sewing", sewing_without_labor_line)[1].total_hkd == 16
    assert calculate_section("assembly", assembly)[1].total_hkd == 2.48
