"""Illustrative input scenarios, kept outside the importable worksheet."""
from datetime import date


def examples(mode):
    paper = dict(packaging_type="外箱", paper_quality="A33", specification="40*30*25", dimension_unit="cm", unit="个")
    if mode == "SPECIAL":
        head = dict(required_date=date(2026, 11, 20))
        return [
            ("样板单／单纸品", dict(paper, **head, group="SAMPLE-01", kind="样板单", quantity=12, note="客户打样")),
            ("样板单／多纸品 1", dict(paper, **head, group="SAMPLE-02", kind="样板单", quantity=20)),
            ("样板单／多纸品 2", dict(head, group="SAMPLE-02", kind="样板单", packaging_type="平卡", paper_quality="A3", specification="30*20", dimension_unit="cm", quantity=40, unit="张")),
            ("杂单／车间用箱", dict(paper, **head, group="MISC-01", kind="杂单", quantity=50, note="车间周转用箱")),
            ("杂单／纸卡", dict(head, group="MISC-02", kind="杂单", packaging_type="刀卡", paper_quality="B3B", specification="20*15", dimension_unit="cm", quantity=100, unit="张")),
        ]
    head = dict(customer="示例客户", item_no="000123", order_date=date(2026, 11, 1), customer_due_date=date(2026, 11, 20))
    return [
        ("正单／直接填数量", dict(paper, **head, contract_no="DEMO-DIRECT", quantity=100)),
        ("正单／按装箱数计算", dict(paper, **head, contract_no="DEMO-PACK", product_quantity=1200, usage_quantity=12)),
        ("正单／配套纸箱", dict(paper, **head, contract_no="DEMO-KIT", product_quantity=1200, usage_quantity=12)),
        ("正单／配套纸卡", dict(head, contract_no="DEMO-KIT", product_quantity=1200, packaging_type="平卡", paper_quality="A3", specification="30*20", dimension_unit="cm", unit="张", carton_source_row=7, per_carton_quantity=2, note="此处 7 指本示例表纸箱行；复制后改为实际行号")),
        ("正单／同合同不同 PO 1", dict(paper, **head, contract_no="DEMO-PO", customer_po="0001", quantity=100)),
        ("正单／同合同不同 PO 2", dict(paper, **head, contract_no="DEMO-PO", customer_po="0002", quantity=80)),
    ]
