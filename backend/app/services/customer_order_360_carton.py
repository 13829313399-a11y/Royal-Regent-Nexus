"""User-maintained carton headers on registered unified schedule export copies."""
from .customer_order_360_manual_column import SHEETS, ensure_manual_columns, unified_manual_sheets


def ensure_carton_columns(workbook, *, factory_id: str, customer_code: str):
    sheets = unified_manual_sheets(workbook, factory_id, customer_code)
    return ensure_manual_columns(workbook, factory_id=factory_id, customer_code=customer_code,
                                 label="纸箱", aliases={"纸箱", "紙箱"}, sheets=sheets,
                                 scopes=((factory_id, customer_code),) if sheets else ())
