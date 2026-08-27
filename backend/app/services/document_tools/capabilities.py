from __future__ import annotations

import importlib.util
import shutil

from app.core.config import Settings
from app.services.document_studio.renderers.office_pdf_renderer import (
    office_renderer_status,
)
from app.services.document_translation import document_translation_status


def _mode(available: bool, *, reason_code: str = "", reason: str = "") -> dict:
    return {
        "available": available,
        "reason_code": reason_code,
        "reason": reason,
    }


def document_tool_capabilities(settings: Settings) -> dict:
    office = office_renderer_status(settings.document_office_renderer_command)
    local_translation = document_translation_status(
        settings.document_translation_model_dir
    )
    enabled = settings.document_tools_enabled
    disabled_reason = "文档工具已被管理员关闭。"
    local_core = enabled
    office_available = enabled and office.available
    local_translation_available = enabled and bool(local_translation["available"])

    def local_modes(available: bool, *, reason_code: str = "", reason: str = "") -> dict:
        return {
            "AUTO": _mode(
                available,
                reason_code="" if available else reason_code,
                reason="" if available else reason,
            ),
            "LOCAL": _mode(
                available,
                reason_code="" if available else reason_code,
                reason="" if available else reason,
            ),
        }

    tools = {
        "pdf-to-excel": {
            "available": local_core,
            "reason_code": "" if local_core else "DOCUMENT_TOOLS_DISABLED",
            "reason": "" if local_core else disabled_reason,
            "modes": local_modes(
                local_core,
                reason_code="DOCUMENT_TOOLS_DISABLED",
                reason=disabled_reason,
            ),
        },
        "pdf-to-word": {
            "available": local_core,
            "reason_code": "" if local_core else "DOCUMENT_TOOLS_DISABLED",
            "reason": "" if local_core else disabled_reason,
            "modes": local_modes(
                local_core,
                reason_code="DOCUMENT_TOOLS_DISABLED",
                reason=disabled_reason,
            ),
        },
        "word-to-pdf": {
            "available": office_available,
            "reason_code": (
                "" if office_available else office.reason_code or "LIBREOFFICE_NOT_INSTALLED"
            ),
            "reason": (
                "" if office_available else "服务器未安装或无法找到 LibreOffice。"
            ),
            "modes": local_modes(
                office_available,
                reason_code=office.reason_code or "LIBREOFFICE_NOT_INSTALLED",
                reason="服务器未安装或无法找到 LibreOffice。",
            ),
        },
        "pdf-translation": {
            "available": local_translation_available,
            "reason_code": (
                "" if local_translation_available else "LOCAL_TRANSLATION_MODEL_MISSING"
            ),
            "reason": (
                "" if local_translation_available else "服务器未安装本地翻译模型。"
            ),
            "modes": local_modes(
                local_translation_available,
                reason_code="LOCAL_TRANSLATION_MODEL_MISSING",
                reason="服务器未安装本地翻译模型。",
            ),
        },
        "pdf-split": {
            "available": local_core,
            "reason_code": "" if local_core else "DOCUMENT_TOOLS_DISABLED",
            "reason": "" if local_core else disabled_reason,
            "modes": local_modes(
                local_core,
                reason_code="DOCUMENT_TOOLS_DISABLED",
                reason=disabled_reason,
            ),
        },
    }
    return {
        "enabled": enabled,
        "default_mode": "AUTO",
        "tools": tools,
        "providers": {
            "libreoffice": {
                "available": office.available,
                "version": office.version,
                "reason_code": office.reason_code,
            },
            "local_translation": local_translation,
        },
        "limits": {
            "max_file_bytes": settings.document_tool_max_file_bytes,
            "max_pdf_pages": settings.document_tool_max_pdf_pages,
            "temp_ttl_minutes": settings.document_tool_temp_ttl_minutes,
        },
    }


def document_tool_diagnostics(settings: Settings) -> dict:
    capabilities = document_tool_capabilities(settings)
    office = office_renderer_status(settings.document_office_renderer_command)
    return {
        "libreoffice": {
            "available": office.available,
            "command": office.executable or office.command,
            "version": office.version,
            "last_error": "" if office.available else office.reason_code,
        },
        "ocr": {
            "tesseract": shutil.which("tesseract") is not None,
            "rapidocr": importlib.util.find_spec("rapidocr") is not None,
        },
        "local_translation": capabilities["providers"]["local_translation"],
        "limits": capabilities["limits"],
    }
