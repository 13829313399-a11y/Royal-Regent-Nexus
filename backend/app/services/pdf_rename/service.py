from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .contracts import (
    PdfRenameIssue,
    PdfRenameManualOverride,
    PdfRenamePlan,
    PdfRenamePreview,
    PdfRenameRule,
    PdfRenameServiceError,
    PdfRenameSource,
    RegionRecognizer,
    replace_plan_issues,
)
from .ocr import _validate_page, recognize_fixed_region
from .registry import get_pdf_rename_rule

MAX_PDF_RENAME_FILES = 50
MAX_PDF_RENAME_BATCH_BYTES = 200 * 1024 * 1024
MAX_TARGET_STEM_CHARS = 160
_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_STEMS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class PdfRenameArchive:
    content: bytes
    output_file_name: str
    file_count: int
    preview: PdfRenamePreview


def safe_pdf_file_name(interval_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", interval_name)
    normalized = _INVALID_FILENAME_CHARS.sub("_", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    normalized = normalized[:MAX_TARGET_STEM_CHARS].rstrip(" .")
    if not normalized:
        raise ValueError("区间名清洗后为空，无法生成文件名。")
    if normalized.casefold() in _WINDOWS_RESERVED_STEMS:
        normalized = f"_{normalized}"
    return f"{normalized}.pdf"


def parse_manual_overrides(value: str) -> tuple[PdfRenameManualOverride, ...]:
    try:
        if len(value) > 32_000:
            raise ValueError
        rows = json.loads(value)
        if not isinstance(rows, list) or len(rows) > MAX_PDF_RENAME_FILES:
            raise ValueError
        for row in rows:
            if (not isinstance(row, dict)
                or set(row) != {"source_index", "target_file_name", "confirmed"}
                or type(row["source_index"]) is not int
                or not isinstance(row["target_file_name"], str)
                or type(row["confirmed"]) is not bool):
                raise ValueError
        return tuple(PdfRenameManualOverride(**row) for row in rows)
    except (ValueError, TypeError) as exc:
        raise PdfRenameServiceError(
            "PDF_RENAME_MANUAL_INVALID", "人工改名参数格式无效。",
            action="请重新输入人工文件名并逐份确认放行。", status_code=400,
        ) from exc


def _manual_target(value: str) -> str:
    name = unicodedata.normalize("NFKC", value).strip()
    if not name.casefold().endswith(".pdf"):
        if "." in name:
            raise ValueError("人工文件名须使用 .pdf 扩展名。")
        name += ".pdf"
    stem = name[:-4]
    if (not stem or stem != stem.strip(" .") or _INVALID_FILENAME_CHARS.search(name)
        or any(unicodedata.category(char).startswith("C") for char in name)
        or stem.split(".")[0].casefold() in _WINDOWS_RESERVED_STEMS):
        raise ValueError("人工文件名不能为空，不能包含路径、非法字符、末尾空格/句点或系统保留名。")
    if len(stem) > MAX_TARGET_STEM_CHARS or len(name.encode("utf-8")) > 240:
        raise ValueError("人工文件名过长，请缩短后重新确认；系统不会自动截断。")
    return name


def _apply_manual_override(plan: PdfRenamePlan, source: PdfRenameSource,
                           override: PdfRenameManualOverride) -> PdfRenamePlan:
    if not plan.manual_override_allowed:
        return plan
    try:
        # A manual name never bypasses actual PDF structure validation.
        _validate_page(source.content, 1)
        target = _manual_target(override.target_file_name)
    except PdfRenameServiceError as exc:
        return replace_plan_issues(plan, (*plan.issues, PdfRenameIssue(exc.code, exc.message)))
    except ValueError as exc:
        return replace_plan_issues(plan, (*plan.issues, PdfRenameIssue("PDF_RENAME_MANUAL_TARGET_INVALID", str(exc))))
    return replace(
        plan, target_file_name=target, interval_name=target[:-4], status="REVIEW", manual_override=True,
        issues=(*plan.issues, PdfRenameIssue(
            "PDF_RENAME_MANUAL_APPLIED", "已按人工文件名放行；原识别结果仅供参考，请核对最终文件名。",
        )),
    )


def _validate_sources(sources: tuple[PdfRenameSource, ...]) -> None:
    if not sources:
        raise PdfRenameServiceError(
            "PDF_RENAME_FILES_REQUIRED",
            "请至少上传一份 PDF。",
            action="请选择需要批量改名的 PDF 文件。",
            status_code=400,
        )
    if len(sources) > MAX_PDF_RENAME_FILES:
        raise PdfRenameServiceError(
            "PDF_RENAME_TOO_MANY_FILES",
            f"单批最多处理 {MAX_PDF_RENAME_FILES} 份 PDF。",
            action="请拆分成多个批次处理。",
            status_code=413,
        )
    if sum(len(source.content) for source in sources) > MAX_PDF_RENAME_BATCH_BYTES:
        raise PdfRenameServiceError(
            "PDF_RENAME_BATCH_TOO_LARGE",
            "单批 PDF 总大小不能超过 200 MB。",
            action="请减少本批文件数量或压缩扫描件后重试。",
            status_code=413,
        )


def _preview_token(
    rule: PdfRenameRule,
    sources: tuple[PdfRenameSource, ...],
    items: tuple[PdfRenamePlan, ...],
) -> str:
    payload = {
        "rule_id": rule.definition.rule_id,
        "rule_version": rule.definition.version,
        "files": [
            {
                "source": source.source_file_name,
                "sha256": hashlib.sha256(source.content).hexdigest(),
                "target": item.target_file_name,
                "status": item.status,
                "manual_override": item.manual_override,
            }
            for source, item in zip(sources, items, strict=True)
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_pdf_rename_preview(
    rule: PdfRenameRule,
    sources: tuple[PdfRenameSource, ...],
    *,
    recognizer: RegionRecognizer = recognize_fixed_region,
    manual_overrides: tuple[PdfRenameManualOverride, ...] = (),
) -> PdfRenamePreview:
    _validate_sources(sources)
    indexes: set[int] = set()
    for override in manual_overrides:
        if (type(override.source_index) is not int or not 0 <= override.source_index < len(sources)
            or override.source_index in indexes):
            raise PdfRenameServiceError(
                "PDF_RENAME_MANUAL_INVALID", "人工改名文件序号无效或重复。",
                action="请重新生成当前批次预览后逐份修改。", status_code=400,
            )
        indexes.add(override.source_index)
        if override.confirmed is not True:
            raise PdfRenameServiceError(
                "PDF_RENAME_MANUAL_CONFIRMATION_REQUIRED", "人工文件名尚未逐份确认放行。",
                action="请确认每份人工文件名后重新预览。", status_code=409,
            )
    plans = [rule.create_plan(source, recognizer) for source in sources]
    for override in manual_overrides:
        index = override.source_index
        plans[index] = _apply_manual_override(plans[index], sources[index], override)

    collisions: dict[str, list[int]] = {}
    for index, plan in enumerate(plans):
        if plan.target_file_name:
            key = unicodedata.normalize("NFKC", plan.target_file_name).casefold()
            collisions.setdefault(key, []).append(index)
    for indexes in collisions.values():
        if len(indexes) < 2:
            continue
        for index in indexes:
            plan = plans[index]
            plans[index] = replace_plan_issues(
                plan,
                (
                    *plan.issues,
                    PdfRenameIssue(
                        "PDF_RENAME_TARGET_COLLISION",
                        "该目标文件名与同批其他文件重复。",
                    ),
                ),
            )

    items = tuple(plans)
    return PdfRenamePreview(
        rule=rule.definition,
        items=items,
        preview_token=_preview_token(rule, sources, items),
    )


def preview_registered_pdf_rename_batch(
    rule_id: str,
    sources: tuple[PdfRenameSource, ...],
    *,
    factory_id: str,
    manual_overrides: tuple[PdfRenameManualOverride, ...] = (),
) -> PdfRenamePreview:
    rule = get_pdf_rename_rule(rule_id, factory_id)
    _validate_sources(sources)
    from .qwen import invalidate_sources
    invalidate_sources(source.content for source in sources)
    return build_pdf_rename_preview(rule, sources, manual_overrides=manual_overrides)


def _deterministic_zip(files: tuple[tuple[str, bytes], ...]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for file_name, content in sorted(files, key=lambda item: item[0].casefold()):
            info = ZipInfo(file_name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            archive.writestr(info, content, compress_type=ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def execute_pdf_rename_batch(
    rule: PdfRenameRule,
    sources: tuple[PdfRenameSource, ...],
    *,
    expected_preview_token: str,
    ocr_review_confirmed: bool = False,
    recognizer: RegionRecognizer = recognize_fixed_region,
    manual_overrides: tuple[PdfRenameManualOverride, ...] = (),
) -> PdfRenameArchive:
    preview = build_pdf_rename_preview(rule, sources, recognizer=recognizer, manual_overrides=manual_overrides)
    if not expected_preview_token or preview.preview_token != expected_preview_token:
        raise PdfRenameServiceError(
            "PDF_RENAME_PREVIEW_STALE",
            "当前文件或识别结果与上次预览不一致。",
            action="请重新生成预览并复核后再执行。",
            status_code=409,
        )
    if any(item.status == "ERROR" for item in preview.items):
        raise PdfRenameServiceError(
            "PDF_RENAME_PREVIEW_HAS_ERRORS",
            "预览中仍有错误，不能生成改名结果。",
            action="请处理重复文件名或识别错误后重新预览。",
        )
    if preview.review_count and not ocr_review_confirmed:
        raise PdfRenameServiceError(
            "PDF_RENAME_OCR_REVIEW_REQUIRED",
            "扫描区域 OCR 结果尚未确认。",
            action="请逐项复核区间名，勾选确认后再执行。",
            status_code=409,
        )
    archive_files = tuple(
        (item.target_file_name, source.content)
        for source, item in zip(sources, preview.items, strict=True)
    )
    fingerprint = preview.preview_token[:12]
    return PdfRenameArchive(
        content=_deterministic_zip(archive_files),
        output_file_name=f"PDF批量改名_{fingerprint}.zip",
        file_count=len(archive_files),
        preview=preview,
    )


def execute_registered_pdf_rename_batch(
    rule_id: str,
    sources: tuple[PdfRenameSource, ...],
    *,
    factory_id: str,
    expected_preview_token: str,
    ocr_review_confirmed: bool = False,
    manual_overrides: tuple[PdfRenameManualOverride, ...] = (),
) -> PdfRenameArchive:
    return execute_pdf_rename_batch(
        get_pdf_rename_rule(rule_id, factory_id),
        sources,
        expected_preview_token=expected_preview_token,
        ocr_review_confirmed=ocr_review_confirmed,
        manual_overrides=manual_overrides,
    )
