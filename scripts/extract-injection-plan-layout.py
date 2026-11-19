import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.injection_scheduling.field_registry import column_name
from app.services.injection_scheduling.sparse_xlsx import read_sheet

src = Path(sys.argv[1])
source = read_sheet(src.read_bytes(), "计划表")
ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
with zipfile.ZipFile(src) as z:
    styles = ET.fromstring(z.read("xl/styles.xml"))
    xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
fonts = styles.find("m:fonts", ns)
fills = styles.find("m:fills", ns)
xfs = styles.find("m:cellXfs", ns)
formats = {
    int(n.get("numFmtId")): n.get("formatCode") for n in styles.find("m:numFmts", ns)
}
from openpyxl.styles.numbers import BUILTIN_FORMATS

formats = {**BUILTIN_FORMATS, **formats}


def color(el):
    if el is None:
        return None
    if el.get("rgb"):
        return "#" + el.get("rgb")[-6:]
    if el.get("indexed"):
        from openpyxl.styles.colors import COLOR_INDEXED

        n = int(el.get("indexed"))
        return "#" + COLOR_INDEXED[n][-6:] if n < len(COLOR_INDEXED) else None
    return None


def fmt(i):
    xf = xfs[i]
    f = fonts[int(xf.get("fontId", 0))]
    fill = fills[int(xf.get("fillId", 0))]
    al = xf.find("m:alignment", ns)
    return {
        "font": {
            "name": f.find("m:name", ns).get("val"),
            "size": float(f.find("m:sz", ns).get("val")),
            "bold": f.find("m:b", ns) is not None,
            "color": color(f.find("m:color", ns)) or "#000000",
        },
        "fill": color(fill.find("m:patternFill/m:fgColor", ns)),
        "numberFormat": formats.get(int(xf.get("numFmtId", 0)), "General"),
        "alignment": dict(al.attrib) if al is not None else {},
    }


rows = {}
styleids = set()
for row in xml.find("m:sheetData", ns):
    n = int(row.get("r"))
    if n > 30:
        break
    cells = {}
    for c in row:
        col = re.sub(r"\d+", "", c.get("r", ""))
        if len(col) > 2 or (len(col) == 2 and col > "BB"):
            continue
        i = int(c.get("s", 0))
        styleids.add(i)
        cells[col] = {"style": i, **source["rows"].get(n, {}).get(col, {})}
    rows[n] = {"height": float(row.get("ht", 15)), "cells": cells}
data = {
    "sha256": source["sha256"],
    "rows": rows,
    "styles": {i: fmt(i) for i in styleids},
    "columns": [
        dict(c.attrib) for c in xml.find("m:cols", ns) if int(c.get("min")) <= 52
    ],
    "headers": [
        source["rows"][3].get(column_name(i), {}).get("cached_value")
        for i in range(1, 51)
    ],
}
out = Path(sys.argv[2])
out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print(
    json.dumps(
        {
            "source": str(src),
            "headers": data["headers"],
            "styles": len(styleids),
            "source_sha256": data["sha256"],
        },
        ensure_ascii=False,
    )
)
