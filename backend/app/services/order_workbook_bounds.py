"""Bounded range discovery for read-only XLSX sheets without optional dimensions."""
from xml.etree.ElementTree import iterparse

from fastapi import HTTPException
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string


def worksheet_bounds(book, sheet, row_limit, column_limit, message, status=422):
    rows, columns = sheet.max_row, sheet.max_column
    if rows is None or columns is None:
        rows = columns = 0
        # Inspect stored coordinates instead of expanding sparse rows into millions
        # of empty cells. Callers already bound compressed and expanded file size.
        current_row = current_column = 0
        with book._archive.open(sheet._worksheet_path) as source:
            for event, element in iterparse(source, events=('start', 'end')):
                if event == 'end':
                    element.clear()
                    continue
                if element.tag == '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row':
                    current_row = int(element.get('r', current_row + 1))
                    current_column = 0
                    rows = max(rows, current_row)
                elif element.tag == '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c':
                    reference = element.get('r')
                    if reference:
                        column, row = coordinate_from_string(reference)
                        current_column = column_index_from_string(column)
                    else:
                        row = current_row
                        current_column += 1
                    rows = max(rows, row)
                    columns = max(columns, current_column)
                if rows > row_limit or columns > column_limit:
                    raise HTTPException(status, message)
    if rows > row_limit or columns > column_limit:
        raise HTTPException(status, message)
    return rows, columns
