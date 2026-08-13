from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from types import MappingProxyType
from typing import Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from PIL import Image
from pypdf import PdfReader


MAX_GROUPS_PER_BATCH = 39
MAX_FILES_PER_GROUP = 25
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
MAX_BATCH_SIZE_BYTES = 250 * 1024 * 1024
MAX_TARGET_FILE_NAME_CHARS = 200
RENAME_RULE_VERSION = "qc-report-rename-v1"

_COUNTRY_CODE_RE = re.compile(r"[A-Za-z]{2,3}")
_DIGITS_RE = re.compile(r"[0-9]+")
_INVALID_FILE_CHARS_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]+')
_WHITESPACE_RE = re.compile(r"\s+")
_UNDERSCORE_RE = re.compile(r"_+")
_WINDOWS_RESERVED_STEMS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ReportRenameBatchError(ValueError):
    """The complete request is invalid and cannot be processed safely."""


@dataclass(frozen=True)
class ReportSourceFile:
    source_file_name: str
    content: bytes
    sequence: int | None = None


@dataclass(frozen=True)
class ReportRenameGroup:
    group_id: str
    files: tuple[ReportSourceFile, ...]
    is_caixing: bool
    item_number: str
    po: str
    actual_inspection_date: date | datetime | str
    export_country: str | None = None
    report_number: str | None = None
    quantity: str | None = None


@dataclass(frozen=True)
class RenameIssue:
    code: str
    message: str
    source_file_name: str | None = None


@dataclass(frozen=True)
class RenamedFile:
    source_file_name: str
    target_file_name: str
    content: bytes
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ReportGroupRenameResult:
    group_id: str
    success: bool
    base_name: str | None
    files: tuple[RenamedFile, ...]
    issues: tuple[RenameIssue, ...]


@dataclass(frozen=True)
class ReportRenameBatchResult:
    archive_bytes: bytes
    archive_file_name: str
    output_files: Mapping[str, bytes]
    group_results: tuple[ReportGroupRenameResult, ...]
    fingerprint: str

    @property
    def successful_group_count(self) -> int:
        return sum(result.success for result in self.group_results)

    @property
    def failed_group_count(self) -> int:
        return len(self.group_results) - self.successful_group_count


def _issue(code: str, message: str, source_file_name: str | None = None) -> RenameIssue:
    return RenameIssue(code=code, message=message, source_file_name=source_file_name)


def _normalized_identifier(value: object, label: str) -> tuple[str | None, RenameIssue | None]:
    if not isinstance(value, str):
        return None, _issue("FIELD_TYPE_INVALID", f"{label}必须是文本。")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None, _issue("FIELD_REQUIRED", f"缺少{label}。")
    normalized = _INVALID_FILE_CHARS_RE.sub("_", normalized)
    normalized = _WHITESPACE_RE.sub("_", normalized)
    normalized = _UNDERSCORE_RE.sub("_", normalized).strip(" ._")
    if not normalized:
        return None, _issue("FIELD_INVALID", f"{label}不能形成有效文件名。")
    if normalized.casefold() in _WINDOWS_RESERVED_STEMS:
        normalized = f"_{normalized}"
    return normalized, None


def _country_code(value: object) -> tuple[str | None, RenameIssue | None]:
    if not isinstance(value, str):
        return None, _issue("COUNTRY_CODE_INVALID", "出口国必须使用2或3位英文国家代码。")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not _COUNTRY_CODE_RE.fullmatch(normalized):
        return None, _issue("COUNTRY_CODE_INVALID", "出口国必须使用2或3位英文国家代码。")
    return normalized.upper(), None


def _quantity(value: object) -> tuple[str | None, RenameIssue | None]:
    if not isinstance(value, str):
        return None, _issue("QUANTITY_INVALID", "数量必须是纯数字文本。")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not _DIGITS_RE.fullmatch(normalized):
        return None, _issue("QUANTITY_INVALID", "数量必须只包含0至9。")
    return normalized, None


def _inspection_date(value: object) -> tuple[str | None, RenameIssue | None]:
    parsed: date
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).strip()
        try:
            parsed = datetime.strptime(normalized, "%Y%m%d").date() if _DIGITS_RE.fullmatch(normalized) and len(normalized) == 8 else date.fromisoformat(normalized)
        except ValueError:
            return None, _issue("INSPECTION_DATE_INVALID", "实际验货日期必须是有效的YYYY-MM-DD或YYYYMMDD日期。")
    else:
        return None, _issue("INSPECTION_DATE_INVALID", "实际验货日期格式无效。")
    return parsed.strftime("%Y%m%d"), None


def _source_extension(source_file_name: object) -> str:
    if not isinstance(source_file_name, str):
        return ""
    safe_name = re.split(r"[\\/]", unicodedata.normalize("NFKC", source_file_name))[-1]
    dot = safe_name.rfind(".")
    return safe_name[dot:].casefold() if dot >= 0 else ""


def _validate_pdf(content: bytes) -> bool:
    if not content.lstrip().startswith(b"%PDF-"):
        return False
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            return False
        return len(reader.pages) > 0
    except Exception:
        return False


def _validate_jpeg(content: bytes) -> bool:
    if len(content) < 4 or not content.startswith(b"\xff\xd8") or not content.endswith(b"\xff\xd9"):
        return False
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "JPEG":
                return False
            image.verify()
        return True
    except Exception:
        return False


def _field_base_name(group: ReportRenameGroup) -> tuple[str | None, list[RenameIssue]]:
    issues: list[RenameIssue] = []
    item_number, item_issue = _normalized_identifier(group.item_number, "客户货号")
    po, po_issue = _normalized_identifier(group.po, "PO")
    inspection_date, date_issue = _inspection_date(group.actual_inspection_date)
    issues.extend(issue for issue in (item_issue, po_issue, date_issue) if issue is not None)

    if group.is_caixing:
        report_number, report_issue = _normalized_identifier(group.report_number, "报告号")
        quantity, quantity_issue = _quantity(group.quantity)
        issues.extend(issue for issue in (report_issue, quantity_issue) if issue is not None)
        parts = (report_number, item_number, po, quantity, inspection_date)
    else:
        export_country, country_issue = _country_code(group.export_country)
        issues.extend(issue for issue in (country_issue,) if issue is not None)
        parts = (export_country, item_number, po, inspection_date)

    if issues or any(part is None for part in parts):
        return None, issues
    base_name = "_".join(part for part in parts if part is not None)
    if base_name.casefold() in _WINDOWS_RESERVED_STEMS:
        issues.append(_issue("TARGET_NAME_RESERVED", "目标文件名是Windows保留名称。"))
    if len(f"{base_name}_00.jpeg") > MAX_TARGET_FILE_NAME_CHARS:
        issues.append(_issue("TARGET_NAME_TOO_LONG", f"目标文件名不能超过{MAX_TARGET_FILE_NAME_CHARS}个字符。"))
    return (None, issues) if issues else (base_name, [])


def _validate_group(group: ReportRenameGroup) -> ReportGroupRenameResult:
    issues: list[RenameIssue] = []
    group_id = unicodedata.normalize("NFKC", group.group_id).strip() if isinstance(group.group_id, str) else ""
    if not group_id:
        issues.append(_issue("GROUP_ID_REQUIRED", "报告组必须有稳定的组ID。"))
    if not group.files:
        issues.append(_issue("FILES_REQUIRED", "报告组没有文件。"))
    if len(group.files) > MAX_FILES_PER_GROUP:
        issues.append(_issue("TOO_MANY_FILES", f"每个报告组最多允许{MAX_FILES_PER_GROUP}个文件。"))

    base_name, field_issues = _field_base_name(group)
    issues.extend(field_issues)
    pdf_files: list[ReportSourceFile] = []
    image_files: list[ReportSourceFile] = []

    for source in group.files:
        source_name = source.source_file_name if isinstance(source.source_file_name, str) else ""
        if not source_name.strip():
            issues.append(_issue("SOURCE_NAME_REQUIRED", "上传文件缺少显示名称。"))
            continue
        if not isinstance(source.content, bytes):
            issues.append(_issue("FILE_CONTENT_INVALID", "文件内容必须是bytes。", source_name))
            continue
        if not source.content:
            issues.append(_issue("FILE_EMPTY", "文件为空。", source_name))
            continue
        if len(source.content) > MAX_FILE_SIZE_BYTES:
            issues.append(_issue("FILE_TOO_LARGE", f"单个文件不能超过{MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB。", source_name))
            continue

        extension = _source_extension(source_name)
        if extension == ".pdf":
            pdf_files.append(source)
            if not _validate_pdf(source.content):
                issues.append(_issue("PDF_INVALID", "PDF扩展名、文件头或文件结构无效。", source_name))
        elif extension in {".jpg", ".jpeg"}:
            image_files.append(source)
            if not _validate_jpeg(source.content):
                issues.append(_issue("JPEG_INVALID", "JPG/JPEG扩展名、文件头或图片结构无效。", source_name))
        else:
            issues.append(_issue("FILE_TYPE_UNSUPPORTED", "只支持PDF、JPG和JPEG文件。", source_name))

    if len(pdf_files) != 1:
        issues.append(_issue("PDF_COUNT_INVALID", "每个报告组必须且只能包含1个PDF。"))
    if not image_files:
        issues.append(_issue("JPEG_REQUIRED", "每个报告组至少需要1张JPG/JPEG图片。"))

    if len(image_files) > 1:
        sequences = [source.sequence for source in image_files]
        if any(not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1 for sequence in sequences):
            issues.append(_issue("IMAGE_SEQUENCE_REQUIRED", "多张图片必须提供从1开始的正整数顺序。"))
        elif len(set(sequences)) != len(sequences):
            issues.append(_issue("IMAGE_SEQUENCE_DUPLICATE", "同一报告组的图片顺序不能重复。"))

    if issues or base_name is None:
        return ReportGroupRenameResult(group_id=group_id, success=False, base_name=base_name, files=(), issues=tuple(issues))

    renamed: list[RenamedFile] = []
    pdf = pdf_files[0]
    renamed.append(_renamed_file(pdf, f"{base_name}.pdf"))
    if len(image_files) == 1:
        renamed.append(_renamed_file(image_files[0], f"{base_name}.jpg"))
    else:
        for position, image in enumerate(sorted(image_files, key=lambda source: source.sequence or 0), start=1):
            renamed.append(_renamed_file(image, f"{base_name}_{position:02d}.jpg"))

    return ReportGroupRenameResult(group_id=group_id, success=True, base_name=base_name, files=tuple(renamed), issues=())


def _renamed_file(source: ReportSourceFile, target_file_name: str) -> RenamedFile:
    return RenamedFile(
        source_file_name=source.source_file_name,
        target_file_name=target_file_name,
        content=source.content,
        sha256=hashlib.sha256(source.content).hexdigest(),
        size_bytes=len(source.content),
    )


def _with_issue(result: ReportGroupRenameResult, issue: RenameIssue) -> ReportGroupRenameResult:
    return ReportGroupRenameResult(
        group_id=result.group_id,
        success=False,
        base_name=result.base_name,
        files=(),
        issues=(*result.issues, issue),
    )


def _fingerprint(groups: Sequence[ReportRenameGroup]) -> str:
    canonical_groups: list[dict[str, object]] = []
    for group in groups:
        canonical_files: list[dict[str, object]] = []
        for source in group.files:
            extension = _source_extension(source.source_file_name)
            file_kind = "pdf" if extension == ".pdf" else "jpeg" if extension in {".jpg", ".jpeg"} else "unsupported"
            canonical_files.append(
                {
                    "sha256": hashlib.sha256(source.content).hexdigest() if isinstance(source.content, bytes) else "invalid",
                    "size": len(source.content) if isinstance(source.content, bytes) else -1,
                    "file_kind": file_kind,
                    "sequence": source.sequence,
                }
            )
        canonical_files.sort(key=lambda item: (str(item["file_kind"]), item["sequence"] or 0, str(item["sha256"])))
        canonical_groups.append(
            {
                "group_id": unicodedata.normalize("NFKC", group.group_id).strip() if isinstance(group.group_id, str) else "",
                "is_caixing": group.is_caixing,
                "item_number": group.item_number,
                "po": group.po,
                "actual_inspection_date": str(group.actual_inspection_date),
                "export_country": group.export_country,
                "report_number": group.report_number,
                "quantity": group.quantity,
                "files": canonical_files,
            }
        )
    canonical_groups.sort(key=lambda item: str(item["group_id"]).casefold())
    payload = json.dumps(
        {"rule_version": RENAME_RULE_VERSION, "groups": canonical_groups},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _deterministic_zip(files: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for file_name in sorted(files, key=lambda value: (value.casefold(), value)):
            info = ZipInfo(file_name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[file_name], compress_type=ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def rename_report_batch(groups: Sequence[ReportRenameGroup]) -> ReportRenameBatchResult:
    """Validate explicit report groups and create deterministic renamed output.

    A source filename is display/audit metadata only. Callers must form groups from
    business records or explicit user selection, never by parsing source filenames.
    A failed group contributes no output; valid unrelated groups still complete.
    """

    materialized = tuple(groups)
    if not materialized:
        raise ReportRenameBatchError("至少需要一个报告组。")
    if len(materialized) > MAX_GROUPS_PER_BATCH:
        raise ReportRenameBatchError(f"单批最多处理{MAX_GROUPS_PER_BATCH}个报告组。")
    total_size = sum(
        len(source.content)
        for group in materialized
        for source in group.files
        if isinstance(source.content, bytes)
    )
    if total_size > MAX_BATCH_SIZE_BYTES:
        raise ReportRenameBatchError(f"单批文件总大小不能超过{MAX_BATCH_SIZE_BYTES // (1024 * 1024)}MB。")

    results = [_validate_group(group) for group in materialized]

    group_id_indexes: dict[str, list[int]] = {}
    for index, result in enumerate(results):
        if result.group_id:
            group_id_indexes.setdefault(result.group_id.casefold(), []).append(index)
    for indexes in group_id_indexes.values():
        if len(indexes) > 1:
            for index in indexes:
                results[index] = _with_issue(results[index], _issue("GROUP_ID_DUPLICATE", "同一批次的报告组ID不能重复。"))

    target_indexes: dict[str, set[int]] = {}
    for index, result in enumerate(results):
        if result.success:
            for renamed in result.files:
                collision_key = unicodedata.normalize("NFKC", renamed.target_file_name).casefold()
                target_indexes.setdefault(collision_key, set()).add(index)
    for indexes in target_indexes.values():
        if len(indexes) > 1:
            for index in indexes:
                if results[index].success:
                    results[index] = _with_issue(results[index], _issue("TARGET_NAME_COLLISION", "目标文件名与同批其他报告组大小写不敏感冲突。"))

    ordered_results = tuple(sorted(results, key=lambda result: (result.group_id.casefold(), result.group_id)))
    output_files: dict[str, bytes] = {}
    for result in ordered_results:
        if result.success:
            for renamed in result.files:
                output_files[renamed.target_file_name] = renamed.content

    fingerprint = _fingerprint(materialized)
    immutable_files = MappingProxyType(dict(sorted(output_files.items(), key=lambda item: (item[0].casefold(), item[0]))))
    return ReportRenameBatchResult(
        archive_bytes=_deterministic_zip(immutable_files),
        archive_file_name=f"QC验货报告改名_{fingerprint[:12]}.zip",
        output_files=immutable_files,
        group_results=ordered_results,
        fingerprint=fingerprint,
    )
