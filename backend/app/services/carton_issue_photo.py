"""Read workshop requisition photos for human review before warehouse issue."""
from __future__ import annotations

import re
import statistics
import unicodedata

from fastapi import HTTPException

from app.services.carton_header_aliases import DELIVERY_IDENTITY_ALIASES

MAX_PHOTO_BYTES = 12 * 1024 * 1024
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_NUMBER = re.compile(r"\d{1,7}(?:\.\d{1,4})?")
_ID = re.compile(r"[A-Z0-9][A-Z0-9./_-]{1,63}")
_CHINESE_ITEM = re.compile(r"[\u4e00-\u9fff][\u4e00-\u9fffA-Z0-9./_-]{1,63}")
_PO = {"po", "pono", "po号", "po编号"}
_CONTRACT = (DELIVERY_IDENTITY_ALIASES["contract_no"] - _PO) | {"合同编号", "contract", "contractno"}
_CUSTOMER_PO = DELIVERY_IDENTITY_ALIASES["customer_po"] | {"客户po号"}
_ITEM = DELIVERY_IDENTITY_ALIASES["item_no"] | {"客货号", "产品货号"}
_REQUESTED = {"领料数", "领料数量", "请领数量", "请领数", "申领数量", "申领数"}
_OTHER_COLUMNS = {"品名规格", "品名", "产品名称", "规格", "单位", "合同数", "合同数量", "实发数", "实发数量", "备注"}
_TRADITIONAL = str.maketrans("貨號編訂單戶採購產規領數請實發備註", "货号编订单户采购产规领数请实发备注")
_DOCUMENT = re.compile(r"(?:\bNO|N[O0])\s*[:：.]?\s*(\d{4,14})(?!\d)")
_UNLABELLED_ID = re.compile(r"[A-Z0-9][A-Z0-9./_-]{3,63}")


def _text(value):
    return unicodedata.normalize("NFKC", value).upper().replace("—", "-").replace("–", "-").strip()


def _header_key(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", _text(value).lower().translate(_TRADITIONAL))


def _column(value):
    key = _header_key(value)
    if key in _CONTRACT:
        return "contract"
    if key in _CUSTOMER_PO:
        return "customer_po"
    if key in _PO or key in {"po合同", "po合同号", "合同po", "合同号po"}:
        return "po"
    if key in _ITEM:
        return "item"
    if key in _REQUESTED:
        return "quantity"
    if key in _OTHER_COLUMNS:
        return "other"
    return ""


def _box(text, locator, meta):
    bounds = locator.get("bbox")
    if not bounds or meta["signal_score"] is None:
        return None
    return dict(text=_text(text), score=meta["signal_score"], **{
        key: bounds[key] for key in ("x", "y", "width", "height")
    })


def _center(box, axis):
    return box[axis] + box["width" if axis == "x" else "height"] / 2


def _header(boxes):
    columns = [(b, kind) for b in boxes if (kind := _column(b["text"]))]
    for kind in ("contract", "customer_po", "po"):
        for reference, role in columns:
            if role != kind:
                continue
            adjacent = [(b, column) for b, column in columns
                        if abs(_center(b, "y") - _center(reference, "y")) < .085]
            items = [b for b, column in adjacent if column == "item"
                     and abs(_center(b, "x") - _center(reference, "x")) > .025]
            if not items:
                continue
            item = min(items, key=lambda b: abs(_center(b, "y") - _center(reference, "y")))
            return reference, kind, item, adjacent
    return None


def _request_rows(boxes, header):
    reference, kind, item, adjacent = header
    reference_x, item_x = (_center(b, "x") for b in (reference, item))
    pitch = (_center(item, "y") - _center(reference, "y")) / (item_x - reference_x)
    # Measured header centers are used as column anchors on rotated or skewed forms.
    def level(box):
        return _center(box, "y") - (_center(box, "x") - reference_x) * pitch

    top = level(reference)
    aligned = sorted(((b, role) for b, role in adjacent if abs(level(b) - top) < .027),
                     key=lambda entry: _center(entry[0], "x"))

    def limits(box):
        centers = [_center(b, "x") for b, _ in aligned]
        center = _center(box, "x")
        index = centers.index(center)
        before = (centers[index - 1] + center) / 2 if index else center - abs(item_x - reference_x) * .75
        after = ((centers[index + 1] + center) / 2 if index + 1 < len(centers)
                 else center + abs(item_x - reference_x) * .75)
        return before, after

    ref_start, ref_end = limits(reference)
    item_start, item_end = limits(item)
    po_column = next((b for b, role in aligned if role == "customer_po"), None)
    if kind == "contract" and not po_column:
        po_column = next((b for b, role in aligned if role == "po"), None)
    po_limits = limits(po_column) if kind == "contract" and po_column else None
    joined_identity_columns = not any(min(reference_x, item_x) < _center(b, "x") < max(reference_x, item_x)
                                      for b, _ in aligned)
    quantity = next((b for b, role in aligned if role == "quantity"), None)
    qty_limits = None
    if quantity:
        center = _center(quantity, "x")
        before, after = limits(quantity)
        half_width = min(center - before, after - center, .035)
        qty_limits = center - half_width, center + half_width
    used_limits = [(ref_start, ref_end), (item_start, item_end)]
    used_limits.extend(pair for pair in (qty_limits, po_limits) if pair)
    min_x = max(0, min(pair[0] for pair in used_limits))
    max_x = max(pair[1] for pair in used_limits)
    stop = min((level(b) for b in boxes if re.match(r"附[注註]", b["text"]) and level(b) > top), default=1)
    content = [b for b in boxes if top + .016 < level(b) < stop - .012
               and min_x <= _center(b, "x") <= max_x and not _column(b["text"])]
    groups = []
    tolerance = max(.012, statistics.median(b["height"] for b, _ in aligned) * .60)
    for box in sorted(content, key=level):
        if not groups or abs(level(box) - statistics.median(level(b) for b in groups[-1])) > tolerance:
            groups.append([])
        groups[-1].append(box)

    output = []
    for group in groups[:24]:
        group.sort(key=lambda b: b["x"])
        contract_text = item_text = customer_po = requested = ""
        evidence = []
        for box in group:
            value = box["text"]
            x = _center(box, "x")
            if po_limits and po_limits[0] <= x < po_limits[1] and _ID.fullmatch(value):
                customer_po = value
            elif ref_start <= box["x"] < ref_end or item_start <= box["x"] < item_end:
                evidence.append(value)
                suffix = re.fullmatch(r"-\s*\d{1,5}", value)
                if suffix and kind == "contract" and ref_start <= box["x"] < ref_end:
                    contract_text = value.replace(" ", "")
                else:
                    tokens = value.split()
                    if len(tokens) == 2 and joined_identity_columns and box["x"] < max(ref_start, item_start) <= box["x"] + box["width"]:
                        ref_token, item_token = tokens if reference_x < item_x else tokens[::-1]
                        if _ID.fullmatch(ref_token) and (_ID.fullmatch(item_token) or _CHINESE_ITEM.fullmatch(item_token)):
                            contract_text, item_text = ref_token, item_token
                    elif ref_start <= x < ref_end and not contract_text and _ID.fullmatch(value):
                        contract_text = value
                    elif item_start <= x < item_end and not item_text and (_ID.fullmatch(value) or _CHINESE_ITEM.fullmatch(value)):
                        item_text = value
            if (qty_limits and qty_limits[0] <= x <= qty_limits[1]
                    and box["x"] >= qty_limits[0] - .008 and box["x"] + box["width"] <= qty_limits[1] + .008
                    and box["score"] >= .85 and _NUMBER.fullmatch(value) and float(value) > 0):
                requested = value
        if not evidence and not requested and not customer_po:
            continue
        output.append({
            "contract_no": contract_text, "reference_kind": kind, "item_no": item_text,
            **({"customer_po": customer_po} if po_limits else {}),
            "requested_quantity": requested, "evidence": " · ".join(evidence)[:200],
            "top": round(max(0, min(b["y"] for b in group) - .01), 4),
            "bottom": round(min(1, max(b["y"] + b["height"] for b in group) + .01), 4),
        })
    return output


def _unlabelled_rows(boxes):
    groups = []
    for box in sorted(boxes, key=lambda b: _center(b, "y")):
        value = box["text"]
        tokens = [token for token in value.split() if _UNLABELLED_ID.fullmatch(token)
                  and sum(char.isdigit() for char in token) >= 4]
        if not tokens or _DOCUMENT.search(value):
            continue
        if not groups or _center(box, "y") - _center(groups[-1][0], "y") > .024:
            groups.append([])
        groups[-1].append(box)
    return [{
        "contract_no": "", "reference_kind": "po", "item_no": "", "requested_quantity": "",
        "evidence": " · ".join(b["text"] for b in sorted(group, key=lambda b: b["x"]))[:200],
        "top": round(max(0, min(b["y"] for b in group) - .01), 4),
        "bottom": round(min(1, max(b["y"] + b["height"] for b in group) + .01), 4),
    } for group in groups[:24]]


def read_issue_photo(content: bytes, extension: str):
    from PIL import Image, ImageFilter, ImageOps
    from app.services.assistant.document_ocr import LocalOcr, OcrError, image_document

    try:
        image = image_document(content, extension)
        angles = (90, 270, 0, 180) if image.height > image.width else (0, 180, 90, 270)
        ocr = LocalOcr(None, detection_side=1184)
        transposes = {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_270}
        attempts = []

        def scan(angle, enhanced=False):
            oriented = image.transpose(transposes[angle]) if angle else image.copy()
            if enhanced:
                oriented = ImageOps.autocontrast(oriented.convert("L"), cutoff=1).filter(
                    ImageFilter.UnsharpMask(radius=1.3, percent=120, threshold=3)
                )
            boxes = []

            def add(text, locator, meta):
                if box := _box(text, locator, meta):
                    boxes.append(box)

            ocr.recognize(oriented, len(attempts) + 1, add)
            header = _header(boxes)
            document = next((match.group(1) for box in boxes if not header or box["y"] < header[0]["y"]
                             if (match := _DOCUMENT.search(box["text"]))), "")
            rows = _request_rows(boxes, header) if header else _unlabelled_rows(boxes)
            coded = [row for row in rows if any(char.isdigit() for char in row["contract_no"] + row["item_no"])]
            pairs = sum(bool(row["contract_no"] and row["item_no"]) for row in coded)
            horizontal = sum(box["width"] >= box["height"] * oriented.height / oriented.width for box in boxes)
            score = (pairs, len(coded), bool(document), bool(header), horizontal, len(rows), sum(b["score"] for b in boxes))
            attempts.append((score, angle, document, rows, bool(header)))
            return bool(header) and (pairs > 0 or bool(document and coded))

        for angle in angles:
            if scan(angle):
                break
        best = max(attempts, key=lambda attempt: attempt[0])
        if not best[0][0] and not best[0][1]:
            scan(best[1], enhanced=True)
            best = max(attempts, key=lambda attempt: attempt[0])
        _, rotation, document, rows, has_header = best
        return {"document_no": document, "rotation": rotation, "rows": rows, "has_header": has_header}
    except OcrError as error:
        if error.code == "ocr_unavailable":
            raise HTTPException(503, "本地照片识别暂不可用，请手动输入合同或货号。") from error
        raise HTTPException(422, "无法读取照片，请重拍清晰的 JPG 或 PNG。") from error
