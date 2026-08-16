from __future__ import annotations

import importlib.util
import shutil

from app.core.config import Settings
from app.services.document_studio.renderers.office_pdf_renderer import (
    office_renderer_status,
)
from app.services.document_tools.qwen_client import qwen_status
from app.services.document_translation import document_translation_status


def _mode(available: bool, *, reason_code: str = "", reason: str = "") -> dict:
    return {
        "available": available,
        "reason_code": reason_code,
        "reason": reason,
    }


def document_tool_capabilities(settings: Settings) -> dict:
    qwen = qwen_status(settings)
    office = office_renderer_status(settings.document_office_renderer_command)
    local_translation = document_translation_status(
        settings.document_translation_model_dir
    )
    enabled = settings.document_tools_enabled
    disabled_reason = "文档工具已被管理员关闭。"

    local_core = enabled
    qwen_available = enabled and qwen.available
    office_available = enabled and office.available
    local_translation_available = enabled and bool(local_translation["available"])
    tools = {
        "pdf-to-excel": {
            "available": local_core,
            "reason_code": "" if local_core else "DOCUMENT_TOOLS_DISABLED",
            "reason": "" if local_core else disabled_reason,
            "modes": {
                "AUTO": _mode(local_core),
                "LOCAL": _mode(local_core),
                "QWEN": _mode(
                    qwen_available,
                    reason_code="" if qwen_available else qwen.reason_code,
                    reason="" if qwen_available else "千问 OCR 或表格模型尚未配置。",
                ),
            },
        },
        "pdf-to-word": {
            "available": local_core,
            "reason_code": "" if local_core else "DOCUMENT_TOOLS_DISABLED",
            "reason": "" if local_core else disabled_reason,
            "modes": {
                "AUTO": _mode(local_core),
                "LOCAL": _mode(local_core),
                "QWEN": _mode(
                    qwen_available,
                    reason_code="" if qwen_available else qwen.reason_code,
                    reason="" if qwen_available else "千问 OCR 尚未配置。",
                ),
            },
        },
        "word-to-pdf": {
            "available": office_available,
            "reason_code": ""
            if office_available
            else (office.reason_code or "LIBREOFFICE_NOT_INSTALLED"),
            "reason": ""
            if office_available
            else "服务器未安装或无法找到 LibreOffice。",
            "modes": {
                "AUTO": _mode(office_available),
                "LOCAL": _mode(office_available),
                "QWEN": _mode(
                    False,
                    reason_code="QWEN_NOT_APPLICABLE",
                    reason="Word 转 PDF 不需要调用千问。",
                ),
            },
        },
        "pdf-translation": {
            "available": qwen_available or local_translation_available,
            "reason_code": ""
            if (qwen_available or local_translation_available)
            else "DOCUMENT_TRANSLATION_UNAVAILABLE",
            "reason": ""
            if (qwen_available or local_translation_available)
            else "千问翻译和本地翻译模型均不可用。",
            "modes": {
                "AUTO": _mode(
                    qwen_available,
                    reason_code="" if qwen_available else qwen.reason_code,
                    reason="" if qwen_available else "自动模式需要千问翻译服务。",
                ),
                "LOCAL": _mode(
                    local_translation_available,
                    reason_code=""
                    if local_translation_available
                    else "LOCAL_TRANSLATION_MODEL_MISSING",
                    reason=""
                    if local_translation_available
                    else "服务器未安装本地翻译模型。",
                ),
                "QWEN": _mode(
                    qwen_available,
                    reason_code="" if qwen_available else qwen.reason_code,
                    reason="" if qwen_available else "千问翻译服务尚未配置。",
                ),
            },
        },
        "pdf-split": {
            "available": local_core,
            "reason_code": "" if local_core else "DOCUMENT_TOOLS_DISABLED",
            "reason": "" if local_core else disabled_reason,
            "modes": {
                "AUTO": _mode(local_core),
                "LOCAL": _mode(local_core),
                "QWEN": _mode(
                    False,
                    reason_code="QWEN_NOT_APPLICABLE",
                    reason="PDF 拆分不需要调用千问。",
                ),
            },
        },
    }
    return {
        "enabled": enabled,
        "default_mode": "AUTO",
        "tools": tools,
        "providers": {
            "qwen": {
                "configured": qwen.configured,
                "available": qwen.available,
                "region": qwen.region,
                "ocr_model": qwen.ocr_model,
                "table_model": qwen.table_model,
                "translation_model": qwen.translation_model,
                "reason_code": qwen.reason_code,
            },
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
    qwen = qwen_status(settings)
    return {
        "qwen": {
            "configured": qwen.configured,
            "endpoint_reachable": None,
            "region": qwen.region,
            "ocr_model": qwen.ocr_model,
            "table_model": qwen.table_model,
            "translation_model": qwen.translation_model,
            "last_error": "" if qwen.available else qwen.reason_code,
            "note": "能力读取不主动产生模型调用；实时连通性由显式 Smoke Test 验证。",
        },
        "libreoffice": {
            "available": office.available,
            "command": office.executable or office.command,
            "version": office.version,
            "last_error": "" if office.available else office.reason_code,
        },
        "ocr": {
            "tesseract": shutil.which("tesseract") is not None,
            "rapidocr": importlib.util.find_spec("rapidocr_onnxruntime") is not None,
        },
        "limits": capabilities["limits"],
    }
