from __future__ import annotations

from app.services.pdf_rename.contracts import PdfRenameRuleDefinition


class FixedRegionRuleTemplate:
    """Catalog placeholder until the first business rule is confirmed.

    Copy this shape into a new rule module, add immutable NormalizedRegion
    coordinates and subclass PdfRenameRuleBase. Register the concrete rule in
    rules/__init__.py only after sample PDFs and expected filenames are verified.
    """

    definition = PdfRenameRuleDefinition(
        rule_id="fixed-region-template",
        label="固定区域区间名（待配置）",
        description="扫描或读取 PDF 固定区域，将识别结果整理为对应文件的区间名。",
        version="draft-1",
        status="draft",
        setup_checklist=(
            "规则名称与适用文件类型",
            "读取页码及固定区域坐标",
            "区间名提取、清洗与组合格式",
            "样例 PDF、期望文件名与异常样例",
        ),
    )

    def create_plan(self, *_args, **_kwargs):
        raise RuntimeError("draft rules cannot create rename plans")
