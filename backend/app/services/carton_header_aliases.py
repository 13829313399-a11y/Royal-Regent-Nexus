"""Order identity headers shared by carton delivery import and requisition OCR."""

DELIVERY_IDENTITY_ALIASES = {
    "customer_po": {"客户po", "客户采购单号", "客户订单号", "customerpo"},
    "contract_no": {"po", "合同号", "合同", "pono", "订单编号", "客户单号"},
    "item_no": {"货号", "产品编号", "itemno", "item", "客户料号"},
}
