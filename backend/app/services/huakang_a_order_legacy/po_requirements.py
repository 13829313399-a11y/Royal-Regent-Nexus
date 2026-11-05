"""Explicit ThreeSixty release requirements, not country/customer guesses.

Keep conditional label clauses verbatim. Product labels and master-carton
labels are different fields; artwork is not an instruction manual or pack type.
"""
from __future__ import annotations

import re


def _value(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I | re.M)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _notes(text: str) -> str:
    # pdfplumber repeats this letterhead between continued note paragraphs.
    body = re.sub(r"(?ms)^28/F, Harbourside HQ,.*?^Page \d+ of \d+[^\n]*\n?", "", text)
    marker = re.search(r"Factory Address\s*:", body, re.I)
    if not marker:
        return ""
    body = body[marker.end():]
    return re.split(r"SPECIAL INSTRUCTION\s*:|Factory Commit Date History\s*:", body, maxsplit=1, flags=re.I)[0]


def extract_requirements(text: str, release_type: str, customer_release: str) -> dict:
    result: dict = {"_360_lineage": {}, "_360_warnings": []}
    lineage = result["_360_lineage"]
    customer = _value(r"End Customer[ \t]*:[ \t]*([^\r\n]+)", text)
    if customer:
        lineage["customer_name"] = "PO · End Customer"
    elif release_type.upper() == "CINV":
        # FC may be before the customer inside the parentheses, or after them.
        match = re.search(r"\((.+)\)\s*(?:[,;]\s*FC-\d+)?\s*$", customer_release, re.I)
        if match:
            customer = re.sub(r"^FC-\d+\s+", "", match.group(1).strip(), flags=re.I)
            if customer:
                lineage["customer_name"] = "PO · Customer Release No. 的明确括号客名（剔除 FC 编号）"
    result["customer_name"] = customer

    # EAN/UPC are the product barcode; never substitute ITF/SCC/SSCC.
    barcodes = list(dict.fromkeys(re.findall(r"\b(?:UPC|EAN) Code[ \t]*:[ \t]*(\d+)\b", text, re.I)))
    result["barcode"] = barcodes[0] if len(barcodes) == 1 else ""
    if result["barcode"]:
        lineage["barcode"] = "PO · 明确 UPC Code / EAN Code（不使用 ITF、SCC 或 SSCC）"
    elif len(barcodes) > 1:
        result["_360_barcode_conflict"] = True
        result["_360_warnings"].append(("barcode", "PO 存在多个不同 UPC/EAN，条码留空，请核对产品条码；不能用历史值掩盖冲突"))

    instruction = _value(r"\bIM[ \t]*:[ \t]*([^\r\n]+?)(?=[ \t]+Safety Warning\s*\+\s*QR\s*:|$)", text)
    safety = _value(r"Safety Warning\s*\+\s*QR[ \t]*:[ \t]*([^\r\n]+)", text)
    manual_parts = ([f"IM : {instruction}"] if instruction else []) + ([f"Safety Warning + QR : {safety}"] if safety else [])
    notes = _notes(text)
    paragraphs = [part.strip() for part in re.split(r"(?m)^\s*\d+\.\s*", notes)[1:] if part.strip()]
    for part in paragraphs:
        if re.search(r"^IM Type\s*:", part, re.I):
            manual_parts.append(re.sub(r"\s+", " ", part))
    result["manual"] = "\n".join(dict.fromkeys(manual_parts))
    if result["manual"]:
        lineage["manual"] = "PO · IM / IM Type 与 Safety Warning + QR 原文，保留 No SW / No QR 和条件"

    result["standard"] = _value(r"(?:Quality|National) Standard[ \t]*:[ \t]*([^\r\n;]+)", notes)
    if result["standard"]:
        lineage["standard"] = "PO · 明确 Quality / National Standard（不根据语言、客名或港口推断）"
    packaging = _value(r"Package Type[ \t]*:[ \t]*([^\r\n]+)", text)
    if packaging:
        lineage["packaging"] = "PO · Package Type"
    else:
        packaging = _value(r"^Packaging[ \t]*:[ \t]*([^\r\n;]+)", notes)
        if packaging:
            lineage["packaging"] = "PO · 明确 Packaging 条款（保留原文，不以 Artwork 代替）"
    result["product_packaging"] = packaging

    labels = []
    carton_labels = []
    for part in paragraphs:
        part = re.split(r"Showed on shipping mark\s*--", part, maxsplit=1, flags=re.I)[0].strip()
        if re.search(r"\b(?:stickers?|labels?|Price Tag|blank stick)\b", part, re.I):
            # A numbered shipping-mark paragraph is not a product-label rule.
            if not re.search(r"^Shipping Mark|^(?:Need|Require) .*?inspection\b", part, re.I):
                is_carton = bool(re.search(r"\b(?:master|outer|inner|shipping)\s+cartons?\b", part, re.I))
                is_product = bool(re.search(r"\b(?:product|color box|poly ?bag|PP bag|remote control)\b", part, re.I))
                # SSCC carton clauses belong to schedule_parser's existing
                # page-aware, negation-aware reader. Never turn a broad notes
                # substring (e.g. "No SSCC ...") into a positive requirement.
                if is_carton and not re.search(r"\bSSCC\b", part, re.I):
                    carton_labels.append(re.sub(r"\s+", " ", part))
                if not is_carton or is_product:
                    labels.append(re.sub(r"\s+", " ", part))
    # Unnumbered importer instructions in the supplied Proxy release.
    match = re.search(r"(?ms)^add an importer sticker\b.*?(?=^Quality Standard\s*:|\Z)", notes)
    if match:
        labels.append(re.sub(r"\s+", " ", match.group(0)).strip())
    no_stickers = _value(r"\b(No stickers[^\r\n]*)", notes)
    if no_stickers:
        # Keep exceptions, but don't turn the subsequent -POE / -MS shipping
        # instructions into product-label requirements.
        labels.append(re.split(r"\s*-(?=POE\b|MS markings\b|PO#|SSCC\b)", no_stickers, maxsplit=1, flags=re.I)[0].strip())
    result["label"] = "\n".join(dict.fromkeys(labels))
    if result["label"]:
        lineage["label"] = "PO · 产品/彩盒贴纸条款原文；保留适用条件、位置及提供方，不继承欠/已订等进度"
        result["_360_warnings"].append(("label", "贴纸要求已按 PO 原文带入；请核对电池/无线电产品等适用条件、贴纸位置及提供方，未自动判定是否适用"))

    result["customer_label"] = "\n".join(dict.fromkeys(carton_labels))
    if result["customer_label"]:
        lineage["customer_label"] = "PO · 明确外箱/内箱标签原文（与产品条码、产品贴纸分列；SSCC另按原页证据识别）"
    return result
