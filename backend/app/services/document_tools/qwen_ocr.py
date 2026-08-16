from __future__ import annotations

import base64
import threading
from functools import lru_cache
from io import BytesIO
from typing import Any

import pypdfium2 as pdfium
from pydantic import ValidationError

from app.core.config import Settings
from app.services.document_tools.contracts import (
    DocumentToolError,
    OcrBlock,
    OcrPage,
    OcrResult,
)
from app.services.document_tools.qwen_client import (
    convert_qwen_error,
    create_qwen_client,
)


@lru_cache(maxsize=4)
def _semaphore(concurrency: int) -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(concurrency)


def _read(value: object, name: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _response_result(response: object) -> object:
    for item in _read(response, "output", ()) or ():
        for part in _read(item, "content", ()) or ():
            result = _read(part, "ocr_result")
            if result is not None:
                return result
            text = _read(part, "text")
            if isinstance(text, str) and text.strip():
                return text
    output_text = _read(response, "output_text")
    if isinstance(output_text, str):
        return output_text
    return ""


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        parsed = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if parsed[2] < parsed[0] or parsed[3] < parsed[1]:
        return None
    return parsed  # type: ignore[return-value]


def _parse_single_page(raw: object, *, page_number: int) -> OcrPage:
    blocks: list[OcrBlock] = []
    candidates: list[object] = []
    if isinstance(raw, dict) and isinstance(raw.get("pages"), list):
        pages = raw["pages"]
        if pages:
            page = pages[0]
            if isinstance(page, dict):
                candidates = list(page.get("blocks") or [])
    elif isinstance(raw, dict) and isinstance(raw.get("layouts"), list):
        layouts = raw["layouts"]
        for layout in layouts:
            if not isinstance(layout, dict):
                continue
            layout_blocks = layout.get("blocks")
            if isinstance(layout_blocks, list):
                candidates.extend(layout_blocks)
            elif isinstance(layout.get("text"), str):
                candidates.append({"text": layout["text"]})
    elif isinstance(raw, dict) and isinstance(raw.get("processed_text"), str):
        candidates = [{"text": raw["processed_text"]}]
    elif isinstance(raw, str):
        candidates = [{"text": raw}]

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        text = str(candidate.get("text") or "").strip()
        if not text:
            continue
        confidence = candidate.get("confidence", 0.85)
        try:
            normalized_confidence = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError):
            normalized_confidence = 0.85
        blocks.append(
            OcrBlock(
                text=text,
                bbox=_bbox(candidate.get("bbox") or candidate.get("box")),
                confidence=normalized_confidence,
            )
        )
    try:
        return OcrPage(page_number=page_number, blocks=tuple(blocks))
    except ValidationError as exc:
        raise DocumentToolError(
            "QWEN_OCR_SCHEMA_INVALID",
            "千问 OCR 返回结构无效。",
            action="请重试；若持续失败，请管理员检查 OCR 模型配置。",
            retryable=True,
            status_code=502,
        ) from exc


class QwenOcrService:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self.client = create_qwen_client(settings, client=client)

    def parse_pdf(
        self,
        data: bytes,
        *,
        page_numbers: tuple[int, ...] | None = None,
    ) -> OcrResult:
        try:
            document = pdfium.PdfDocument(data)
        except Exception as exc:
            raise DocumentToolError(
                "PDF_INVALID",
                "PDF 无法读取或渲染。",
                action="请确认文件未加密、未损坏。",
            ) from exc
        selected = page_numbers or tuple(range(1, len(document) + 1))
        if not selected or any(
            number < 1 or number > len(document) for number in selected
        ):
            raise DocumentToolError(
                "PDF_PAGE_RANGE_INVALID",
                "OCR 页码超出 PDF 范围。",
                action="请重新选择有效页码。",
            )
        pages: list[OcrPage] = []
        try:
            for page_number in selected:
                page = document[page_number - 1]
                width, height = page.get_size()
                scale = max(1.5, min(3.0, 2000 / max(width, height, 1)))
                image = page.render(scale=scale).to_pil().convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=84, optimize=True)
                image_bytes = output.getvalue()
                if len(image_bytes) > min(
                    self.settings.document_tool_max_file_bytes,
                    5 * 1024 * 1024,
                ):
                    raise DocumentToolError(
                        "QWEN_OCR_PAGE_TOO_LARGE",
                        f"第 {page_number} 页渲染图片过大，无法发送给千问。",
                        action="请降低扫描分辨率或先拆分文档。",
                    )
                encoded = base64.b64encode(image_bytes).decode("ascii")
                with _semaphore(self.settings.ai_document_ocr_max_concurrency):
                    response = self.client.responses.create(
                        model=self.settings.qwen_ocr_model,
                        input=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_image",
                                        "image_url": f"data:image/jpeg;base64,{encoded}",
                                    },
                                ],
                            }
                        ],
                        store=False,
                        extra_body={"ocr_options": {"task": "document_parsing"}},
                    )
                pages.append(
                    _parse_single_page(
                        _response_result(response),
                        page_number=page_number,
                    )
                )
        except DocumentToolError:
            raise
        except Exception as exc:
            raise convert_qwen_error(exc, operation="OCR") from exc
        return OcrResult(pages=tuple(pages))
