import pytest

from app.services.internal_quote_calculator import CalculationInputError, calculate_section


def calculate(value):
    return calculate_section(
        "sales", {"customer_quote_fields": {"yinhui": {"domestic_price_rmb": value}}},
        {"fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8"}}, "test-snapshot",
        context={"factory_price_hkd": "20"},
    )


@pytest.mark.parametrize("value", [None, "", 0, "55.615"])
def test_domestic_quote_is_optional_metadata_not_an_internal_cost(value):
    result = calculate(value)
    assert result["status"] == "valid"
    assert result["totals"] == calculate(None)["totals"]


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity", "bad"])
def test_domestic_quote_rejects_invalid_values(value):
    with pytest.raises(CalculationInputError, match="银辉内销最终单价 RMB"):
        calculate(value)
