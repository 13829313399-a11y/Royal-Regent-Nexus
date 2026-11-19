import re
from typing import Mapping

from ..contracts import NormalizedRegion, PdfRenameRuleBase, PdfRenameRuleDefinition, RecognizedRegionValue


class ShippingSoRule(PdfRenameRuleBase):
    definition = PdfRenameRuleDefinition(
        rule_id="shipping-so",
        label="船务部SO",
        description="读取首页 EI Booking No.，按 SO-订舱号.pdf 命名，例如 SO-S1N3059162.pdf。",
        version="1.0.0",
        factory_ids=("huaxing",),
        regions=(NormalizedRegion(
            key="ei_booking_no", label="EI Booking No.", page_number=1,
            left=.47, top=.045, right=.66, bottom=.29, language="eng",
        ),),
    )

    def build_interval_name(self, values: Mapping[str, RecognizedRegionValue]) -> str:
        text = values["ei_booking_no"].normalized_text
        parts = re.split(r"\bEI\s+Booking\s+No\b\.?\s*[:：]?\s*", text, flags=re.IGNORECASE)
        if len(parts) != 2:
            raise ValueError("首页未找到唯一的 EI Booking No. 栏，请核对原件。")
        # The Notes cell is directly below the booking cell on the shipping order.
        number = re.split(r"\bNotes\b\s*[:：]?", parts[1], maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*", number):
            raise ValueError("EI Booking No. 为空、含有多个值或无法完整辨认，请核对订舱号。")
        return f"SO-{number}"
