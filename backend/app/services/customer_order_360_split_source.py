"""Split provenance is manual metadata, never a new order type or stock movement."""
from .customer_order_360_manual_column import SHEETS, ensure_manual_columns, unified_manual_sheets


def ensure_split_source_columns(workbook, *, factory_id: str, customer_code: str):
    sheets = unified_manual_sheets(workbook, factory_id, customer_code)
    return ensure_manual_columns(workbook, factory_id=factory_id, customer_code=customer_code,
                                 label="拆单来源", aliases={"拆单来源", "拆單來源"},
                                 scopes=((factory_id, customer_code),) if sheets else (), sheets=sheets)
