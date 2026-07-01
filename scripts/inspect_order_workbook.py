from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def normalize_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: inspect_order_workbook.py <xlsx-path>", file=sys.stderr)
        return 1

    workbook_path = Path(sys.argv[1])
    excel_file = pd.ExcelFile(workbook_path)

    payload = {
        "path": str(workbook_path),
        "sheets": [],
    }

    for sheet_name in excel_file.sheet_names:
        frame = pd.read_excel(workbook_path, sheet_name=sheet_name, header=None)
        frame = frame.dropna(how="all").dropna(axis=1, how="all")

        rows = frame.head(12).fillna("").values.tolist()
        normalized_rows = [[normalize_value(cell) for cell in row] for row in rows]

        payload["sheets"].append(
            {
                "sheetName": sheet_name,
                "rowCount": int(frame.shape[0]),
                "columnCount": int(frame.shape[1]),
                "previewRows": normalized_rows,
            }
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
