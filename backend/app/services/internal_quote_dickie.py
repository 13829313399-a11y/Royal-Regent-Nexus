"""Read-only customer handoff of authoritative prices; never recalculate costs in JS."""
import json
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace


def build_dickie_handoff(quote, sections, snapshot, cost_context):
    from app.services.internal_quote import _rr2_cost_summary
    from app.services.internal_quote_excel import _testing_fee_values

    if quote.factory_id != "huaxing" or quote.customer.strip().lower() not in {"dickie", "dicky"}:
        return None
    sales = next((section for section in sections if section.department == "sales"), None)
    if sales is None:
        return None
    payload = json.loads(sales.payload_json or "{}")
    mapping = payload.get("customer_quote_fields", {}).get("dickie", {}).get("mapping", {})
    if mapping.get("version") != "dickie-v2":
        return None
    summary = _rr2_cost_summary(sections, cost_context, snapshot, quote.qty, factory_id=quote.factory_id)
    pricing = summary["shipping_pricing"]
    options = json.loads(sales.calculation_json or "{}").get("totals", {}).get("freight_options", [])
    # Match the internal workbook's final, testing-inclusive quotation. The
    # approved per-MOQ fee is marked up once, then converted using frozen FX;
    # it is not part of the route subtotal or its settlement deduction.
    _, testing_rows = _testing_fee_values(sales, payload)
    testing_usd_by_moq = {
        Decimal(str(row["moq"])): Decimal(str(row["unit_price_usd"]))
        for row in testing_rows
    }
    prices = []
    for tier in pricing["markup_tiers"]:
        if not tier.get("include_in_output", True):
            continue
        # Never copy SQLAlchemy state: the pricing view only needs these scalar fields.
        selected = SimpleNamespace(department="sales", is_required=sales.is_required,
                                   calculation_status=sales.calculation_status,
                                   calculation_json=sales.calculation_json)
        selected_payload = deepcopy(payload)
        selected_payload.setdefault("shipping", {})["selected_markup_moq"] = tier["moq"]
        selected.payload_json = json.dumps(selected_payload, ensure_ascii=False)
        tier_sections = [selected if section.department == "sales" else section for section in sections]
        tier_summary = _rr2_cost_summary(tier_sections, cost_context, snapshot, quote.qty, factory_id=quote.factory_id)
        route_rows = tier_summary["shipping_pricing"]["rows"][1:]
        if len(route_rows) != len(options):
            # Disabled freight is not an invitation to fabricate a route price.
            continue
        testing_hkd = (
            testing_usd_by_moq.get(Decimal(tier["moq"]), Decimal("0"))
            * Decimal(tier["markup"]) * Decimal(pricing["hkd_usd"])
        )
        for option, row in zip(options, route_rows):
            final_hkd = Decimal(row["total_hkd"]) + testing_hkd
            prices.append({
                "moq": tier["moq"], "route_key": option.get("route_key", ""),
                "route_name": row["name"],
                "price_hkd": str(final_hkd.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
                "unrounded_hkd": str(final_hkd), "lift_hkd": row["lift_hkd"],
            })
    return {
        "version": "dickie-v2", "quote_id": quote.id, "factory_id": quote.factory_id,
        "customer": quote.customer, "quote_no": quote.quote_no, "product_name": quote.product_name,
        "quantity": quote.qty, "version_label": quote.version_label,
        "formula_version": quote.formula_version, "reference_snapshot_id": quote.reference_snapshot_id,
        "prices": prices,
    }
