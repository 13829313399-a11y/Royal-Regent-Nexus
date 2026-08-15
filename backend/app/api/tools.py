import json
import logging
from pathlib import Path
from typing import Annotated
from urllib.parse import quote as url_quote

from anyio import from_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.ai_artifacts import (
    ArtifactScannerDependency,
    ArtifactStorageDependency,
    _artifact_error,
    _require_artifacts,
)
from app.core.config import settings
from app.db import get_db
from app.schemas.ai.artifact import AIArtifactEgressConsent
from app.services.ai.artifacts.service import ArtifactError, create_artifact
from app.services.ai.artifacts.translation_adapter import translate_artifact
from app.services.ai.cloud_document_translation import translate_cloud_fragments
from app.services.ai.provider_factory import (
    ProviderConfigurationError,
    build_provider,
    get_provider_status,
)
from app.services.ai.providers import ProviderError
from app.services.auth import AuthContext, get_current_user
from app.services.document_studio.renderers.office_pdf_renderer import (
    OfficePdfRenderError,
    render_docx_to_pdf,
)
from app.services.document_translation import (
    DocumentTranslationError,
    DocumentTranslationUnavailableError,
    document_translation_status,
    translate_document,
)
from app.services.pdf_split import PdfSplitError, split_pdf
from app.services.pdf_to_excel import PdfToExcelConversionError, convert_pdf_to_excel
from app.services.pdf_to_word import PdfToWordConversionError, convert_pdf_to_word
from app.services.pdf_translation import (
    PdfTranslationConversionError,
    convert_pdf_translation,
)

router = APIRouter(prefix="/api/tools")
translation_logger = logging.getLogger("app.tools.document_translation")

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ZIP_MEDIA_TYPE = "application/zip"


def _cloud_translation_provider_error(
    exc: ProviderError,
    *,
    request_id: str,
) -> HTTPException:
    translation_logger.warning(
        "document_translation_provider_error request_id=%s code=%s "
        "status_code=%s retryable=%s",
        request_id,
        exc.code.value,
        exc.status_code,
        exc.retryable,
    )
    return HTTPException(
        status_code=503,
        detail="云端翻译服务暂时不可用，请稍后重试。",
    )


async def _read_office_document(document_file: UploadFile) -> tuple[bytes, str]:
    file_name = document_file.filename or "文档.docx"
    extension = Path(file_name).suffix.lower()
    if extension not in {".xlsx", ".xlsm", ".docx"}:
        raise HTTPException(status_code=400, detail="只支持上传 .xlsx、.xlsm 或 .docx 文件。")

    document_bytes = await document_file.read()
    if not document_bytes:
        raise HTTPException(status_code=400, detail="Office 文档不能为空。")
    if len(document_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="单个 Office 文档不可超过 20MB。")
    if not document_bytes.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 Office 文档。")
    return document_bytes, file_name


async def _read_word_document(document_file: UploadFile) -> tuple[bytes, str]:
    document_bytes, file_name = await _read_office_document(document_file)
    if Path(file_name).suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="Word 转 PDF 只支持上传 .docx 文件。")
    return document_bytes, file_name


async def _read_pdf(pdf_file: UploadFile) -> tuple[bytes, str]:
    file_name = pdf_file.filename or "PDF文件.pdf"
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持上传 .pdf 文件。")

    pdf_bytes = await pdf_file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF 文件不能为空。")
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="单个 PDF 不可超过 20MB。")
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 PDF。")
    return pdf_bytes, file_name


@router.get("/document-translation/status")
def document_translation_service_status(
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    local_status = document_translation_status(settings.document_translation_model_dir)
    provider_status = get_provider_status(settings)
    cloud_available = bool(
        settings.ai_cloud_document_translation_enabled and provider_status.available
    )
    return {
        **local_status,
        "cloudAvailable": cloud_available,
        "artifactWorkflowsEnabled": bool(
            settings.ai_artifacts_enabled
            and settings.ai_artifact_workflows_enabled
        ),
        "modes": {
            "local_private": {
                "available": local_status["available"],
                "label": "Local Private",
            },
            "ai_smart_cloud": {
                "available": cloud_available,
                "label": "AI Smart / Cloud",
                "provider": provider_status.provider,
                "model": provider_status.model,
            },
        },
    }


@router.post("/document-translation")
async def document_translation(
    request: Request,
    document_file: Annotated[UploadFile, File()],
    direction: Annotated[str, Form()],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    storage: ArtifactStorageDependency,
    scanner: ArtifactScannerDependency,
    db: Annotated[Session, Depends(get_db)],
    sheet_names: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "local_private",
    cloud_consent: Annotated[bool, Form()] = False,
    factory_id: Annotated[str, Form()] = "",
):
    document_bytes, file_name = await _read_office_document(document_file)
    if direction not in {"zh_to_en", "en_to_zh"}:
        raise HTTPException(status_code=400, detail="翻译方向无效，只支持中译英或英译中。")

    selected_sheet_names: list[str] | None = None
    if sheet_names.strip():
        try:
            parsed_sheet_names = json.loads(sheet_names)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="工作表选择参数格式不正确。") from exc
        if not isinstance(parsed_sheet_names, list) or any(
            not isinstance(name, str) for name in parsed_sheet_names
        ):
            raise HTTPException(status_code=400, detail="工作表选择参数格式不正确。")
        selected_sheet_names = parsed_sheet_names

    if mode not in {"local_private", "ai_smart_cloud"}:
        raise HTTPException(status_code=400, detail="翻译模式无效。")
    if mode == "ai_smart_cloud" and not cloud_consent:
        raise HTTPException(
            status_code=422,
            detail="AI Smart / Cloud 模式必须明确同意发送待翻译文本片段。",
        )

    selected_factory = factory_id.strip()
    concrete_factories = tuple(
        item for item in current_user.factory_scopes if item != "*"
    )
    if not selected_factory and len(concrete_factories) == 1:
        selected_factory = concrete_factories[0]
    extension = Path(file_name).suffix.lower()
    use_artifact_adapter = bool(
        settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
        and extension in {".xlsx", ".docx"}
        and selected_factory
    )
    if use_artifact_adapter:
        allowed_factories = _require_artifacts(current_user)
        mime_type = XLSX_MEDIA_TYPE if extension == ".xlsx" else DOCX_MEDIA_TYPE
        provider = None
        try:
            source = create_artifact(
                db,
                user=current_user,
                factory_id=selected_factory,
                classification="CONFIDENTIAL_BUSINESS",
                filename=file_name,
                declared_mime_type=mime_type,
                data=document_bytes,
                storage=storage,
                scanner=scanner,
                settings=settings,
                allowed_factory_ids=allowed_factories,
            )
            consent = None
            if mode == "ai_smart_cloud":
                if not settings.ai_cloud_document_translation_enabled:
                    raise HTTPException(
                        status_code=503,
                        detail="AI Smart / Cloud 翻译尚未启用。",
                    )
                provider = build_provider(settings)
            translated = await translate_artifact(
                db,
                artifact_id=source.id,
                user=current_user,
                direction=direction,
                mode=mode,
                selected_sheet_names=selected_sheet_names,
                consent=consent,
                provider=provider,
                request_id=str(request.state.request_id),
                allowed_factory_ids=allowed_factories,
                storage=storage,
                scanner=scanner,
                settings=settings,
                legacy_cloud_consent_accepted=(
                    mode == "ai_smart_cloud" and cloud_consent
                ),
            )
        except ArtifactError as exc:
            raise _artifact_error(exc) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=503, detail="云端翻译 Provider 不可用。") from exc
        except ProviderError as exc:
            raise _cloud_translation_provider_error(
                exc,
                request_id=str(request.state.request_id),
            ) from exc
        except DocumentTranslationUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except DocumentTranslationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            if provider is not None:
                await provider.aclose()
        result = translated.document
        translation_logger.info(
            "document_translation_legacy_adapter request_id=%s user_id=%s "
            "source_artifact_id=%s derived_artifact_id=%s mode=%s",
            str(request.state.request_id),
            current_user.id,
            translated.source.id,
            translated.derived.id,
            mode,
        )
        return Response(
            content=result.content,
            media_type=result.media_type,
            headers={
                "Content-Disposition": (
                    "attachment; filename*=UTF-8''"
                    f"{url_quote(result.output_file_name)}"
                ),
                "X-Translation-Unit-Count": str(result.translated_unit_count),
                "X-Translation-Skipped-Count": str(result.skipped_unit_count),
                "X-Translation-Part-Count": str(result.processed_part_count),
                "X-Translation-Mode": mode,
                "X-Source-Artifact-ID": translated.source.id,
                "X-Derived-Artifact-ID": translated.derived.id,
                "Cache-Control": "no-store",
            },
        )

    provider = None
    try:
        translator = None
        model_dir = settings.document_translation_model_dir
        if mode == "ai_smart_cloud":
            if not settings.ai_cloud_document_translation_enabled:
                raise HTTPException(status_code=503, detail="AI Smart / Cloud 翻译尚未启用。")
            try:
                provider = build_provider(settings)
            except ProviderConfigurationError as exc:
                raise HTTPException(status_code=503, detail="云端翻译 Provider 不可用。") from exc

            async def translate_fragments(texts, fragment_direction):
                assert provider is not None
                return await translate_cloud_fragments(
                    texts,
                    fragment_direction,
                    provider=provider,
                    settings=settings,
                    request_id=str(request.state.request_id),
                )

            def translator(texts, fragment_direction):
                return from_thread.run(translate_fragments, texts, fragment_direction)

            model_dir = None
        result = await run_in_threadpool(
            translate_document,
            document_bytes,
            file_name,
            direction=direction,
            translator=translator,
            model_dir=model_dir,
            device=settings.document_translation_device,
            selected_sheet_names=selected_sheet_names,
        )
    except DocumentTranslationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentTranslationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _cloud_translation_provider_error(
            exc,
            request_id=str(request.state.request_id),
        ) from exc
    finally:
        if provider is not None:
            await provider.aclose()

    translation_logger.info(
        "document_translation request_id=%s user_id=%s mode=%s units=%s parts=%s",
        str(request.state.request_id),
        current_user.id,
        mode,
        result.translated_unit_count,
        result.processed_part_count,
    )

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-Translation-Unit-Count": str(result.translated_unit_count),
            "X-Translation-Skipped-Count": str(result.skipped_unit_count),
            "X-Translation-Part-Count": str(result.processed_part_count),
            "X-Translation-Mode": mode,
            "Cache-Control": "no-store",
        },
    )


@router.post("/document-translation/artifact")
async def document_translation_artifact(
    request: Request,
    artifact_id: Annotated[str, Form()],
    direction: Annotated[str, Form()],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    storage: ArtifactStorageDependency,
    scanner: ArtifactScannerDependency,
    db: Annotated[Session, Depends(get_db)],
    sheet_names: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "local_private",
    cloud_consent_json: Annotated[str, Form()] = "",
):
    if not settings.ai_artifact_workflows_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    if direction not in {"zh_to_en", "en_to_zh"}:
        raise HTTPException(status_code=400, detail="翻译方向无效，只支持中译英或英译中。")

    selected_sheet_names: list[str] | None = None
    if sheet_names.strip():
        try:
            parsed_sheet_names = json.loads(sheet_names)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="工作表选择参数格式不正确。") from exc
        if not isinstance(parsed_sheet_names, list) or any(
            not isinstance(name, str) for name in parsed_sheet_names
        ):
            raise HTTPException(status_code=400, detail="工作表选择参数格式不正确。")
        selected_sheet_names = parsed_sheet_names

    consent = None
    if cloud_consent_json.strip():
        try:
            consent = AIArtifactEgressConsent.model_validate_json(cloud_consent_json)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "AI_ARTIFACT_WORKFLOW_CONTRACT_INVALID",
                    "message": "Artifact 云端处理同意格式无效。",
                    "retryable": False,
                },
            ) from exc
    allowed_factories = _require_artifacts(current_user)
    provider = None
    try:
        if mode == "ai_smart_cloud":
            try:
                provider = build_provider(settings)
            except ProviderConfigurationError as exc:
                raise HTTPException(status_code=503, detail="云端翻译 Provider 不可用。") from exc
        translated = await translate_artifact(
            db,
            artifact_id=artifact_id,
            user=current_user,
            direction=direction,
            mode=mode,
            selected_sheet_names=selected_sheet_names,
            consent=consent,
            provider=provider,
            request_id=str(request.state.request_id),
            allowed_factory_ids=allowed_factories,
            storage=storage,
            scanner=scanner,
            settings=settings,
        )
    except ArtifactError as exc:
        raise _artifact_error(exc) from exc
    except DocumentTranslationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentTranslationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _cloud_translation_provider_error(
            exc,
            request_id=str(request.state.request_id),
        ) from exc
    finally:
        if provider is not None:
            await provider.aclose()

    translation_logger.info(
        "document_translation_artifact request_id=%s user_id=%s mode=%s "
        "source_artifact_id=%s derived_artifact_id=%s model=%s terms=%s units=%s parts=%s",
        str(request.state.request_id),
        current_user.id,
        mode,
        translated.source.id,
        translated.derived.id,
        translated.derived.model_version,
        translated.derived.parser_version,
        translated.document.translated_unit_count,
        translated.document.processed_part_count,
    )
    return Response(
        content=translated.document.content,
        media_type=translated.document.media_type,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''"
                f"{url_quote(translated.document.output_file_name)}"
            ),
            "X-Translation-Unit-Count": str(
                translated.document.translated_unit_count
            ),
            "X-Translation-Skipped-Count": str(
                translated.document.skipped_unit_count
            ),
            "X-Translation-Part-Count": str(
                translated.document.processed_part_count
            ),
            "X-Translation-Mode": mode,
            "X-Source-Artifact-ID": translated.source.id,
            "X-Derived-Artifact-ID": translated.derived.id,
            "X-Parser-Version": translated.derived.parser_version,
            "X-Model-Version": translated.derived.model_version,
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-to-excel")
async def pdf_to_excel(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)

    try:
        result = await run_in_threadpool(convert_pdf_to_excel, pdf_bytes, file_name)
    except PdfToExcelConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Table-Count": str(result.table_count),
            "X-PDF-Text-Page-Count": str(result.text_page_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-to-word")
async def pdf_to_word(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        result = await run_in_threadpool(convert_pdf_to_word, pdf_bytes, file_name)
    except PdfToWordConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Table-Count": str(result.table_count),
            "X-PDF-Image-Count": str(result.image_count),
            "X-PDF-Text-Page-Count": str(result.text_page_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
        },
    )


@router.post("/word-to-pdf")
async def word_to_pdf(
    document_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    document_bytes, file_name = await _read_word_document(document_file)
    try:
        result = await run_in_threadpool(
            render_docx_to_pdf,
            document_bytes,
            file_name,
            command=settings.document_office_renderer_command,
            timeout_seconds=settings.document_office_renderer_timeout_seconds,
            # The synchronous tool already rejects macros/external relationships,
            # uses LibreOffice safe mode and a disposable profile, and applies
            # subprocess resource limits. Reuse an attested network namespace when
            # present, without making the full Document Job gate a prerequisite.
            network_isolation_command=(
                settings.document_office_renderer_network_isolation_command
                if settings.document_office_renderer_network_isolation_verified
                else None
            ),
        )
    except OfficePdfRenderError as exc:
        status_code = 503 if exc.retryable or exc.code.endswith("UNAVAILABLE") else 422
        raise HTTPException(status_code=status_code, detail=exc.public_message) from exc

    return Response(
        content=result.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-Word-Page-Count": str(result.page_count),
            "X-Word-Blank-Page-Count": str(result.blank_page_count),
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-translation")
async def pdf_translation(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    direction: Annotated[str, Form()] = "AUTO",
    layout: Annotated[str, Form()] = "TRANSLATED_ONLY",
    protected_tokens: Annotated[str, Form()] = "[]",
    include_editable_docx: Annotated[bool, Form()] = False,
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        parsed_tokens = json.loads(protected_tokens)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="保护词参数格式不正确。") from exc
    if (
        not isinstance(parsed_tokens, list)
        or len(parsed_tokens) > 100
        or any(
            not isinstance(token, str) or len(token) > 200
            for token in parsed_tokens
        )
    ):
        raise HTTPException(status_code=400, detail="保护词参数格式不正确。")

    try:
        result = await run_in_threadpool(
            convert_pdf_translation,
            pdf_bytes,
            file_name,
            settings=settings,
            requested_direction=direction,
            layout=layout,
            protected_tokens=tuple(
                dict.fromkeys(token.strip() for token in parsed_tokens if token.strip())
            ),
            include_editable_docx=include_editable_docx,
        )
    except PdfTranslationConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-PDF-Page-Count": str(result.page_count),
            "X-Translation-Unit-Count": str(result.translated_unit_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-split")
async def pdf_split(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    split_mode: Annotated[str, Form()] = "each_page",
    page_ranges: Annotated[str, Form()] = "",
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        result = await run_in_threadpool(
            split_pdf,
            pdf_bytes,
            file_name,
            mode=split_mode,
            page_ranges=page_ranges,
        )
    except PdfSplitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Split-File-Count": str(result.file_count),
            "Cache-Control": "no-store",
        },
    )
