from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, BinaryIO

import pdfplumber

from app.services.carton_mark import configure_tesseract, missing_tesseract_message


def extract_pdf_text(
    source: str | Path | bytes | BinaryIO,
    *,
    ocr_if_empty: bool = True,
    min_text_chars: int = 80,
    resolution: int = 300,
) -> tuple[str, int, bool]:
    """Return PDF text and transparently OCR image-only pages when necessary."""
    stream: Any = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(stream) as pdf:
        pages = [page.extract_text(x_tolerance=2, y_tolerance=4) or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
        if not ocr_if_empty or len(re.sub(r"\s+", "", text)) >= min_text_chars:
            return text, len(pdf.pages), False
        try:
            import pytesseract
        except ImportError as exc:
            raise ValueError("扫描版 PDF 需要服务器 OCR 组件（pytesseract/tesseract）") from exc
        tesseract_cmd, language = configure_tesseract(pytesseract)
        if not tesseract_cmd:
            raise ValueError(
                "扫描版 PDF 无文字层且服务器 OCR 未配置："
                + missing_tesseract_message()
            )
        ocr_pages = [
            pytesseract.image_to_string(
                page.to_image(resolution=resolution).original,
                lang=language,
                config="--psm 6",
            )
            for page in pdf.pages
        ]
        return "\n".join(ocr_pages).strip(), len(pdf.pages), True
