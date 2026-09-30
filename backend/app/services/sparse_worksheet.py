"""Move existing worksheet cells without materializing its rectangular extent."""


def insert_rows(worksheet, index: int, amount: int = 1) -> None:
    """Match insert_rows cell semantics; callers still shift formulas/structures.

    Excel often saves one formatted cell far below the real table. openpyxl's
    insert_rows first creates every intervening cell, turning a small upload into
    millions of Python objects. Moving the sparse cell map retains those distant
    cells, styles, comments and hyperlinks without allocating the empty grid.
    """
    if index < 1 or amount < 1:
        raise ValueError("Row insertion requires a positive index and amount")
    keys = sorted((key for key in worksheet._cells if key[0] >= index), reverse=True)
    if keys and keys[0][0] + amount > 1_048_576:
        raise ValueError("排期底部已有内容或格式，插行会超出 Excel 行数上限，请整理排期后重试。")
    for row, column in keys:
        cell = worksheet._cells.pop((row, column))
        cell.row = row + amount
        worksheet._cells[(row + amount, column)] = cell
    worksheet._current_row = worksheet.max_row
