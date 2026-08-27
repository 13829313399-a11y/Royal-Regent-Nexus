from __future__ import annotations

from enum import StrEnum


class ProcessingMode(StrEnum):
    AUTO = "AUTO"
    LOCAL = "LOCAL"

    @classmethod
    def parse(cls, value: str) -> ProcessingMode:
        try:
            return cls(value.strip().upper())
        except ValueError as exc:
            raise DocumentToolError(
                "DOCUMENT_PROCESSING_MODE_INVALID",
                "处理模式无效，只支持 AUTO 或 LOCAL。",
                action="请选择自动或仅本地模式后重试。",
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
