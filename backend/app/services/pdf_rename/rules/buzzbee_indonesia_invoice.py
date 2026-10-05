from __future__ import annotations

import re
from typing import Mapping

from ..contracts import (
    NormalizedRegion,
    PdfRenameRuleBase,
    PdfRenameRuleDefinition,
    RecognizedRegionValue,
)


class BuzzBeeIndonesiaInvoiceRule(PdfRenameRuleBase):
    definition = PdfRenameRuleDefinition(
        rule_id="buzzbee-indonesia-invoice",
        label="BuzzBee印尼发票",
        description="识别首页右上方红色发票号，生成 客发票--发票号.pdf，例如 客发票--104753.pdf。",
        version="1.0.0",
        factory_ids=("huaxing",),
        regions=(
            NormalizedRegion(
                key="invoice_header", label="BuzzBee 发票标题", page_number=1,
                left=.01, top=.14, right=.60, bottom=.225,
                language="eng", ocr_only=True, ocr_page_segmentation=11, ocr_engine="rapidocr",
            ),
            NormalizedRegion(
                key="invoice_number", label="红色发票号", page_number=1,
                left=.72, top=.135, right=.94, bottom=.178,
                language="eng", ocr_only=True, ocr_page_segmentation=7, red_only=True,
            ),
        ),
    )

    def build_interval_name(self, values: Mapping[str, RecognizedRegionValue]) -> str:
        header = values["invoice_header"].normalized_text
        if not (re.search(r"BUZZ\s*BEE\s*TOYS", header, re.IGNORECASE)
                and re.search(r"\bINVOICE\b", header, re.IGNORECASE)):
            raise ValueError("首页未识别到 BUZZ BEE TOYS / INVOICE，请确认发票类型及页面方向。")
        # Color filtering removes the black 'A' prefix before transcription.
        # Only spacing is normalized; never repair O/0 or use the upload name.
        number = re.sub(r"\s+", "", values["invoice_number"].normalized_text)
        if not re.fullmatch(r"[0-9]{6}", number):
            raise ValueError("红色发票号须为完整的 6 位数字，请对照原发票核对；不会猜测或补号。")
        return f"客发票--{number}"
