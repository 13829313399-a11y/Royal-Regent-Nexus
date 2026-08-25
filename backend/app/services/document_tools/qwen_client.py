from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from app.core.config import Settings
from app.services.ai.provider_factory import resolve_qwen_base_url
from app.services.document_tools.contracts import DocumentToolError

_SENSITIVE_LOGGERS = ("openai", "httpx", "httpcore", "httpx2")


@dataclass(frozen=True, slots=True)
class QwenStatus:
    configured: bool
    available: bool
    region: str
    ocr_model: str
    table_model: str
    translation_model: str
    reason_code: str = ""


def qwen_status(settings: Settings) -> QwenStatus:
    reason = ""
    if not settings.document_tools_enabled:
        reason = "DOCUMENT_TOOLS_DISABLED"
    elif not settings.effective_qwen_document_enabled:
        reason = "QWEN_DOCUMENT_DISABLED"
    elif not settings.ai_workspace_id.strip():
        reason = "QWEN_WORKSPACE_MISSING"
    elif not settings.dashscope_api_key.get_secret_value().strip():
        reason = "QWEN_API_KEY_MISSING"
    configured = not reason
    return QwenStatus(
        configured=configured,
        available=configured,
        region=settings.ai_region.strip() or "cn-beijing",
        ocr_model=settings.qwen_ocr_model,
        table_model=settings.qwen_table_model,
        translation_model=settings.qwen_translation_model,
        reason_code=reason,
    )


def create_qwen_client(settings: Settings, *, client: Any | None = None) -> Any:
    status = qwen_status(settings)
    if not status.available:
        raise DocumentToolError(
            status.reason_code or "QWEN_NOT_CONFIGURED",
            "千问文档服务尚未配置。",
            action="请管理员检查 QWEN_DOCUMENT_ENABLED、DASHSCOPE_API_KEY、AI_WORKSPACE_ID 和 AI_REGION。",
            status_code=503,
        )
    if client is not None:
        return client
    for name in _SENSITIVE_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    return OpenAI(
        api_key=settings.dashscope_api_key.get_secret_value(),
        base_url=resolve_qwen_base_url(settings),
        timeout=settings.qwen_document_timeout_seconds,
        max_retries=0,
    )


def convert_qwen_error(exc: Exception, *, operation: str) -> DocumentToolError:
    if isinstance(exc, DocumentToolError):
        return exc
    if isinstance(exc, RateLimitError):
        return DocumentToolError(
            "QWEN_RATE_LIMITED",
            f"千问{operation}服务当前繁忙。",
            action="请稍后重试，或改用仅本地模式。",
            retryable=True,
            status_code=503,
        )
    if isinstance(exc, APITimeoutError):
        return DocumentToolError(
            "QWEN_TIMEOUT",
            f"千问{operation}请求超时。",
            action="请重试；较长文档可先拆分后处理。",
            retryable=True,
            status_code=504,
        )
    if isinstance(exc, APIConnectionError):
        return DocumentToolError(
            "QWEN_UNREACHABLE",
            f"服务器暂时无法连接千问{operation}服务。",
            action="请管理员检查服务器到阿里云百炼的网络连接。",
            retryable=True,
            status_code=503,
        )
    if isinstance(exc, APIStatusError):
        retryable = exc.status_code == 429 or exc.status_code >= 500
        return DocumentToolError(
            "QWEN_PROVIDER_REJECTED",
            f"千问{operation}请求未成功。",
            action="请重试；若持续失败，请管理员检查模型授权、地域和配额。",
            retryable=retryable,
            status_code=503 if retryable else 422,
        )
    return DocumentToolError(
        "QWEN_RESPONSE_INVALID",
        f"千问{operation}返回了无法使用的结果。",
        action="请重试；若持续失败，请联系管理员并提供错误码。",
        retryable=True,
        status_code=502,
    )
