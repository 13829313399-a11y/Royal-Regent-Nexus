from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class NormalizedRegion:
    """A page region expressed as ratios so rules are resolution-independent."""

    key: str
    label: str
    page_number: int
    left: float
    top: float
    right: float
    bottom: float
    required: bool = True
    language: str = "chi_sim+eng"
    ocr_only: bool = False
    ocr_page_segmentation: int = 6
    ocr_engine: str = "tesseract"

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must start at 1")
        if not (0 <= self.left < self.right <= 1):
            raise ValueError("region horizontal bounds must be within 0..1")
        if not (0 <= self.top < self.bottom <= 1):
            raise ValueError("region vertical bounds must be within 0..1")
        if self.ocr_page_segmentation not in (6, 7, 11):
            raise ValueError("unsupported OCR page segmentation")
        if self.ocr_engine not in ("tesseract", "rapidocr"):
            raise ValueError("unsupported OCR engine")

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "page_number": self.page_number,
            "bbox": [self.left, self.top, self.right, self.bottom],
            "required": self.required,
            "language": self.language,
            "ocr_only": self.ocr_only,
            "ocr_page_segmentation": self.ocr_page_segmentation,
            "ocr_engine": self.ocr_engine,
        }


@dataclass(frozen=True)
class PdfRenameRuleDefinition:
    rule_id: str
    label: str
    description: str
    version: str
    status: str = "active"
    regions: tuple[NormalizedRegion, ...] = ()
    setup_checklist: tuple[str, ...] = ()
    factory_ids: tuple[str, ...] = ()  # Empty means shared across production factories.

    @property
    def available(self) -> bool:
        return self.status == "active"

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.rule_id,
            "label": self.label,
            "description": self.description,
            "version": self.version,
            "status": self.status,
            "available": self.available,
            "regions": [region.as_dict() for region in self.regions],
            "setup_checklist": list(self.setup_checklist),
            "factory_ids": list(self.factory_ids),
        }


@dataclass(frozen=True)
class PdfRenameSource:
    source_file_name: str
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class PdfRenameManualOverride:
    source_index: int
    target_file_name: str
    confirmed: bool


@dataclass(frozen=True)
class RecognizedTextBox:
    """Internal spatial OCR evidence; polygon ratios are relative to the crop."""

    text: str
    polygon: tuple[tuple[float, float], ...]  # top-left, top-right, bottom-right, bottom-left
    confidence: float


@dataclass(frozen=True)
class RecognizedRegionValue:
    key: str
    label: str
    raw_text: str
    normalized_text: str
    route: str
    confidence: float | None = None
    text_boxes: tuple[RecognizedTextBox, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "route": self.route,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PdfRenameIssue:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class PdfRenamePlan:
    source_file_name: str
    target_file_name: str
    interval_name: str
    status: str
    fields: tuple[RecognizedRegionValue, ...] = ()
    issues: tuple[PdfRenameIssue, ...] = ()
    manual_override: bool = False

    @property
    def manual_override_allowed(self) -> bool:
        # Unknown/infrastructure/file-structure failures must not be released.
        return all(issue.code in {
            "PDF_RENAME_INTERVAL_INVALID", "PDF_RENAME_INTERVAL_EMPTY",
            "PDF_RENAME_REGION_EMPTY", "PDF_RENAME_TARGET_INVALID",
            "PDF_RENAME_REGION_UNCERTAIN",
            "PDF_RENAME_OCR_REVIEW_REQUIRED", "PDF_RENAME_TARGET_COLLISION",
            "PDF_RENAME_MANUAL_APPLIED", "PDF_RENAME_MANUAL_TARGET_INVALID",
        } for issue in self.issues)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_file_name": self.source_file_name,
            "target_file_name": self.target_file_name,
            "interval_name": self.interval_name,
            "status": self.status,
            "fields": [field.as_dict() for field in self.fields],
            "issues": [issue.as_dict() for issue in self.issues],
            "manual_override": self.manual_override,
            "manual_override_allowed": self.manual_override_allowed,
        }


class RegionRecognizer(Protocol):
    def __call__(
        self,
        pdf_bytes: bytes,
        region: NormalizedRegion,
    ) -> RecognizedRegionValue: ...


class PdfRenameRule(Protocol):
    definition: PdfRenameRuleDefinition

    def create_plan(
        self,
        source: PdfRenameSource,
        recognizer: RegionRecognizer,
    ) -> PdfRenamePlan: ...


@dataclass(frozen=True)
class PdfRenamePreview:
    rule: PdfRenameRuleDefinition
    items: tuple[PdfRenamePlan, ...]
    preview_token: str

    @property
    def ready_count(self) -> int:
        return sum(item.status == "READY" for item in self.items)

    @property
    def review_count(self) -> int:
        return sum(item.status == "REVIEW" for item in self.items)

    @property
    def error_count(self) -> int:
        return sum(item.status == "ERROR" for item in self.items)

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule.as_dict(),
            "items": [item.as_dict() for item in self.items],
            "preview_token": self.preview_token,
            "summary": {
                "total": len(self.items),
                "ready": self.ready_count,
                "review": self.review_count,
                "error": self.error_count,
            },
        }


class PdfRenameServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        action: str,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.status_code = status_code


class PdfRenameRuleBase:
    """Base class for one business-specific fixed-region rename rule.

    A new requirement should get one subclass with its own immutable definition
    and interval parser. The batch service and API stay unchanged.
    """

    definition: PdfRenameRuleDefinition

    def build_interval_name(
        self,
        values: Mapping[str, RecognizedRegionValue],
    ) -> str:
        raise NotImplementedError

    def build_target_file_name(self, interval_name: str) -> str:
        from .service import safe_pdf_file_name

        return safe_pdf_file_name(interval_name)

    def create_plan(
        self,
        source: PdfRenameSource,
        recognizer: RegionRecognizer,
    ) -> PdfRenamePlan:
        values: list[RecognizedRegionValue] = []
        issues: list[PdfRenameIssue] = []
        for region in self.definition.regions:
            try:
                value = recognizer(source.content, region)
            except PdfRenameServiceError as exc:
                issues.append(PdfRenameIssue(exc.code, exc.message))
                continue
            values.append(value)
            if region.required and not value.normalized_text:
                issues.append(
                    PdfRenameIssue(
                        "PDF_RENAME_REGION_EMPTY",
                        f"固定区域“{region.label}”没有识别到文字。",
                    )
                )

        if issues:
            return PdfRenamePlan(
                source_file_name=source.source_file_name,
                target_file_name="",
                interval_name="",
                status="ERROR",
                fields=tuple(values),
                issues=tuple(issues),
            )

        by_key = {value.key: value for value in values}
        try:
            interval_name = self.build_interval_name(by_key).strip()
        except ValueError as exc:
            return PdfRenamePlan(
                source_file_name=source.source_file_name,
                target_file_name="",
                interval_name="",
                status="ERROR",
                fields=tuple(values),
                issues=(PdfRenameIssue("PDF_RENAME_INTERVAL_INVALID", str(exc)),),
            )
        if not interval_name:
            return PdfRenamePlan(
                source_file_name=source.source_file_name,
                target_file_name="",
                interval_name="",
                status="ERROR",
                fields=tuple(values),
                issues=(PdfRenameIssue("PDF_RENAME_INTERVAL_EMPTY", "规则没有生成区间名。"),),
            )

        try:
            target = self.build_target_file_name(interval_name)
        except ValueError as exc:
            return PdfRenamePlan(
                source_file_name=source.source_file_name,
                target_file_name="",
                interval_name=interval_name,
                status="ERROR",
                fields=tuple(values),
                issues=(PdfRenameIssue("PDF_RENAME_TARGET_INVALID", str(exc)),),
            )
        needs_review = any(
            value.route == "LOCAL_OCR"
            or (value.confidence is not None and value.confidence < 0.85)
            for value in values
        )
        return PdfRenamePlan(
            source_file_name=source.source_file_name,
            target_file_name=target,
            interval_name=interval_name,
            status="REVIEW" if needs_review else "READY",
            fields=tuple(values),
            issues=(
                PdfRenameIssue(
                    "PDF_RENAME_OCR_REVIEW_REQUIRED",
                    "区间名来自扫描区域 OCR，请对照原 PDF 复核。",
                ),
            )
            if needs_review
            else (),
        )


def replace_plan_issues(
    plan: PdfRenamePlan,
    issues: Sequence[PdfRenameIssue],
    *,
    status: str = "ERROR",
) -> PdfRenamePlan:
    return PdfRenamePlan(
        source_file_name=plan.source_file_name,
        target_file_name=plan.target_file_name,
        interval_name=plan.interval_name,
        status=status,
        fields=plan.fields,
        issues=tuple(issues),
        manual_override=plan.manual_override,
    )
