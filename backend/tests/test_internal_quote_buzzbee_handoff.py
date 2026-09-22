import json
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.services import internal_quote_excel as excel


@pytest.mark.parametrize("customer,factory,release,expected", [
    ("BuzzBee", "huaxing", "p4_final_approved", True),
    ("BuzzBee", "huaxing", "p3", False),
    ("BuzzBee", "huakang-a", "p4_final_approved", False),
    ("银辉", "huaxing", "p4_final_approved", False),
])
def test_buzzbee_handoff_uses_creation_identity_only(monkeypatch, customer, factory, release, expected):
    quote = SimpleNamespace(quote_no="IQ-BB", customer=customer, factory_id=factory,
                            product_name="本方案产品", version_label="R2", formula_version="F1",
                            reference_snapshot_id="REF1", header_revision=3,
                            created_at=datetime(2026, 9, 2, 10, 20))
    # Layout is covered separately; exercise the actual export gate and structured writer.
    monkeypatch.setattr(excel, "_build_summary_sheet", lambda *args: None)
    for name in ("_build_electronic_sheet", "_build_sewing_sheet", "_build_hair_sheet", "_build_assembly_sheet"):
        monkeypatch.setattr(excel, name, lambda *args: None)
    data = excel.build_internal_quote_workbook(quote, [], {"release_stage": release}, {})
    book = load_workbook(BytesIO(data))
    rows = list(book["结构化数据"].values) if "结构化数据" in book.sheetnames else []
    chunks = [row[10] for row in rows if row[0] == "customer_mapping"]
    assert bool(chunks) is expected
    if expected:
        mapping = json.loads("".join(chunks))
        assert mapping == {"version": "buzzbee-v2", "factory_id": "huaxing", "quote_no": "IQ-BB",
                           "version_label": "R2", "customer": "BuzzBee", "product_name": "本方案产品",
                           "quote_date": "2026-09-02", "formula_version": "F1", "reference_snapshot_id": "REF1"}
        assert book["结构化数据"].sheet_state == "veryHidden"
