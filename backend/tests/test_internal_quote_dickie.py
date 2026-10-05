import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from app.services.internal_quote_dickie import build_dickie_handoff
from app.services.internal_quote_excel import _build_structured_data_sheet


def fixture():
    quote = SimpleNamespace(id="IQ-DICKIE", factory_id="huaxing", customer="Dickie", qty=5000,
                            quote_no="D-001", product_name="车", version_label="V1",
                            formula_version="F1", reference_snapshot_id="R1", header_revision=1)
    sales = SimpleNamespace(department="sales", department_name="业务", is_required=True,
                            status="approved", revision=2, dependency_status="current",
                            calculation_status="valid", calculation_hash="sales-hash",
                            payload_json=json.dumps({
                                "customer_quote_fields": {"dickie": {"mapping": {"version": "dickie-v2"}}},
                                "shipping": {"markup_tiers": [{"moq": 3000, "markup_x": "1.2"}, {"moq": 5000, "markup_x": "1.1"}, {"moq": 10000, "markup_x": "1.05", "include_in_output": False}],
                                             "selected_markup_moq": 5000, "misc_ratio": "0", "freight_pct": "1", "lifting_pct": "0"},
                                "freight_calc": {"enabled": True, "lifting_enabled": False},
                            }), calculation_json=json.dumps({"totals": {"freight_options": [
                                {"route_key": key, "item": key, "has_lifting_fee": True, "freight_per_piece_hkd": cost, "lifting_per_piece_hkd": "0", "total_cartons": "100"}
                                for key, cost in [("hk40", "1"), ("hk20", "2"), ("hk5t", "3")]
                            ]}}))
    return quote, sales


def test_handoff_uses_all_enabled_moq_tiers_without_mutating_sales():
    quote, sales = fixture()
    original = sales.payload_json
    result = build_dickie_handoff(quote, [sales], {}, {"factory_price_hkd": Decimal("10")})
    assert sales.payload_json == original
    assert result["quote_no"] == "D-001"
    assert [(p["moq"], p["route_key"], p["price_hkd"]) for p in result["prices"]] == [
        ("3000.0000", "hk40", "13.2"), ("3000.0000", "hk20", "14.4"), ("3000.0000", "hk5t", "15.6"),
        ("5000.0000", "hk40", "12.1"), ("5000.0000", "hk20", "13.2"), ("5000.0000", "hk5t", "14.3"),
    ]


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("fx, expected3000, expected5000, exact5000", [
    ("7.8", "31.9", "20.7", "20.68"),
    ("7.5", "31.2", "20.4", "20.35"),
])
def test_handoff_matches_testing_inclusive_prices_per_moq(enabled, fx, expected3000, expected5000, exact5000):
    quote, sales = fixture()
    payload = json.loads(sales.payload_json)
    payload["testing_fee_enabled"] = enabled
    # Stale retained inputs must not add a charge when testing is disabled.
    payload["testing_fee_total_usd"] = "9999"
    sales.payload_json = json.dumps(payload)
    calculation = json.loads(sales.calculation_json)
    calculation["totals"]["testing_fee_tiers"] = [
        {"moq": "3000.0000", "unit_price_usd": "2.0000"},
        {"moq": "5000.0000", "unit_price_usd": "1.0000"},
    ]
    sales.calculation_json = json.dumps(calculation)
    result = build_dickie_handoff(quote, [sales], {"fx": {"hkd_usd": fx}}, {"factory_price_hkd": Decimal("10")})
    first_route = {p["moq"]: p for p in result["prices"] if p["route_key"] == "hk40"}
    # Route subtotal plus approved USD fee * that tier's markup * frozen FX.
    assert first_route["3000.0000"]["price_hkd"] == (expected3000 if enabled else "13.2")
    assert first_route["5000.0000"]["price_hkd"] == (expected5000 if enabled else "12.1")
    assert Decimal(first_route["5000.0000"]["unrounded_hkd"]) == (Decimal(exact5000) if enabled else Decimal("12.1"))


def test_testing_fee_does_not_spread_to_a_different_moq():
    quote, sales = fixture()
    calculation = json.loads(sales.calculation_json)
    calculation["totals"]["testing_fee_tiers"] = [{"moq": "10000", "unit_price_usd": "1"}]
    sales.calculation_json = json.dumps(calculation)
    result = build_dickie_handoff(quote, [sales], {}, {"factory_price_hkd": Decimal("10")})
    assert result["prices"][0]["price_hkd"] == "13.2"


@pytest.mark.parametrize("factory,customer", [("huakang_a", "Dickie"), ("huaxing", "银辉"), ("huaxing", "Disney")])
def test_handoff_does_not_change_other_customers(factory, customer):
    quote, sales = fixture()
    quote.factory_id, quote.customer = factory, customer
    assert build_dickie_handoff(quote, [sales], {}, {}) is None


def test_old_dickie_payload_is_not_upgraded_implicitly():
    quote, sales = fixture()
    sales.payload_json = json.dumps({"customer_quote_fields": {"dickie": {"client_name": "Dickie"}}})
    assert build_dickie_handoff(quote, [sales], {}, {}) is None


def test_disabled_freight_never_fabricates_three_route_prices():
    quote, sales = fixture()
    payload = json.loads(sales.payload_json)
    payload["freight_calc"]["enabled"] = False
    sales.payload_json = json.dumps(payload)
    assert build_dickie_handoff(quote, [sales], {}, {})["prices"] == []


def test_new_record_is_chunked_in_controlled_structured_sheet():
    quote, sales = fixture()
    mapping = build_dickie_handoff(quote, [sales], {}, {"factory_price_hkd": Decimal("10")})
    workbook = Workbook()
    _build_structured_data_sheet(workbook, quote, [sales], {}, mapping)
    rows = list(workbook["结构化数据"].values)
    chunks = [row[10] for row in rows if row[0] == "customer_mapping"]
    assert json.loads("".join(chunks)) == mapping
    assert len([row for row in rows if row[0] == "payload"]) == 1
