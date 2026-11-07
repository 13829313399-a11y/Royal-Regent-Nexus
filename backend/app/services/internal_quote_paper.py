"""Resolve selected paper exclusively from this quotation's frozen catalogue."""
from decimal import Decimal

def paper_reference(row, snapshot, fallback, *, strict=True):
    from app.services.internal_quote_calculator import positive_value, CalculationInputError
    key = str(row.get("paper_material_key") or "").strip()
    if not key:
        try:
            return positive_value(fallback, "纸价系数"), "沿用原系数"
        except CalculationInputError:
            if strict:
                raise
            return Decimal(0), "系数待补全"
    matches = [r for r in snapshot.get("paper_prices", []) if isinstance(r, dict) and r.get("key") == key]
    if len(matches) != 1:
        if not strict:
            return Decimal(0), "纸材待重新选择"
        raise CalculationInputError(f"{row.get('item') or row.get('name') or '纸箱/平卡'}所选纸材未匹配本报价价目表，请重新选择")
    return positive_value(matches[0].get("price_factor_hkd"), "纸材系数 HKD"), str(matches[0].get("name", ""))


def paper_basis(row):
    # No extra keys for legacy rows: old approved manual adjustments keep their basis.
    key = str(row.get("paper_material_key") or "").strip()
    return {"paper_material_key": key} if key else {}
