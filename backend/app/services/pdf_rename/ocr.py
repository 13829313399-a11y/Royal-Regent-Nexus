from __future__ import annotations

import re
from io import BytesIO

import pdfplumber
from pypdf import PdfReader

from app.services.carton_mark import configure_tesseract

from .contracts import (
    NormalizedRegion,
    PdfRenameServiceError,
    RecognizedRegionValue,
    RecognizedTextBox,
)


def _normalize_ocr_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return " ".join(line for line in lines if line).strip()


def _validate_page(pdf_bytes: bytes, page_number: int) -> None:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfRenameServiceError(
                "PDF_RENAME_PDF_ENCRYPTED",
                "PDF 已加密，无法读取固定区域。",
                action="请先解除 PDF 密码保护后重试。",
            )
        if page_number > len(reader.pages):
            raise PdfRenameServiceError(
                "PDF_RENAME_PAGE_MISSING",
                f"规则要求读取第 {page_number} 页，但文件页数不足。",
                action="请确认上传了与所选规则匹配的 PDF。",
            )
    except PdfRenameServiceError:
        raise
    except Exception as exc:
        raise PdfRenameServiceError(
            "PDF_RENAME_PDF_INVALID",
            "PDF 文件结构无效或无法读取。",
            action="请重新导出 PDF 后重试。",
        ) from exc


def recognize_fixed_region(
    pdf_bytes: bytes,
    region: NormalizedRegion,
) -> RecognizedRegionValue:
    """Read a fixed region; rules can bypass untrustworthy embedded OCR text."""

    _validate_page(pdf_bytes, region.page_number)
    if not region.ocr_only:
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as document:
                page = document.pages[region.page_number - 1]
                bbox = (
                    float(page.width) * region.left,
                    float(page.height) * region.top,
                    float(page.width) * region.right,
                    float(page.height) * region.bottom,
                )
                native = _normalize_ocr_text(
                    page.crop(bbox).extract_text(x_tolerance=2, y_tolerance=3) or ""
                )
            if native:
                return RecognizedRegionValue(
                    key=region.key,
                    label=region.label,
                    raw_text=native,
                    normalized_text=native,
                    route="NATIVE_TEXT",
                    confidence=0.98,
                )
        except Exception:
            pass

    if region.ocr_engine == "rapidocr":
        return _recognize_spatial_region(pdf_bytes, region)

    try:
        import pypdfium2 as pdfium  # type: ignore
        import pytesseract  # type: ignore
    except Exception as exc:
        raise PdfRenameServiceError(
            "PDF_RENAME_OCR_UNAVAILABLE",
            "扫描区域识别组件未安装。",
            action="请管理员安装 pypdfium2、Pillow、pytesseract 和 Tesseract。",
            status_code=503,
        ) from exc

    command, fallback_language = configure_tesseract(pytesseract)
    if not command:
        raise PdfRenameServiceError(
            "PDF_RENAME_OCR_UNAVAILABLE",
            "服务器未找到 Tesseract OCR。",
            action="请管理员配置 Tesseract 后再启用该规则。",
            status_code=503,
        )

    document = None
    page = None
    bitmap = None
    try:
        document = pdfium.PdfDocument(pdf_bytes)
        page = document[region.page_number - 1]
        bitmap = page.render(scale=4)
        image = bitmap.to_pil().convert("RGB")
        width, height = image.size
        crop = image.crop(
            (
                round(width * region.left),
                round(height * region.top),
                round(width * region.right),
                round(height * region.bottom),
            )
        )
        requested = [
            language.strip()
            for language in region.language.split("+")
            if language.strip()
        ]
        try:
            available_languages = set(pytesseract.get_languages(config=""))
        except Exception:
            available_languages = set()
        selected_languages = [
            language for language in requested if language in available_languages
        ]
        requested_language = "+".join(selected_languages) or fallback_language
        config = f"--oem 3 --psm {region.ocr_page_segmentation} -c preserve_interword_spaces=1"
        try:
            text = pytesseract.image_to_string(
                crop,
                lang=requested_language,
                config=config,
                timeout=45,
            )
        except TypeError:
            text = pytesseract.image_to_string(
                crop,
                lang=requested_language,
                config=config,
            )
    except PdfRenameServiceError:
        raise
    except Exception as exc:
        raise PdfRenameServiceError(
            "PDF_RENAME_OCR_FAILED",
            "固定区域 OCR 识别失败。",
            action="请检查 PDF 清晰度、页面方向及规则区域坐标。",
        ) from exc
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        if document is not None:
            document.close()

    normalized = _normalize_ocr_text(text)
    return RecognizedRegionValue(
        key=region.key,
        label=region.label,
        raw_text=text.strip(),
        normalized_text=normalized,
        route="LOCAL_OCR",
        confidence=0.80 if normalized else None,
    )


def _recognize_spatial_region(pdf_bytes: bytes, region: NormalizedRegion) -> RecognizedRegionValue:
    """Local table OCR, opt-in only. Never read the scan's embedded text layer."""
    from app.services.carton_mark import get_rapidocr_engine

    engine = get_rapidocr_engine()
    if engine is None:
        raise PdfRenameServiceError(
            "PDF_RENAME_OCR_UNAVAILABLE", "彩星版面识别组件或本地模型不可用。",
            action="请管理员检查 RapidOCR、ONNX Runtime 及本地模型。", status_code=503,
        )
    document = page = bitmap = None
    try:
        import numpy as np
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(pdf_bytes)
        page = document[region.page_number - 1]
        bitmap = page.render(scale=3)
        image = bitmap.to_pil().convert("RGB")
        width, height = image.size
        crop = image.crop((int(width * region.left), int(height * region.top),
                           int(width * region.right), int(height * region.bottom)))
        result = engine(np.asarray(crop))
        boxes = []
        if result is not None and result.boxes is not None:
            for text, polygon, score in zip(result.txts, result.boxes, result.scores, strict=True):
                if str(text).strip() and len(polygon) == 4:
                    boxes.append(RecognizedTextBox(
                        str(text).strip(),
                        tuple((float(x) / crop.width, float(y) / crop.height) for x, y in polygon),
                        float(score),
                    ))
        raw = "\n".join(box.text for box in boxes)
        return RecognizedRegionValue(
            region.key, region.label, raw, _normalize_ocr_text(raw), "LOCAL_OCR",
            min((box.confidence for box in boxes), default=None), tuple(boxes),
        )
    except Exception as exc:
        raise PdfRenameServiceError(
            "PDF_RENAME_OCR_FAILED", "彩星固定区域版面识别失败。",
            action="请检查扫描清晰度、方向及本地 OCR 组件。",
        ) from exc
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        if document is not None:
            document.close()
