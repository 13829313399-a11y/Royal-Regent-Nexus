from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import date
from typing import Mapping

from ..contracts import (
    NormalizedRegion, PdfRenameIssue, PdfRenamePlan, PdfRenameRuleBase, PdfRenameRuleDefinition,
    PdfRenameServiceError, PdfRenameSource, RecognizedRegionValue, RecognizedTextBox, RegionRecognizer,
)

FILENAME_TEMPLATE = "{report_no}-#{item_no}-{po_numbers}-{quantity}-{report_date}.pdf"


def _uncertain_keys(names: tuple[str, ...]) -> set[str]:
    aliases = {
        "report_no": ("Batch no.", "报告号", "报告号（Batch no.）"),
        "item_no": ("Item number", "货号", "货号（Item number 前 5 位）"),
        "po_numbers": ("P/O no.", "PO", "PO 号", "PO 号（P/O no.）"),
        "quantity": ("Quantity (Pcs)", "数量", "Pcs", "数量（Pcs）"),
        "report_date": ("DATE", "日期", "日期（DATE，月/日/年）"),
    }
    def canonical(value: str) -> str:
        return re.sub(r"[\W_]+", "", _text(value)).casefold()
    lookup = {canonical(alias): key for key, values in aliases.items() for alias in (key, *values)}
    keys = set()
    for name in names:
        key = lookup.get(canonical(name))
        if key is None:
            # An unbound uncertainty must not silently certify any naming field.
            return set(aliases)
        keys.add(key)
    return keys


def _text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _geometry(box: RecognizedTextBox) -> tuple[float, float, float, float, float]:
    tl, tr, br, bl = box.polygon
    lx, ly = (tl[0] + bl[0]) / 2, (tl[1] + bl[1]) / 2
    rx, ry = (tr[0] + br[0]) / 2, (tr[1] + br[1]) / 2
    height = ((bl[1] - tl[1]) + (br[1] - tr[1])) / 2
    if rx <= lx or height <= 0:
        raise ValueError("识别文字位置无效，请人工核对。")
    return (lx + rx) / 2, (ly + ry) / 2, height, (ry - ly) / (rx - lx), rx


def _field(value: RecognizedRegionValue, label: str, pattern: str, right: float, display_label: str) -> tuple[str, str, float | None]:
    """Read the unique label and its same-row, same-column value, not OCR order.

    Label baselines account for mildly skewed photographs. Column limits prevent
    a missing value from borrowing a neighbour. Never skip an invalid first cell.
    """
    expression = re.compile(rf"^{label}\s*:?\s*(.*?)\s*$", re.I)
    if value.route == "QWEN":
        # Qwen transcribes each label with its corresponding cell. Keep these
        # labelled lines as evidence; never fabricate spatial OCR boxes/scores.
        matches = [(line, match) for line in value.raw_text.splitlines()
                   if (match := expression.fullmatch(_text(line)))]
        if len(matches) != 1 or not re.fullmatch(pattern, _text(matches[0][1][1]), re.I):
            raise ValueError(f"千问未完整识别唯一的{display_label}，请核对原 PDF。")
        return _text(matches[0][1][1]), matches[0][0], None
    labels = [(box, match) for box in value.text_boxes
              if (match := expression.fullmatch(_text(box.text)))]
    if len(labels) != 1:
        raise ValueError(f"未识别到唯一的{display_label}标签，请核对首页或人工改名。")
    box, match = labels[0]
    candidate = _text(match[1])
    evidence, confidence = box.text, box.confidence
    if not candidate:
        x, y, height, slope, edge = _geometry(box)
        neighbours = []
        for other in value.text_boxes:
            if other is box:
                continue
            ox, oy, oh, _, _ = _geometry(other)
            # Compare to the projected row, not the uncorrected vertical position.
            if edge < ox < right and abs(oy - y - slope * (ox - x)) < .42 * min(height, oh):
                neighbours.append(other)
        if len(neighbours) != 1:
            raise ValueError(f"{box.text} 右侧单元格缺失或存在歧义，请人工核对；不使用相邻行补值。")
        other = neighbours[0]
        candidate = _text(other.text)
        evidence += "\n" + other.text
        confidence = min(confidence, other.confidence)
    if confidence < .85 or not re.fullmatch(pattern, candidate, re.I):
        raise ValueError(f"{box.text} 的值不完整、模糊或格式不支持，请人工核对；不会自动修补数字。")
    return candidate, evidence, confidence


def _fields(value: RecognizedRegionValue) -> tuple[RecognizedRegionValue, ...]:
    header = value.normalized_text
    if not (re.search(r"Playmates\s+International\s+Company", header, re.I)
            and re.search(r"SHIPMENT\s+QUALITY\s+INSPECTION\s+REPORT", header, re.I)):
        raise ValueError("首页未识别到 Playmates / SHIPMENT QUALITY INSPECTION REPORT，请确认彩星报告类型。")
    specs = (
        ("report_no", "报告号（Batch no.）", r"Batch\s+no\.?", r"RR[0-9]{4}P?", 1.0),
        ("item_no", "货号（Item number 前 5 位）", r"Item\s+number", r"[0-9]{5}(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)?", .32),
        ("po_numbers", "PO 号（P/O no.）", r"P\s*[/I]\s*O\s+no\.?", r"[0-9]{7}", .64),
        ("quantity", "数量（Pcs）", r"Quantity\s*\(\s*Pcs\s*\)", r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", .32),
        ("report_date", "日期（DATE，月/日/年）", r"DATE\b(?!\s+Code\b)", r"[0-9]{1,2}\s*/\s*[0-9]{1,2}\s*/\s*[0-9]{4}", 1.0),
    )
    fields = []
    uncertain = _uncertain_keys(value.uncertain_fields)
    for key, label, source_label, pattern, right in specs:
        raw, confidence = "", None
        try:
            parsed, raw, confidence = _field(value, source_label, pattern, right, label)
            if key in uncertain:
                raise ValueError(f"千问标记{label}不确定，请对照原 PDF 补充。")
            if key == "item_no":
                parsed = parsed[:5]
            elif key == "report_no":
                parsed = parsed.upper()
            elif key == "quantity":
                quantity = int(parsed.replace(",", ""))
                if quantity <= 0:
                    raise ValueError("Quantity (Pcs) 必须大于 0，请人工核对数量。")
                parsed = str(quantity)
            elif key == "report_date":
                month, day, year = map(int, parsed.split("/"))
                try:
                    date(year, month, day)
                except ValueError as exc:
                    raise ValueError("DATE 不是有效的月/日/年日期，请人工核对。") from exc
                parsed = f"{year}.{month}.{day}"
        except ValueError as exc:
            fields.append(RecognizedRegionValue(key, label, raw, "", value.route, confidence,
                                               validation_error=str(exc)))
        else:
            fields.append(RecognizedRegionValue(key, label, raw, parsed, value.route, confidence))
    return tuple(fields)


class CaixingInspectionRule(PdfRenameRuleBase):
    definition = PdfRenameRuleDefinition(
        rule_id="caixing-inspection", label="彩星行验报告", version="1.0.2",
        factory_ids=("huaxing",),
        description=(
            "仅限华兴厂区。按首页正文生成 报告号-#货号-PO号-数量-日期.pdf。"
            "报告号取 Batch no.（保留 P），货号取 Item number 前 5 位，PO 取 P/O no.，"
            "数量取 Quantity (Pcs)，DATE 按月/日/年读取并转为 年.月.日。"
            "不使用 Date Code、箱数或原文件名补值；千问识别完整且校验通过即可下载。"
            "个别字段不清晰时保留其余结果，只需补充未识别字段。"
        ),
        regions=(NormalizedRegion(
            "report_header", "彩星首页标识与命名字段", 1, .07, .05, .95, .26,
            language="eng", ocr_only=True, ocr_engine="rapidocr", allow_partial_fields=True,
        ),),
    )

    def build_interval_name(self, values: Mapping[str, RecognizedRegionValue]) -> str:
        fields = _fields(values["report_header"])
        if errors := [field.validation_error for field in fields if field.validation_error]:
            raise ValueError("；".join(errors))
        return FILENAME_TEMPLATE.format(**{field.key: field.normalized_text for field in fields})[:-4]

    def create_plan(self, source: PdfRenameSource, recognizer: RegionRecognizer) -> PdfRenamePlan:
        try:
            value = recognizer(source.content, self.definition.regions[0])
        except PdfRenameServiceError as exc:
            return PdfRenamePlan(source.source_file_name, "", "", "ERROR",
                                 issues=(PdfRenameIssue(exc.code, exc.message),))
        plan = PdfRenamePlan(source.source_file_name, "", "", "ERROR", fields=(value,))
        try:
            fields = _fields(value)
        except ValueError as exc:
            return replace(plan, issues=(PdfRenameIssue("PDF_RENAME_INTERVAL_INVALID", str(exc)),))
        issues = tuple(PdfRenameIssue("PDF_RENAME_INTERVAL_INVALID", field.validation_error)
                       for field in fields if field.validation_error)
        plan = replace(plan, fields=(value, *fields), issues=issues)
        if issues:
            # Keep valid fields, but never publish a downloadable placeholder name.
            return replace(plan, filename_template=FILENAME_TEMPLATE)
        interval = FILENAME_TEMPLATE.format(**{field.key: field.normalized_text for field in fields})[:-4]
        try:
            target = self.build_target_file_name(interval)
        except ValueError as exc:
            return replace(plan, interval_name=interval,
                           issues=(PdfRenameIssue("PDF_RENAME_TARGET_INVALID", str(exc)),))
        needs_review = value.route == "LOCAL_OCR" or (value.confidence is not None and value.confidence < .85)
        return replace(plan, target_file_name=target, interval_name=interval,
                       status="REVIEW" if needs_review else "READY", issues=(
                           PdfRenameIssue("PDF_RENAME_OCR_REVIEW_REQUIRED", "区间名来自扫描区域 OCR，请对照原 PDF 复核。"),
                       ) if needs_review else ())
