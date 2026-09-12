from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import Mapping

from ..contracts import (
    NormalizedRegion,
    PdfRenamePlan,
    PdfRenameRuleBase,
    PdfRenameRuleDefinition,
    PdfRenameServiceError,
    PdfRenameSource,
    RecognizedRegionValue,
    RegionRecognizer,
)

# Labels may contain scan/table-border noise; identifiers themselves must remain
# five literal digits. Never repair O/0, 8/3, missing '+' or consult the filename.
_ITEM_LABEL = re.compile(
    r"(?:[Ii1l\[]tem)\s+No\.?\s*/?\s*Description\s*:\s*[-—–~“\" ]*", re.IGNORECASE,
)
_ITEM = re.compile(_ITEM_LABEL.pattern + r"(?P<item>[0-9]{5})\s*/", re.IGNORECASE)
_SC_LABEL = re.compile(r"^[|I\[\] ]*(?:[S5]\s*)?/\s*C\s*:\s*[-—–~ ]*", re.IGNORECASE)
_PO_LIST = re.compile(r"[0-9]{5}(?:\s*\+\s*[0-9]{5})*")


def _lines(value: RecognizedRegionValue) -> list[str]:
    text = unicodedata.normalize("NFKC", value.raw_text or value.normalized_text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _item_identifier(lines: list[str]) -> tuple[str, str]:
    labels = [(index, match) for index, line in enumerate(lines) for match in _ITEM_LABEL.finditer(line)]
    if len(labels) != 1:
        raise ValueError("首页 Item No./Description 须包含唯一的 5 位货号；不使用 Date Code 或原文件名推断。")
    index, label = labels[0]
    evidence = [lines[index]]
    # Sparse OCR may put the value in the next block. Join only an empty label
    # with its immediately adjacent nonempty line; never search past other fields.
    if not lines[index][label.end():].strip() and index + 1 < len(lines):
        evidence.append(lines[index + 1])
    items = [(match.group("item"), "\n".join(evidence)) for match in _ITEM.finditer(" ".join(evidence))]
    if len(items) != 1:
        raise ValueError("首页 Item No./Description 须包含唯一的 5 位货号；不使用 Date Code 或原文件名推断。")
    return items[0]


def _po_candidates(lines: list[str]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for index, line in enumerate(lines):
        label = _SC_LABEL.match(line)
        if not label:
            continue
        content = line[label.end():].strip()
        evidence = [line]
        # Only explicit '+' joins are allowed across wrapped lines.
        for following in lines[index + 1:]:
            if re.fullmatch(r"[0-9+\s]+", following) and not (content.endswith("+") or following.startswith("+")):
                raise ValueError("S/C 后存在未以 + 连接的数字行，无法确认全部 PO；请核对扫描区域。")
            if not (content.endswith("+") or following.startswith("+")):
                break
            # Keep malformed explicit continuations too. Dropping '+529I3'
            # here would incorrectly release a truncated, apparently valid PO.
            content += following
            evidence.append(following)
        candidates.append((content, "\n".join(evidence)))
    return candidates


def _identifiers(value: RecognizedRegionValue) -> tuple[str, str, str, str]:
    lines = _lines(value)
    item, item_evidence = _item_identifier(lines)
    candidates = _po_candidates(lines)
    if len(candidates) != 1:
        raise ValueError("首页未识别到唯一的 S/C 字段，请核对报告或修改文件名。")
    if not _PO_LIST.fullmatch(candidates[0][0]):
        invalid = next((part.strip() for part in candidates[0][0].split("+")
                        if not re.fullmatch(r"\s*[0-9]{5}\s*", part)), "")
        raise ValueError(f"S/C 片段“{invalid[:40] or '空白'}”未识别为完整的 5 位 PO，请核对该片段或修改文件名。")
    po_list = re.sub(r"\s+", "", candidates[0][0])
    return item, po_list, item_evidence, candidates[0][1]


def _recognize_identifiers(source: bytes, region: NormalizedRegion,
                           recognizer: RegionRecognizer) -> RecognizedRegionValue:
    value = recognizer(source, region)
    if region.key != "identifiers" or value.route != "LOCAL_OCR":
        return value
    try:
        _identifiers(value)
        return value
    except ValueError:
        pass
    # Retry the same pixels with the installed layout OCR engine. Do not repair
    # characters (e.g. turning 4 into '+'), guess digits, or use the upload name.
    lines = _lines(value)
    try:
        original_item, _ = _item_identifier(lines)
    except ValueError:
        return value
    try:
        original_candidates = _po_candidates(lines)
    except ValueError:
        return value
    if len(original_candidates) != 1:
        return value
    try:
        recovered = recognizer(source, replace(region, ocr_engine="rapidocr"))
        item, pos, _, _ = _identifiers(recovered)
    except (PdfRenameServiceError, ValueError):
        return value
    if recovered.text_boxes and any(box.confidence < .85 for box in recovered.text_boxes):
        return value
    if item != original_item:
        return value
    # Every already-complete PO must remain in order in the second reading.
    original_parts = original_candidates[0][0].split("+")
    if len(pos.split("+")) < len(original_parts):
        return value
    recovered_parts = iter(pos.split("+"))
    for part in original_parts:
        if re.fullmatch(r"[0-9]{5}", part.strip()):
            if not any(candidate == part.strip() for candidate in recovered_parts):
                return value
    return recovered


class BuzzBeeInspectionRule(PdfRenameRuleBase):
    definition = PdfRenameRuleDefinition(
        rule_id="buzzbee-inspection",
        factory_ids=("huaxing",),
        label="BuzzBee 行验报告",
        description=(
            "仅限华兴厂区。读取首页 Item No./Description 的货号和 S/C 的 PO，生成 #货号-PO+PO.pdf；"
            "多个 PO 保持原顺序，保留前导零。首版支持 5 位货号、5 位 PO；"
            "Date Code 为批次信息，不代替货号。识别完整且校验通过即可下载；异常片段自动重识别。"
        ),
        version="1.0.2",
        regions=(
            NormalizedRegion(
                key="report_header", label="BuzzBee 报告标识", page_number=1,
                left=.33, top=.045, right=.69, bottom=.124,
                language="eng", ocr_only=True,
            ),
            NormalizedRegion(
                key="identifiers", label="货号与 PO（Item No. / S/C）", page_number=1,
                left=.02, top=.12, right=.665, bottom=.205,
                language="eng", ocr_only=True, ocr_page_segmentation=11,
            ),
        ),
    )

    def build_interval_name(self, values: Mapping[str, RecognizedRegionValue]) -> str:
        header = values["report_header"].normalized_text
        if not (re.search(r"BUZZ\s*BEE\s+TOYS", header, re.IGNORECASE)
                and re.search(r"INSPECTION\s+REPORT", header, re.IGNORECASE)):
            raise ValueError("首页未识别到 BUZZ BEE TOYS / INSPECTION REPORT，请确认报告类型及页面方向。")
        item, po_list, _, _ = _identifiers(values["identifiers"])
        return f"#{item}-{po_list}"

    def build_target_file_name(self, interval_name: str) -> str:
        from ..service import MAX_TARGET_STEM_CHARS

        if len(interval_name) > MAX_TARGET_STEM_CHARS:
            raise ValueError("PO 数量过多，目标文件名超出长度限制；不会截断或遗漏 PO。")
        return super().build_target_file_name(interval_name)

    def create_plan(self, source: PdfRenameSource, recognizer: RegionRecognizer) -> PdfRenamePlan:
        plan = super().create_plan(source, lambda data, region: _recognize_identifiers(data, region, recognizer))
        if plan.status == "ERROR":
            return plan
        values = {value.key: value for value in plan.fields}
        original = values["identifiers"]
        item, po_list, item_line, po_line = _identifiers(original)
        # Tesseract's shared adapter uses a fixed .80 score, not measured field
        # confidence. OCR alone is not a reason to gate a valid BuzzBee filename.
        return replace(plan, status="READY", issues=(), fields=(
            values["report_header"],
            replace(original, key="item_no", label="货号", raw_text=item_line, normalized_text=item),
            replace(original, key="po_numbers", label="PO（报告顺序）", raw_text=po_line, normalized_text=po_list),
        ))
