from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from app.schemas.carton_mark import CartonMarkDocumentTextItem


_EXCEL_CELL_RE = re.compile(
    r"^\$?(?P<column>[A-Z]{1,4})\$?(?P<row>\d+)$",
    re.IGNORECASE,
)
_EXCEL_ERROR_RE = re.compile(
    r"^#(?:N/A|REF!?|VALUE!?|DIV/0!?|NAME\??|NULL!?|NUM!?|SPILL!?|CALC!?|"
    r"GETTING_DATA|FIELD!?|BLOCKED!?|CONNECT!?|UNKNOWN!?)$",
    re.IGNORECASE,
)
_SAFE_LAYOUT_SEPARATORS = str.maketrans({
    ":": "",
    "：": "",
    "|": "",
    "｜": "",
    "·": "",
    "•": "",
    "‧": "",
    "_": "",
})
_GENERIC_ANCHORS = {
    "PO",
    "PONO",
    "PURCHASEORDER",
    "ITEM",
    "ITEMNO",
    "STYLE",
    "STYLENO",
    "SKU",
    "SKUNO",
    "QTY",
    "QUANTITY",
    "PCPERCARTON",
    "NOCARTONS",
    "PCS",
    "CTN",
    "CTNS",
    "DESCRIPTION",
    "GROSSWEIGHT",
    "NETWEIGHT",
    "MEASUREMENT",
    "MADEINCHINA",
    "CUSTOMER",
    "CUSTOMERNAME",
    "ARTICLENO",
    "ARTICLENUMBER",
    "ARTICLEQUANTITY",
    "BARCODE",
    "BARCODENO",
    "BARCODENUMBER",
    "BRAND",
    "CARTONCBM",
    "CARTONGROSSWEIGHT",
    "CARTONNETWEIGHT",
    "CARTONNO",
    "CARTONNUMBER",
    "CARTONQTY",
    "CARTONSIZE",
    "CARTONSIZE(CM)",
    "COUNTRYOFORIGIN",
    "DEPTNO",
    "FTYPO",
    "FRONTMARK",
    "G.RW",
    "GRSWT",
    "GTIN",
    "ITEMDESCRIPTION",
    "ITEMNUMBER",
    "LOINO",
    "NAMEOFSUPPLIER",
    "NETWT",
    "NUMBEROFPIECES",
    "ORDERNO",
    "PINO",
    "PRODUCTDESCRIPTION",
    "PURCHASEORDERNO",
    "QUANTITYPERCTN",
    "SUPPLIER",
    "SIDEMARK",
    "WGR",
    "WNET",
}
_NARRATIVE_PREFIXES = (
    "NOTE",
    "NOTES",
    "REMARK",
    "REMARKS",
    "INSTRUCTION",
    "INSTRUCTIONS",
    "说明",
    "备注",
    "制作说明",
    "注意",
    "数据引用",
)

# Headers used to retain a value which is deliberately blank in the PDF.  This
# matters for the central use-case: an identifier on the same wide source-data
# row proves which item it is, while the missing G.W./N.W./measurement values are
# precisely the differences that must remain visible to the comparison engine.
_PRINT_FIELD_HEADER_PARTS = (
    "PO",
    "PURCHASEORDER",
    "ORDERNO",
    "PI",
    "PINO",
    "ITEM",
    "ARTICLE",
    "STYLE",
    "SKU",
    "DESCRIPTION",
    "QTY",
    "QUANTITY",
    "PCPERCARTON",
    "NOCARTONS",
    "CARTONNO",
    "CARTONNUMBER",
    "CARTONQTY",
    "GROSSWEIGHT",
    "NETWEIGHT",
    "GRSWT",
    "WGR",
    "WNET",
    "MEASUREMENT",
    "DIMENSION",
    "CARTONSIZE",
    "BARCODE",
    "GTIN",
)


@dataclass(frozen=True)
class CartonMarkDocumentScopeDiagnostics:
    excel_input_count: int
    excel_usable_count: int
    excel_selected_count: int
    excel_output_count: int
    pdf_input_count: int
    pdf_cleaned_count: int
    pdf_output_count: int
    ignored_excel_error_count: int
    expected_duplicate_count: int
    actual_duplicate_count: int
    candidate_row_count: int
    selected_row_count: int
    selected_sheet_count: int
    strong_anchor_count: int
    selected_sheets: tuple[str, ...]

    def describe(self) -> str:
        """Return a compact audit trail suitable for an extraction status message."""

        selected = "、".join(self.selected_sheets) if self.selected_sheets else "无可靠选区"
        return (
            f"Excel 抽取 {self.excel_input_count} 项，忽略模板错误 "
            f"{self.ignored_excel_error_count} 项，正文选中 {self.excel_selected_count} 项，"
            f"位置内去重后 {self.excel_output_count} 项；PDF 抽取 {self.pdf_input_count} 项，"
            f"清洗后 {self.pdf_cleaned_count} 项，位置内去重后 {self.pdf_output_count} 项；"
            f"选区：{selected}。"
        )


@dataclass(frozen=True)
class CartonMarkDocumentScopeResult:
    """Pure comparison-scope result; callers decide how to render review evidence."""

    excel_items: list[CartonMarkDocumentTextItem]
    pdf_items: list[CartonMarkDocumentTextItem]
    requires_review: bool
    confidence: float
    review_note: str
    diagnostics: CartonMarkDocumentScopeDiagnostics


@dataclass(frozen=True)
class _ExcelRow:
    sheet: str
    row: str
    order: int
    items: tuple[CartonMarkDocumentTextItem, ...]
    keys: tuple[str, ...]
    matched_indexes: tuple[int, ...]
    anchor_indexes: tuple[int, ...]
    candidate: bool
    precision: float
    has_instruction: bool


@dataclass(frozen=True)
class _SheetCandidate:
    name: str
    order: int
    rows: tuple[_ExcelRow, ...]
    anchors: frozenset[str]
    score: float
    precision: float


@dataclass(frozen=True)
class _RowCluster:
    rows: tuple[_ExcelRow, ...]
    anchors: frozenset[str]
    score: float


def clean_pdf_document_text(value: str) -> str:
    """Remove PDF extraction artefacts while preserving business punctuation.

    Controls, replacement glyphs, private-use font codes and Unicode line/paragraph
    separators become spaces.  Hyphens, slashes, decimal points, currency signs,
    copyright marks and ordinary punctuation are intentionally retained.
    """

    cleaned: list[str] = []
    for character in str(value or ""):
        category = unicodedata.category(character)
        if (
            character in {"\ufffd", "\ufffc", "\ufeff", "\u00ad"}
            or category in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}
        ):
            cleaned.append(" ")
            continue
        cleaned.append(character)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def clean_pdf_document_items(
    items: Iterable[CartonMarkDocumentTextItem],
) -> list[CartonMarkDocumentTextItem]:
    """Return cleaned non-empty PDF items without mutating extraction results."""

    cleaned: list[CartonMarkDocumentTextItem] = []
    for item in items:
        text = clean_pdf_document_text(item.text)
        if not _semantic_key(text):
            continue
        cleaned.append(CartonMarkDocumentTextItem(
            text=text,
            location=item.location,
            field_key=item.field_key,
        ))
    return cleaned


def prepare_carton_mark_document_scope(
    excel_items: list[CartonMarkDocumentTextItem],
    pdf_items: list[CartonMarkDocumentTextItem],
) -> CartonMarkDocumentScopeResult:
    """Select reliable Excel body rows and clean both comparison sides.

    Selection is evidence-based: exact, meaningful Excel values must occur in the
    PDF text.  Once a row is selected, *all* usable cells on that row are retained,
    including unmatched weights, dimensions or quantities.  The PDF side is never
    scoped to matched text, so genuine additions remain available to the existing
    comparison engine as unexpected residuals.
    """

    original_excel = list(excel_items)
    original_pdf = list(pdf_items)
    usable_excel, ignored_errors = _usable_excel_items(original_excel)
    cleaned_pdf = clean_pdf_document_items(original_pdf)
    deduped_pdf, actual_duplicates = _location_deduplicate(cleaned_pdf)

    if not usable_excel or not deduped_pdf:
        fallback_excel, expected_duplicates = _location_deduplicate(usable_excel)
        note = (
            "Excel 没有可用正文文字，无法建立可靠核对选区，请人工复核。"
            if not usable_excel
            else "PDF 清洗后没有可用文字，无法建立可靠核对选区，请人工复核。"
        )
        diagnostics = _diagnostics(
            original_excel=original_excel,
            usable_excel=usable_excel,
            selected_excel=usable_excel,
            output_excel=fallback_excel,
            original_pdf=original_pdf,
            cleaned_pdf=cleaned_pdf,
            output_pdf=deduped_pdf,
            ignored_errors=ignored_errors,
            expected_duplicates=expected_duplicates,
            actual_duplicates=actual_duplicates,
            rows=[],
            selected_rows=[],
            selected_sheets=[],
            strong_anchor_count=0,
        )
        return CartonMarkDocumentScopeResult(
            excel_items=fallback_excel,
            pdf_items=deduped_pdf,
            requires_review=True,
            confidence=0.0,
            review_note=f"{note} {diagnostics.describe()}",
            diagnostics=diagnostics,
        )

    page_keys = _pdf_page_keys(deduped_pdf)
    rows = _build_excel_rows(usable_excel, page_keys)
    sheets = _build_sheet_candidates(rows)
    selected_sheets, ambiguous = _select_sheets(sheets)
    selected_sheet_names = {sheet.name for sheet in selected_sheets}
    sheet_rows = [
        row
        for row in rows
        if row.candidate and row.sheet in selected_sheet_names
    ]
    selected_rows, selector_ambiguous = _select_body_rows(
        sheet_rows,
        all_rows=rows,
    )
    selected_rows = _include_adjacent_static_rows(rows, selected_rows, page_keys)
    ambiguous = (
        ambiguous
        or selector_ambiguous
        or _has_explicit_unmatched_item_blocks(
            usable_excel,
            selected_sheet_names,
            page_keys,
        )
    )
    relevant_columns, header_categories, header_ambiguous = _relevant_header_columns(
        usable_excel,
        page_keys,
        selected_sheet_names=selected_sheet_names,
    )
    ambiguous = ambiguous or header_ambiguous
    selected_excel = [
        _annotate_expected_item(
            item,
            row,
            header_categories.get(row.sheet, ()),
            selected_rows,
        )
        for row in selected_rows
        for item in _selected_row_items(row, relevant_columns.get(row.sheet, ()))
    ]

    # A tiny flat contract (for example three cells containing PO, ITEM and an
    # unmatched weight) has no need for layout inference.  Two exact identifiers
    # are sufficient evidence to keep the sibling value and compare it.
    if not selected_excel and len(usable_excel) <= 3:
        small_matches = [
            item
            for item in usable_excel
            if _is_strong_anchor(item.text, _semantic_key(item.text))
            and any(_semantic_key(item.text) in page for page in page_keys)
        ]
        if len(small_matches) >= 2:
            selected_excel = list(usable_excel)
            selected_rows = rows
            selected_sheets = sheets

    if not selected_excel:
        # Keep the usable Excel evidence in the result.  Returning an empty expected
        # side could otherwise turn a failed selection into an accidental pass.
        fallback_excel, expected_duplicates = _location_deduplicate(usable_excel)
        diagnostics = _diagnostics(
            original_excel=original_excel,
            usable_excel=usable_excel,
            selected_excel=usable_excel,
            output_excel=fallback_excel,
            original_pdf=original_pdf,
            cleaned_pdf=cleaned_pdf,
            output_pdf=deduped_pdf,
            ignored_errors=ignored_errors,
            expected_duplicates=expected_duplicates,
            actual_duplicates=actual_duplicates,
            rows=rows,
            selected_rows=[],
            selected_sheets=[],
            strong_anchor_count=0,
        )
        note = "未找到同时具备强匹配锚点和足够正文密度的 Excel 行，请人工选择箱唛正文。"
        return CartonMarkDocumentScopeResult(
            excel_items=fallback_excel,
            pdf_items=deduped_pdf,
            requires_review=True,
            confidence=0.0,
            review_note=f"{note} {diagnostics.describe()}",
            diagnostics=diagnostics,
        )

    output_excel, expected_duplicates = _location_deduplicate(selected_excel)
    selected_anchors = {
        row.keys[index]
        for row in selected_rows
        for index in row.anchor_indexes
    }
    all_candidate_anchors = {
        row.keys[index]
        for row in rows
        if row.candidate
        for index in row.anchor_indexes
    }
    selected_signal_count = sum(
        _is_signal_key(key)
        for row in selected_rows
        for key in row.keys
    )
    selected_match_count = sum(
        _is_signal_key(row.keys[index])
        for row in selected_rows
        for index in row.matched_indexes
    )
    precision = selected_match_count / max(1, selected_signal_count)
    recall = len(selected_anchors) / max(1, len(all_candidate_anchors))
    anchor_strength = min(1.0, len(selected_anchors) / 3)
    confidence = round(min(1.0, 0.40 * precision + 0.35 * recall + 0.25 * anchor_strength), 3)
    small_unambiguous_document = (
        len(usable_excel) <= 3
        and len(selected_anchors) >= 1
        and precision >= 0.65
    )
    reliable = (
        not ambiguous
        and precision >= 0.45
        and (len(selected_anchors) >= 2 or small_unambiguous_document)
        and confidence >= 0.60
    )

    diagnostics = _diagnostics(
        original_excel=original_excel,
        usable_excel=usable_excel,
        selected_excel=selected_excel,
        output_excel=output_excel,
        original_pdf=original_pdf,
        cleaned_pdf=cleaned_pdf,
        output_pdf=deduped_pdf,
        ignored_errors=ignored_errors,
        expected_duplicates=expected_duplicates,
        actual_duplicates=actual_duplicates,
        rows=rows,
        selected_rows=selected_rows,
        selected_sheets=selected_sheets,
        strong_anchor_count=len(selected_anchors),
    )
    review_reasons: list[str] = []
    if ambiguous:
        review_reasons.append("有多个得分接近但内容不同的 Excel 候选区")
    if len(selected_anchors) < 2 and not small_unambiguous_document:
        review_reasons.append("强匹配锚点不足 2 个")
    if precision < 0.45:
        review_reasons.append("候选行中未匹配文字比例过高")
    if confidence < 0.60:
        review_reasons.append("正文选区置信度偏低")
    review_note = ""
    if not reliable:
        reason = "；".join(review_reasons) or "正文选区证据不足"
        review_note = f"{reason}，本次结果必须人工复核。 {diagnostics.describe()}"

    return CartonMarkDocumentScopeResult(
        excel_items=output_excel,
        pdf_items=deduped_pdf,
        requires_review=not reliable,
        confidence=confidence,
        review_note=review_note,
        diagnostics=diagnostics,
    )


def _usable_excel_items(
    items: list[CartonMarkDocumentTextItem],
) -> tuple[list[CartonMarkDocumentTextItem], int]:
    usable: list[CartonMarkDocumentTextItem] = []
    ignored = 0
    for item in items:
        text = str(item.text or "").strip()
        compact = re.sub(r"\s+", "", text)
        if _EXCEL_ERROR_RE.fullmatch(compact):
            ignored += 1
            continue
        if not _semantic_key(text):
            continue
        usable.append(CartonMarkDocumentTextItem(
            text=text,
            location=item.location,
            field_key=item.field_key,
        ))
    return usable, ignored


def _semantic_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).translate(
        _SAFE_LAYOUT_SEPARATORS
    ).casefold().upper()
    values: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace() or category in {"Cc", "Cf", "Cs", "Co", "Cn"}:
            continue
        values.append(character)
    return "".join(values)


def _location_deduplicate(
    items: Iterable[CartonMarkDocumentTextItem],
) -> tuple[list[CartonMarkDocumentTextItem], int]:
    """Remove duplicate extraction artefacts only at the same source position.

    A repeated value on another Excel row or another PDF page is a separate
    business occurrence.  Global value de-duplication used to hide missing fields
    in multi-item contracts, so the location is deliberately part of the key.
    """

    output: list[CartonMarkDocumentTextItem] = []
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for item in items:
        key = _semantic_key(item.text)
        if not key:
            continue
        signature = (str(item.location or ""), key)
        if signature in seen:
            duplicate_count += 1
            continue
        seen.add(signature)
        output.append(item)
    return output, duplicate_count


def _pdf_page_keys(items: list[CartonMarkDocumentTextItem]) -> tuple[str, ...]:
    pages: dict[str, list[str]] = {}
    for item in items:
        page = item.location.split(" · ", 1)[0]
        pages.setdefault(page, []).append(_semantic_key(item.text))
    return tuple("".join(values) for values in pages.values() if any(values))


def _excel_group(location: str, fallback_index: int) -> tuple[str, str]:
    if "!" in location:
        sheet, cell = location.rsplit("!", 1)
        match = _EXCEL_CELL_RE.fullmatch(cell.strip())
        if match:
            return sheet.strip() or "未命名工作表", match.group("row")
    return "未识别位置", f"item-{fallback_index}"


def _excel_position(location: str) -> tuple[str, str, str] | None:
    if "!" not in location:
        return None
    sheet, cell = location.rsplit("!", 1)
    match = _EXCEL_CELL_RE.fullmatch(cell.strip())
    if not match:
        return None
    return (
        sheet.strip() or "未命名工作表",
        match.group("column").upper(),
        match.group("row"),
    )


def _relevant_header_columns(
    items: list[CartonMarkDocumentTextItem],
    page_keys: tuple[str, ...],
    *,
    selected_sheet_names: set[str] | None = None,
) -> tuple[
    dict[str, tuple[tuple[int, frozenset[str]], ...]],
    dict[str, tuple[tuple[int, dict[str, str]], ...]],
    bool,
]:
    """Find source-table columns whose field label is present in the PDF body.

    A customer workbook may carry source-only columns such as ``Customer PO#``.
    Merely recognising that as a carton-related header is not enough: if no PO
    label is printed in the scoped PDF body, its repeated values must not become
    false missing items.  Alias groups still retain blank-but-required fields
    such as G.W./N.W./measurement when the PDF contains their labels.
    """

    by_sheet_row: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for item in items:
        position = _excel_position(item.location)
        if position is None:
            continue
        sheet, column, row = position
        if selected_sheet_names is not None and sheet not in selected_sheet_names:
            continue
        if not row.isdigit():
            continue
        by_sheet_row.setdefault((sheet, int(row)), []).append((column, item.text))

    recognised_rows: dict[
        tuple[str, int],
        list[tuple[str, str, str]],
    ] = {}
    for (sheet, row_number), values in by_sheet_row.items():
        recognised = []
        for column, value in values:
            header = _semantic_key(value)
            category = _print_header_category(header)
            if category:
                recognised.append((column, header, category))
        # Repeated templates above a source table often use the same physical
        # columns for unrelated labels.  Treat only a row with several field
        # headings as a table header, then apply it to the following data rows.
        recognised_categories = {category for _column, _header, category in recognised}
        recognised_columns = {column for column, _header, _category in recognised}
        has_embedded_business_value = any(
            column not in recognised_columns
            and any(character.isdigit() for character in _semantic_key(value))
            and _is_strong_anchor(value, _semantic_key(value))
            for column, value in values
        )
        if (
            len(recognised) >= 3
            and len(recognised_categories) >= 3
            and not has_embedded_business_value
        ):
            recognised_rows[(sheet, row_number)] = recognised

    result: dict[str, list[tuple[int, frozenset[str]]]] = {}
    category_result: dict[str, list[tuple[int, dict[str, str]]]] = {}
    ambiguous = False
    for (sheet, row_number), recognised in recognised_rows.items():
        next_header_row = min(
            (
                other_row
                for other_sheet, other_row in recognised_rows
                if other_sheet == sheet and other_row > row_number
            ),
            default=10**9,
        )
        evidence_columns = {
            column
            for column, header, _category in recognised
            if _print_header_is_in_pdf(header, page_keys)
            or _column_has_pdf_value(
                items,
                sheet=sheet,
                column=column,
                first_row=row_number + 1,
                last_row=next_header_row - 1,
                page_keys=page_keys,
            )
        }
        category_columns: dict[str, list[str]] = {}
        for column, _header, category in recognised:
            category_columns.setdefault(category, []).append(column)

        core_categories = {
            category
            for category in category_columns
            if category in _REQUIRED_PRINT_TABLE_CATEGORIES
        }
        evidenced_categories = {
            category
            for column, _header, category in recognised
            if column in evidence_columns
        }
        table_proven = (
            len(core_categories) >= 3
            and len(evidenced_categories & core_categories) >= 2
        ) or (
            len(core_categories) >= 2
            and bool(core_categories & {"item", "description", "barcode"})
            and bool(evidenced_categories & core_categories)
        )

        columns = set(evidence_columns)
        for category, category_values in category_columns.items():
            missing_columns = [
                column for column in category_values if column not in evidence_columns
            ]
            if not missing_columns:
                continue
            if category in _SOURCE_ONLY_WITHOUT_PDF_EVIDENCE:
                # "Customer PO" and bare PI columns are common planning/source
                # selectors.  They only become printable evidence when their label
                # or value is actually present in the PDF.
                continue
            if category not in _REQUIRED_PRINT_TABLE_CATEGORIES:
                continue
            if table_proven and len(category_values) == 1:
                # A proven carton-mark table must not silently lose an entire
                # ITEM/QTY/CTN/BARCODE/PO column merely because the PDF omitted
                # both its label and value -- that omission is the defect.
                columns.update(missing_columns)
            else:
                # Multiple columns claim the same role (or the table itself is not
                # proven).  Retaining one arbitrarily risks comparing an internal
                # code; dropping all risks a false pass.  Keep direct evidence and
                # force a human review.
                ambiguous = True

        if columns:
            result.setdefault(sheet, []).append((row_number, frozenset(columns)))
            category_result.setdefault(sheet, []).append((
                row_number,
                {
                    column: category
                    for column, _header, category in recognised
                    if column in columns
                },
            ))
    return ({
        sheet: tuple(sorted(sections, key=lambda section: section[0]))
        for sheet, sections in result.items()
    }, {
        sheet: tuple(sorted(sections, key=lambda section: section[0]))
        for sheet, sections in category_result.items()
    }, ambiguous)


def _is_print_field_header(key: str) -> bool:
    return bool(_print_header_category(key))


_REQUIRED_PRINT_TABLE_CATEGORIES = frozenset({
    "po",
    "order",
    "item",
    "description",
    "qty",
    "carton",
    "carton_qty",
    "gross_weight",
    "net_weight",
    "measurement",
    "barcode",
})
_SOURCE_ONLY_WITHOUT_PDF_EVIDENCE = frozenset({"customer_po", "pi"})
_FIELD_KEY_BY_CATEGORY = {
    "po": "po",
    "order": "po",
    "customer_po": "po",
    "pi": "pi_no",
    "item": "item",
    "description": "description",
    "qty": "quantity",
    "carton": "carton_no",
    "carton_qty": "quantity",
    "gross_weight": "gross_weight",
    "net_weight": "net_weight",
    "measurement": "measurement",
    "barcode": "barcode",
}


def _print_header_category(key: str) -> str:
    compact = re.sub(r"[^A-Z0-9]", "", key.replace(".", "").replace("#", ""))
    if not compact:
        return ""
    if compact.startswith("CUSTOMERPO"):
        return "customer_po"
    if compact in {"PI", "PINO", "PINUMBER"}:
        return "pi"
    if compact in {"PO", "PONO", "PONUMBER", "PURCHASEORDER", "PURCHASEORDERNO"}:
        return "po"
    if compact in {"ORDER", "ORDERNO", "ORDERNUMBER", "FTYPO"}:
        return "order"
    if compact in {"DESCRIPTION", "ITEMDESCRIPTION", "PRODUCTDESCRIPTION", "NEWDESCRIPTION"}:
        return "description"
    if compact in {
        "ITEM", "ITEMNO", "ITEMNUMBER",
        "ARTICLE", "ARTICLENO", "ARTICLENUMBER",
        "STYLE", "STYLENO", "STYLENUMBER",
        "SKU", "SKUNO", "SKUNUMBER",
    }:
        return "item"
    if compact in {
        "QTY", "QTYPCS", "QTYCTN", "QTYPERCTN", "QTYCARTON",
        "QUANTITY", "ARTICLEQUANTITY", "ITEMQUANTITY", "PCPERCARTON",
        "QUANTITYPERCTN", "NUMBEROFPIECES",
    }:
        return "qty"
    if compact in {"CTNQTY", "CARTONQTY"}:
        return "carton_qty"
    if compact in {
        "NOCARTONS", "CARTONNO", "CARTONNOOF", "CARTONNUMBER",
        "CTNNO", "CTNNOOF", "CTNNUMBER",
    }:
        return "carton"
    if compact in {"GW", "GROSS", "GROSSWEIGHT", "GRSWT", "WGR", "CARTONGROSSWEIGHT"}:
        return "gross_weight"
    if compact in {"NW", "NET", "NETWT", "NETWEIGHT", "WNET", "CARTONNETWEIGHT"}:
        return "net_weight"
    if (
        compact in {"MEAS", "MEASUREMENT", "DIMENSION", "DIMENSIONS"}
        or (compact.startswith("CARTONSIZE") and not any(character.isdigit() for character in compact))
    ):
        return "measurement"
    if compact.startswith("BARCODE") or compact == "GTIN":
        return "barcode"
    return ""


def _column_has_pdf_value(
    items: list[CartonMarkDocumentTextItem],
    *,
    sheet: str,
    column: str,
    first_row: int,
    last_row: int,
    page_keys: tuple[str, ...],
) -> bool:
    for item in items:
        position = _excel_position(item.location)
        if position is None:
            continue
        item_sheet, item_column, item_row = position
        if (
            item_sheet != sheet
            or item_column != column
            or not item_row.isdigit()
            or not first_row <= int(item_row) <= last_row
        ):
            continue
        key = _semantic_key(item.text)
        if _is_signal_key(key) and any(key in page for page in page_keys):
            same_row_values = [
                _semantic_key(other.text)
                for other in items
                if (
                    (other_position := _excel_position(other.location)) is not None
                    and other_position[0] == sheet
                    and other_position[2] == item_row
                    and other_position[1] != column
                )
            ]
            if len(key) >= 6 and any(
                len(other_key) > len(key)
                and key in other_key
                and any(other_key in page for page in page_keys)
                for other_key in same_row_values
            ):
                continue
            return True
    return False


def _annotate_expected_item(
    item: CartonMarkDocumentTextItem,
    row: _ExcelRow,
    header_sections: tuple[tuple[int, dict[str, str]], ...],
    selected_rows: list[_ExcelRow],
) -> CartonMarkDocumentTextItem:
    """Attach a field identity without changing displayed text or location."""

    field_key = item.field_key
    position = _excel_position(item.location)
    if position is not None and row.row.isdigit():
        _sheet, column, row_value = position
        row_number = int(row_value)
        categories = next((
            mapping
            for header_row, mapping in reversed(header_sections)
            if header_row < row_number
        ), {})
        category = categories.get(column, "")
        if category:
            field_key = _FIELD_KEY_BY_CATEGORY.get(category, "")

    if not field_key:
        category = _row_item_category(item, row)
        field_key = _FIELD_KEY_BY_CATEGORY.get(category, "")
    if not field_key:
        category = _adjacent_column_category(item, row, selected_rows)
        field_key = _FIELD_KEY_BY_CATEGORY.get(category, "")
    if not field_key:
        return item
    return CartonMarkDocumentTextItem(
        text=item.text,
        location=item.location,
        field_key=field_key,
    )


def _adjacent_column_category(
    target: CartonMarkDocumentTextItem,
    row: _ExcelRow,
    selected_rows: list[_ExcelRow],
) -> str:
    """Inherit a narrow-template label only from the cell immediately above.

    Some printable layouts put ``/ Order #`` on one row and its value directly
    below it.  Requiring the same sheet, adjacent row and physical column keeps
    this useful inference away from wide data tables and unrelated nearby text.
    The source cell must itself be a pure recognised label; a value-bearing cell
    can therefore never leak its field identity into the following row.
    """

    position = _excel_position(target.location)
    if position is None or not row.row.isdigit():
        return ""
    target_key = _semantic_key(target.text)
    if _is_field_label_key(target_key) or _combined_value_category(target_key):
        # A labelled/static field on the next row starts a new contract line;
        # it is not the value belonging to the label above (for example
        # ``MADE IN CHINA`` after quantity or ``Brand`` after barcode).
        return ""
    sheet, column, row_value = position
    previous_number = int(row_value) - 1
    previous_row = next((
        candidate
        for candidate in selected_rows
        if (
            candidate.sheet == sheet
            and candidate.row.isdigit()
            and int(candidate.row) == previous_number
        )
    ), None)
    if previous_row is None:
        return ""
    previous_item = next((
        candidate
        for candidate in previous_row.items
        if (
            (candidate_position := _excel_position(candidate.location)) is not None
            and candidate_position[1] == column
        )
    ), None)
    if previous_item is None:
        return ""
    previous_key = _semantic_key(previous_item.text)
    category = _print_header_category(previous_key)
    # ``_print_header_category`` accepts only a label spelling, never a
    # value-bearing prefix.  It also handles layout punctuation such as the
    # leading slash in ``/ Order #`` which the broader label predicate keeps.
    if not category:
        return ""
    return _resolve_row_category(category, row)


def _row_item_category(
    target: CartonMarkDocumentTextItem,
    row: _ExcelRow,
) -> str:
    """Infer a narrow-template value field from a label on the same row."""

    target_index = next(
        (index for index, item in enumerate(row.items) if item is target),
        -1,
    )
    if target_index < 0:
        return ""
    labelled = [
        (index, _print_header_category(key))
        for index, key in enumerate(row.keys)
        if _print_header_category(key)
    ]
    if not labelled:
        # Self-contained cells such as "ITEM ABC-900" still carry useful type.
        return _combined_value_category(row.keys[target_index])
    preceding = [entry for entry in labelled if entry[0] <= target_index]
    if preceding:
        return _resolve_row_category(preceding[-1][1], row)
    # Cells before the first field label are unrelated static text, not values of
    # that later field (for example FTC/Dept/LOI before Order and Article).
    return ""


def _resolve_row_category(category: str, row: _ExcelRow) -> str:
    if category != "carton_qty":
        return category
    combined = " ".join(str(item.text or "").upper() for item in row.items)
    if re.search(r"\b(?:CTNS?|CARTONS?)\b", combined) and not re.search(
        r"(?:PCS|PIECES)\b",
        combined,
    ):
        return "carton"
    # In carton-mark templates CTN QTY followed by `50PCS` means pieces per
    # carton.  A repeated label whose formula cache is blank inherits this common
    # interpretation rather than becoming a carton-number field.
    return "qty"


def _combined_value_category(key: str) -> str:
    compact = re.sub(r"[^A-Z0-9]", "", key.replace(".", "").replace("#", ""))
    if any(token in compact for token in ("ITEMDESCRIPTION", "PRODUCTDESCRIPTION")):
        return "description"
    if re.search(r"PONUMBER[A-Z0-9]+", compact):
        return "po"
    if re.search(r"(?:ITEMNO|ITEMNUMBER|ARTICLENO|ARTICLENUMBER)[A-Z0-9]+", compact):
        return "item"
    numbers = re.findall(r"\d+(?:\.\d+)?", str(key or ""))
    if len(numbers) >= 3 and re.search(r"[X×]", str(key or ""), re.IGNORECASE):
        return "measurement"
    for prefix, category in (
        ("PURCHASEORDER", "po"),
        ("PONO", "po"),
        ("ORDERNO", "order"),
        ("ARTICLE", "item"),
        ("ITEM", "item"),
        ("SKU", "item"),
        ("STYLE", "item"),
        ("DESCRIPTION", "description"),
        ("BARCODE", "barcode"),
        ("GTIN", "barcode"),
        ("QUANTITY", "qty"),
        ("QTY", "qty"),
        ("CARTONNO", "carton"),
        ("CTNNO", "carton"),
        ("GRSWT", "gross_weight"),
        ("GROSSWEIGHT", "gross_weight"),
        ("NETWEIGHT", "net_weight"),
        ("MEASUREMENT", "measurement"),
    ):
        if compact.startswith(prefix) and len(compact) > len(prefix):
            return category
    return ""


_PRINT_HEADER_ALIAS_GROUPS = (
    (("CUSTOMERPO", "PURCHASEORDER", "PONO", "PO#", "PO"),
     ("PURCHASEORDER", "PONO", "PO#")),
    (("ITEM", "ARTICLE", "STYLE", "SKU"),
     ("ITEM", "ARTICLE", "STYLE", "SKU")),
    (("DESCRIPTION",), ("DESCRIPTION",)),
    (("PCPERCARTON", "QTY", "QUANTITY"),
     ("NUMBEROFPIECES", "PCPERCARTON", "QTY", "QUANTITY", "PCS")),
    (("NOCARTONS", "CARTONNO", "CARTONNUMBER", "CARTONQTY"),
     ("NOCARTONS", "CARTONNO", "CARTONNUMBER", "CARTONQTY", "CTNNO", "CTNQTY")),
    (("GROSSWEIGHT", "GRSWT", "WGR"),
     ("GROSSWEIGHT", "GRSWT", "WGR")),
    (("NETWEIGHT", "NETWT", "WNET"),
     ("NETWEIGHT", "NETWT", "WNET")),
    (("MEASUREMENT", "DIMENSION", "CARTONSIZE"),
     ("MEASUREMENT", "DIMENSION", "CARTONSIZE", "MEAS")),
    (("BARCODE", "GTIN"), ("BARCODE", "GTIN")),
    (("PINO", "PI"), ("PINO", "PI#")),
    (("ORDERNO",), ("ORDERNO",)),
)


def _print_header_is_in_pdf(header: str, page_keys: tuple[str, ...]) -> bool:
    compact = header.replace(".", "")
    for header_aliases, pdf_aliases in _PRINT_HEADER_ALIAS_GROUPS:
        if not any(
            compact == alias or compact.startswith(alias) or compact.endswith(alias)
            for alias in header_aliases
        ):
            continue
        # These are safety-critical physical values.  A completely blank PDF
        # field is exactly the defect we must detect, so the source value stays
        # in scope even when neither its value nor its label was extractable.
        if any(alias in {"GROSSWEIGHT", "GRSWT", "WGR", "NETWEIGHT", "NETWT", "WNET", "MEASUREMENT", "DIMENSION", "CARTONSIZE"} for alias in header_aliases):
            return True
        return any(alias in page for page in page_keys for alias in pdf_aliases)
    return False


def _selected_row_items(
    row: _ExcelRow,
    header_sections: tuple[tuple[int, frozenset[str]], ...],
) -> tuple[CartonMarkDocumentTextItem, ...]:
    """Retain printable siblings while removing notes and source-only columns."""

    filtered = tuple(
        item
        for item in row.items
        if (
            not _is_instruction_text(item.text)
            and _semantic_key(item.text) not in {"/", "\\", "|", "｜"}
        )
    )
    if _is_table_header_context_row(row):
        return ()
    has_field_label = any(
        _is_field_label_key(key) or bool(_print_header_category(key))
        for key in row.keys
    )
    value_only_table_row = (
        len(row.items) >= 4
        and not has_field_label
    )
    # A wide *source data* row needs header-based column filtering.  A printable
    # template row may also span seven cells (label, three dimensions, two X
    # separators and a unit); its field label makes the whole row intentional.
    if has_field_label:
        label_items = tuple(
            item
            for item, key in zip(row.items, row.keys)
            if _print_header_category(key)
        )
        value_items = tuple(
            item
            for item, key in zip(row.items, row.keys)
            if not _print_header_category(key)
            and not _is_instruction_text(item.text)
        )
        if not value_items:
            # A blank field label is layout context, not customer content.
            categories = {
                _print_header_category(key)
                for key in row.keys
                if _print_header_category(key)
            }
            return label_items if categories <= {"carton", "carton_qty"} else ()
        if all(_is_placeholder_field_text(item.text) for item in value_items):
            # Keep the meaningful label but not formatting such as "/ CTNS";
            # inserted values in the PDF remain visible as additions.
            return label_items
        return filtered
    if len(row.items) < 7 and not value_only_table_row:
        return filtered

    relevant_columns: frozenset[str] = frozenset()
    if row.row.isdigit():
        row_number = int(row.row)
        relevant_columns = next((
            columns
            for header_row, columns in reversed(header_sections)
            if header_row < row_number
        ), frozenset())

    output: list[CartonMarkDocumentTextItem] = []
    for index, item in enumerate(row.items):
        if _is_instruction_text(item.text):
            continue
        position = _excel_position(item.location)
        column = position[1] if position is not None else ""
        # Direct PDF evidence is always safe.  A relevant header is the only
        # reason to retain an unmatched cell from a wide raw-data row.
        direct_match = index in row.matched_indexes
        if direct_match and column not in relevant_columns:
            # Do not let a source-only value become "matched" solely because it
            # is a substring of a longer printable value on the same row (PI
            # 1100037622 versus Order 1100037622-Warehouse 1).  A genuine ITEM,
            # PO or BARCODE column is retained above by its table-header role.
            key = row.keys[index]
            direct_match = not (
                len(key) >= 6
                and any(
                    other_index != index
                    and len(other_key) > len(key)
                    and key in other_key
                    and other_index in row.matched_indexes
                    for other_index, other_key in enumerate(row.keys)
                )
            )
        if direct_match or column in relevant_columns:
            output.append(item)
    return tuple(output)


def _is_table_header_context_row(row: _ExcelRow) -> bool:
    recognised_indexes = {
        index
        for index, key in enumerate(row.keys)
        if _print_header_category(key)
    }
    categories = {
        _print_header_category(row.keys[index])
        for index in recognised_indexes
    }
    has_embedded_business_value = any(
        index not in recognised_indexes
        and any(character.isdigit() for character in row.keys[index])
        and _is_strong_anchor(item.text, row.keys[index])
        for index, item in enumerate(row.items)
    )
    return (
        len(recognised_indexes) >= 3
        and len(categories) >= 3
        and not has_embedded_business_value
    )


def _is_placeholder_field_text(value: str) -> bool:
    compact = _semantic_key(value)
    for token in ("PCS", "PIECES", "CTNS", "CTN", "CARTONS", "OF", "KG", "KGS", "CM"):
        compact = compact.replace(token, "")
    compact = re.sub(r"[/_\-–—.,()]+", "", compact)
    return not compact


def _build_excel_rows(
    items: list[CartonMarkDocumentTextItem],
    page_keys: tuple[str, ...],
) -> list[_ExcelRow]:
    grouped: dict[tuple[str, str], list[tuple[int, CartonMarkDocumentTextItem]]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(_excel_group(item.location, index), []).append((index, item))

    rows: list[_ExcelRow] = []
    for (sheet, row), entries in grouped.items():
        row_items = tuple(item for _, item in entries)
        keys = tuple(_semantic_key(item.text) for item in row_items)
        matched = tuple(
            index
            for index, key in enumerate(keys)
            if _is_signal_key(key) and any(key in page for page in page_keys)
        )
        anchors = tuple(index for index in matched if _is_strong_anchor(row_items[index].text, keys[index]))
        signal_count = sum(_is_signal_key(key) for key in keys)
        precision = len(matched) / max(1, signal_count)
        unmatched_count = max(0, signal_count - len(matched))
        candidate = bool(anchors) and (
            signal_count <= 3
            or (len(matched) >= 2 and precision >= 0.40)
            or precision >= 0.60
            or (len(anchors) >= 2 and unmatched_count <= 3)
        )
        rows.append(_ExcelRow(
            sheet=sheet,
            row=row,
            order=min(index for index, _ in entries),
            items=row_items,
            keys=keys,
            matched_indexes=matched,
            anchor_indexes=anchors,
            candidate=candidate,
            precision=precision,
            has_instruction=any(_is_instruction_text(item.text) for item in row_items),
        ))
    return sorted(rows, key=lambda row_value: row_value.order)


def _is_signal_key(key: str) -> bool:
    return len(key) >= 3 and not _is_field_label_key(key)


def _is_field_label_key(key: str) -> bool:
    if key in _GENERIC_ANCHORS:
        return True
    # Punctuation has already been normalized out of the semantic key.  Exact
    # label stems cover common variants such as "ITEM NO." and "G.W.(KGS)"
    # without treating a value-bearing line ("ITEM 92120") as a label.
    compact = key.replace(".", "").replace("#", "")
    if compact in _GENERIC_ANCHORS:
        return True
    label_suffixes = ("NO", "NUMBER", "QTY", "QUANTITY", "WEIGHT", "SIZE")
    label_roots = (
        "ARTICLE",
        "BARCODE",
        "CARTON",
        "CUSTOMER",
        "DESCRIPTION",
        "DEPT",
        "GROSS",
        "ITEM",
        "MEASUREMENT",
        "NET",
        "ORDER",
        "PO",
        "PRODUCTDESCRIPTION",
        "PURCHASEORDER",
        "SKU",
        "STYLE",
        "SUPPLIER",
    )
    return any(
        compact == root or compact == f"{root}{suffix}"
        for root in label_roots
        for suffix in ("", *label_suffixes)
    )


def _is_strong_anchor(text: str, key: str) -> bool:
    if not _is_signal_key(key):
        return False
    stripped = str(text or "").strip().upper()
    if _is_instruction_text(stripped):
        return False
    has_digit = any(character.isdigit() for character in key)
    has_cjk = any("\u4e00" <= character <= "\u9fff" for character in key)
    if has_digit:
        return len(key) >= 5
    if has_cjk:
        return len(key) >= 4
    return 8 <= len(key) <= 80


def _is_instruction_text(value: str) -> bool:
    stripped = str(value or "").strip().upper()
    compact = re.sub(r"\s+", "", stripped)
    if any(stripped.startswith(prefix) for prefix in _NARRATIVE_PREFIXES):
        return True
    return any(
        marker in compact
        for marker in (
            "数据引用",
            "不要打印",
            "无需打印",
            "仅供参考",
            "请以实际为准",
            "调整空间排版",
            "制作说明",
        )
    )


def _build_sheet_candidates(rows: list[_ExcelRow]) -> list[_SheetCandidate]:
    grouped: dict[str, list[_ExcelRow]] = {}
    for row in rows:
        if row.candidate:
            grouped.setdefault(row.sheet, []).append(row)

    candidates: list[_SheetCandidate] = []
    all_anchor_values = {
        row.keys[index]
        for row in rows
        if row.candidate
        for index in row.anchor_indexes
    }
    for sheet, sheet_rows in grouped.items():
        anchors = frozenset(
            row.keys[index]
            for row in sheet_rows
            for index in row.anchor_indexes
        )
        signal_count = sum(_is_signal_key(key) for row in sheet_rows for key in row.keys)
        match_count = sum(
            _is_signal_key(row.keys[index])
            for row in sheet_rows
            for index in row.matched_indexes
        )
        precision = match_count / max(1, signal_count)
        coverage = len(anchors) / max(1, len(all_anchor_values))
        anchor_strength = min(1.0, len(anchors) / 4)
        score = 0.55 * precision + 0.30 * coverage + 0.15 * anchor_strength
        candidates.append(_SheetCandidate(
            name=sheet,
            order=min(row.order for row in sheet_rows),
            rows=tuple(sheet_rows),
            anchors=anchors,
            score=score,
            precision=precision,
        ))
    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            -len(candidate.anchors),
            -candidate.precision,
            candidate.order,
        ),
    )


def _select_sheets(
    candidates: list[_SheetCandidate],
) -> tuple[list[_SheetCandidate], bool]:
    if not candidates:
        return [], False
    primary = candidates[0]
    selected = [primary]
    covered = set(primary.anchors)
    all_anchors = set().union(*(candidate.anchors for candidate in candidates))
    primary_coverage = len(covered) / max(1, len(all_anchors))
    ambiguous = False
    for candidate in candidates[1:]:
        new_anchors = set(candidate.anchors) - covered
        new_share = len(new_anchors) / max(1, len(all_anchors))
        source_table_beside_layout = (
            _looks_like_wide_source_table(candidate)
            and not _looks_like_wide_source_table(primary)
        )
        can_extend = (
            primary_coverage < 0.65
            and new_share >= 0.20
            and len(new_anchors) >= 2
            and candidate.score >= max(0.55, primary.score * 0.80)
            and not source_table_beside_layout
        )
        if can_extend:
            selected.append(candidate)
            covered.update(candidate.anchors)
            primary_coverage = len(covered) / max(1, len(all_anchors))
            continue

        # A near-tied alternative with genuinely different identifiers is unsafe
        # to choose automatically.  Lower-scoring raw tables remain useful source
        # material, but are not themselves a second printable body.
        if (
            new_anchors
            and candidate.score >= primary.score - 0.06
            and candidate.score >= 0.60
        ):
            ambiguous = True
    return selected, ambiguous


def _looks_like_wide_source_table(candidate: _SheetCandidate) -> bool:
    if not candidate.rows:
        return False
    wide_rows = sum(len(row.items) >= 7 for row in candidate.rows)
    return wide_rows / len(candidate.rows) >= 0.60


def _select_body_rows(
    rows: list[_ExcelRow],
    *,
    all_rows: list[_ExcelRow],
) -> tuple[list[_ExcelRow], bool]:
    """Keep the page/item blocks supported by the strongest PDF evidence.

    A workbook may contain four item marks while the supplied PDF is for only one
    of them.  Row-level label matches used to pull all four into scope.  Contiguous
    blocks make the comparison unit explicit: equally supported blocks are all
    retained (multi-page PDF), while weaker blocks with different identifiers are
    excluded and force a human review.
    """

    selected: list[_ExcelRow] = []
    cluster_ambiguous = False
    by_sheet: dict[str, list[_ExcelRow]] = {}
    for row in rows:
        by_sheet.setdefault(row.sheet, []).append(row)

    for sheet_rows in by_sheet.values():
        clusters = _row_clusters(sheet_rows)
        if not clusters:
            continue
        top_score = max(cluster.score for cluster in clusters)
        top_cluster = max(clusters, key=lambda cluster: cluster.score)
        kept_clusters = [top_cluster]
        kept_clusters.extend(
            cluster
            for cluster in clusters
            if cluster is not top_cluster
            and cluster.score >= max(0.56, top_score * 0.88)
        )
        kept_anchor_values = set().union(*(cluster.anchors for cluster in kept_clusters))
        # A compact static template (for example supplier label/value) can sit
        # several rows away from the multi-page data table and therefore score
        # lower than it.  When every cell is directly supported by the PDF and
        # the cluster introduces new evidence, retain it as a second printed
        # section.  Isolated selector cells and wide source rows do not qualify.
        kept_clusters.extend(
            cluster
            for cluster in clusters
            if cluster not in kept_clusters
            and _is_fully_supported_static_cluster(cluster)
            and bool(set(cluster.anchors) - kept_anchor_values)
        )
        kept_anchors = set().union(*(cluster.anchors for cluster in kept_clusters))

        for cluster in clusters:
            if cluster in kept_clusters:
                selected.extend(cluster.rows)
                continue
            novel = set(cluster.anchors) - kept_anchors
            if novel and cluster.score >= 0.52:
                cluster_ambiguous = True

        # Purchase/order headings often sit above the first item block.  They are
        # part of the printed contract, not an alternative item candidate.
        clustered_rows = {id(row) for cluster in kept_clusters for row in cluster.rows}
        for row in sheet_rows:
            if id(row) not in clustered_rows and _is_document_header_row(row):
                selected.append(row)

    selected, selector_ambiguous = _drop_redundant_control_rows(
        selected,
        all_rows=all_rows,
    )
    selected.sort(key=lambda row: row.order)
    # Cluster ambiguity is intentionally not promoted here: unmatched explicit
    # ITEM blocks are handled by _has_explicit_unmatched_item_blocks, while
    # lower-scoring raw/static clusters routinely coexist with the print body.
    _ = cluster_ambiguous
    return selected, selector_ambiguous


def _is_fully_supported_static_cluster(cluster: _RowCluster) -> bool:
    return (
        bool(cluster.rows)
        and all(row.precision >= 0.99 and not row.has_instruction for row in cluster.rows)
        and any(
            len(row.items) >= 2
            and any(_is_field_label_key(key) for key in row.keys)
            for row in cluster.rows
        )
        and all(len(row.items) < 7 for row in cluster.rows)
    )


def _include_adjacent_static_rows(
    all_rows: list[_ExcelRow],
    selected_rows: list[_ExcelRow],
    page_keys: tuple[str, ...],
) -> list[_ExcelRow]:
    """Include fully PDF-supported static text directly beside a body block."""

    output = list(selected_rows)
    selected_ids = {id(row) for row in output}
    selected_numbers: dict[str, set[int]] = {}
    for row in selected_rows:
        if row.row.isdigit() and _can_seed_narrow_template_block(row):
            selected_numbers.setdefault(row.sheet, set()).add(int(row.row))

    # Expand to a fixed point.  A printed template commonly has a strong ITEM
    # row followed by several static/physical rows (brand, weights, dimensions,
    # origin).  A single adjacency pass kept only the first neighbour and left
    # the rest looking like PDF-only additions.  Requiring every value on each
    # newly added row to be present in the PDF prevents this walk from entering
    # blank helper templates or source-only notes.
    changed = True
    while changed:
        changed = False
        for row in all_rows:
            if id(row) in selected_ids or not row.row.isdigit() or row.has_instruction:
                continue
            neighbors = selected_numbers.get(row.sheet, set())
            if not any(abs(int(row.row) - number) == 1 for number in neighbors):
                continue
            meaningful = [
                key
                for item, key in zip(row.items, row.keys)
                if not _is_instruction_text(item.text)
                and len(key) >= 3
                and key not in {"FRONTMARK", "SIDEMARK"}
            ]
            fully_supported = meaningful and all(
                any(key in page for page in page_keys) for key in meaningful
            )
            missing_critical_field = _is_narrow_critical_field_row(row)
            if fully_supported or missing_critical_field:
                output.append(row)
                selected_ids.add(id(row))
                if _can_seed_narrow_template_block(row):
                    selected_numbers.setdefault(row.sheet, set()).add(int(row.row))
                changed = True

    output.sort(key=lambda row: row.order)
    return output


def _can_seed_narrow_template_block(row: _ExcelRow) -> bool:
    # Seven-cell measurement rows (label + 3 values + two X separators + unit)
    # are still printable template rows, not raw source-table rows.
    return len(row.items) <= 10 and not row.has_instruction


def _is_narrow_critical_field_row(row: _ExcelRow) -> bool:
    if not _can_seed_narrow_template_block(row):
        return False
    categories = {
        _print_header_category(key)
        for key in row.keys
        if _print_header_category(key)
    }
    if not categories & _REQUIRED_PRINT_TABLE_CATEGORIES:
        return False
    # A label-only placeholder or blank formula row is not evidence.  Require a
    # concrete sibling value, even when it is a short quantity such as "6".
    return any(
        bool(key)
        and not _print_header_category(key)
        and not _is_instruction_text(item.text)
        for item, key in zip(row.items, row.keys)
    )


def _has_unmatched_item_alternatives(
    rows: list[_ExcelRow],
    selected_rows: list[_ExcelRow],
    selected_sheet_names: set[str],
    page_keys: tuple[str, ...],
) -> bool:
    """Detect other explicit item/article blocks not represented by the PDF."""

    selected_ids = {id(row) for row in selected_rows}
    item_label_stems = ("ITEM", "ARTICLE", "STYLE", "SKU")
    for row in rows:
        if row.sheet not in selected_sheet_names or id(row) in selected_ids:
            continue
        has_item_label = any(
            any(_semantic_key(item.text).startswith(stem) for stem in item_label_stems)
            and _is_field_label_key(_semantic_key(item.text))
            for item in row.items
        )
        if not has_item_label:
            continue
        for item, key in zip(row.items, row.keys):
            if _is_field_label_key(key) or not _is_strong_anchor(item.text, key):
                continue
            if not any(key in page for page in page_keys):
                return True
    return False


def _has_explicit_unmatched_item_blocks(
    items: list[CartonMarkDocumentTextItem],
    selected_sheet_names: set[str],
    page_keys: tuple[str, ...],
) -> bool:
    """Detect a printable item block for which no supplied PDF page exists.

    Multiple item blocks are normal for a multi-page contract.  Only a concrete
    value beside an ITEM/ARTICLE/STYLE/SKU label that is absent from every PDF page
    is ambiguous (the PDF may intentionally be a selected subset).
    """

    grouped: dict[tuple[str, str], list[CartonMarkDocumentTextItem]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(_excel_group(item.location, index), []).append(item)

    item_label_stems = ("ITEM", "ARTICLE", "STYLE", "SKU")
    for (sheet, _), row_items in grouped.items():
        if sheet not in selected_sheet_names:
            continue
        field_label_count = sum(
            _is_field_label_key(_semantic_key(item.text))
            for item in row_items
        )
        # A wide row containing several labels is a source-table header, not an
        # ITEM label/value pair.  Its following columns must not be interpreted
        # as alternative item values.
        if field_label_count >= 2:
            continue
        label_indexes = [
            index
            for index, item in enumerate(row_items)
            if _is_field_label_key(_semantic_key(item.text))
            and any(_semantic_key(item.text).startswith(stem) for stem in item_label_stems)
        ]
        for label_index in label_indexes:
            for item in row_items[label_index + 1:]:
                key = _semantic_key(item.text)
                if _is_field_label_key(key) or not _is_strong_anchor(item.text, key):
                    continue
                if not any(key in page for page in page_keys):
                    return True
                # The first strong value after this label is its value; remaining
                # values on a wide data row belong to other columns.
                break
    return False


def _row_clusters(rows: list[_ExcelRow]) -> list[_RowCluster]:
    ordered = sorted(rows, key=lambda row: row.order)
    groups: list[list[_ExcelRow]] = []
    current: list[_ExcelRow] = []
    previous_number: int | None = None
    for row in ordered:
        number = int(row.row) if row.row.isdigit() else None
        if (
            current
            and number is not None
            and previous_number is not None
            and number - previous_number > 4
        ):
            groups.append(current)
            current = []
        elif current and (number is None or previous_number is None):
            groups.append(current)
            current = []
        current.append(row)
        previous_number = number
    if current:
        groups.append(current)

    clusters: list[_RowCluster] = []
    for group in groups:
        anchors = frozenset(
            row.keys[index]
            for row in group
            for index in row.anchor_indexes
        )
        signal_count = sum(_is_signal_key(key) for row in group for key in row.keys)
        match_count = sum(len(row.matched_indexes) for row in group)
        precision = match_count / max(1, signal_count)
        anchor_strength = min(1.0, len(anchors) / 6)
        density = min(1.0, len(group) / 4)
        score = 0.55 * precision + 0.35 * anchor_strength + 0.10 * density
        clusters.append(_RowCluster(tuple(group), anchors, score))
    return clusters


def _is_document_header_row(row: _ExcelRow) -> bool:
    texts = " ".join(str(item.text or "").upper() for item in row.items)
    has_order_word = "SHIPPING MARK" in texts or "PURCHASE ORDER" in texts or "PO#" in texts
    return has_order_word and bool(row.anchor_indexes)


def _drop_redundant_control_rows(
    rows: list[_ExcelRow],
    *,
    all_rows: list[_ExcelRow],
) -> tuple[list[_ExcelRow], bool]:
    result: list[_ExcelRow] = []
    ambiguous = False
    clean_signatures = [
        tuple(
            key
            for item, key in zip(row.items, row.keys)
            if not _is_instruction_text(item.text) and _is_signal_key(key)
        )
        for row in rows
    ]
    singleton_columns: list[str] = []
    singleton_has_item_label: list[bool] = []
    for row, signature in zip(rows, clean_signatures):
        column = ""
        if len(signature) == 1:
            matching_item = next(
                (
                    item
                    for item, key in zip(row.items, row.keys)
                    if not _is_instruction_text(item.text)
                    and _is_signal_key(key)
                    and key == signature[0]
                ),
                None,
            )
            position = (
                _excel_position(matching_item.location)
                if matching_item is not None
                else None
            )
            column = position[1] if position is not None else ""
        singleton_columns.append(column)
        singleton_has_item_label.append(
            any(_is_item_field_label(_semantic_key(item.text)) for item in row.items)
        )

    for index, row in enumerate(rows):
        signature = clean_signatures[index]
        if row.has_instruction and signature and any(
            other_index != index
            and set(signature).issubset(set(other_signature))
            for other_index, other_signature in enumerate(clean_signatures)
        ):
            continue
        # Repeated print templates often have one selector/control cell above the
        # front and side mark bodies.  When the same single business identifier
        # appears twice in another column, the odd-column singleton is the input
        # selector, not a third printed occurrence.  Keeping it used to create a
        # false missing item even when both printed faces were present in the PDF.
        if (
            len(signature) == 1
            and singleton_columns[index]
            and not singleton_has_item_label[index]
        ):
            same_signature = [
                other_index
                for other_index, other_signature in enumerate(clean_signatures)
                if other_signature == signature and singleton_columns[other_index]
            ]
            current_column_count = sum(
                singleton_columns[other_index] == singleton_columns[index]
                for other_index in same_signature
            )
            labelled_body_columns = {
                singleton_columns[other_index]
                for other_index in same_signature
                if singleton_columns[other_index] != singleton_columns[index]
                and singleton_has_item_label[other_index]
            }
            repeated_labelled_body = any(
                sum(
                    singleton_columns[other_index] == column
                    and singleton_has_item_label[other_index]
                    for other_index in same_signature
                ) >= 2
                for column in labelled_body_columns
            )
            repeated_other_column = any(
                sum(
                    singleton_columns[other_index] == column
                    for other_index in same_signature
                ) >= 2
                for column in {
                    singleton_columns[other_index]
                    for other_index in same_signature
                    if singleton_columns[other_index] != singleton_columns[index]
                }
            )
            if current_column_count == 1 and repeated_labelled_body:
                if _has_adjacent_item_label(row, all_rows):
                    # The value may belong to a split label/value layout rather
                    # than a selector.  Preserve it so a missing third print is
                    # never hidden, and require human confirmation.
                    ambiguous = True
                else:
                    continue
            elif current_column_count == 1 and repeated_other_column:
                # Selector-like repetition without two explicitly labelled body
                # occurrences is not strong enough evidence to delete anything.
                ambiguous = True
        result.append(row)
    return result, ambiguous


def _has_adjacent_item_label(row: _ExcelRow, all_rows: list[_ExcelRow]) -> bool:
    if not row.row.isdigit():
        return False
    row_number = int(row.row)
    for other in all_rows:
        if other.sheet != row.sheet or not other.row.isdigit():
            continue
        if abs(int(other.row) - row_number) > 1:
            continue
        if any(_is_item_field_label(_semantic_key(item.text)) for item in other.items):
            return True
    return False


def _is_item_field_label(key: str) -> bool:
    compact = key.replace(".", "").replace("#", "")
    return any(
        compact == root or compact in {f"{root}NO", f"{root}NUMBER"}
        for root in ("ITEM", "ARTICLE", "STYLE", "SKU")
    )


def _diagnostics(
    *,
    original_excel: list[CartonMarkDocumentTextItem],
    usable_excel: list[CartonMarkDocumentTextItem],
    selected_excel: list[CartonMarkDocumentTextItem],
    output_excel: list[CartonMarkDocumentTextItem],
    original_pdf: list[CartonMarkDocumentTextItem],
    cleaned_pdf: list[CartonMarkDocumentTextItem],
    output_pdf: list[CartonMarkDocumentTextItem],
    ignored_errors: int,
    expected_duplicates: int,
    actual_duplicates: int,
    rows: list[_ExcelRow],
    selected_rows: list[_ExcelRow],
    selected_sheets: list[_SheetCandidate],
    strong_anchor_count: int,
) -> CartonMarkDocumentScopeDiagnostics:
    return CartonMarkDocumentScopeDiagnostics(
        excel_input_count=len(original_excel),
        excel_usable_count=len(usable_excel),
        excel_selected_count=len(selected_excel),
        excel_output_count=len(output_excel),
        pdf_input_count=len(original_pdf),
        pdf_cleaned_count=len(cleaned_pdf),
        pdf_output_count=len(output_pdf),
        ignored_excel_error_count=ignored_errors,
        expected_duplicate_count=expected_duplicates,
        actual_duplicate_count=actual_duplicates,
        candidate_row_count=sum(row.candidate for row in rows),
        selected_row_count=len(selected_rows),
        selected_sheet_count=len(selected_sheets),
        strong_anchor_count=strong_anchor_count,
        selected_sheets=tuple(sheet.name for sheet in selected_sheets),
    )
