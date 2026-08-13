from app.schemas.carton_mark import CartonMarkDocumentTextItem
from app.services.carton_mark_document_scope import (
    clean_pdf_document_text,
    prepare_carton_mark_document_scope,
)


def _item(text: str, location: str) -> CartonMarkDocumentTextItem:
    return CartonMarkDocumentTextItem(text=text, location=location)


def test_scope_excludes_raw_data_and_instruction_regions_in_favor_of_print_body():
    excel = [
        _item("PO NO", "箱唛!A10"),
        _item("4500216242", "箱唛!B10"),
        _item("ITEM", "箱唛!A11"),
        _item("77794UQ1", "箱唛!B11"),
        _item("4500216242", "原始数据!A2"),
        _item("77794UQ1", "原始数据!B2"),
        _item("内部单价", "原始数据!C2"),
        _item("19.88", "原始数据!D2"),
        _item("不要打印说明", "原始数据!E2"),
        _item("制作说明：调整空间排版并增加图案", "原始数据!A20"),
    ]
    pdf = [
        _item("PO NO: 4500216242", "第 1 页 · 第 1 行"),
        _item("ITEM: 77794UQ1", "第 1 页 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert {item.location.split("!", 1)[0] for item in result.excel_items} == {"箱唛"}
    assert [item.text for item in result.excel_items] == [
        "PO NO",
        "4500216242",
        "ITEM",
        "77794UQ1",
    ]
    assert result.diagnostics.excel_input_count == 10
    assert result.diagnostics.excel_selected_count == 4
    assert result.diagnostics.selected_sheets == ("箱唛",)


def test_scope_keeps_unmatched_sibling_field_from_selected_identity_row():
    excel = [
        _item("PO 4500216242", "箱唛!A10"),
        _item("ITEM 77794UQ1", "箱唛!A11"),
        _item("G.W. 5.93 KGS", "箱唛!B11"),
    ]
    pdf = [
        _item("PO 4500216242", "第 1 页 · 第 1 行"),
        _item("ITEM 77794UQ1", "第 1 页 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert [item.text for item in result.excel_items] == [
        "PO 4500216242",
        "ITEM 77794UQ1",
        "G.W. 5.93 KGS",
    ]
    assert not result.requires_review


def test_scope_preserves_repeated_business_values_across_rows_and_pages():
    excel = [
        _item("PO: 123456", "箱唛!A1"),
        _item("PO 123456", "箱唛!A2"),
        _item("ITEM: ABC-900", "箱唛!A3"),
        _item("ITEM ABC-900", "箱唛!A4"),
    ]
    pdf = [
        _item("PO 123456", "第 1 页 · 第 1 行"),
        _item("ITEM ABC-900", "第 1 页 · 第 2 行"),
        _item("PO: 123456", "第 2 页 · 第 1 行"),
        _item("ITEM: ABC-900", "第 2 页 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert [item.text for item in result.excel_items] == [
        "PO: 123456",
        "PO 123456",
        "ITEM: ABC-900",
        "ITEM ABC-900",
    ]
    assert [item.text for item in result.pdf_items] == [
        "PO 123456",
        "ITEM ABC-900",
        "PO: 123456",
        "ITEM: ABC-900",
    ]
    assert result.diagnostics.expected_duplicate_count == 0
    assert result.diagnostics.actual_duplicate_count == 0
    assert "Excel 抽取 4 项" in result.diagnostics.describe()
    assert "PDF 抽取 4 项" in result.diagnostics.describe()


def test_scope_without_strong_anchor_requires_review_and_keeps_evidence():
    excel = [
        _item("Notes", "箱唛!A1"),
        _item("Please adjust artwork", "箱唛!A2"),
        _item("#N/A", "箱唛!A3"),
        _item("#REF!", "箱唛!A4"),
    ]
    pdf = [_item("Artwork approved", "第 1 页 · 第 1 行")]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert result.requires_review
    assert result.confidence == 0.0
    assert [item.text for item in result.excel_items] == ["Notes", "Please adjust artwork"]
    assert result.diagnostics.ignored_excel_error_count == 2
    assert "未找到" in result.review_note


def test_pdf_cleaning_removes_controls_but_preserves_business_characters():
    assert clean_pdf_document_text(
        "PO\x00NO\ufffd:\u2028 AB-123/45  © 2026"
    ) == "PO NO : AB-123/45 © 2026"


def test_scope_does_not_filter_unmatched_pdf_additions():
    excel = [
        _item("PO 484860", "箱唛!A1"),
        _item("ITEM 415647", "箱唛!A2"),
    ]
    pdf = [
        _item("PO 484860", "第 1 页 · 第 1 行"),
        _item("ITEM 415647", "第 1 页 · 第 2 行"),
        _item("12 PCS", "第 1 页 · 第 3 行"),
        _item("42 CTNS", "第 1 页 · 第 4 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert [item.text for item in result.pdf_items] == [
        "PO 484860",
        "ITEM 415647",
        "12 PCS",
        "42 CTNS",
    ]


def test_scope_wide_source_rows_keep_print_columns_and_missing_values_only():
    excel = [
        _item("PI", "数据!A1"),
        _item("PO", "数据!D1"),
        _item("Item No.", "数据!E1"),
        _item("物料编码", "数据!F1"),
        _item("New Description", "数据!H1"),
        _item("Carton No.:", "数据!K1"),
        _item("QTY: PCS", "数据!L1"),
        _item("W. G.R", "数据!M1"),
        _item("W. NET", "数据!N1"),
        _item("MEASUREMENT", "数据!O1"),
        _item("GTIN", "数据!P1"),
        _item("采购订单号", "数据!Q1"),
        _item("Actual Factory", "数据!R1"),
        _item("供应商", "数据!S1"),
        _item("1100037622", "数据!A2"),
        _item("1100037622-Warehouse 1", "数据!D2"),
        _item("92121", "数据!E2"),
        _item("11028414", "数据!F2"),
        _item("S001-RAINBOCORNS-MAMACORN SURPRISE", "数据!H2"),
        _item("/84", "数据!K2"),
        _item("6", "数据!L2"),
        _item("3.74", "数据!M2"),
        _item("3.14", "数据!N2"),
        _item("55.6 x 19.7 x 57.5", "数据!O2"),
        _item("10193052078411", "数据!P2"),
        _item("4500216623", "数据!Q2"),
        _item("Example Factory Ltd.", "数据!R2"),
        _item("内部供应商", "数据!S2"),
    ]
    pdf = [
        _item("Order No: 1100037622-Warehouse 1", "第 1 页 · 第 1 行"),
        _item("ITEM: 92121", "第 1 页 · 第 2 行"),
        _item("S001-RAINBOCORNS-MAMACORN SURPRISE", "第 1 页 · 第 3 行"),
        _item("CARTON NO: /84", "第 1 页 · 第 4 行"),
        _item("QTY: 6 PCS", "第 1 页 · 第 5 行"),
        _item("GTIN 10193052078411", "第 1 页 · 第 6 行"),
        _item("PO 4500216623", "第 1 页 · 第 7 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    locations = {item.location for item in result.excel_items}

    assert {"数据!M2", "数据!N2", "数据!O2"} <= locations
    assert "数据!A2" not in locations
    assert "数据!F2" not in locations
    assert "数据!R2" not in locations
    assert "数据!S2" not in locations
    by_location = {item.location: item for item in result.excel_items}
    assert by_location["数据!M2"].field_key == "gross_weight"
    assert by_location["数据!N2"].field_key == "net_weight"
    assert by_location["数据!O2"].field_key == "measurement"


def test_scope_excludes_customer_po_column_when_po_is_not_printed():
    excel = [
        _item("Customer PO#", "箱唛!A1"),
        _item("SKU NO.", "箱唛!B1"),
        _item("DESCRIPTION", "箱唛!C1"),
        _item("PC PER CARTON", "箱唛!D1"),
        _item("NO CARTONS", "箱唛!E1"),
        _item("order 5462 Bekasovo 2", "箱唛!A2"),
        _item("100372", "箱唛!B2"),
        _item("SPARKLE UNICORN STYLING", "箱唛!C2"),
        _item("6", "箱唛!D2"),
        _item("288", "箱唛!E2"),
    ]
    pdf = [
        _item("ARTICLE NO.: 100372", "第 1 页 · 第 1 行"),
        _item("DESCRIPTION: SPARKLE UNICORN STYLING", "第 1 页 · 第 2 行"),
        _item("NUMBER OF PIECES: 6 PCS", "第 1 页 · 第 3 行"),
        _item("CTN NO.: 1 OF 288", "第 1 页 · 第 4 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    locations = {item.location for item in result.excel_items}

    assert "箱唛!A2" not in locations
    assert {"箱唛!B2", "箱唛!C2", "箱唛!D2", "箱唛!E2"} <= locations
    by_location = {item.location: item for item in result.excel_items}
    assert by_location["箱唛!B2"].field_key == "item"
    assert by_location["箱唛!D2"].field_key == "quantity"
    assert by_location["箱唛!E2"].field_key == "carton_no"


def test_multi_page_table_headers_and_unprinted_selector_do_not_force_review():
    excel = [
        _item("ITEM#92120TQ1", "箱唛!A1"),
        _item("Customer PO#", "箱唛!A2"),
        _item("SKU NO.", "箱唛!B2"),
        _item("DESCRIPTION", "箱唛!C2"),
        _item("order 5462", "箱唛!A3"),
        _item("100372", "箱唛!B3"),
        _item("SPARKLE UNICORN", "箱唛!C3"),
        _item("order 5462", "箱唛!A4"),
        _item("100373", "箱唛!B4"),
        _item("SPARKLE UNICORN SET", "箱唛!C4"),
    ]
    pdf = [
        _item("ARTICLE NO.: 100372", "第 1 页 · 第 1 行"),
        _item("DESCRIPTION: SPARKLE UNICORN", "第 1 页 · 第 2 行"),
        _item("ARTICLE NO.: 100373", "第 2 页 · 第 1 行"),
        _item("DESCRIPTION: SPARKLE UNICORN SET", "第 2 页 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert not result.requires_review
    assert {item.text for item in result.excel_items} >= {"100372", "100373"}


def test_scope_single_pdf_item_excludes_other_excel_item_blocks_and_requires_review():
    excel = [
        _item("ARTICLE Number:", "SM!A8"),
        _item("7057526", "SM!M8"),
        _item("Gross Weight:", "SM!K10"),
        _item("7.600", "SM!M10"),
        _item("Barcode Number:", "SM!K12"),
        _item("193052098443", "SM!M12"),
        _item("ARTICLE Number:", "SM!A34"),
        _item("7044498", "SM!M34"),
        _item("Gross Weight:", "SM!K36"),
        _item("2.800", "SM!M36"),
        _item("Measurement:", "SM!K37"),
        _item("29.0 x 21.0 x 31.0 cm", "SM!M37"),
        _item("Barcode Number:", "SM!K38"),
        _item("193052090409", "SM!M38"),
        _item("ARTICLE Number:", "SM!A49"),
        _item("7044499", "SM!M49"),
        _item("Gross Weight:", "SM!K51"),
        _item("1.490", "SM!M51"),
        _item("Barcode Number:", "SM!K53"),
        _item("193052090065", "SM!M53"),
    ]
    pdf = [
        _item("ARTICLE Number: 7044498", "第 1 页 · 第 1 行"),
        _item("Gross Weight: 2.800", "第 1 页 · 第 2 行"),
        _item("Measurement: 29.0 x 21.0 x 31.0 cm", "第 1 页 · 第 3 行"),
        _item("Barcode Number: 193052090409", "第 1 页 · 第 4 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    values = {item.text for item in result.excel_items}

    assert "7044498" in values
    assert "7057526" not in values
    assert "7044499" not in values
    assert result.requires_review


def test_scope_drops_selector_cell_before_repeated_front_and_side_item_values():
    excel = [
        _item("77770GQ2", "箱唛!A7"),
        _item("ITEM NO.", "箱唛!B11"),
        _item("77770GQ2", "箱唛!D11"),
        _item("50PCS", "箱唛!D14"),
        _item("ITEM NO.", "箱唛!B21"),
        _item("77770GQ2", "箱唛!D21"),
        _item("50PCS", "箱唛!D24"),
    ]
    pdf = [
        _item("ITEM NO.: 77770GQ2", "第 1 页 · 正唛 · 第 1 行"),
        _item("50PCS", "第 1 页 · 正唛 · 第 2 行"),
        _item("ITEM NO.: 77770GQ2", "第 1 页 · 侧唛 · 第 1 行"),
        _item("50PCS", "第 1 页 · 侧唛 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    locations = [item.location for item in result.excel_items]
    assert "箱唛!A7" not in locations
    assert locations.count("箱唛!D11") == 1
    assert locations.count("箱唛!D21") == 1


def test_scope_does_not_drop_symmetric_repetitions_across_two_columns():
    excel = [
        _item("ITEM NO.", "箱唛!B1"),
        _item("ABC-900", "箱唛!A1"),
        _item("ITEM NO.", "箱唛!B2"),
        _item("ABC-900", "箱唛!A2"),
        _item("ITEM NO.", "箱唛!C3"),
        _item("ABC-900", "箱唛!D3"),
        _item("ITEM NO.", "箱唛!C4"),
        _item("ABC-900", "箱唛!D4"),
    ]
    pdf = [
        _item("ITEM NO. ABC-900", f"第 {page} 页 · 第 1 行")
        for page in range(1, 5)
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert sum(item.text == "ABC-900" for item in result.excel_items) == 4


def test_scope_does_not_treat_a_third_labelled_item_as_selector():
    excel = [
        _item("ITEM NO.", "箱唛!B1"),
        _item("ABC-900", "箱唛!A1"),
        _item("ITEM NO.", "箱唛!C2"),
        _item("ABC-900", "箱唛!D2"),
        _item("ITEM NO.", "箱唛!C3"),
        _item("ABC-900", "箱唛!D3"),
    ]
    pdf = [
        _item("ITEM NO. ABC-900", f"第 {page} 页 · 第 1 行")
        for page in range(1, 4)
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert sum(item.text == "ABC-900" for item in result.excel_items) == 3


def test_scope_expands_through_consecutive_pdf_supported_template_rows():
    excel = [
        _item("ITEM", "箱唛!A1"),
        _item("ABC-900", "箱唛!B1"),
        _item("G.W.", "箱唛!A2"),
        _item("5.93 KGS", "箱唛!B2"),
        _item("MEASUREMENT", "箱唛!A3"),
        _item("56.5", "箱唛!B3"),
        _item("x", "箱唛!C3"),
        _item("31.4", "箱唛!D3"),
        _item("x", "箱唛!E3"),
        _item("63.5", "箱唛!F3"),
        _item("CM", "箱唛!G3"),
        _item("MADE IN CHINA", "箱唛!A4"),
        _item("source-only helper", "箱唛!A5"),
    ]
    pdf = [
        _item("ITEM ABC-900", "第 1 页 · 第 1 行"),
        _item("G.W. 5.93 KGS", "第 1 页 · 第 2 行"),
        _item("MEASUREMENT 56.5 x 31.4 x 63.5 CM", "第 1 页 · 第 3 行"),
        _item("MADE IN CHINA", "第 1 页 · 第 4 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    values = {item.text for item in result.excel_items}

    assert {"5.93 KGS", "56.5", "31.4", "63.5", "MADE IN CHINA"} <= values
    assert "source-only helper" not in values


def test_scope_keeps_separate_fully_supported_static_template_section():
    excel = [
        _item("NAME OF SUPPLIER", "箱唛!A1"),
        _item("ZURU.INC", "箱唛!B1"),
        _item("helper selector", "箱唛!A8"),
        _item("Customer PO", "箱唛!A10"),
        _item("ITEM", "箱唛!B10"),
        _item("DESCRIPTION", "箱唛!C10"),
        _item("QTY", "箱唛!D10"),
        _item("NO CARTONS", "箱唛!E10"),
        _item("source only", "箱唛!A11"),
        _item("ABC-900", "箱唛!B11"),
        _item("WALKING PUPPY", "箱唛!C11"),
        _item("6", "箱唛!D11"),
        _item("100", "箱唛!E11"),
        _item("source only", "箱唛!A12"),
        _item("ABC-901", "箱唛!B12"),
        _item("WALKING PUPPY BLUE", "箱唛!C12"),
        _item("12", "箱唛!D12"),
        _item("200", "箱唛!E12"),
    ]
    pdf = [
        _item("NAME OF SUPPLIER: ZURU.INC", "第 1 页 · 第 1 行"),
        _item("ITEM: ABC-900", "第 1 页 · 第 2 行"),
        _item("DESCRIPTION: WALKING PUPPY", "第 1 页 · 第 3 行"),
        _item("QTY: 6 PCS / 100 CTNS", "第 1 页 · 第 4 行"),
        _item("ITEM: ABC-901", "第 2 页 · 第 2 行"),
        _item("DESCRIPTION: WALKING PUPPY BLUE", "第 2 页 · 第 3 行"),
        _item("QTY: 12 PCS / 200 CTNS", "第 2 页 · 第 4 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    values = {item.text for item in result.excel_items}

    assert {
        "NAME OF SUPPLIER",
        "ZURU.INC",
        "ABC-900",
        "ABC-901",
        "WALKING PUPPY",
        "WALKING PUPPY BLUE",
    } <= values
    assert "helper selector" not in values
    assert "source only" not in values


def test_scope_keeps_adjacent_critical_row_when_entire_pdf_field_is_missing():
    excel = [
        _item("ITEM", "箱唛!A1"),
        _item("ABC-900", "箱唛!B1"),
        _item("GROSS WEIGHT", "箱唛!A2"),
        _item("5.93 KGS", "箱唛!B2"),
        _item("MEASUREMENT", "箱唛!A3"),
        _item("56.5 x 31.4 x 63.5 CM", "箱唛!B3"),
        _item("source helper", "箱唛!A4"),
    ]
    pdf = [_item("ITEM ABC-900", "第 1 页 · 第 1 行")]

    result = prepare_carton_mark_document_scope(excel, pdf)
    values = {item.text for item in result.excel_items}

    assert {"5.93 KGS", "56.5 x 31.4 x 63.5 CM"} <= values
    assert "source helper" not in values


def test_scope_wide_table_missing_item_column_is_not_silently_dropped():
    excel = [
        _item("ITEM", "数据!A1"),
        _item("DESCRIPTION", "数据!B1"),
        _item("QTY", "数据!C1"),
        _item("CARTON NO", "数据!D1"),
        _item("ABC-900", "数据!A2"),
        _item("WALKING PUPPY", "数据!B2"),
        _item("6", "数据!C2"),
        _item("100", "数据!D2"),
    ]
    pdf = [
        _item("DESCRIPTION WALKING PUPPY", "第 1 页 · 第 1 行"),
        _item("QTY 6 PCS", "第 1 页 · 第 2 行"),
        _item("CARTON NO / 100", "第 1 页 · 第 3 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    by_location = {item.location: item for item in result.excel_items}

    assert by_location["数据!A2"].text == "ABC-900"
    assert by_location["数据!A2"].field_key == "item"
    assert by_location["数据!C2"].field_key == "quantity"
    assert by_location["数据!D2"].field_key == "carton_no"


def test_scope_does_not_drop_item_contained_in_barcode_on_same_row():
    excel = [
        _item("ITEM", "数据!A1"),
        _item("DESCRIPTION", "数据!B1"),
        _item("BARCODE", "数据!C1"),
        _item("ABC123", "数据!A2"),
        _item("WALKING PUPPY", "数据!B2"),
        _item("ABC123456789", "数据!C2"),
    ]
    pdf = [
        _item("DESCRIPTION WALKING PUPPY", "第 1 页 · 第 1 行"),
        _item("BARCODE ABC123456789", "第 1 页 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    by_location = {item.location: item for item in result.excel_items}

    assert by_location["数据!A2"].text == "ABC123"
    assert by_location["数据!A2"].field_key == "item"
    assert by_location["数据!C2"].field_key == "barcode"


def test_scope_uncertain_selector_is_preserved_and_forces_review():
    excel = [
        _item("ITEM NO.", "箱唛!B6"),
        _item("ABC-900", "箱唛!A7"),
        _item("ITEM NO.", "箱唛!B11"),
        _item("ABC-900", "箱唛!D11"),
        _item("ITEM NO.", "箱唛!B21"),
        _item("ABC-900", "箱唛!D21"),
    ]
    pdf = [
        _item("ITEM NO. ABC-900", "第 1 页 · 第 1 行"),
        _item("ITEM NO. ABC-900", "第 2 页 · 第 1 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)

    assert "箱唛!A7" in {item.location for item in result.excel_items}
    assert result.requires_review


def test_scope_template_rows_assign_fields_by_label_not_physical_column():
    excel = [
        _item("FTC", "SM!A34"),
        _item("/ Order #", "SM!E34"),
        _item("ARTICLE Number:", "SM!K34"),
        _item("7044498", "SM!M34"),
        _item("4504244551", "SM!E35"),
        _item("/", "SM!D35"),
        _item("ARTICLE - Quantity:", "SM!K35"),
        _item("8 PCS", "SM!M35"),
        _item("ARTICLE Number:", "SM!A36"),
        _item("7044498", "SM!C36"),
        _item("Gross Weight:", "SM!K36"),
        _item("2.800", "SM!M36"),
        _item("KGS", "SM!N36"),
        _item("ARTICLE - Quantity:", "SM!A37"),
        _item("8 PCS", "SM!C37"),
        _item("Measurement:", "SM!K37"),
        _item("29.0 x 21.0 x 31.0 cm", "SM!M37"),
        _item("Carton number:", "SM!A38"),
        _item("of 120", "SM!C38"),
        _item("Barcode Number:", "SM!K38"),
        _item("193052090409", "SM!M38"),
    ]
    pdf = [
        _item("FTC / Order # 4504244551", "第 1 页 · 第 1 行"),
        _item("ARTICLE Number: 7044498", "第 1 页 · 第 2 行"),
        _item("ARTICLE - Quantity: 8 PCS", "第 1 页 · 第 3 行"),
        _item("Gross Weight: 2.800 KGS", "第 1 页 · 第 4 行"),
        _item("Measurement: 29.0 x 21.0 x 31.0 cm", "第 1 页 · 第 5 行"),
        _item("Carton number: of 120", "第 1 页 · 第 6 行"),
        _item("Barcode Number: 193052090409", "第 1 页 · 第 7 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    fields = {item.location: item.field_key for item in result.excel_items}

    assert fields["SM!A34"] == ""
    assert "SM!D35" not in fields
    assert fields["SM!E34"] == fields["SM!E35"] == "po"
    assert fields["SM!K34"] == fields["SM!M34"] == "item"
    assert fields["SM!K35"] == fields["SM!M35"] == "quantity"
    assert fields["SM!A36"] == fields["SM!C36"] == "item"
    assert {fields[cell] for cell in ("SM!K36", "SM!M36", "SM!N36")} == {
        "gross_weight"
    }
    assert fields["SM!A37"] == fields["SM!C37"] == "quantity"
    assert fields["SM!K37"] == fields["SM!M37"] == "measurement"
    assert fields["SM!A38"] == fields["SM!C38"] == "carton_no"
    assert fields["SM!K38"] == fields["SM!M38"] == "barcode"


def test_scope_distinguishes_ctn_qty_from_ctn_number():
    excel = [
        _item("ITEM NO.", "箱唛!B1"),
        _item("77770GQ2", "箱唛!D1"),
        _item("CTN QTY:", "箱唛!B2"),
        _item("50PCS", "箱唛!D2"),
        _item("CTN NUMBER:", "箱唛!B3"),
        _item("49 CTNS", "箱唛!D3"),
    ]
    pdf = [
        _item("ITEM NO. 77770GQ2", "第 1 页 · 第 1 行"),
        _item("CTN QTY: 50PCS", "第 1 页 · 第 2 行"),
        _item("CTN NUMBER: 49 CTNS", "第 1 页 · 第 3 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    fields = {item.location: item.field_key for item in result.excel_items}

    assert fields["箱唛!B2"] == fields["箱唛!D2"] == "quantity"
    assert fields["箱唛!B3"] == fields["箱唛!D3"] == "carton_no"


def test_scope_split_carton_no_of_label_assigns_bare_value():
    excel = [
        _item("ITEM NO.", "箱唛!A1"),
        _item("ABC-900", "箱唛!B1"),
        _item("Carton No. of", "箱唛!A2"),
        _item("5", "箱唛!B2"),
    ]
    pdf = [
        _item("ITEM NO. ABC-900", "第 1 页 · 第 1 行"),
        _item("Carton No. of 5", "第 1 页 · 第 2 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    fields = {item.location: item.field_key for item in result.excel_items}

    assert fields["箱唛!A2"] == fields["箱唛!B2"] == "carton_no"


def test_scope_qty_and_carton_size_rows_propagate_field_identity():
    excel = [
        _item("Item No.", "箱唛!D1"),
        _item("ABC-900", "箱唛!E1"),
        _item("Qty/Ctn:", "箱唛!D2"),
        _item("12", "箱唛!E2"),
        _item("PCS", "箱唛!F2"),
        _item("Carton Size(cm):", "箱唛!D3"),
        _item("45.10", "箱唛!E3"),
        _item("X", "箱唛!F3"),
        _item("23.20", "箱唛!G3"),
        _item("X", "箱唛!H3"),
        _item("40.30", "箱唛!I3"),
        _item("CM", "箱唛!J3"),
    ]
    pdf = [
        _item("Item No. ABC-900", "第 1 页 · 第 1 行"),
        _item("Qty/Ctn: 12 PCS", "第 1 页 · 第 2 行"),
        _item("Carton Size(cm): 45.10 X 23.20 X 40.30 CM", "第 1 页 · 第 3 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    fields = {item.location: item.field_key for item in result.excel_items}

    assert {fields[cell] for cell in ("箱唛!D2", "箱唛!E2", "箱唛!F2")} == {
        "quantity"
    }
    assert {
        fields[cell]
        for cell in (
            "箱唛!D3", "箱唛!E3", "箱唛!F3", "箱唛!G3",
            "箱唛!H3", "箱唛!I3", "箱唛!J3",
        )
    } == {"measurement"}


def test_scope_adjacent_label_inheritance_stops_at_next_static_field():
    excel = [
        _item("ITEM", "箱唛!A1"),
        _item("ABC-900", "箱唛!B1"),
        _item("NUMBER OF PIECES", "箱唛!A2"),
        _item("12 PCS", "箱唛!B2"),
        _item("MADE IN CHINA", "箱唛!A3"),
        _item("Barcode", "箱唛!A4"),
        _item("193052090409", "箱唛!B4"),
        _item("Brand", "箱唛!A5"),
        _item("ZURU", "箱唛!B5"),
    ]
    pdf = [
        _item("ITEM ABC-900", "第 1 页 · 第 1 行"),
        _item("NUMBER OF PIECES 12 PCS", "第 1 页 · 第 2 行"),
        _item("MADE IN CHINA", "第 1 页 · 第 3 行"),
        _item("Barcode 193052090409", "第 1 页 · 第 4 行"),
        _item("Brand ZURU", "第 1 页 · 第 5 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    fields = {item.location: item.field_key for item in result.excel_items}

    assert fields["箱唛!A3"] == ""
    assert fields["箱唛!A5"] == fields["箱唛!B5"] == ""


def test_scope_combined_fields_identify_dimension_description_po_and_item():
    excel = [
        _item("45.10 X 23.20 X 40.30 CMS", "箱唛!B1"),
        _item("ITEM DESCRIPTION: FUGGLER BADDIE", "箱唛!D2"),
        _item("PO NUMBER: 484860", "箱唛!D3"),
        _item("ZUMIEZ ITEM NO.: 415647", "箱唛!D4"),
    ]
    pdf = [
        _item("45.10 X 23.20 X 40.30 CMS", "第 1 页 · 第 1 行"),
        _item("ITEM DESCRIPTION: FUGGLER BADDIE", "第 1 页 · 第 2 行"),
        _item("PO NUMBER: 484860", "第 1 页 · 第 3 行"),
        _item("ZUMIEZ ITEM NO.: 415647", "第 1 页 · 第 4 行"),
    ]

    result = prepare_carton_mark_document_scope(excel, pdf)
    fields = {item.location: item.field_key for item in result.excel_items}

    assert fields["箱唛!B1"] == "measurement"
    assert fields["箱唛!D2"] == "description"
    assert fields["箱唛!D3"] == "po"
    assert fields["箱唛!D4"] == "item"
