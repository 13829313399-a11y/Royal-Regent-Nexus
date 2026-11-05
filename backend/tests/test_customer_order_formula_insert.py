"""Formula insertion must preserve references while avoiding unrelated parsing."""
import openpyxl
import pytest
from openpyxl.formula.tokenizer import Tokenizer, TokenizerError
from openpyxl.worksheet.formula import ArrayFormula

from app.services.huakang_a_order_legacy.unified_schedule import _insert_rows
from app.services.huaxing_order_legacy.new_order_excel import _rewrite_formula_for_insert


@pytest.mark.parametrize(
    "formula,formula_sheet,target_sheet,expected",
    [
        ("=A10+$B$11", "ITEM表", "ITEM表", "=A12+$B$13"),
        ("=SUM(A1:A9)", "ITEM表", "ITEM表", "=SUM(A1:A11)"),
        ("=A10+$B$11", "其他款项", "ITEM表", "=A10+$B$11"),
        ("='Item表'!A10", "其他款项", "ITEM表", "='Item表'!A12"),
        ("=ITEM表!$A$10+A10", "其他款项", "ITEM表", "=ITEM表!$A$12+A10"),
        ("='O''Brien'!A10", "其他款项", "O'Brien", "='O''Brien'!A12"),
        ("='O''''Brien'!A10", "其他款项", "O''Brien", "='O''''Brien'!A12"),
        ("=' O''Brien '!A10", "其他款项", "O'Brien", "=' O''Brien '!A12"),
        ('=IF(A1="ITEM表!A10",A10,0)', "其他款项", "ITEM表", '=IF(A1="ITEM表!A10",A10,0)'),
        ('=INDIRECT("ITEM表!A10")', "其他款项", "ITEM表", '=INDIRECT("ITEM表!A10")'),
        ('=INDIRECT("Other!A10")', "其他款项", "ITEM表", '=INDIRECT("Other!A10")'),
        ("=SUM('ITEM表:Other'!A10)", "其他款项", "ITEM表", "=SUM('ITEM表:Other'!A10)"),
        ("='[Other.xlsx]ITEM表'!A10", "其他款项", "ITEM表", "='[Other.xlsx]ITEM表'!A10"),
        ("=ITEM表Total+A10", "其他款项", "ITEM表", "=ITEM表Total+A10"),
    ],
)
def test_formula_insertion_preserves_local_quoted_and_indirect_reference_semantics(
    formula, formula_sheet, target_sheet, expected
):
    assert _rewrite_formula_for_insert(
        formula,
        formula_sheet=formula_sheet,
        target_sheet=target_sheet,
        formula_row=10,
        insert_row=10,
        amount=2,
    ) == expected


def test_insertion_does_not_tokenize_unrelated_history_formulas(monkeypatch):
    book = openpyxl.Workbook()
    item = book.active
    item.title = "ITEM表"
    history = book.create_sheet("已出发票")
    for row in range(1, 101):
        history.cell(row, 1, f'=IF(B{row}="","",B{row}*C{row})')
    history["D1"] = "='ITEM表'!A10"
    item["A10"] = "=SUM(A1:A9)"
    original = Tokenizer.__init__
    parsed = []

    def record(self, formula):
        parsed.append(formula)
        original(self, formula)

    monkeypatch.setattr(Tokenizer, "__init__", record)
    _insert_rows(book, item, 10, 2)

    assert len(parsed) == 2
    assert item["A12"].value == "=SUM(A1:A11)"
    assert history["D1"].value == "='ITEM表'!A12"
    assert history["A100"].value == '=IF(B100="","",B100*C100)'


def test_repeated_insertion_moves_array_ranges_and_only_target_references():
    book = openpyxl.Workbook()
    item = book.active
    item.title = "ITEM表"
    other = book.create_sheet("历史")
    item["A10"] = ArrayFormula("A10:A12", "=ROW(A10:A12)")
    other["A10"] = ArrayFormula("A10:A12", "=ROW(A10:A12)")
    other["B10"] = ArrayFormula("B10:B12", "='ITEM表'!A10:A12")

    _insert_rows(book, item, 10, 2)
    _insert_rows(book, item, 13, 1)

    assert item["A12"].value.ref == "A12:A15"
    assert item["A12"].value.text == "=ROW(A12:A15)"
    assert other["A10"].value.ref == "A10:A12"
    assert other["A10"].value.text == "=ROW(A10:A12)"
    assert other["B10"].value.ref == "B10:B12"
    assert other["B10"].value.text == "='ITEM表'!A12:A15"


@pytest.mark.parametrize(
    "formula_sheet,formula,must_parse",
    [
        ("历史", '="unterminated', False),
        ("ITEM表", '="unterminated', True),
        ("历史", '="ITEM表', True),
    ],
)
def test_insertion_preserves_unrelated_bad_formula_but_keeps_relevant_errors(
    formula_sheet, formula, must_parse
):
    book = openpyxl.Workbook()
    item = book.active
    item.title = "ITEM表"
    book.create_sheet("历史")
    book[formula_sheet]["A1"] = formula

    if must_parse:
        with pytest.raises(TokenizerError):
            _insert_rows(book, item, 10, 2)
    else:
        _insert_rows(book, item, 10, 2)
        assert book[formula_sheet]["A1"].value == formula
