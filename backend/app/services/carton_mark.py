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
    CartonMarkBatchCheckItem,
    CartonMarkBatchCheckResponse,
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


@dataclass(frozen=True)
class PdfTextSpan:
    text: str
    x: float
    y: float


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: int
    top: int
    right: int
    bottom: int
    confidence: float


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
        "QTY PER CARTON", "PCS/CTN", "PIEZAS POR BULTO",
    )),
    FieldDefinition("carton_no", "箱号", (
        "CARTON NO", "CARTON NO.", "CARTON NUMBER", "CTN NO", "CTN NO.", "CTN#", "C/NO",
        "CARTON", "BULTO", "BULTOS", "BULTO NO",
        "BULTO NO.", "NO DE BULTO", "NO. DE BULTO", "NRO BULTO", "NRO. BULTO",
    )),
    FieldDefinition("box_no", "箱序", ("CAJA NUMERO", "CAJA NÚMERO", "BOX NO", "BOX NUMBER")),
    FieldDefinition("size", "尺码", ("SIZE", "TALLA")),
    FieldDefinition("gw", "G.W", ("G.W", "G.W.", "GW", "GROSS WEIGHT", "PESO BRUTO")),
    FieldDefinition("nw", "N.W", ("N.W", "N.W.", "NW", "NET WEIGHT", "PESO NETO")),
    FieldDefinition("measurement", "尺寸", ("MEAS", "MEAS.", "MEASUREMENT", "DIMENSION", "CARTON SIZE", "CARTON MEAS", "MEDIDA")),
    FieldDefinition("section", "分区", ("SECCION / UNECO", "SECCIÓN / UNECO", "SECCION/UNECO", "SECCIÓN/UNECO", "SECCION", "SECCIÓN")),
    FieldDefinition("barcode", "条码", (
        "BARCODE", "BAR CODE", "BARCODE NO", "BAR CODE NO", "CODE", "EAN", "UPC",
        "CODIGO DE BARRAS", "CÓDIGO DE BARRAS",
    )),
]

FIELD_BY_KEY = {field.key: field for field in FIELD_DEFINITIONS}
FIELD_ORDER = [field.key for field in FIELD_DEFINITIONS]
IDENTIFIER_FIELD_KEYS = {"po", "item", "sku", "carton_no", "barcode"}
OCR_IDENTIFIER_TRANSLATION = str.maketrans({
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "|": "1",
    "S": "5",
    "Z": "2",
    "B": "8",
    "G": "6",
})
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

    front_extracted_fields = extract_fields(front_text, source="front_photo")
    side_extracted_fields = extract_fields(side_text, source="side_photo")
    front_expected_fields = enrich_expected_fields_from_actual_values(
        front_template_fields or template_fields,
        front_extracted_fields,
        f"{front_pdf_text}\n{pdf_text}",
        source="pdf_front_value_match",
    )
    side_expected_fields = enrich_expected_fields_from_actual_values(
        side_template_fields or template_fields,
        side_extracted_fields,
        f"{side_pdf_text}\n{pdf_text}",
        source="pdf_side_value_match",
    )
    front_fields = enrich_fields_from_expected_values(
        front_extracted_fields,
        front_expected_fields,
        front_text,
        source="front_photo_value_match",
    )
    side_fields = enrich_fields_from_expected_values(
        side_extracted_fields,
        side_expected_fields,
        side_text,
        source="side_photo_value_match",
    )
    comparisons = [
        *compare_side("front", front_expected_fields, front_fields, front_status),
        *compare_label_column("front", front_pdf_text, front_text, front_status),
        *compare_side("side", side_expected_fields, side_fields, side_status),
        *compare_label_column("side", side_pdf_text, side_text, side_status),
    ]

    summary = summarize_comparisons(comparisons)
    return CartonMarkAutoCheckResponse(
        summary=summary,
        template_fields=template_fields,
        front_template_fields=front_expected_fields,
        side_template_fields=side_expected_fields,
        front_photo_fields=front_fields,
        side_photo_fields=side_fields,
        comparisons=comparisons,
        extraction=[pdf_status, pdf_layout_status, front_status, side_status],
    )


def build_carton_mark_batch_auto_check(
    *,
    pdf_bytes: bytes,
    front_images: list[tuple[str, bytes]],
    side_images: list[tuple[str, bytes]],
    customer_name: str = "",
    po: str = "",
    item: str = "",
) -> CartonMarkBatchCheckResponse:
    """Check every uploaded front/side image independently against one PDF template."""
    pdf_text, pdf_status = extract_pdf_text(pdf_bytes)
    front_pdf_text, side_pdf_text, pdf_layout_status = extract_pdf_template_side_texts(
        pdf_bytes,
        fallback_text=pdf_text,
    )
    metadata = {
        "customer_name": customer_name,
        "po": po,
        "item": item,
    }
    template_fields = merge_metadata_fields(
        extract_fields(pdf_text, source="pdf_template"),
        metadata,
        source="template_metadata",
    )
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

    def build_item(side: str, image_bytes: bytes) -> CartonMarkAutoCheckResponse:
        source = f"{side}_photo"
        photo_text, photo_status = extract_image_text(image_bytes, source=source)
        is_front = side == "front"
        template_text = front_pdf_text if is_front else side_pdf_text
        expected_template_seed = front_template_fields if is_front else side_template_fields
        extracted_fields = extract_fields(photo_text, source=source)
        expected_fields = enrich_expected_fields_from_actual_values(
            expected_template_seed or template_fields,
            extracted_fields,
            f"{template_text}\n{pdf_text}",
            source=f"pdf_{side}_value_match",
        )
        photo_fields = enrich_fields_from_expected_values(
            extracted_fields,
            expected_fields,
            photo_text,
            source=f"{side}_photo_value_match",
        )
        comparisons = [
            *compare_side(side, expected_fields, photo_fields, photo_status),
            *compare_label_column(side, template_text, photo_text, photo_status),
        ]
        return CartonMarkAutoCheckResponse(
            summary=summarize_comparisons(comparisons),
            template_fields=template_fields,
            front_template_fields=expected_fields if is_front else [],
            side_template_fields=expected_fields if not is_front else [],
            front_photo_fields=photo_fields if is_front else [],
            side_photo_fields=photo_fields if not is_front else [],
            comparisons=comparisons,
            extraction=[pdf_status, pdf_layout_status, photo_status],
        )

    items: list[CartonMarkBatchCheckItem] = []
    all_comparisons: list[CartonMarkComparisonItem] = []
    for side, images in (("front", front_images), ("side", side_images)):
        for file_index, (file_name, image_bytes) in enumerate(images):
            result = build_item(side, image_bytes)
            items.append(CartonMarkBatchCheckItem(
                side=side,
                file_name=file_name,
                file_index=file_index,
                result=result,
            ))
            all_comparisons.extend(result.comparisons)

    return CartonMarkBatchCheckResponse(
        summary=summarize_comparisons(all_comparisons),
        items=items,
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


def extract_pdf_vector_mark_regions(pdf_bytes: bytes) -> list[PdfMarkRegion]:
    """Read repeated mark layouts from vector PDF text before falling back to OCR.

    Customer carton-mark PDFs are commonly exported as one very wide page with
    front / side / front / side marks laid out horizontally.  Raster OCR can
    identify the outer boxes but loses table cells, while the original PDF
    already contains text at precise coordinates.  This path keeps that text
    and splits only deliberately wide pages into their horizontal mark areas.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return []

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        regions: list[PdfMarkRegion] = []

        for page_index, page in enumerate(reader.pages):
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            spans: list[PdfTextSpan] = []

            def collect_text(text, _cm, tm, _font_dict, _font_size):
                value = str(text or "").strip()
                if not value:
                    return
                try:
                    x = float(tm[4])
                    y = float(tm[5])
                except (IndexError, TypeError, ValueError):
                    return
                spans.append(PdfTextSpan(text=value, x=x, y=y))

            page.extract_text(visitor_text=collect_text)
            regions.extend(build_pdf_vector_mark_regions(
                spans,
                page_width=page_width,
                page_height=page_height,
                page_index=page_index,
            ))

        return classify_pdf_mark_regions(regions)
    except Exception:
        return []


def build_pdf_vector_mark_regions(
    spans: list[PdfTextSpan],
    *,
    page_width: float,
    page_height: float,
    page_index: int = 0,
) -> list[PdfMarkRegion]:
    """Build ordered mark regions from text origins on a deliberately wide page."""
    if page_width <= 0 or page_height <= 0 or page_width / page_height < 2.2:
        return []

    # Decorative footer text is often one long vector string spanning every
    # mark.  It is not part of any mark table and would otherwise bridge the
    # horizontal groups, so only use text in the primary page area.
    usable_spans = [
        span
        for span in spans
        if normalize_compare_value(span.text)
        and 0 <= span.x <= page_width
        and span.y >= page_height * 0.32
    ]
    if len(usable_spans) < 6:
        return []

    group_gap = max(80.0, page_width * 0.12)
    groups: list[list[PdfTextSpan]] = []
    last_x: float | None = None
    for span in sorted(usable_spans, key=lambda item: item.x):
        if last_x is None or span.x - last_x <= group_gap:
            if not groups:
                groups.append([])
            groups[-1].append(span)
        else:
            groups.append([span])
        last_x = span.x

    groups = [group for group in groups if len(group) >= 3]
    if len(groups) < 2:
        return []

    # Make later PDF pages sort after the current one.  The box is only used
    # for reading order after vector extraction, never for an image crop.
    page_offset = int(page_index * max(page_width * 4, 10_000))
    regions: list[PdfMarkRegion] = []
    for group in groups:
        text = build_pdf_vector_region_text(group)
        if not text:
            continue
        left = int(min(span.x for span in group)) + page_offset
        right = int(max(span.x for span in group)) + page_offset
        top = int(max(0, page_height - max(span.y for span in group)))
        bottom = int(max(0, page_height - min(span.y for span in group)))
        regions.append(PdfMarkRegion(kind="", text=text, box=(left, top, right, bottom)))

    return regions


def build_pdf_vector_region_text(spans: list[PdfTextSpan]) -> str:
    if not spans:
        return ""

    row_threshold = 8.0
    rows: list[list[PdfTextSpan]] = []
    for span in sorted(spans, key=lambda item: (-item.y, item.x)):
        row = next(
            (
                candidate
                for candidate in rows
                if abs(span.y - sum(item.y for item in candidate) / len(candidate)) <= row_threshold
            ),
            None,
        )
        if row is None:
            rows.append([span])
        else:
            row.append(span)

    lines = []
    for row in rows:
        line = " | ".join(item.text for item in sorted(row, key=lambda item: item.x))
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def extract_pdf_template_side_texts(pdf_bytes: bytes, *, fallback_text: str) -> tuple[str, str, CartonMarkExtractionStatus]:
    regions, status = extract_pdf_mark_regions(pdf_bytes)
    if not regions:
        return fallback_text, fallback_text, status

    regions = select_primary_pdf_mark_regions(regions)
    front_region = next((region for region in regions if region.kind == "front"), None)
    side_region = next((region for region in regions if region.kind == "side"), None)
    front_text = front_region.text.strip() if front_region else ""
    side_text = side_region.text.strip() if side_region else ""

    if not front_text:
        front_text = fallback_text
    if not side_text:
        side_text = fallback_text

    return front_text, side_text, status


def extract_pdf_mark_regions(pdf_bytes: bytes) -> tuple[list[PdfMarkRegion], CartonMarkExtractionStatus]:
    vector_regions = extract_pdf_vector_mark_regions(pdf_bytes)
    if vector_regions:
        regions = select_primary_pdf_mark_regions(vector_regions)
        return regions, CartonMarkExtractionStatus(
            source="pdf_template_regions",
            ok=True,
            engine="pypdf-vector-coordinates",
            message="已读取 PDF 原始文字坐标，并只提取最左侧第一组正唛和侧唛。",
            raw_text=clip_text(merge_region_texts(regions)),
        )

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

        regions = select_primary_pdf_mark_regions(classify_pdf_mark_regions(regions))
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
            message="已按 PDF 页面顺序只提取第一组正唛和侧唛区域。",
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


def find_connected_boxes(
    mask,
    *,
    min_width_ratio: float = 0.035,
    min_height_ratio: float = 0.03,
    min_area_ratio: float = 0.0008,
    max_area_ratio: float = 0.18,
) -> list[tuple[int, int, int, int]]:
    width, height = mask.size
    pixels = mask.load()
    visited = bytearray(width * height)
    boxes: list[tuple[int, int, int, int]] = []
    min_width = max(28, int(width * min_width_ratio))
    min_height = max(22, int(height * min_height_ratio))
    min_area = max(500, int(width * height * min_area_ratio))
    max_area = int(width * height * max_area_ratio)

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
        normalized_text = normalize_compare_value(region.text)
        front_score = sum(
            marker in normalized_text
            for marker in ("IMPORTADOR", "DIRECCION", "PROVEEDOR", "RFC")
        )
        side_score = sum(
            marker in normalized_text
            for marker in ("DESCRIPCION", "PIEZASPORBULTO", "CAJANUMERO", "MEAS", "SECCION")
        )
        if front_score != side_score:
            kind = "front" if front_score > side_score else "side"
        else:
            kind = "front" if width >= width_threshold or aspect_ratio >= 1.08 else "side"
        classified.append(PdfMarkRegion(kind=kind, text=region.text, box=region.box))

    return sorted(classified, key=pdf_region_position_key)


def select_primary_pdf_mark_regions(regions: list[PdfMarkRegion]) -> list[PdfMarkRegion]:
    if not regions:
        return []

    ordered = sorted(regions, key=pdf_region_position_key)
    front_region = next((region for region in ordered if region.kind == "front"), None)
    if front_region is None:
        front_region = ordered[0]

    front_index = next(
        (index for index, region in enumerate(ordered) if region is front_region),
        0,
    )
    side_region = next(
        (region for region in ordered[front_index + 1:] if region.kind == "side"),
        None,
    )
    if side_region is None:
        side_region = next(
            (region for region in ordered if region.kind == "side" and region is not front_region),
            None,
        )
    if side_region is None:
        side_region = next((region for region in ordered[front_index + 1:] if region is not front_region), None)

    selected = [
        PdfMarkRegion(kind="front", text=front_region.text, box=front_region.box),
    ]
    if side_region is not None:
        selected.append(PdfMarkRegion(kind="side", text=side_region.text, box=side_region.box))

    return selected


def pdf_region_position_key(region: PdfMarkRegion) -> tuple[int, int, int]:
    left, top, right, bottom = region.box
    return (left, top, -((right - left) * (bottom - top)))


def merge_region_texts(regions) -> str:
    return "\n".join(region.text for region in regions if region.text.strip())


@lru_cache(maxsize=1)
def get_rapidocr_engine():
    try:
        from rapidocr import RapidOCR  # type: ignore

        return RapidOCR()
    except Exception:
        return None


def extract_image_text(image_bytes: bytes, *, source: str) -> tuple[str, CartonMarkExtractionStatus]:
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # type: ignore
    except Exception:
        return "", CartonMarkExtractionStatus(
            source=source,
            ok=False,
            engine="unconfigured",
            message="图片 OCR 引擎未配置。请在后端安装 Pillow 及 RapidOCR 或 Tesseract。",
            raw_text="",
        )

    try:
        image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
        variants = build_photo_ocr_variants(image, ImageEnhance, ImageFilter, ImageOps)
        rapidocr_texts = []
        rapidocr_engine = get_rapidocr_engine()

        if rapidocr_engine is not None:
            # PP-OCR can detect text lines on perspective/low-contrast carton
            # labels.  Test the whole label plus the most relevant crops before
            # falling back to the older character-level Tesseract path.
            for variant in variants[:8]:
                text = rapidocr_image_to_text(rapidocr_engine, variant)
                if text.strip():
                    rapidocr_texts.append(text)
                candidate_text = merge_ocr_text_outputs(rapidocr_texts)
                if len(extract_fields(candidate_text, source=source)) >= 3:
                    break

        rapidocr_text = merge_ocr_text_outputs(rapidocr_texts)
        if rapidocr_text and len(extract_fields(rapidocr_text, source=source)) >= 3:
            return rapidocr_text, CartonMarkExtractionStatus(
                source=source,
                ok=True,
                engine="rapidocr-pp-ocrv6",
                message="",
                raw_text=clip_text(rapidocr_text),
            )

        try:
            import pytesseract  # type: ignore
        except Exception:
            if rapidocr_text:
                return rapidocr_text, CartonMarkExtractionStatus(
                    source=source,
                    ok=True,
                    engine="rapidocr-pp-ocrv6",
                    message="RapidOCR 已识别到部分文字；请根据核验结果复核未提取字段。",
                    raw_text=clip_text(rapidocr_text),
                )
            raise RuntimeError("RapidOCR 与 pytesseract 均不可用")

        tesseract_cmd, tesseract_lang = configure_tesseract(pytesseract)
        if not tesseract_cmd:
            if rapidocr_text:
                return rapidocr_text, CartonMarkExtractionStatus(
                    source=source,
                    ok=True,
                    engine="rapidocr-pp-ocrv6",
                    message="RapidOCR 已识别到部分文字；请根据核验结果复核未提取字段。",
                    raw_text=clip_text(rapidocr_text),
                )
            return "", CartonMarkExtractionStatus(
                source=source,
                ok=False,
                engine="rapidocr+pytesseract",
                message=missing_tesseract_message(),
                raw_text="",
            )

        texts = list(rapidocr_texts)
        primary_configs = (
            "--oem 3 --psm 6 -c preserve_interword_spaces=1",
            "--oem 3 --psm 4 -c preserve_interword_spaces=1",
            "--oem 3 --psm 11",
        )
        crop_configs = (
            "--oem 3 --psm 6 -c preserve_interword_spaces=1",
            "--oem 3 --psm 11",
        )
        for index, variant in enumerate(variants):
            configs = primary_configs if index < 3 else crop_configs
            for config in configs:
                text = tesseract_image_to_string(
                    pytesseract,
                    variant,
                    lang=tesseract_lang,
                    config=config,
                    timeout=10,
                )
                if text.strip():
                    texts.append(text)
            if index < 8:
                table_text = tesseract_image_to_table_text(
                    pytesseract,
                    variant,
                    lang=tesseract_lang,
                    config="--oem 3 --psm 6 -c preserve_interword_spaces=1",
                    timeout=10,
                )
                if table_text.strip():
                    texts.append(table_text)

        text = merge_ocr_text_outputs(texts)
        return text, CartonMarkExtractionStatus(
            source=source,
            ok=bool(text.strip()),
            engine="rapidocr-pp-ocrv6+pytesseract-fallback" if rapidocr_engine is not None else "pytesseract-multi-pass",
            message="" if text.strip() else "图片 OCR 已尝试 PP-OCR、整图、箱唛候选区域裁剪和轻微旋转，仍未识别到文字；请镜头正对单块箱唛、让标签占画面约 70%，避开反光后重拍，或先框选箱唛区域再核对。",
            raw_text=clip_text(text),
        )
    except Exception as exc:
        return "", CartonMarkExtractionStatus(
            source=source,
            ok=False,
            engine="rapidocr+pytesseract",
            message=f"图片 OCR 失败：{exc}",
            raw_text="",
        )


def rapidocr_image_to_text(engine, image) -> str:
    try:
        return rapidocr_result_to_text(engine(image))
    except Exception:
        return ""


def rapidocr_result_to_text(result) -> str:
    if result is None:
        return ""

    try:
        texts = tuple(str(value or "").strip() for value in getattr(result, "txts", ()) or ())
    except Exception:
        return ""

    raw_lines = [text for text in texts if text]
    boxes = getattr(result, "boxes", None)
    scores = getattr(result, "scores", None)
    words: list[OcrWord] = []

    if boxes is not None:
        for index, text in enumerate(texts):
            if not text:
                continue
            try:
                points = boxes[index]
                xs = [float(point[0]) for point in points]
                ys = [float(point[1]) for point in points]
                score = float(scores[index]) if scores is not None else 0.8
            except (IndexError, TypeError, ValueError):
                continue
            if not xs or not ys:
                continue
            left = int(min(xs))
            top = int(min(ys))
            words.append(OcrWord(
                text=text,
                left=left,
                top=top,
                right=max(left + 1, int(max(xs))),
                bottom=max(top + 1, int(max(ys))),
                confidence=score * 100,
            ))

    table_text = build_ocr_word_table_text(words)
    lines = []
    if table_text.strip():
        lines.append(table_text)
    lines.extend(raw_lines)
    return merge_ocr_text_outputs(lines)


def tesseract_image_to_string(pytesseract_module, image, *, lang: str, config: str, timeout: int) -> str:
    try:
        return pytesseract_module.image_to_string(image, lang=lang, config=config, timeout=timeout)
    except TypeError:
        return pytesseract_module.image_to_string(image, lang=lang, config=config)
    except RuntimeError:
        return ""


def tesseract_image_to_table_text(pytesseract_module, image, *, lang: str, config: str, timeout: int) -> str:
    try:
        from pytesseract import Output  # type: ignore
    except Exception:
        return ""

    try:
        data = pytesseract_module.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=Output.DICT,
            timeout=timeout,
        )
    except TypeError:
        data = pytesseract_module.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=Output.DICT,
        )
    except RuntimeError:
        return ""

    return build_ocr_word_table_text(collect_ocr_words(data))


def collect_ocr_words(data: dict) -> list[OcrWord]:
    words: list[OcrWord] = []
    texts = data.get("text", [])
    for index, raw_text in enumerate(texts):
        text = str(raw_text or "").strip()
        if not re.search(r"[A-Z0-9一-龥]", text, re.IGNORECASE):
            continue

        try:
            confidence = float(data.get("conf", [])[index])
        except Exception:
            confidence = 0
        if confidence < 8 and len(normalize_compare_value(text)) < 3:
            continue

        try:
            left = int(float(data.get("left", [])[index]))
            top = int(float(data.get("top", [])[index]))
            width = int(float(data.get("width", [])[index]))
            height = int(float(data.get("height", [])[index]))
        except Exception:
            continue
        if width <= 0 or height <= 0:
            continue

        words.append(OcrWord(
            text=text,
            left=left,
            top=top,
            right=left + width,
            bottom=top + height,
            confidence=confidence,
        ))

    return words


def build_ocr_word_table_text(words: list[OcrWord]) -> str:
    if not words:
        return ""

    rows = group_ocr_words_into_rows(words)
    lines = []
    lines.extend(words_to_spaced_line(row) for row in rows)
    lines.extend(build_label_value_lines_from_rows(rows))
    return merge_ocr_text_outputs(lines)


def group_ocr_words_into_rows(words: list[OcrWord]) -> list[list[OcrWord]]:
    sorted_words = sorted(words, key=lambda word: (word.top + word.bottom, word.left))
    median_height = median_number([word.bottom - word.top for word in sorted_words]) or 12
    row_threshold = max(10, int(median_height * 0.75))
    rows: list[list[OcrWord]] = []

    for word in sorted_words:
        center_y = (word.top + word.bottom) // 2
        best_row = None
        best_distance = row_threshold + 1
        for row in rows:
            row_center = sum((item.top + item.bottom) // 2 for item in row) // len(row)
            distance = abs(center_y - row_center)
            if distance <= row_threshold and distance < best_distance:
                best_row = row
                best_distance = distance

        if best_row is None:
            rows.append([word])
        else:
            best_row.append(word)

    return [sorted(row, key=lambda word: word.left) for row in rows]


def words_to_spaced_line(words: list[OcrWord]) -> str:
    if not words:
        return ""

    sorted_words = sorted(words, key=lambda word: word.left)
    widths = [word.right - word.left for word in sorted_words]
    median_width = median_number(widths) or 16
    parts = [sorted_words[0].text]
    previous = sorted_words[0]

    for word in sorted_words[1:]:
        gap = word.left - previous.right
        parts.append(" | " if gap > median_width * 1.8 else " ")
        parts.append(word.text)
        previous = word

    return "".join(parts)


def build_label_value_lines_from_rows(rows: list[list[OcrWord]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        if len(row) < 2:
            continue

        row_line = words_to_spaced_line(row)
        for definition in FIELD_DEFINITIONS:
            alias_match = find_alias_word_span(row, definition)
            if alias_match is None:
                continue

            alias_text, alias_right = alias_match
            value_words = [
                word
                for word in row
                if word.left >= alias_right - 2 and not word_looks_like_any_alias(word.text)
            ]
            value_text = clean_field_value(" ".join(word.text for word in value_words))
            if is_plausible_field_value(value_text, definition):
                lines.append(f"{alias_text} {value_text}")
            elif line_looks_like_alias(row_line, alias_text):
                lines.append(row_line)

    return lines


def find_alias_word_span(row: list[OcrWord], definition: FieldDefinition) -> tuple[str, int] | None:
    normalized_words = [normalize_compare_value(word.text) for word in row]
    for alias in sorted(definition.aliases, key=lambda value: len(normalize_compare_value(value)), reverse=True):
        alias_key = normalize_compare_value(alias)
        if not alias_key:
            continue

        for start in range(len(row)):
            combined = ""
            for end in range(start, min(len(row), start + 6)):
                combined += normalized_words[end]
                if combined == alias_key:
                    return alias, row[end].right
                if len(combined) > len(alias_key) + 4:
                    break

    return None


def word_looks_like_any_alias(text: str) -> bool:
    normalized = normalize_compare_value(text)
    if not normalized:
        return False
    return any(
        normalized == normalize_compare_value(alias)
        for definition in FIELD_DEFINITIONS
        for alias in definition.aliases
    )


def median_number(values: list[int]) -> float:
    if not values:
        return 0

    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])

    return (ordered[middle - 1] + ordered[middle]) / 2


def build_photo_ocr_variants(image, image_enhance, image_filter, image_ops) -> list:
    base = resize_for_ocr(image.convert("RGB"))
    variants = []
    seen_sizes: set[tuple[int, int, int]] = set()

    def add_variant(variant) -> None:
        key = (variant.width, variant.height, len(variants))
        if variant.width < 120 or variant.height < 80:
            return
        if key in seen_sizes:
            return
        seen_sizes.add(key)
        variants.append(variant)

    gray = image_ops.grayscale(base)
    contrast = image_ops.autocontrast(gray)
    enhanced = image_enhance.Contrast(contrast).enhance(1.8)
    sharpened = image_enhance.Sharpness(enhanced).enhance(2.0)
    denoised = sharpened.filter(image_filter.MedianFilter(size=3))
    threshold = estimate_binary_threshold(denoised)
    binary = denoised.point(lambda pixel: 255 if pixel > threshold else 0)

    add_variant(base)
    add_variant(denoised)
    add_variant(binary)

    content_crop = crop_to_dark_content(base)
    if content_crop is not None:
        add_photo_region_variants(content_crop, variants, seen_sizes, image_enhance, image_filter, image_ops)

    for box in locate_photo_mark_boxes(base, image_filter, image_ops)[:4]:
        region = base.crop(box)
        add_photo_region_variants(region, variants, seen_sizes, image_enhance, image_filter, image_ops)

    rotated = [
        base.rotate(angle, expand=True, fillcolor=(255, 255, 255))
        for angle in (-2, 2)
    ]
    for rotated_base in rotated:
        rotated_crop = crop_to_dark_content(rotated_base)
        if rotated_crop is not None:
            add_photo_region_variants(rotated_crop, variants, seen_sizes, image_enhance, image_filter, image_ops)

    return variants[:12]


def add_photo_region_variants(region, variants: list, seen_sizes: set[tuple[int, int, int]], image_enhance, image_filter, image_ops) -> None:
    def add_variant(variant) -> None:
        key = (variant.width, variant.height, len(variants))
        if variant.width < 120 or variant.height < 80:
            return
        if key in seen_sizes:
            return
        seen_sizes.add(key)
        variants.append(variant)

    region = resize_for_ocr(region.convert("RGB"))
    crop_gray = image_ops.grayscale(region)
    crop_contrast = image_ops.autocontrast(crop_gray)
    crop_enhanced = image_enhance.Contrast(crop_contrast).enhance(2.2)
    crop_sharp = image_enhance.Sharpness(crop_enhanced).enhance(2.4)
    crop_denoised = crop_sharp.filter(image_filter.MedianFilter(size=3))
    crop_threshold = estimate_binary_threshold(crop_denoised)
    crop_binary = crop_denoised.point(lambda pixel: 255 if pixel > crop_threshold else 0)

    add_variant(region)
    add_variant(crop_denoised)
    add_variant(crop_binary)


def locate_photo_mark_boxes(image, image_filter, image_ops) -> list[tuple[int, int, int, int]]:
    width, height = image.size
    if width <= 0 or height <= 0:
        return []

    max_analysis_width = 1200
    scale = min(1.0, max_analysis_width / max(width, 1))
    analysis_image = image.resize((int(width * scale), int(height * scale))) if scale < 1 else image
    gray = image_ops.autocontrast(image_ops.grayscale(analysis_image))

    masks = []
    edge_mask = gray.filter(image_filter.FIND_EDGES)
    edge_threshold = estimate_highlight_threshold(edge_mask)
    masks.append(edge_mask.point(lambda pixel: 255 if pixel > edge_threshold else 0))

    dark_threshold = estimate_binary_threshold(gray)
    masks.append(gray.point(lambda pixel: 255 if pixel < dark_threshold else 0))

    candidate_boxes = []
    for mask in masks:
        grouped = mask.filter(image_filter.MaxFilter(31)).filter(image_filter.MinFilter(7))
        candidate_boxes.extend(find_connected_boxes(
            grouped,
            min_width_ratio=0.08,
            min_height_ratio=0.08,
            min_area_ratio=0.008,
            max_area_ratio=0.72,
        ))

    boxes = []
    for box in filter_plausible_photo_mark_boxes(candidate_boxes, analysis_image.width, analysis_image.height):
        boxes.append(expand_box(
            (
                int(box[0] / scale),
                int(box[1] / scale),
                int(box[2] / scale),
                int(box[3] / scale),
            ),
            width,
            height,
            padding=max(30, int(min(width, height) * 0.025)),
        ))

    return dedupe_boxes(sorted(
        boxes,
        key=lambda box: (box[2] - box[0]) * (box[3] - box[1]),
        reverse=True,
    ))


def estimate_highlight_threshold(gray_image) -> int:
    histogram = gray_image.histogram()
    total = sum(histogram)
    if not total:
        return 28

    weighted_sum = sum(index * count for index, count in enumerate(histogram))
    mean = weighted_sum / total
    return max(18, min(55, int(mean * 1.35)))


def filter_plausible_photo_mark_boxes(
    boxes: list[tuple[int, int, int, int]],
    image_width: int,
    image_height: int,
) -> list[tuple[int, int, int, int]]:
    filtered = []

    for box in boxes:
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width <= 0 or height <= 0:
            continue

        area_ratio = (width * height) / max(image_width * image_height, 1)
        aspect_ratio = width / max(height, 1)
        if area_ratio < 0.02 or area_ratio > 0.78:
            continue
        if aspect_ratio < 0.35 or aspect_ratio > 4.8:
            continue
        if width < image_width * 0.12 or height < image_height * 0.10:
            continue

        filtered.append(box)

    return filtered


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
                value=normalize_extracted_field_value(value, definition),
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
    if not normalize_compare_value(text):
        return fields

    for expected in expected_fields:
        if expected.key in merged:
            continue

        expected_value = expected.value.strip()
        if not photo_text_matches_expected_value(text, expected_value, expected.key):
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


def enrich_expected_fields_from_actual_values(
    expected_fields: list[CartonMarkExtractedField],
    actual_fields: list[CartonMarkExtractedField],
    template_text: str,
    *,
    source: str,
) -> list[CartonMarkExtractedField]:
    merged = {field.key: field for field in expected_fields}
    if not normalize_compare_value(template_text):
        return expected_fields

    for actual in actual_fields:
        if actual.key in merged:
            continue

        actual_value = actual.value.strip()
        if not actual_value:
            continue
        if not photo_text_matches_expected_value(template_text, actual_value, actual.key):
            continue

        definition = FIELD_BY_KEY.get(actual.key)
        if not definition:
            continue

        merged[actual.key] = CartonMarkExtractedField(
            key=definition.key,
            label=definition.label,
            value=actual_value,
            confidence=min(0.62, actual.confidence),
            source=source,
        )

    return [merged[key] for key in FIELD_ORDER if key in merged]


def photo_text_matches_expected_value(text: str, expected_value: str, key: str) -> bool:
    normalized_expected = normalize_compare_value(expected_value)
    if not is_searchable_expected_value(key, normalized_expected):
        return False

    normalized_text = normalize_compare_value(text)
    if normalized_expected in normalized_text:
        return True
    if key not in IDENTIFIER_FIELD_KEYS:
        return False

    numeric_bias = key in {"po", "item", "carton_no", "barcode"}
    expected_identifier = normalize_identifier_value(expected_value, numeric_bias=numeric_bias)
    if not is_searchable_expected_value(key, expected_identifier):
        return False

    candidates = build_identifier_candidates(text, numeric_bias=numeric_bias)
    if any(expected_identifier in candidate for candidate in candidates):
        return True

    max_distance = 2 if len(expected_identifier) >= 8 else 1
    return any(
        fuzzy_contains_identifier(candidate, expected_identifier, max_distance)
        for candidate in candidates
    )


def is_searchable_expected_value(key: str, normalized_value: str) -> bool:
    if key == "barcode":
        return len(normalized_value) >= 8
    if key in {"po", "item", "sku", "carton_no"}:
        return len(normalized_value) >= 4

    return len(normalized_value) >= 6


def normalize_identifier_value(value: str, *, numeric_bias: bool) -> str:
    normalized = value.upper()
    if numeric_bias:
        normalized = normalized.translate(OCR_IDENTIFIER_TRANSLATION)
    return re.sub(r"[^A-Z0-9]+", "", normalized)


def build_identifier_candidates(text: str, *, numeric_bias: bool) -> list[str]:
    tokens = [
        normalize_identifier_value(token, numeric_bias=numeric_bias)
        for token in re.findall(r"[A-Z0-9|]+", text.upper())
    ]
    tokens = [token for token in tokens if token]

    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(candidate: str) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    for token in tokens:
        add_candidate(token)

    max_window_size = min(6, len(tokens))
    for window_size in range(2, max_window_size + 1):
        for start in range(0, len(tokens) - window_size + 1):
            add_candidate("".join(tokens[start:start + window_size]))

    joined = "".join(tokens)
    if len(joined) <= 300:
        add_candidate(joined)

    return candidates


def fuzzy_contains_identifier(candidate: str, expected: str, max_distance: int) -> bool:
    if not candidate or not expected:
        return False
    if expected in candidate:
        return True

    min_length = max(1, len(expected) - max_distance)
    max_length = len(expected) + max_distance
    for length in range(min_length, max_length + 1):
        if length > len(candidate):
            continue
        for start in range(0, len(candidate) - length + 1):
            segment = candidate[start:start + length]
            if levenshtein_distance_at_most(expected, segment, max_distance):
                return True

    return False


def levenshtein_distance_at_most(left: str, right: str, max_distance: int) -> bool:
    if abs(len(left) - len(right)) > max_distance:
        return False

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(min(
                current[right_index - 1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + cost,
            ))
            row_min = min(row_min, current[-1])

        if row_min > max_distance:
            return False
        previous = current

    return previous[-1] <= max_distance


def levenshtein_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(min(
                current[right_index - 1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + cost,
            ))
        previous = current

    return previous[-1]


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
        elif field_values_match(key, expected, actual):
            status = "pass"
            note = ""
        else:
            status = "mismatch"
            note = "PDF 模板值与实拍识别值不一致。"

        comparisons.append(CartonMarkComparisonItem(
            side=side,
            field_key=key,
            label=label,
            comparison_scope="right_value",
            expected=expected,
            actual=actual,
            status=status,
            confidence=confidence,
            note=note,
        ))

    return comparisons


def compare_label_column(
    side: str,
    template_text: str,
    photo_text: str,
    photo_status: CartonMarkExtractionStatus,
) -> list[CartonMarkComparisonItem]:
    """Compare the printed left-column field names, not only their values."""
    expected_labels = extract_field_labels(template_text)
    actual_labels = extract_field_labels(photo_text)
    comparisons: list[CartonMarkComparisonItem] = []

    for definition in FIELD_DEFINITIONS:
        expected = expected_labels.get(definition.key, "")
        if not expected:
            continue

        actual = actual_labels.get(definition.key, "")
        if not actual:
            status = "review" if not photo_status.ok else "missing_actual"
            note = photo_status.message if not photo_status.ok else "照片左侧字段名未识别，或与 PDF 模板字段名不符。"
        elif field_label_values_match(expected, actual):
            status = "pass"
            note = ""
        else:
            status = "mismatch"
            note = "PDF 模板左侧字段名与实拍不一致。"

        comparisons.append(CartonMarkComparisonItem(
            side=side,
            field_key=f"left_label:{definition.key}",
            label=f"左侧字段名 · {definition.label}",
            comparison_scope="left_label",
            expected=expected,
            actual=actual,
            status=status,
            confidence=0.82 if actual else 0.45,
            note=note,
        ))

    return comparisons


def extract_field_labels(text: str) -> dict[str, str]:
    candidates = extract_label_candidates(text)
    labels: dict[str, str] = {}
    for definition in FIELD_DEFINITIONS:
        exact = find_exact_field_label(candidates, definition)
        if exact:
            labels[definition.key] = exact
            continue

        approximate = find_approximate_field_label(candidates, definition)
        if approximate:
            labels[definition.key] = approximate

    return labels


def extract_label_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    seen = set()
    for line in normalize_ocr_lines(text):
        first_cell = line.split("|", 1)[0].strip(" :：|#.-")
        if re.match(r"^\d", first_cell):
            first_cell = re.sub(r"^\d+(?:[.,]\d+)?", "", first_cell).strip(" :：|#.-")
        else:
            first_cell = re.split(r"\d", first_cell, maxsplit=1)[0].strip(" :：|#.-")
        if not first_cell or not re.search(r"[A-Z一-龥]", first_cell, re.IGNORECASE):
            continue
        key = normalize_alias_key(first_cell)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(first_cell)
    return candidates


def find_exact_field_label(candidates: list[str], definition: FieldDefinition) -> str:
    for candidate in candidates:
        candidate_key = normalize_alias_key(candidate)
        for alias in sorted(definition.aliases, key=lambda value: len(normalize_alias_key(value)), reverse=True):
            if candidate_key == normalize_alias_key(alias):
                return candidate
    return ""


def find_approximate_field_label(candidates: list[str], definition: FieldDefinition) -> str:
    best_candidate = ""
    best_distance: int | None = None
    for candidate in candidates:
        candidate_key = normalize_alias_key(candidate)
        if len(candidate_key) < 5:
            continue
        for alias in definition.aliases:
            alias_key = normalize_alias_key(alias)
            if len(alias_key) < 6:
                continue
            distance_limit = max(2, int(max(len(candidate_key), len(alias_key)) * 0.42))
            if not levenshtein_distance_at_most(candidate_key, alias_key, distance_limit):
                continue
            distance = levenshtein_distance(candidate_key, alias_key)
            if best_distance is None or distance < best_distance:
                best_candidate = candidate
                best_distance = distance
    return best_candidate


def field_label_values_match(expected: str, actual: str) -> bool:
    return normalize_alias_key(expected) == normalize_alias_key(actual)


def field_values_match(key: str, expected: str, actual: str) -> bool:
    if normalize_compare_value(expected) == normalize_compare_value(actual):
        return True
    if key in IDENTIFIER_FIELD_KEYS:
        return photo_text_matches_expected_value(actual, expected, key)

    return False


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
            if alias_is_shadowed_by_other_field(line, alias, definition):
                continue
            value = extract_value_after_alias(line, alias)
            if is_plausible_field_value(value, definition):
                return clean_field_value(value)
            if len(normalize_compare_value(alias)) >= 6:
                value = extract_value_before_alias(line, alias)
                if is_plausible_field_value(value, definition):
                    return clean_field_value(value)
            if line_looks_like_alias(line, alias):
                next_value = find_next_line_value(lines, index, definition)
                if next_value:
                    return next_value

    return ""


def alias_is_shadowed_by_other_field(line: str, alias: str, definition: FieldDefinition) -> bool:
    """Do not parse a short field alias inside a longer label from another field."""
    alias_key = normalize_alias_key(alias)
    line_key = normalize_alias_key(line)
    if not alias_key or not line_key:
        return False

    for other_definition in FIELD_DEFINITIONS:
        if other_definition.key == definition.key:
            continue
        for other_alias in other_definition.aliases:
            other_key = normalize_alias_key(other_alias)
            if len(other_key) <= len(alias_key):
                continue
            if alias_key in other_key and other_key in line_key:
                return True

    return False


def normalize_alias_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9一-龥]+", "", value.upper())


def normalize_extracted_field_value(value: str, definition: FieldDefinition) -> str:
    cleaned = clean_field_value(value)
    if definition.key != "quantity":
        return cleaned

    numeric_values = re.findall(r"\d+(?:[.,]\d+)?", cleaned)
    if len(numeric_values) > 1 and len(set(numeric_values)) == 1:
        return numeric_values[0]
    return cleaned


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


def extract_value_before_alias(line: str, alias: str) -> str:
    """Recover table cells exported as `value + label` in vector PDFs."""
    match = re.search(
        rf"^(.*?){build_flexible_alias_pattern(alias)}(?![A-Z0-9])",
        line,
        re.IGNORECASE,
    )
    if not match:
        return ""

    prefix = match.group(1).strip(" \t|:/\\#=_;")
    if not prefix:
        return ""

    # Keep only the last cell/token: a row can contain another label before
    # this one, while the immediately preceding token is the actual value.
    prefix = prefix.split("|")[-1]
    tokens = re.findall(r"[A-Z0-9][A-Z0-9./-]*", prefix, re.IGNORECASE)
    return tokens[-1] if tokens else ""


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
