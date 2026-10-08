"""Bounded, read-only XLSX adapter; never execute Excel/EVALUATE expressions."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import json
import re
import unicodedata
from zipfile import BadZipFile, ZipFile
import posixpath
import xml.etree.ElementTree as ET

from fastapi import HTTPException

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000
MAX_SCANNED_ROWS = 100_000
MAX_SCANNED_CELLS = 2_500_000
PARSER_VERSION = "material-tracking-v4"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SHEETS = {"未回物料": "PENDING", "已回料": "RETURNED", "补数未回物料": "PENDING", "补数已回": "RETURNED"}
HEADERS = {
    "供应商复期": "supplier_reply", "订单日期": "order_date", "订单号": "order_no",
    "供应商": "supplier", "生产单号": "production_no", "放产单号": "production_no",
    "计划跟踪号": "plan_no", "物料编码": "material_code", "旧物料编码": "old_material_code",
    "物料名称": "material_name", "订单数量": "ordered_quantity", "基本单位": "unit",
    "单价": "unit_price", "合同号": "contract_no", "交货明细": "delivery_detail",
    "入库数量": "reported_received_quantity", "二次复期": "second_reply",
    "送货单号": "delivery_note_no", "送货单日期": "delivery_note_date",
    "入库日期婷": "reported_receipt_date", "备注": "note", "备注2仓库": "warehouse_note",
    "采购明细id": "source_line_id", "采购明细编号": "source_line_id",
}
SUPPLEMENT_HEADERS = {**HEADERS, "放产日期": "release_date", "款号": "style_no", "物料编号": "material_code",
                      "旧编码": "old_material_code", "订货量": "ordered_quantity", "单位": "unit",
                      "车间组别": "workshop_group", "送货单": "delivery_note_no", "补数单号": "supplement_no"}
REQUIRED_HEADERS = {"order_no", "supplier", "material_code", "material_name", "ordered_quantity", "unit"}
IDENTIFIER_FIELDS = {"source_line_id", "order_no", "production_no", "plan_no", "material_code", "old_material_code", "contract_no", "delivery_note_no", "supplement_no", "style_no"}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def text(value):
    return str(value).strip() if value is not None else ""


def header_key(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", unicodedata.normalize("NFKC", text(value)).lower())


def number(value):
    raw = text(value)
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", raw):
        raw = raw.replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", raw):
        return None
    try:
        result = Decimal(raw)
        return result if result.is_finite() and abs(result) < Decimal("1e15") else None
    except InvalidOperation:
        return None


def quantity_sum(value):
    raw = text(value)
    parts = raw.split("+")
    if len(parts) > 100:
        return None
    numbers = [number(part.strip()) for part in parts]
    return sum(numbers, Decimal(0)) if numbers and all(n is not None and n >= 0 for n in numbers) else None


def decimal_text(value):
    return format(value, "f") if value is not None else None


def source_date(value, epoch_1904=False):
    raw = text(value)
    num = number(raw)
    if num is not None and 25000 <= num < 73050:
        epoch = datetime(1904, 1, 1) if epoch_1904 else datetime(1899, 12, 30)
        return (epoch + timedelta(days=float(num))).date().isoformat()
    match = re.fullmatch(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})(?:日)?(?:[ T].*)?", raw)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def normalize_row(values, status, epoch_1904=False, *, pending_empty_reference=False):
    """Shared purchase contract for file and future upstream adapters."""
    errors, warnings = [], []
    facts = {key: text(values.get(key)) for key in (
        "source_line_id", "order_no", "supplier", "production_no", "plan_no", "material_code",
        "old_material_code", "material_name", "unit", "contract_no", "delivery_detail",
        "delivery_note_no", "note", "warehouse_note", "supplier_reply", "second_reply",
    )}
    facts["status"] = status
    if values.get("source_category") == "SUPPLEMENT":
        facts.update(source_category="SUPPLEMENT", **{key: text(values.get(key)) for key in ("style_no", "workshop_group", "supplement_no")})
        facts["release_date_raw"] = text(values.get("release_date"))
        facts["release_date"] = source_date(values.get("release_date"), epoch_1904)
        if facts["release_date_raw"] and not facts["release_date"]:
            warnings.append("放产日期未能识别，保留原文")
    if facts["source_line_id"].startswith("#"):
        errors.append("采购明细 ID 是 Excel 错误值，请核对")
    for key, label in [("order_no", "订单号"), ("supplier", "供应商"), ("material_code", "物料编码"),
                       ("material_name", "物料名称"), ("unit", "基本单位")]:
        if not facts[key] or facts[key].startswith("#"):
            errors.append(f"缺少或无效的{label}")
    if facts["unit"] and (number(facts["unit"]) is not None or len(facts["unit"]) > 32):
        errors.append("基本单位疑似错位，请核对原表")
    for key, value in facts.items():
        limit = 10000 if key in {"delivery_detail", "note", "warehouse_note"} else 128 if key in {"source_line_id", "order_no", "material_code", "old_material_code"} else 255
        if isinstance(value, str) and len(value) > limit:
            errors.append(f"字段过长：{key}")
    ordered = number(values.get("ordered_quantity"))
    if ordered is None or ordered <= 0:
        errors.append("订单数量必须是明确的正数")
    price = number(values.get("unit_price"))
    if price is None:
        warnings.append("单价未确认，保留空值")
    elif price < 0:
        errors.append("单价不能为负数")
    reported = number(values.get("reported_received_quantity"))
    detail = quantity_sum(values.get("delivery_detail")) if facts["delivery_detail"] else None
    if reported is None and detail is not None:
        reported = detail
        warnings.append("采购已回数量由原表交货明细的纯数字加总取得")
    elif reported is not None and detail is not None and reported != detail:
        reported = None
        warnings.append("入库数量与交货明细不一致，采购已回数量待核对")
    if reported is None and pending_empty_reference and status == "PENDING":
        reported = Decimal(0)
        facts["reported_received_quantity_basis"] = "EMPTY_PENDING_DELIVERY"
        warnings.append("未回表交货记录为空，按尚未到货追订单数量；原始空值或空明细公式保留")
    if reported is None:
        warnings.append("采购已回数量未确认，不按零处理")
    elif reported < 0:
        reported = None
        warnings.append("采购已回数量为负数，待核对")
    elif ordered is not None and reported > ordered:
        warnings.append("采购已回数量超过订单数量，请核对")
    facts.update(ordered_quantity=decimal_text(ordered), unit_price=decimal_text(price), reported_received_quantity=decimal_text(reported))
    for key in ("order_date", "delivery_note_date", "reported_receipt_date"):
        facts[key + "_raw"] = text(values.get(key))
        facts[key] = source_date(values.get(key), epoch_1904)
        if facts[key + "_raw"] and not facts[key]:
            warnings.append(f"{ {'order_date': '订单日期', 'delivery_note_date': '送货单日期', 'reported_receipt_date': '原表入库日期'}[key]}未能识别，保留原文")
    for key in ("supplier_reply", "second_reply"):
        facts[key + "_date"] = source_date(facts[key], epoch_1904)
    if not facts["production_no"]:
        warnings.append("原表缺少生产单号，保留采购来源，不推断归属")
    if facts["old_material_code"].upper().startswith("CGDD"):
        warnings.append("旧物料编码列疑似存有采购单号，原值保留，请核对旧表列位")
    # Quantities, price, row position and sheet status NEVER identify a source line.
    return facts, upstream_identity(facts) if facts["source_line_id"] else document_identity(facts), errors, warnings


def upstream_identity(facts):
    identity = ["UPSTREAM", facts["source_line_id"]]
    return digest(["SUPPLEMENT", *identity] if facts.get("source_category") == "SUPPLEMENT" else identity)


def document_identity(facts):
    identity = ["DOCUMENT", *[facts[k] for k in (
        "order_no", "supplier", "production_no", "plan_no", "material_code", "material_name", "unit", "contract_no")]]
    if facts.get("source_category") == "SUPPLEMENT":
        identity = ["SUPPLEMENT", *identity, facts.get("style_no", ""), facts.get("supplement_no", "")]
    return digest(identity)


def shared_formula_index(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value):
        return None
    return str(int(value)) if int(value) <= 4294967295 else None


def pending_empty_reference(values, header, formulas, row_no, status, formula_metadata=None, shared_formulas=None):
    """Recognize confirmed empty delivery records, without evaluating any formula."""
    if status != "PENDING" or "reported_received_quantity" not in header.values() or "delivery_detail" not in header.values():
        return False
    columns = {field: col for col, field in header.items()}
    received_col, detail_col = columns["reported_received_quantity"], columns["delivery_detail"]
    if text(values.get("delivery_detail")) or f"{detail_col}{row_no}" in formulas:
        return False
    value = text(values.get("reported_received_quantity"))
    address = f"{received_col}{row_no}"
    formula = formulas.get(address)
    if formula is None:
        return not value
    if not formula and (metadata := (formula_metadata or {}).get(address, {})).get("t") == "shared":
        index = shared_formula_index(metadata.get("si"))
        anchor = (shared_formulas or {}).get(index) if index is not None else None
        if anchor:
            base_address, base_formula, reference = anchor
            base = re.fullmatch(rf"{re.escape(received_col)}([0-9]+)", base_address)
            extent = re.fullmatch(rf"{re.escape(received_col)}([0-9]+):{re.escape(received_col)}([0-9]+)", reference)
            if base and extent and int(extent[1]) <= int(base[1]) <= int(extent[2]) and int(extent[1]) <= row_no <= int(extent[2]) and re.fullmatch(
                rf"\s*=?EVALUATE\(\s*\$?{re.escape(detail_col)}{base[1]}\s*\)\s*", base_formula, re.IGNORECASE):
                # Translate only this recognized relative-row reference. Shared
                # absolute-row, cross-column and arbitrary formulas stay unknown.
                formula = f"EVALUATE({detail_col}{row_no})"
    # This workbook uses EVALUATE(N4) for its arrival-total column. An empty N4
    # is a confirmed no-arrival record even when the cached result is #VALUE!.
    # Other formulas/errors or references to another row remain unknown.
    return value in {"", "#VALUE!"} and bool(re.fullmatch(
        rf"\s*=?EVALUATE\(\s*\$?{re.escape(detail_col)}\$?{row_no}\s*\)\s*", formula, re.IGNORECASE))


def parse_source_feed(feed):
    """A future Kingdee fetcher submits this same validated ingestion contract."""
    source = feed.model_dump(mode="json")
    rows = []
    bindings = defaultdict(list)
    for index, line in enumerate(source["lines"], start=1):
        facts, key, errors, warnings = normalize_row(line, line["status"])
        if not facts["source_line_id"]:
            errors.append("采购直用数据必须提供非空的稳定采购明细 ID")
        row = {"sheet": "金蝶采购来源", "row_number": index, "row_key": f"KINGDEE:{line.get('source_category', 'PURCHASE')}:{line['source_line_id']}", "identity_key": key,
               "facts": facts, "errors": errors, "warnings": warnings, "raw": {"source_system": "KINGDEE", "snapshot_id": source["snapshot_id"], "values": line},
               "bind_line_id": line["warehouse_line_id"], "expected_line_revision": line["expected_line_revision"]}
        rows.append(row)
        if row["bind_line_id"]:
            bindings[row["bind_line_id"]].append(row)
    for group in bindings.values():
        if len(group) > 1:
            for row in group:
                row["errors"].append("多条采购来源指向同一个仓库来源编号，请核对")
    return {"rows": rows, "sheets": ["金蝶采购来源"], "ignored_sheets": [], "source_digest": digest(source), "scope": "ALL"}


def parse_workbook(filename, content, scope="PENDING"):
    if scope not in {"PENDING", "RETURNED", "ALL", "TRACKING"}:
        raise HTTPException(422, "请选择未回来源、已回历史或跟进范围")
    if not filename.lower().endswith(".xlsx") or not content or len(content) > MAX_FILE_BYTES:
        raise HTTPException(422, "请上传不超过 20 MiB 的 .xlsx 物料跟踪表")
    rows, ignored, found = [], [], []
    scanned_rows = scanned_cells = 0
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > 5000 or sum(m.file_size for m in members) > 200 * 1024 * 1024:
                raise HTTPException(422, "工作簿解压后过大，请拆分后导入")
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook.find("s:sheets", NS)
            if sheets is None:
                raise HTTPException(422, "工作簿缺少工作表结构")
            epoch_1904 = (workbook.find("s:workbookPr", NS) is not None and workbook.find("s:workbookPr", NS).get("date1904") in {"1", "true"})
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {r.get("Id"): posixpath.normpath(posixpath.join("xl", r.get("Target", ""))).lstrip("/") for r in rels if r.get("TargetMode") != "External"}
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = ["".join(t.text or "" for t in si.findall(".//s:t", NS)) for si in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
            styles = ["General"]
            if "xl/styles.xml" in archive.namelist():
                style_root = ET.fromstring(archive.read("xl/styles.xml"))
                formats = {"0": "General", "1": "0", "49": "@"}
                num_formats = style_root.find("s:numFmts", NS)
                if num_formats is not None:
                    formats.update({f.get("numFmtId"): f.get("formatCode", "") for f in num_formats})
                cell_formats = style_root.find("s:cellXfs", NS)
                if cell_formats is not None:
                    styles = [formats.get(f.get("numFmtId", "0"), "unsupported:" + f.get("numFmtId", "0")) for f in cell_formats]
            for sheet in sheets:
                name = sheet.get("name", "")
                status = SHEETS.get(name.strip())
                if not status or scope not in {"ALL", "TRACKING"} and status != scope:
                    ignored.append(name)
                    continue
                found.append(name)
                supplement = name.strip() in {"补数未回物料", "补数已回"}
                sheet_headers = SUPPLEMENT_HEADERS if supplement else HEADERS
                target = targets.get(sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
                if not target.startswith("xl/worksheets/"):
                    raise HTTPException(422, "工作表引用无效")
                header = None
                shared_formulas = {}
                with archive.open(target) as stream:
                    sheet_data = None
                    for event, element in ET.iterparse(stream, events=("start", "end")):
                        if event == "start":
                            if element.tag == "{" + NS["s"] + "}sheetData":
                                sheet_data = element
                            continue
                        if element.tag != "{" + NS["s"] + "}row":
                            continue
                        scanned_rows += 1
                        scanned_cells += len(element)
                        if scanned_rows > MAX_SCANNED_ROWS or scanned_cells > MAX_SCANNED_CELLS:
                            raise HTTPException(422, "工作表扫描范围过大，请清除多余空行或拆分文件")
                        if sheet_data is None:
                            raise HTTPException(422, "工作表行结构无效")
                        sheet_data.remove(element)
                        row_no = int(element.get("r", "0"))
                        cells, raw, formulas, formula_metadata, number_formats, format_errors = {}, {}, {}, {}, {}, []
                        for cell in element:
                            address = cell.get("r", "")
                            column = re.sub(r"\d", "", address)
                            value = cell.find("s:v", NS)
                            value = value.text if value is not None else ""
                            if cell.get("t") == "s" and value:
                                value = strings[int(value)]
                            elif cell.get("t") == "inlineStr":
                                value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                            elif cell.get("t", "n") == "n" and value and header and header.get(column) in IDENTIFIER_FIELDS:
                                numeric_format = styles[int(cell.get("s", "0"))]
                                number_formats[address] = {"stored": value, "format": numeric_format}
                                if re.fullmatch(r"0{1,128}", numeric_format):
                                    if re.fullmatch(r"\d{1,128}", value):
                                        value = value.zfill(len(numeric_format))
                                    else:
                                        format_errors.append(f"{header[column]} 的数字编号不是明确的非负整数，请转为文本后核对")
                                elif numeric_format not in {"General", "@"}:
                                    format_errors.append(f"{header[column]} 的数字编号格式无法确认，请将原表编号转为文本后核对")
                            formula = cell.find("s:f", NS)
                            if formula is not None:
                                formulas[address] = formula.text or ""
                                formula_metadata[address] = dict(formula.attrib)
                                if formula.get("t") == "shared" and formula.text and (index := shared_formula_index(formula.get("si"))) is not None:
                                    if index in shared_formulas:
                                        raise HTTPException(422, f"{name}共享公式分组重复，无法核对到货数量，请修正原表")
                                    shared_formulas[index] = (address, formula.text, formula.get("ref", ""))
                            cells[column] = value
                        if header is None:
                            candidate = {col: sheet_headers[header_key(v)] for col, v in cells.items() if header_key(v) in sheet_headers}
                            if REQUIRED_HEADERS <= set(candidate.values()):
                                if len(set(candidate.values())) != len(candidate):
                                    raise HTTPException(422, f"{name}存在重复业务表头")
                                header = candidate
                            elif row_no > 20:
                                raise HTTPException(422, f"{name}未找到订单号、供应商、物料、数量和单位表头")
                            element.clear()
                            continue
                        values = {field: cells.get(col, "") for col, field in header.items()}
                        if supplement:
                            values["source_category"] = "SUPPLEMENT"
                        if not any(text(values.get(k)) for k in REQUIRED_HEADERS):
                            element.clear()
                            continue
                        facts, key, errors, warnings = normalize_row(values, status, epoch_1904,
                            pending_empty_reference=pending_empty_reference(values, header, formulas, row_no, status, formula_metadata, shared_formulas))
                        errors.extend(format_errors)
                        raw = {"values": cells, "formulas": formulas, "formula_metadata": formula_metadata, "number_formats": number_formats, "headers": header}
                        if len(dump(raw)) > 100_000:
                            errors.append("原表行内容过大，请核对")
                        rows.append({"sheet": name, "row_number": row_no, "row_key": f"{name}:{row_no}", "identity_key": key,
                                     "facts": facts, "errors": errors, "warnings": warnings, "raw": raw})
                        if len(rows) > MAX_ROWS:
                            raise HTTPException(422, "一次最多读取 50,000 条明细，请拆分文件")
                        element.clear()
                if header is None:
                    raise HTTPException(422, f"{name}没有有效表头")
    except HTTPException:
        raise
    except (BadZipFile, KeyError, IndexError, ValueError, ET.ParseError, RuntimeError) as exc:
        raise HTTPException(422, "无法读取工作簿，请检查文件是否完整、未加密且为 .xlsx") from exc
    if not found or not rows:
        raise HTTPException(422, "没有找到所选的未回物料 / 已回料明细")
    return {"rows": rows, "sheets": found, "ignored_sheets": ignored, "source_digest": hashlib.sha256(content).hexdigest(), "scope": scope}
