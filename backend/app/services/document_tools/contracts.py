from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProcessingMode(StrEnum):
    AUTO = "AUTO"
    LOCAL = "LOCAL"
    QWEN = "QWEN"

    @classmethod
    def parse(cls, value: str) -> ProcessingMode:
        try:
            return cls(value.strip().upper())
        except ValueError as exc:
            raise DocumentToolError(
                "DOCUMENT_PROCESSING_MODE_INVALID",
                "处理模式无效，只支持 AUTO、LOCAL 或 QWEN。",
                action="请选择自动、仅本地或千问增强后重试。",
            ) from exc


class DocumentToolError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        action: str = "请稍后重试；若持续失败，请联系管理员并提供错误码。",
        retryable: bool = False,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.retryable = retryable
        self.status_code = status_code


class OcrBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50_000)
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = Field(default=0.85, ge=0, le=1)


class OcrPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1, le=200)
    blocks: tuple[OcrBlock, ...] = Field(default=(), max_length=10_000)


class OcrResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: tuple[OcrPage, ...] = Field(min_length=1, max_length=200)


class TableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(default="", max_length=10_000)
    confidence: float = Field(default=0.9, ge=0, le=1)


class StructuredTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    header: tuple[TableCell, ...] = Field(min_length=1, max_length=200)
    rows: tuple[tuple[TableCell, ...], ...] = Field(default=(), max_length=10_000)
    continuation_key: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.9, ge=0, le=1)

    @field_validator("continuation_key", mode="before")
    @classmethod
    def normalize_empty_continuation_key(cls, value: object) -> object:
        # Qwen commonly emits JSON null when the table does not continue. It is
        # semantically identical to an empty key and must not invalidate an
        # otherwise well-formed single-page table.
        return "" if value is None else value

    @model_validator(mode="after")
    def validate_width(self) -> StructuredTable:
        width = len(self.header)
        if any(len(row) != width for row in self.rows):
            raise ValueError("table row width must match header width")
        return self


class StructuredTables(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tables: tuple[StructuredTable, ...] = Field(default=(), max_length=100)
