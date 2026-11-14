import pytest

from app.services.carton_issue_photo import _header, _request_rows, _unlabelled_rows


def box(text, x, y, width=.025, height=.022, score=.98):
    return dict(text=text, x=x, y=y, width=width, height=height, score=score)


def test_issue_photo_recovers_continued_contract_and_rejects_cross_column_quantity():
    boxes = [
        box("合同", .24, .29), box("貨號", .32, .29), box("品名規格", .44, .29),
        box("領料數", .68, .29), box("實發數", .75, .29),
        box("RL-449995-69 1423020051", .205, .333, .185),
        box("125", .689, .334), box("-70", .287, .375),
        box("500125", .62, .375, .102), box("76", .76, .375),
    ]
    header = _header(boxes)
    rows = _request_rows(boxes, header)
    assert [(row["contract_no"], row["item_no"], row["requested_quantity"]) for row in rows] == [
        ("RL-449995-69", "1423020051", "125"), ("-70", "", ""),
    ]
    assert rows[0]["top"] < rows[0]["bottom"] < rows[1]["bottom"]


@pytest.mark.parametrize(("reference", "item", "kind"), [
    ("客戶單號", "客戶料號", "contract"),
    ("合同編號", "客貨號", "contract"),
    ("Contract No.", "Item No.", "contract"),
    ("Ｐ／Ｏ＃", "產品編號", "po"),
    ("PO / 合同号", "產品貨號", "po"),
    ("客戶採購單號", "ITEM", "customer_po"),
])
def test_issue_photo_reads_project_header_aliases_with_item_first(reference, item, kind):
    boxes = [
        box(item, .17, .29, .07), box(reference, .35, .29, .08),
        box("合同数量", .58, .29, .08), box("实发数", .70, .29, .06),
        box("IT001", .17, .34, .07), box("RL-007", .35, .34, .08),
        box("500", .60, .34), box("25", .72, .34),
    ]
    row, = _request_rows(boxes, _header(boxes))
    assert (row["contract_no"], row["reference_kind"], row["item_no"], row["requested_quantity"]) == (
        "RL-007", kind, "IT001", "",
    )


def test_issue_photo_keeps_contract_and_po_columns_separate():
    boxes = [
        box("合同號", .17, .29, .07), box("P/O#", .35, .29, .08),
        box("產品貨號", .53, .29, .08), box("請領數量", .70, .29, .06),
        box("RL-007", .17, .34, .07), box("PO-0008", .35, .34, .08),
        box("森林动物", .53, .34, .08), box("125", .72, .34),
    ]
    row, = _request_rows(boxes, _header(boxes))
    assert (row["contract_no"], row["customer_po"], row["item_no"], row["requested_quantity"]) == (
        "RL-007", "PO-0008", "森林动物", "125",
    )


def test_partial_scan_preserves_number_evidence_but_never_guesses_quantity():
    rows = _unlabelled_rows([
        box("NO: 0021452", .73, .15),
        box("RL-449995-69", .2, .33), box("1423020051", .4, .334), box("125", .7, .335),
        box("4500225182-3", .2, .38),
    ])
    assert [row["evidence"] for row in rows] == ["RL-449995-69 · 1423020051", "4500225182-3"]
    assert all(not row["requested_quantity"] and not row["contract_no"] for row in rows)
