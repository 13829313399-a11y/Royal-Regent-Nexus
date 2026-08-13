from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import warnings
import zipfile
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from app.services.ai.artifacts.contracts import (
    ALLOWED_TYPES,
    MAX_DOCUMENT_BYTES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_OOXML_COMPRESSION_RATIO,
    MAX_OOXML_ENTRIES,
    MAX_OOXML_EXPANDED_BYTES,
    MAX_PDF_PAGES,
    ArtifactContentClass,
    ValidatedArtifact,
)


class ArtifactValidationError(ValueError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _invalid(code: str, message: str) -> ArtifactValidationError:
    return ArtifactValidationError(code, message)


def normalize_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKC", filename or "")
    normalized = normalized.replace("\\", "/").rsplit("/", 1)[-1]
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
    ).strip().strip(".")
    if not normalized or normalized in {".", ".."}:
        raise _invalid("AI_ARTIFACT_FILENAME_INVALID", "文件名无效。")
    encoded = normalized.encode("utf-8")
    if len(encoded) > 255:
        raise _invalid("AI_ARTIFACT_FILENAME_INVALID", "文件名过长。")
    return normalized


def _extension(filename: str) -> str:
    lower = filename.casefold()
    extension = next((item for item in ALLOWED_TYPES if lower.endswith(item)), "")
    if not extension or lower.removesuffix(extension).endswith("."):
        raise _invalid("AI_ARTIFACT_TYPE_NOT_ALLOWED", "不支持该文件类型。")
    return extension


def _validate_exact_image_boundary(data: bytes, extension: str) -> None:
    if extension == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or not data.endswith(
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        ):
            raise _invalid("AI_ARTIFACT_MAGIC_MISMATCH", "图片容器无效。")
    elif extension in {".jpg", ".jpeg"}:
        if not data.startswith(b"\xff\xd8\xff") or not data.endswith(b"\xff\xd9"):
            raise _invalid("AI_ARTIFACT_MAGIC_MISMATCH", "图片容器无效。")
    elif extension == ".webp" and (
        len(data) < 12
        or data[:4] != b"RIFF"
        or data[8:12] != b"WEBP"
        or int.from_bytes(data[4:8], "little") + 8 != len(data)
    ):
        raise _invalid("AI_ARTIFACT_MAGIC_MISMATCH", "图片容器无效。")


def _validate_image(data: bytes, extension: str) -> None:
    _validate_exact_image_boundary(data, extension)
    expected_format = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
    }[extension]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != expected_format:
                    raise _invalid(
                        "AI_ARTIFACT_MAGIC_MISMATCH", "图片类型与扩展名不一致。"
                    )
                if bool(getattr(image, "is_animated", False)) or int(
                    getattr(image, "n_frames", 1)
                ) != 1:
                    raise _invalid(
                        "AI_ARTIFACT_ACTIVE_CONTENT", "不接受动画图片。"
                    )
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise _invalid(
                        "AI_ARTIFACT_PIXEL_LIMIT", "图片像素超过允许上限。"
                    )
                image.verify()
    except ArtifactValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise _invalid("AI_ARTIFACT_INVALID_IMAGE", "图片损坏或无法安全解码。") from exc


def _safe_zip_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return (
        bool(normalized)
        and not normalized.startswith("/")
        and not re.match(r"^[A-Za-z]:", normalized)
        and ".." not in path.parts
    )


def _validate_ooxml(data: bytes, extension: str) -> None:
    if not data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        raise _invalid("AI_ARTIFACT_MAGIC_MISMATCH", "Office 文件容器无效。")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_OOXML_ENTRIES:
                raise _invalid("AI_ARTIFACT_ZIP_LIMIT", "Office 文件条目过多。")
            names = {entry.filename.replace("\\", "/") for entry in entries}
            required = (
                {"[Content_Types].xml", "xl/workbook.xml"}
                if extension == ".xlsx"
                else {"[Content_Types].xml", "word/document.xml"}
            )
            if not required <= names:
                raise _invalid(
                    "AI_ARTIFACT_MAGIC_MISMATCH", "Office 文件类型与扩展名不一致。"
                )

            expanded = 0
            compressed = 0
            active_name_tokens = (
                "vbaproject",
                "macrosheet",
                "/activex/",
                "/embeddings/",
                "/externallinks/",
                "/customui/",
                "oleobject",
            )
            for entry in entries:
                if not _safe_zip_name(entry.filename):
                    raise _invalid(
                        "AI_ARTIFACT_ZIP_PATH", "Office 文件包含不安全路径。"
                    )
                if entry.flag_bits & 0x1:
                    raise _invalid(
                        "AI_ARTIFACT_ENCRYPTED", "不接受加密 Office 文件。"
                    )
                unix_mode = entry.external_attr >> 16
                if unix_mode & 0o170000 == 0o120000:
                    raise _invalid(
                        "AI_ARTIFACT_ZIP_PATH", "Office 文件包含不安全链接。"
                    )
                lower_name = "/" + entry.filename.replace("\\", "/").casefold()
                if any(token in lower_name for token in active_name_tokens):
                    raise _invalid(
                        "AI_ARTIFACT_ACTIVE_CONTENT", "不接受含宏或活动内容的 Office 文件。"
                    )
                expanded += entry.file_size
                compressed += entry.compress_size
                if entry.file_size > MAX_OOXML_EXPANDED_BYTES:
                    raise _invalid("AI_ARTIFACT_ZIP_LIMIT", "Office 文件解压体积过大。")
                if entry.file_size and (
                    entry.compress_size == 0
                    or entry.file_size > entry.compress_size * MAX_OOXML_COMPRESSION_RATIO
                ):
                    raise _invalid("AI_ARTIFACT_ZIP_RATIO", "Office 文件压缩比过高。")
            if expanded > MAX_OOXML_EXPANDED_BYTES:
                raise _invalid("AI_ARTIFACT_ZIP_LIMIT", "Office 文件解压体积过大。")
            if expanded and (
                compressed == 0
                or expanded > compressed * MAX_OOXML_COMPRESSION_RATIO
            ):
                raise _invalid("AI_ARTIFACT_ZIP_RATIO", "Office 文件压缩比过高。")

            for entry in entries:
                lower_name = entry.filename.casefold()
                if not lower_name.endswith((".xml", ".rels")):
                    continue
                xml = archive.read(entry)
                folded = xml.lower()
                if (
                    re.search(rb"targetmode\s*=\s*['\"]external['\"]", folded)
                    or b"<!doctype" in folded
                    or b"<!entity" in folded
                    or b"vbaproject" in folded
                    or b"oleobject" in folded
                ):
                    raise _invalid(
                        "AI_ARTIFACT_ACTIVE_CONTENT", "不接受含外部关系或活动内容的 Office 文件。"
                    )
    except ArtifactValidationError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise _invalid("AI_ARTIFACT_INVALID_OOXML", "Office 文件损坏或无法安全读取。") from exc


def _validate_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise _invalid("AI_ARTIFACT_MAGIC_MISMATCH", "PDF 魔数无效。")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise _invalid("AI_ARTIFACT_ENCRYPTED", "不接受加密 PDF。")
        page_count = len(reader.pages)
        if page_count <= 0 or page_count > MAX_PDF_PAGES:
            raise _invalid("AI_ARTIFACT_PAGE_LIMIT", "PDF 页数超过允许上限。")
    except ArtifactValidationError:
        raise
    except Exception as exc:
        raise _invalid("AI_ARTIFACT_INVALID_PDF", "PDF 损坏或无法安全读取。") from exc


def _validate_csv(data: bytes) -> None:
    if b"\x00" in data:
        raise _invalid("AI_ARTIFACT_MAGIC_MISMATCH", "CSV 包含二进制内容。")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _invalid("AI_ARTIFACT_INVALID_CSV", "CSV 必须使用 UTF-8 编码。") from exc
    if not text.strip():
        raise _invalid("AI_ARTIFACT_EMPTY", "文件不能为空。")


def validate_artifact_upload(
    *, filename: str, declared_mime_type: str, data: bytes
) -> ValidatedArtifact:
    safe_filename = normalize_filename(filename)
    extension = _extension(safe_filename)
    expected_mime, content_class = ALLOWED_TYPES[extension]
    mime_type = (declared_mime_type or "").strip().casefold()
    if mime_type != expected_mime:
        raise _invalid(
            "AI_ARTIFACT_MIME_MISMATCH", "文件声明类型与扩展名不一致。"
        )
    if not data:
        raise _invalid("AI_ARTIFACT_EMPTY", "文件不能为空。")
    limit = MAX_IMAGE_BYTES if content_class is ArtifactContentClass.IMAGE else MAX_DOCUMENT_BYTES
    if len(data) > limit:
        raise _invalid("AI_ARTIFACT_TOO_LARGE", "文件超过允许大小。")

    if extension in {".xlsx", ".docx"}:
        _validate_ooxml(data, extension)
    elif extension == ".pdf":
        _validate_pdf(data)
    elif extension == ".csv":
        _validate_csv(data)
    else:
        _validate_image(data, extension)

    return ValidatedArtifact(
        original_filename=safe_filename,
        normalized_extension=extension,
        declared_mime_type=mime_type,
        detected_mime_type=expected_mime,
        content_class=content_class,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        data=data,
    )
