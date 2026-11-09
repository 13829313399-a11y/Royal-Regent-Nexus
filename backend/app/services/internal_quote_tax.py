"""Factory-scoped quotation deduction rules, shared by summary and output."""
from decimal import Decimal
from typing import Any

SEWING_TAX_FACTORIES = frozenset({"huakang-c", "huakang-d"})
NON_TAX_CATEGORIES = frozenset({"carton", "material", "imp_mat", "dom_mat", "slush", "slush3"})
SEWING_TAX_CATEGORIES = {"sewing_hair": "sewing_hair", "sewhair13": "sewing_hair",
                         "sewing_clothes": "sewing_clothes", "sewcloth13": "sewing_clothes"}


def deduction_excluded(category: str, factory_id: str = "") -> bool:
    return category in NON_TAX_CATEGORIES or (
        category in SEWING_TAX_CATEGORIES and factory_id not in SEWING_TAX_FACTORIES)


def sewing_deduction_rate(snapshot: dict[str, Any], category: str, factory_id: str = "") -> Decimal | None:
    if factory_id not in SEWING_TAX_FACTORIES:
        return None
    rates = snapshot.get("tax_rates") or {}
    value = rates.get(SEWING_TAX_CATEGORIES[category], "0.115")
    return Decimal(str(value if value not in (None, "") else "0.115"))
