import importlib.util
import hashlib
import importlib.metadata

from app.core.config import settings
from app.services.document_tools import job_service, storage


def engine_fingerprint(name):
    if name == "qwen":
        values = [settings.document_tools_qwen_base_url, settings.document_tools_qwen_protocol,
            settings.document_tools_qwen_ocr_model, settings.document_tools_qwen_layout_model,
            settings.document_tools_qwen_api_key.get_secret_value()]
    elif name == "office":
        from app.services.document_tools.office_engine import office_executable
        values = [str(office_executable()), settings.document_tools_uno_python]
    else:
        package = "pypdf" if name == "pdf" else "rapidocr"
        try:
            values = [package, importlib.metadata.version(package)]
        except importlib.metadata.PackageNotFoundError:
            values = [package, "missing"]
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def get_capabilities():
    from app.services.document_tools.office_engine import office_executable
    office = bool(office_executable())
    key = settings.document_tools_qwen_api_key.get_secret_value()
    configured = bool(key and settings.document_tools_qwen_base_url)
    records = storage.read_json("engine-smoke.json", {})
    tested = {name: isinstance(record, dict) and record.get("passed") is True and record.get("fingerprint") == engine_fingerprint(name)
              for name, record in records.items()}
    operations = []
    for operation, (label, _) in job_service.OPERATIONS.items():
        required = operation in {"word_to_pdf", "excel_to_pdf"}
        operations.append({"id": operation, "label": label, "available": not required or office,
            "reason": "" if not required or office else "Office 渲染引擎未安装"})
    return {"operations": operations, "worker": job_service.heartbeat_status(),
        "engines": {"office": {"configured": office, "tested": bool(tested.get("office"))},
            "pdf": {"configured": True, "tested": bool(tested.get("pdf"))},
            "local_ocr": {"configured": importlib.util.find_spec("rapidocr") is not None, "tested": bool(tested.get("local_ocr"))},
            "qwen": {"configured": configured, "tested": bool(tested.get("qwen")),
                "status": "tested" if tested.get("qwen") and configured else "configured_not_tested" if configured else "not_configured",
                "model": settings.document_tools_qwen_ocr_model, "protocol": settings.document_tools_qwen_protocol}},
        "limits": {"max_file_bytes": settings.document_tools_max_file_bytes, "max_pages": settings.document_tools_max_pages},
        "retention_days": settings.document_tools_retention_days}
