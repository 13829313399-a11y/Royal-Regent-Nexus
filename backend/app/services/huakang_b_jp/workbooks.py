"""Own the OS file handle even when a streaming worksheet exits early."""
from contextlib import contextmanager

import openpyxl


@contextmanager
def reference_workbook(path):
    # Workbook.close() alone can leave a ZipExtFile held by an interrupted row
    # iterator. Owning the binary stream releases Windows locks on every exit,
    # including load failures and exceptions whose tracebacks retain iterators.
    with open(path, 'rb') as source:
        workbook = openpyxl.load_workbook(source, data_only=True, read_only=True)
        try:
            yield workbook
        finally:
            workbook.close()
