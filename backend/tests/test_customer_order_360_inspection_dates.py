"""360 inspection labels retain their own date, independently of FCD."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import customer_order_huakang_a as service
from app.services.huakang_a_order_legacy import schedule_parser as parser
from customer_order_360_private_samples import private_po_samples


def _parse(tmp_path: Path, dates: str):
    source = tmp_path / "release.txt"
    source.write_text("date-label fixture", encoding="utf-8")
    text = "\n".join([
        "PURCHASE ORDER RELEASE (CINV) RL-765433-10 - REVISION 0",
        "1 8765432109.34 Each 240",
        "Toy Synthetic Craft Set 12pc",
        "Master Carton Qty : 4",
        dates,
        "Notify Party : As Per Instruction",
    ])
    return parser._parse_po_text(source, text, 1, tmp_path)


@pytest.mark.parametrize("label", ["Planned Inspection Date", "Planned Inspection"])
@pytest.mark.parametrize("separator", [" ", "\n"])
def test_both_inspection_labels_keep_the_explicit_date_and_mapping(tmp_path, label, separator):
    record = _parse(tmp_path, f"{label} : 8-Dec-2026{separator}Factory Commit Date : 10-Dec-2026")
    assert record["planned_inspection_date"] == "2026-12-08"
    assert record["factory_commit_date"] == "2026-12-10"
    fields = service._record_fields(service.get_huakang_a_customer_mapping("360"), record)
    assert fields["line_q"] == "2026-12-08"
    assert fields["customer_q"] == ""
    assert fields["requested_ship_date"] == "2026-12-10"


@pytest.mark.parametrize("inspection", ["", "Planned Inspection : TBD ", "Planned Inspection Date : TBD "])
def test_missing_or_unknown_inspection_does_not_borrow_fcd(tmp_path, inspection):
    record = _parse(tmp_path, inspection + "Factory Commit Date : 10-Dec-2026")
    assert record["planned_inspection_date"] == ""
    assert record["factory_commit_date"] == "2026-12-10"


@pytest.mark.parametrize("label", ["Planned Inspection Date", "Planned Inspection"])
def test_empty_label_does_not_capture_the_following_iso_fcd(tmp_path, label):
    record = _parse(tmp_path, f"{label} : Factory Commit Date : 2026-12-10")
    assert record["planned_inspection_date"] == ""
    assert record["factory_commit_date"] == "2026-12-10"


@pytest.mark.parametrize("sample", private_po_samples())
def test_supplied_360_po_inspection_dates(sample):
    """Opt-in real evidence stays outside the repository and is never modified."""
    source, expected = sample["source"], sample["expected"]
    assert source.is_file(), f"Missing supplied evidence: {source}"
    before = source.read_bytes()
    record = parser.parse_po_file(source, sample["manifest"]["po_directory"])
    assert record["planned_inspection_date"] == expected["planned_inspection_date"]
    assert record["factory_commit_date"] == expected["factory_commit_date"]
    assert source.read_bytes() == before
