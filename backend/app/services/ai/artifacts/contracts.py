from dataclasses import dataclass
from enum import StrEnum


class ArtifactClassification(StrEnum):
    INTERNAL = "INTERNAL"
    CONFIDENTIAL_BUSINESS = "CONFIDENTIAL_BUSINESS"
    RESTRICTED = "RESTRICTED"


class ArtifactContentClass(StrEnum):
    WORKBOOK = "WORKBOOK"
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"


class ArtifactStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"
    EXPIRED = "EXPIRED"


class ArtifactScannerStatus(StrEnum):
    CLEAN = "CLEAN"
    REJECTED = "REJECTED"


class ArtifactParserStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class ArtifactDerivationType(StrEnum):
    ORIGINAL = "ORIGINAL"
    WORKBOOK_MAPPING = "WORKBOOK_MAPPING"
    TRANSLATION = "TRANSLATION"
    OCR = "OCR"
    REPORT = "REPORT"
    OTHER_DERIVED = "OTHER_DERIVED"


MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_PDF_PAGES = 200
MAX_OOXML_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_OOXML_COMPRESSION_RATIO = 100
MAX_OOXML_ENTRIES = 10_000

ALLOWED_TYPES: dict[str, tuple[str, ArtifactContentClass]] = {
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ArtifactContentClass.WORKBOOK,
    ),
    ".csv": ("text/csv", ArtifactContentClass.WORKBOOK),
    ".pdf": ("application/pdf", ArtifactContentClass.DOCUMENT),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ArtifactContentClass.DOCUMENT,
    ),
    ".png": ("image/png", ArtifactContentClass.IMAGE),
    ".jpg": ("image/jpeg", ArtifactContentClass.IMAGE),
    ".jpeg": ("image/jpeg", ArtifactContentClass.IMAGE),
    ".webp": ("image/webp", ArtifactContentClass.IMAGE),
}

CLASSIFICATION_RANK = {
    ArtifactClassification.INTERNAL: 1,
    ArtifactClassification.CONFIDENTIAL_BUSINESS: 2,
    ArtifactClassification.RESTRICTED: 3,
}


@dataclass(frozen=True, slots=True)
class ValidatedArtifact:
    original_filename: str
    normalized_extension: str
    declared_mime_type: str
    detected_mime_type: str
    content_class: ArtifactContentClass
    size_bytes: int
    sha256: str
    data: bytes
