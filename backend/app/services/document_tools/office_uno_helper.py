"""Standalone helper executed by a Python interpreter that really imports UNO.

Only JSON request/response cross the interpreter boundary. This module must not
import the application package, SQLAlchemy or the worker's site-packages.
"""
import json
import sys
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue


def prop(name, value):
    item = PropertyValue()
    item.Name, item.Value = name, value
    return item


def main(request):
    options = request["options"]
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    context = None
    for _ in range(600):
        try:
            context = resolver.resolve(request["connection"])
            break
        except Exception:
            time.sleep(.1)
    if context is None:
        return {"error": "无法连接到独立 LibreOffice 实例", "code": "UNO_CONNECTION_FAILED"}
    desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    properties = [prop("Hidden", True), prop("ReadOnly", False), prop("UpdateDocMode", 0),
                  prop("MacroExecutionMode", 0), prop("Silent", True)]
    if options.get("password"):
        properties.append(prop("Password", options["password"]))
    document = desktop.loadComponentFromURL(uno.systemPathToFileUrl(request["input"]), "_blank", 0, tuple(properties))
    if document is None:
        return {"error": "文件无法打开，可能密码不正确或文档已损坏", "code": "OFFICE_OPEN_FAILED"}
    result = {"uno_interpreter": sys.executable, "external_links_updated": False, "macros_executed": False}
    try:
        is_calc = document.supportsService("com.sun.star.sheet.SpreadsheetDocument")
        if is_calc:
            sheets = document.getSheets()
            names = sheets.getElementNames()
            requested = options.get("sheets") or [name for name in names if sheets.getByName(name).IsVisible or options.get("include_hidden")]
            if any(name not in names for name in requested):
                return {"error": "所选工作表不存在", "code": "INVALID_SHEETS"}
            included = [name for name in requested if sheets.getByName(name).IsVisible or options.get("include_hidden")]
            if not included:
                return {"error": "没有可输出的工作表", "code": "EMPTY_SELECTION"}
            # Set intended visible sheets first: Calc always needs one visible sheet.
            for name in included:
                sheets.getByName(name).IsVisible = True
            for name in names:
                sheets.getByName(name).IsVisible = name in included
            result["selected_sheets"] = included
            for name in included:
                sheet = sheets.getByName(name)
                if options.get("include_hidden"):
                    cursor = sheet.createCursor()
                    cursor.gotoEndOfUsedArea(True)
                    used = cursor.getRangeAddress()
                    sheet.getRows().getByIndex(used.StartRow).IsVisible = True
                    sheet.getCellRangeByPosition(0, 0, used.EndColumn, used.EndRow).getRows().IsVisible = True
                    sheet.getCellRangeByPosition(0, 0, used.EndColumn, used.EndRow).getColumns().IsVisible = True
                chosen = options.get("range")
                if chosen:
                    if "!" in chosen:
                        title, chosen = chosen.rsplit("!", 1)
                        if title.strip("'") != name:
                            sheet.IsVisible = False
                            continue
                    if document.NamedRanges.hasByName(chosen):
                        selected = document.NamedRanges.getByName(chosen).getReferredCells()
                        if selected.getRangeAddress().Sheet != sheet.getCellRangeByName("A1").getRangeAddress().Sheet:
                            sheet.IsVisible = False
                            continue
                    else:
                        selected = sheet.getCellRangeByName(chosen)
                    sheet.setPrintAreas((selected.getRangeAddress(),))
                styles = document.getStyleFamilies().getByName("PageStyles")
                style = styles.getByName(sheet.PageStyle)
                layout_change = options.get("paper", "original") != "original" or options.get("orientation", "auto") != "auto" or options.get("print_mode", "original") != "original"
                if layout_change:
                    # Sheets can share a style; clone only when actual layout
                    # modifications are requested. Original mode keeps its style.
                    style_name = "RRDocument" + str(sheet.getCellRangeByName("A1").getRangeAddress().Sheet)
                    clone = document.createInstance("com.sun.star.style.PageStyle")
                    styles.insertByName(style_name, clone)
                    for entry in style.getPropertySetInfo().getProperties():
                        if entry.Attributes & 16:  # READONLY
                            continue
                        try:
                            clone.setPropertyValue(entry.Name, style.getPropertyValue(entry.Name))
                        except Exception:
                            pass  # Optional Writer-only properties need not exist in Calc.
                    sheet.PageStyle = style_name
                    style = clone
                paper = options.get("paper", "original")
                if paper in ("A4", "A3"):
                    width, height = (21000, 29700) if paper == "A4" else (29700, 42000)
                    if style.IsLandscape:
                        width, height = height, width
                    style.Width, style.Height = width, height
                orientation = options.get("orientation", "auto")
                if orientation in ("landscape", "portrait"):
                    landscape = orientation == "landscape"
                    width, height = min(style.Width, style.Height), max(style.Width, style.Height)
                    style.IsLandscape = landscape
                    style.Width, style.Height = (height, width) if landscape else (width, height)
                if options.get("print_mode") in ("fit_width", "selection"):
                    style.ScaleToPages = 0
                    style.ScaleToPagesX, style.ScaleToPagesY = 1, 0
                style.PrintFormulas = options.get("formula_mode") == "formula"
            if options.get("recalculate"):
                document.calculateAll()
                result["recalculated"] = True
            else:
                result["recalculated"] = False
            # Formatted strings are read from Calc, so custom number formats are
            # observable separately from the numeric cached values.
            display = {}
            for name in included:
                sheet = sheets.getByName(name)
                cursor = sheet.createCursor()
                cursor.gotoEndOfUsedArea(True)
                used = cursor.getRangeAddress()
                if (used.EndColumn+1)*(used.EndRow+1) <= 250000:
                    values = {}
                    for row in range(used.EndRow+1):
                        for column in range(used.EndColumn+1):
                            cell = sheet.getCellByPosition(column, row)
                            if cell.getFormula():
                                kind = cell.getType().value
                                numeric_result = kind == "VALUE" or (kind == "FORMULA" and cell.FormulaResultType == 1)
                                values[f"{row+1}:{column+1}"] = {"display": cell.getString(), "formula": cell.getFormula(), "error": cell.getError(),
                                                                "value_kind": "number" if numeric_result else "text",
                                                                "value": cell.getValue() if numeric_result else cell.getString()}
                    display[name] = values
            result["display_cells"] = display
            graphics = []
            graphics_failed = []
            for name in included:
                sheet = sheets.getByName(name)
                drawing = sheet.getDrawPage()
                for index in range(drawing.getCount()):
                    shape = drawing.getByIndex(index)
                    output_image = Path(request["output"]).parent / ("office-shape-" + str(names.index(name)) + "-" + str(index) + ".png")
                    try:
                        exporter = context.ServiceManager.createInstanceWithContext("com.sun.star.drawing.GraphicExportFilter", context)
                        exporter.setSourceDocument(shape)
                        ok = exporter.filter((prop("MediaType", "image/png"), prop("URL", uno.systemPathToFileUrl(str(output_image)))))
                        if not ok or not output_image.is_file():
                            raise ValueError("No image")
                        graphics.append({"sheet": name, "path": str(output_image), "width_pt": shape.Size.Width * 72 / 2540,
                                         "height_pt": shape.Size.Height * 72 / 2540})
                    except Exception:
                        graphics_failed.append({"sheet": name, "index": index})
            result["graphics"], result["graphics_failed"] = graphics, graphics_failed
        suffix = Path(request["output"]).suffix.lower()
        filters = {".pdf": "calc_pdf_Export" if is_calc else "writer_pdf_Export",
                   ".xlsx": "Calc MS Excel 2007 XML", ".docx": "Office Open XML Text",
                   ".xls": "MS Excel 97", ".doc": "MS Word 97"}
        filter_data = [prop("UseLosslessCompression", True), prop("ReduceImageResolution", False), prop("SinglePageSheets", False)]
        if options.get("page_selection", "all") != "all":
            filter_data.append(prop("PageRange", options["page_selection"]))
        document.storeToURL(uno.systemPathToFileUrl(request["output"]),
                            (prop("FilterName", filters[suffix]), prop("Overwrite", True), prop("FilterData", tuple(filter_data))))
        return result
    finally:
        document.close(True)
        desktop.terminate()


if __name__ == "__main__":
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        response = main(payload)
    except Exception:
        response = {"error": "LibreOffice 无法应用文档选项或生成输出，请检查文件及所选范围", "code": "UNO_EXPORT_FAILED"}
    Path(payload["response"]).write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
