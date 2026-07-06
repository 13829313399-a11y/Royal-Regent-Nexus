from __future__ import annotations

import re
import os
import shutil
import string
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from app.schemas.carton_mark import (
    CartonMarkAutoCheckResponse,
    CartonMarkAutoCheckSummary,
    CartonMarkComparisonItem,
    CartonMarkExtractedField,
    CartonMarkExtractionStatus,
)


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    label: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class PdfMarkRegion:
    kind: str
    text: str
    box: tuple[int, int, int, int]


FIELD_DEFINITIONS = [
    FieldDefinition("customer_name", "客名", ("CUSTOMER", "CLIENT", "CLIENTE", "NOMBRE", "CUSTOMER NAME")),
    FieldDefinition("po", "PO", (
        "PO", "P.O.", "P/O", "PO NO", "PO NO.", "P.O. NO", "P.O.NO", "PO NUMBER", "ORDER NO",
        "ORDER NO.", "ORDER NUMBER", "NUMERO DE PEDIDO", "NÚMERO DE PEDIDO", "PEDIDO",
    )),
    FieldDefinition("item", "ITEM", (
        "ITEM", "ITEM NO", "ITEM NO.", "ITEM NUMBER", "ITEM#", "STYLE", "STYLE NO", "STYLE NO.",
        "MODEL", "MODELO", "ART NO", "ART NO.", "ARTICLE", "REF", "REFERENCE",
    )),
    FieldDefinition("description", "描述", ("DESCRIPTION", "DESCRIPCION", "DESCRIPCIÓN")),
    FieldDefinition("sku", "SKU", ("SKU", "S.K.U.", "SKU NO", "SKU NO.")),
    FieldDefinition("color", "颜色", ("COLOR", "COLOUR", "COL")),
    FieldDefinition("quantity", "数量", (
        "QTY", "QUANTITY", "CANTIDAD", "PCS", "PZAS", "CTN QTY", "QTY/CTN", "QTY PER CTN",
        "QTY PER CARTON", "PCS/CTN",
    )),
    FieldDefinition("carton_no", "箱号", (
        "CARTON NO", "CARTON NO.", "CARTON NUMBER", "CTN NO", "CTN NO.", "CTN#", "C/NO",
        "CARTON", "CAJA NUMERO", "CAJA NÚMERO",
    )),
    FieldDefinition("gw", "G.W", ("G.W", "G.W.", "GW", "GROSS WEIGHT", "PESO BRUTO")),
    FieldDefinition("nw", "N.W", ("N.W", "N.W.", "NW", "NET WEIGHT", "PESO NETO")),
    FieldDefinition("measurement", "尺寸", ("MEAS", "MEAS.", "MEASUREMENT", "DIMENSION", "CARTON SIZE", "CARTON MEAS", "MEDIDA")),
    FieldDefinition("barcode", "条码", (
        "BARCODE", "BAR CODE", "BARCODE NO", "BAR CODE NO", "CODE", "EAN", "UPC",
        "CODIGO DE BARRAS", "CÓDIGO DE BARRAS",
    )),
]

FIELD_BY_KEY = {field.key: field for field in FIELD_DEFINITIONS}
FIELD_ORDER = [field.key for field in FIELD_DEFINITIONS]
TEXT_CHARS = set(string.printable) | set("，。：；、（）【】《》±×")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
TESSERACT_CANDIDATE_PATHS = (
    PROJECT_ROOT / "tools" / "Tesseract-OCR" / "tesseract.exe",
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


@lru_cache(maxsize=1)
def find_tesseract_cmd() -> str:
    env_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if env_cmd and Path(env_cmd).exists():
        return env_cmd

    path_cmd = shutil.which("tesseract")
    if path_cmd:
        return path_cmd

    for candidate in TESSERACT_CANDIDATE_PATHS:
        if candidate.exists():
            return str(candidate)

    return ""


@lru_cache(maxsize=8)
def get_tesseract_languages(tesseract_cmd: str) -> tuple[str, ...]:
    try:
        completed = subprocess.run(
            [tesseract_cmd, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return ()

    languages = []
    for line in f"{completed.stdout}\n{completed.stderr}".splitlines():
        value = line.strip()
        if not value or value.startswith("List of available"):
            continue
        languages.append(value)

    return tuple(languages)


def select_tesseract_language(tesseract_cmd: str) -> str:
    languages = set(get_tesseract_languages(tesseract_cmd))
    if "eng" in languages and "chi_sim" in languages:
        return "eng+chi_sim"
    if "eng" in languages:
        return "eng"

    for language in languages:
        if language != "osd":
            return language

    return "eng"


def configure_tesseract(pytesseract_module) -> tuple[str, str]:
    tesseract_cmd = find_tesseract_cmd()
    if not tesseract_cmd:
        return "", ""

    pytesseract_module.pytesseract.tesseract_cmd = tesseract_cmd
    return tesseract_cmd, select_tesseract_language(tesseract_cmd)


def missing_tesseract_message() -> str:
    checked_paths = "、".join(str(path) for path in TESSERACT_CANDIDATE_PATHS)
    return f"未找到 tesseract.exe。已检查 PATH、TESSERACT_CMD 和 {checked_paths}。"


def build_carton_mark_auto_check(
    *,
    pdf_bytes: bytes,
    front_image_bytes: bytes,
    side_image_bytes: bytes,
    customer_name: str = "",
    po: str = "",
    item: str = "",
) -> CartonMarkAutoCheckResponse:
    pdf_text, pdf_status = extract_pdf_text(pdf_bytes)
    front_pdf_text, side_pdf_text, pdf_layout_status = extract_pdf_template_side_texts(
        pdf_bytes,
        fallback_text=pdf_text,
    )
    front_text, front_status = extract_image_text(front_image_bytes, source="front_photo")
    side_text, side_status = extract_image_text(side_image_bytes, source="side_photo")

    metadata = {
        "customer_name": customer_name,
        "po": po,
        "item": item,
    }
    template_fields = extract_fields(pdf_text, source="pdf_template")
    template_fields = merge_metadata_fields(template_fields, metadata, source="template_metadata")
    front_template_fields = merge_metadata_fields(
        extract_fields(front_pdf_text, source="pdf_front_mark"),
        metadata,
        source="template_metadata",
    )
    side_template_fields = merge_metadata_fields(
        extract_fields(side_pdf_text, source="pdf_side_mark"),
        metadata,
        source="template_metadata",
    )

    front_expected_fields = front_template_fields or template_fields
    side_expected_fields = side_template_fields or template_fields
    front_fields = enrich_fields_from_expected_values(
        extract_fields(front_text, source="front_photo"),
        front_expected_fields,
        front_text,
        source="front_photo_value_match",
    )
    side_fields = enrich_fields_from_expected_values(
        extract_fields(side_text, source="side_photo"),
        side_expected_fields,
        side_text,
        source="side_photo_value_match",
    )
    comparisons = [
        *compare_side("front", front_expected_fields, front_fields, front_status),
        *compare_side("side", side_expected_fields, side_fields, side_status),
    ]

    summary = summarize_comparisons(comparisons)
    return CartonMarkAutoCheckResponse(
        summary=summary,
        template_fields=template_fields,
        front_template_fields=front_template_fields,
        side_template_fields=side_template_fields,
        front_photo_fields=front_fields,
        side_photo_fields=side_fields,
        comparisons=comparisons,
        extraction=[pdf_status, pdf_layout_status, front_status, side_status],
    )


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, CartonMarkExtractionStatus]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        text = fallback_decode_bytes(pdf_bytes)
        return text, CartonMarkExtractionStatus(
            source="pdf_template",
            ok=bool(text.strip()),
            engine="fallback-bytes",
            message="未安装 pypdf，已使用文本字节兜底解析；扫描型 PDF 需要安装 OCR/PDF 解析引擎。",
            raw_text=clip_text(text),
        )

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        page_texts = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(page_texts)
        return text, CartonMarkExtractionStatus(
            source="pdf_template",
            ok=bool(text.strip()),
            engine="pypdf",
            message="" if text.strip() else "PDF 没有可抽取文本，可能是扫描图或纯图片 PDF，需要 OCR。",
            raw_text=clip_text(text),
        )
    except Exception as exc:
        text = fallback_decode_bytes(pdf_bytes)
        return text, CartonMarkExtractionStatus(
            source="pdf_template",
            ok=bool(text.strip()),
            engine="fallback-bytes",
            message=f"pypdf 解析失败，已尝试兜底文本解析：{exc}",
            raw_text=clip_text(text),
        )


def extract_pdf_template_side_texts(pdf_bytes: bytes, *, fallback_text: str) -> tuple[str, str, CartonMarkExtractionStatus]:
    regions, status = extract_pdf_mark_regions(pdf_bytes)
    if not regions:
        return fallback_text, fallback_text, status

    front_text = merge_region_texts(region for region in regions if region.kind == "front")
    side_text = merge_region_texts(region for region in regions if region.kind == "side")

    if not front_text:
        front_text = fallback_text
    if not side_text:
        side_text = fallback_text

    return front_text, side_text, status


def extract_pdf_mark_regions(pdf_bytes: bytes) -> tuple[list[PdfMarkRegion], CartonMarkExtractionStatus]:
    try:
        from PIL import ImageFilter  # type: ignore
        import pypdfium2 as pdfium  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return [], CartonMarkExtractionStatus(
            source="pdf_template_regions",
            ok=False,
            engine="unconfigured",
            message="PDF 正唛/侧唛区域识别引擎未配置。请安装 pypdfium2、Pillow、pytesseract，并部署 Tesseract 或接入 PaddleOCR。",
            raw_text="",
        )

    try:
        try:
            document = pdfium.PdfDocument(pdf_bytes)
        except Exception:
            document = pdfium.PdfDocument(BytesIO(pdf_bytes))

        if not document:
            raise ValueError("PDF 没有页面")

        page = document[0]
        rendered = page.render(scale=3).to_pil().convert("RGB")
        regions: list[PdfMarkRegion] = []
        tesseract_cmd, tesseract_lang = configure_tesseract(pytesseract)
        if not tesseract_cmd:
            return [], CartonMarkExtractionStatus(
                source="pdf_template_regions",
                ok=False,
                engine="pypdfium2+pytesseract",
                message=f"{missing_tesseract_message()} 已退回使用 PDF 全文模板字段。",
                raw_text="",
            )

        boxes = locate_pdf_mark_boxes(rendered, ImageFilter)
        if len(boxes) < 2:
            boxes = dedupe_boxes([
                *boxes,
                *locate_pdf_ocr_text_boxes(rendered, pytesseract, tesseract_lang, ImageFilter),
            ])

        for box in boxes[:8]:
            crop = rendered.crop(box)
            text = pytesseract.image_to_string(crop, lang=tesseract_lang)
            if len(normalize_compare_value(text)) < 4:
                continue
            regions.append(PdfMarkRegion(kind="", text=text, box=box))

        regions = classify_pdf_mark_regions(regions)
        combined_text = merge_region_texts(regions)
        if not regions:
            full_page_text = pytesseract.image_to_string(rendered, lang=tesseract_lang)
            if full_page_text.strip():
                full_page_box = (0, 0, rendered.width, rendered.height)
                return [
                    PdfMarkRegion(kind="front", text=full_page_text, box=full_page_box),
                    PdfMarkRegion(kind="side", text=full_page_text, box=full_page_box),
                ], CartonMarkExtractionStatus(
                    source="pdf_template_regions",
                    ok=True,
                    engine="pypdfium2+pytesseract",
                    message="未能稳定切分 PDF 正唛/侧唛区域，已使用 PDF 整页 OCR 字段参与自动核对。",
                    raw_text=clip_text(full_page_text),
                )

            return [], CartonMarkExtractionStatus(
                source="pdf_template_regions",
                ok=False,
                engine="pypdfium2+pytesseract",
                message="未能在 PDF 中定位正唛/侧唛区域，已退回使用 PDF 全文模板字段。",
                raw_text="",
            )

        return regions, CartonMarkExtractionStatus(
            source="pdf_template_regions",
            ok=True,
            engine="pypdfium2+pytesseract",
            message="已按 PDF 页面上的长框/短框自动分离正唛和侧唛区域。",
            raw_text=clip_text(combined_text),
        )
    except Exception as exc:
        return [], CartonMarkExtractionStatus(
            source="pdf_template_regions",
            ok=False,
            engine="pypdfium2+pytesseract",
            message=f"PDF 正唛/侧唛区域识别失败，已退回使用 PDF 全文模板字段：{exc}",
            raw_text="",
        )


def locate_pdf_mark_boxes(image, image_filter) -> list[tuple[int, int, int, int]]:
    max_analysis_width = 1800
    scale = min(1.0, max_analysis_width / max(image.width, 1))
    analysis_image = image
    if scale < 1:
        analysis_image = image.resize((int(image.width * scale), int(image.height * scale)))

    gray = analysis_image.convert("L")
    mask = gray.point(lambda pixel: 255 if pixel < 125 else 0)
    mask = mask.filter(image_filter.MaxFilter(21))
    mask = mask.filter(image_filter.MinFilter(5))
    boxes = find_connected_boxes(mask)

    scaled_boxes = []
    for left, top, right, bottom in boxes:
        scaled_boxes.append(expand_box(
            (
                int(left / scale),
                int(top / scale),
                int(right / scale),
                int(bottom / scale),
            ),
            image.width,
            image.height,
            padding=28,
        ))

    return dedupe_boxes(scaled_boxes)


def locate_pdf_ocr_text_boxes(image, pytesseract_module, tesseract_lang: str, image_filter) -> list[tuple[int, int, int, int]]:
    try:
        from PIL import Image, ImageDraw  # type: ignore
        from pytesseract import Output  # type: ignore
    except Exception:
        return []

    try:
        data = pytesseract_module.image_to_data(
            image,
            lang=tesseract_lang,
            output_type=Output.DICT,
            config="--psm 11",
        )
    except Exception:
        return []

    max_analysis_width = 1800
    scale = min(1.0, max_analysis_width / max(image.width, 1))
    analysis_size = (int(image.width * scale), int(image.height * scale))
    mask = Image.new("L", analysis_size, 0)
    draw = ImageDraw.Draw(mask)
    padding_x = max(10, int(analysis_size[0] * 0.012))
    padding_y = max(8, int(analysis_size[1] * 0.018))

    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text or "").strip()
        if len(normalize_compare_value(text)) < 2:
            continue

        try:
            confidence = float(data.get("conf", [])[index])
        except Exception:
            confidence = 0
        if confidence < 15:
            continue

        left = int(data.get("left", [])[index] * scale)
        top = int(data.get("top", [])[index] * scale)
        width = int(data.get("width", [])[index] * scale)
        height = int(data.get("height", [])[index] * scale)
        if width < 3 or height < 3:
            continue

        draw.rectangle(
            (
                max(0, left - padding_x),
                max(0, top - padding_y),
                min(analysis_size[0], left + width + padding_x),
                min(analysis_size[1], top + height + padding_y),
            ),
            fill=255,
        )

    mask = mask.filter(image_filter.MaxFilter(31))
    mask = mask.filter(image_filter.MinFilter(5))
    boxes = find_connected_boxes(mask)
    boxes = filter_plausible_mark_boxes(boxes, analysis_size[0], analysis_size[1])

    scaled_boxes = []
    for left, top, right, bottom in boxes:
        scaled_boxes.append(expand_box(
            (
                int(left / scale),
                int(top / scale),
                int(right / scale),
                int(bottom / scale),
            ),
            image.width,
            image.height,
            padding=36,
        ))

    return scaled_boxes


def filter_plausible_mark_boxes(
    boxes: list[tuple[int, int, int, int]],
    image_width: int,
    image_height: int,
) -> list[tuple[int, int, int, int]]:
    filtered = []
    min_width = max(45, int(image_width * 0.035))
    min_height = max(45, int(image_height * 0.07))
    max_width = int(image_width * 0.45)
    max_height = int(image_height * 0.55)

    for box in boxes:
        width = box[2] - box[0]
        height = box[3] - box[1]
        aspect_ratio = width / max(height, 1)
        if width < min_width or height < min_height:
            continue
        if width > max_width or height > max_height:
            continue
        if aspect_ratio < 0.35 or aspect_ratio > 3.6:
            continue
        filtered.append(box)

    return filtered


def find_connected_boxes(mask) -> list[tuple[int, int, int, int]]:
    width, height = mask.size
    pixels = mask.load()
    visited = bytearray(width * height)
    boxes: list[tuple[int, int, int, int]] = []
    min_width = max(28, int(width * 0.035))
    min_height = max(22, int(height * 0.03))
    min_area = max(500, int(width * height * 0.0008))
    max_area = int(width * height * 0.18)

    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or pixels[x, y] < 128:
                continue

            stack = [(x, y)]
            visited[index] = 1
            left = right = x
            top = bottom = y
            count = 0

            while stack:
                current_x, current_y = stack.pop()
                count += 1
                left = min(left, current_x)
                right = max(right, current_x)
                top = min(top, current_y)
                bottom = max(bottom, current_y)

                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if next_x < 0 or next_y < 0 or next_x >= width or next_y >= height:
                        continue
                    next_index = next_y * width + next_x
                    if visited[next_index] or pixels[next_x, next_y] < 128:
                        continue
                    visited[next_index] = 1
                    stack.append((next_x, next_y))

            box_width = right - left + 1
            box_height = bottom - top + 1
            box_area = box_width * box_height
            if box_width < min_width or box_height < min_height:
                continue
            if box_area < min_area or box_area > max_area:
                continue

            boxes.append((left, top, right, bottom))

    return sorted(boxes, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True)


def expand_box(box: tuple[int, int, int, int], image_width: int, image_height: int, *, padding: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(image_width, right + padding),
        min(image_height, bottom + padding),
    )


def dedupe_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if all(box_iou(box, kept_box) < 0.55 for kept_box in kept):
            kept.append(box)

    return kept


def box_iou(left_box: tuple[int, int, int, int], right_box: tuple[int, int, int, int]) -> float:
    left = max(left_box[0], right_box[0])
    top = max(left_box[1], right_box[1])
    right = min(left_box[2], right_box[2])
    bottom = min(left_box[3], right_box[3])
    if right <= left or bottom <= top:
        return 0

    intersection = (right - left) * (bottom - top)
    left_area = (left_box[2] - left_box[0]) * (left_box[3] - left_box[1])
    right_area = (right_box[2] - right_box[0]) * (right_box[3] - right_box[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0


def classify_pdf_mark_regions(regions: list[PdfMarkRegion]) -> list[PdfMarkRegion]:
    if not regions:
        return []

    widths = [region.box[2] - region.box[0] for region in regions]
    width_threshold = (max(widths) + min(widths)) / 2 if len(widths) > 1 else widths[0]
    classified: list[PdfMarkRegion] = []

    for region in regions:
        width = region.box[2] - region.box[0]
        height = max(region.box[3] - region.box[1], 1)
        aspect_ratio = width / height
        kind = "front" if width >= width_threshold or aspect_ratio >= 1.08 else "side"
        classified.append(PdfMarkRegion(kind=kind, text=region.text, box=region.box))

    return sorted(classified, key=lambda region: (region.kind, region.box[1], region.box[0]))


def merge_region_texts(regions) -> str:
    return "\n".join(region.text for region in regions if region.text.strip())


def extract_image_text(image_bytes: bytes, *, source: str) -> tuple[str, CartonMarkExtractionStatus]:
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return "", CartonMarkExtractionStatus(
            source=source,
            ok=False,
            engine="unconfigured",
            message="图片 OCR 引擎未配置。请在后端安装 Pillow、pytesseract，并部署 Tesseract 或接入 PaddleOCR。",
            raw_text="",
        )

    try:
        tesseract_cmd, tesseract_lang = configure_tesseract(pytesseract)
        if not tesseract_cmd:
            return "", CartonMarkExtractionStatus(
                source=source,
                ok=False,
                engine="pytesseract",
                message=missing_tesseract_message(),
                raw_text="",
            )

        image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
        texts = []
        for variant in build_photo_ocr_variants(image, ImageEnhance, ImageFilter, ImageOps):
            for config in ("--oem 3 --psm 6 -c preserve_interword_spaces=1", "--oem 3 --psm 11"):
                text = pytesseract.image_to_string(variant, lang=tesseract_lang, config=config)
                if text.strip():
                    texts.append(text)

        text = merge_ocr_text_outputs(texts)
        return text, CartonMarkExtractionStatus(
            source=source,
            ok=bool(text.strip()),
            engine="pytesseract-multi-pass",
            message="" if text.strip() else "图片 OCR 未识别到文字，请检查照片清晰度或 OCR 语言包。",
            raw_text=clip_text(text),
        )
    except Exception as exc:
        return "", CartonMarkExtractionStatus(
            source=source,
            ok=False,
            engine="pytesseract",
            message=f"图片 OCR 失败：{exc}",
            raw_text="",
        )


def build_photo_ocr_variants(image, image_enhance, image_filter, image_ops) -> list:
    base = resize_for_ocr(image.convert("RGB"))
    gray = image_ops.grayscale(base)
    contrast = image_ops.autocontrast(gray)
    enhanced = image_enhance.Contrast(contrast).enhance(1.8)
    sharpened = image_enhance.Sharpness(enhanced).enhance(2.0)
    denoised = sharpened.filter(image_filter.MedianFilter(size=3))
    threshold = estimate_binary_threshold(denoised)
    binary = denoised.point(lambda pixel: 255 if pixel > threshold else 0)

    variants = [base, denoised, binary]
    content_crop = crop_to_dark_content(base)
    if content_crop is not None:
        crop_gray = image_ops.grayscale(resize_for_ocr(content_crop))
        crop_contrast = image_ops.autocontrast(crop_gray)
        variants.append(image_enhance.Sharpness(crop_contrast).enhance(2.0))

    return variants


def resize_for_ocr(image):
    width, height = image.size
    if width <= 0 or height <= 0:
        return image

    target_width = width
    if width < 1800:
        target_width = 1800
    elif width > 2800:
        target_width = 2800

    if target_width == width:
        return image

    target_height = max(1, int(height * target_width / width))
    return image.resize((target_width, target_height))


def estimate_binary_threshold(gray_image) -> int:
    histogram = gray_image.histogram()
    total = sum(histogram)
    if not total:
        return 170

    weighted_sum = sum(index * count for index, count in enumerate(histogram))
    background_mean = weighted_sum / total
    return max(120, min(205, int(background_mean * 0.82)))


def crop_to_dark_content(image):
    width, height = image.size
    if width <= 0 or height <= 0:
        return None

    analysis = image.convert("L")
    threshold = estimate_binary_threshold(analysis)
    mask = analysis.point(lambda pixel: 255 if pixel < threshold else 0)
    box = mask.getbbox()
    if not box:
        return None

    left, top, right, bottom = expand_box(box, width, height, padding=max(24, int(min(width, height) * 0.03)))
    crop_width = right - left
    crop_height = bottom - top
    if crop_width < width * 0.25 or crop_height < height * 0.18:
        return None
    if crop_width > width * 0.96 and crop_height > height * 0.96:
        return None

    return image.crop((left, top, right, bottom))


def merge_ocr_text_outputs(texts: list[str]) -> str:
    seen = set()
    lines = []
    for text in texts:
        for line in normalize_ocr_lines(text):
            key = normalize_compare_value(line)
            if not key or key in seen:
                continue
            seen.add(key)
            lines.append(line)

    return "\n".join(lines)


def extract_fields(text: str, *, source: str) -> list[CartonMarkExtractedField]:
    fields: dict[str, CartonMarkExtractedField] = {}
    normalized_lines = normalize_ocr_lines(text)

    for definition in FIELD_DEFINITIONS:
        value = find_field_value(normalized_lines, definition)
        if value:
            fields[definition.key] = CartonMarkExtractedField(
                key=definition.key,
                label=definition.label,
                value=value,
                confidence=0.76,
                source=source,
            )

    if "barcode" not in fields:
        barcode = find_barcode_candidate(text)
        if barcode:
            fields["barcode"] = CartonMarkExtractedField(
                key="barcode",
                label=FIELD_BY_KEY["barcode"].label,
                value=barcode,
                confidence=0.62,
                source=source,
            )

    return [fields[key] for key in FIELD_ORDER if key in fields]


def enrich_fields_from_expected_values(
    fields: list[CartonMarkExtractedField],
    expected_fields: list[CartonMarkExtractedField],
    text: str,
    *,
    source: str,
) -> list[CartonMarkExtractedField]:
    merged = {field.key: field for field in fields}
    normalized_text = normalize_compare_value(text)
    if not normalized_text:
        return fields

    for expected in expected_fields:
        if expected.key in merged:
            continue

        expected_value = expected.value.strip()
        normalized_expected = normalize_compare_value(expected_value)
        if not is_searchable_expected_value(expected.key, normalized_expected):
            continue
        if normalized_expected not in normalized_text:
            continue

        definition = FIELD_BY_KEY.get(expected.key)
        if not definition:
            continue

        merged[expected.key] = CartonMarkExtractedField(
            key=definition.key,
            label=definition.label,
            value=expected_value,
            confidence=0.58,
            source=source,
        )

    return [merged[key] for key in FIELD_ORDER if key in merged]


def is_searchable_expected_value(key: str, normalized_value: str) -> bool:
    if key == "barcode":
        return len(normalized_value) >= 8
    if key in {"po", "item", "sku", "carton_no"}:
        return len(normalized_value) >= 4

    return len(normalized_value) >= 6


def merge_metadata_fields(
    fields: list[CartonMarkExtractedField],
    metadata: dict[str, str],
    *,
    source: str,
) -> list[CartonMarkExtractedField]:
    merged = {field.key: field for field in fields}

    for key, value in metadata.items():
        normalized_value = value.strip()
        if not normalized_value or key in merged or key not in FIELD_BY_KEY:
            continue
        definition = FIELD_BY_KEY[key]
        merged[key] = CartonMarkExtractedField(
            key=definition.key,
            label=definition.label,
            value=normalized_value,
            confidence=0.9,
            source=source,
        )

    return [merged[key] for key in FIELD_ORDER if key in merged]


def compare_side(
    side: str,
    template_fields: list[CartonMarkExtractedField],
    photo_fields: list[CartonMarkExtractedField],
    photo_status: CartonMarkExtractionStatus,
) -> list[CartonMarkComparisonItem]:
    template_map = {field.key: field for field in template_fields}
    photo_map = {field.key: field for field in photo_fields}
    comparisons: list[CartonMarkComparisonItem] = []

    for key in FIELD_ORDER:
        expected_field = template_map.get(key)
        actual_field = photo_map.get(key)
        if not expected_field and not actual_field:
            continue

        label = (expected_field or actual_field).label  # type: ignore[union-attr]
        expected = expected_field.value if expected_field else ""
        actual = actual_field.value if actual_field else ""
        confidence = min(
            expected_field.confidence if expected_field else 0.4,
            actual_field.confidence if actual_field else 0.4,
        )

        if not expected:
            status = "missing_expected"
            note = "PDF 模板未识别到该字段。"
        elif not actual:
            status = "review" if not photo_status.ok else "missing_actual"
            note = photo_status.message if not photo_status.ok else "照片未识别到该字段。"
        elif normalize_compare_value(expected) == normalize_compare_value(actual):
            status = "pass"
            note = ""
        else:
            status = "mismatch"
            note = "PDF 模板值与实拍识别值不一致。"

        comparisons.append(CartonMarkComparisonItem(
            side=side,
            field_key=key,
            label=label,
            expected=expected,
            actual=actual,
            status=status,
            confidence=confidence,
            note=note,
        ))

    return comparisons


def summarize_comparisons(comparisons: list[CartonMarkComparisonItem]) -> CartonMarkAutoCheckSummary:
    pass_count = sum(1 for item in comparisons if item.status == "pass")
    mismatch_count = sum(1 for item in comparisons if item.status == "mismatch")
    missing_count = sum(1 for item in comparisons if item.status in {"missing_expected", "missing_actual"})
    review_count = sum(1 for item in comparisons if item.status == "review")

    if mismatch_count:
        overall_status = "发现异常"
    elif review_count or missing_count:
        overall_status = "需复核"
    elif pass_count:
        overall_status = "核对通过"
    else:
        overall_status = "未识别"

    return CartonMarkAutoCheckSummary(
        overall_status=overall_status,
        pass_count=pass_count,
        mismatch_count=mismatch_count,
        missing_count=missing_count,
        review_count=review_count,
    )


def find_field_value(lines: list[str], definition: FieldDefinition) -> str:
    for index, line in enumerate(lines):
        for alias in sorted(definition.aliases, key=lambda value: len(normalize_compare_value(value)), reverse=True):
            value = extract_value_after_alias(line, alias)
            if is_plausible_field_value(value, definition):
                return clean_field_value(value)
            if line_looks_like_alias(line, alias):
                next_value = find_next_line_value(lines, index, definition)
                if next_value:
                    return next_value

    return ""


def extract_value_after_alias(line: str, alias: str) -> str:
    pattern = re.compile(
        rf"(?<![A-Z0-9]){build_flexible_alias_pattern(alias)}(?![A-Z0-9])\s*(?:[:：#=.\-])?\s*(.*)",
        re.IGNORECASE,
    )
    match = pattern.search(line)
    if not match:
        return ""

    value = match.group(1)
    value = strip_leading_label_noise(value)
    value = truncate_at_next_field_alias(value, alias)

    return value


def find_next_line_value(lines: list[str], index: int, definition: FieldDefinition) -> str:
    for next_line in lines[index + 1:index + 4]:
        candidate = clean_field_value(truncate_at_next_field_alias(strip_leading_label_noise(next_line), ""))
        if is_plausible_field_value(candidate, definition):
            return candidate

    return ""


def line_looks_like_alias(line: str, alias: str) -> bool:
    cleaned_line = normalize_compare_value(line)
    cleaned_alias = normalize_compare_value(alias)
    if not cleaned_line or not cleaned_alias:
        return False
    if cleaned_line == cleaned_alias:
        return True
    return bool(re.fullmatch(rf"{build_flexible_alias_pattern(alias)}(?:N[O0]|NUMBER|NUM)?", line.strip(), re.IGNORECASE))


def build_flexible_alias_pattern(alias: str) -> str:
    parts = []
    for char in alias:
        upper = char.upper()
        if upper.isspace() or upper in {".", "/", "-", "_"}:
            parts.append(r"[\s./_\-]*")
        elif upper == "O":
            parts.append("[O0]")
        elif upper == "I":
            parts.append("[I1L]")
        elif upper == "S":
            parts.append("[S5]")
        elif upper == "B":
            parts.append("[B8]")
        elif upper.isalnum():
            parts.append(re.escape(upper))
        else:
            parts.append(re.escape(char))

    return "".join(parts)


def strip_leading_label_noise(value: str) -> str:
    value = value.strip(" \t|:/\\#=_;")
    value = re.sub(r"^(?:N[O0]|NO\.|NUMBER|NUM|#)\b\s*[:：#=.\-]?\s*", "", value, flags=re.IGNORECASE)
    return value.strip(" \t|:/\\#=_;")


def truncate_at_next_field_alias(value: str, current_alias: str) -> str:
    earliest = len(value)
    current_key = normalize_compare_value(current_alias)

    for definition in FIELD_DEFINITIONS:
        for alias in definition.aliases:
            if current_key and normalize_compare_value(alias) == current_key:
                continue
            split_match = re.search(
                rf"(?<![A-Z0-9]){build_flexible_alias_pattern(alias)}(?![A-Z0-9])",
                value,
                re.IGNORECASE,
            )
            if split_match and split_match.start() < earliest:
                earliest = split_match.start()

    return value[:earliest]


def is_plausible_field_value(value: str, definition: FieldDefinition) -> bool:
    cleaned = clean_field_value(value)
    normalized = normalize_compare_value(cleaned)
    if not normalized:
        return False
    if any(normalized == normalize_compare_value(alias) for alias in definition.aliases):
        return False
    if any(normalized == normalize_compare_value(other_alias) for field in FIELD_DEFINITIONS for other_alias in field.aliases):
        return False

    return bool(re.search(r"[A-Z0-9一-龥]", cleaned, re.IGNORECASE))


def find_barcode_candidate(text: str) -> str:
    candidates = re.findall(r"\b\d{8,18}\b", text)
    if not candidates:
        return ""

    return max(candidates, key=len)


def normalize_ocr_lines(text: str) -> list[str]:
    text = text.replace("\r", "\n")
    lines = []
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip(" \t|")
        if line:
            lines.append(line)
    return lines


def clean_field_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" :：|#.-")
    return value[:120]


def normalize_compare_value(value: str) -> str:
    value = value.upper()
    value = value.replace("O", "0") if re.fullmatch(r"[A-Z0-9\s\-/.]+", value) else value
    return re.sub(r"[^A-Z0-9一-龥]+", "", value)


def fallback_decode_bytes(content: bytes) -> str:
    decoded = content.decode("utf-8", errors="ignore") or content.decode("latin-1", errors="ignore")
    return "".join(char if char in TEXT_CHARS or "\u4e00" <= char <= "\u9fff" else " " for char in decoded)


def clip_text(text: str, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]
