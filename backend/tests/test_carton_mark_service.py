import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_carton_mark_auto_check_extracts_template_fields_and_requests_photo_review():
    from app.services.carton_mark import build_carton_mark_auto_check

    response = build_carton_mark_auto_check(
        pdf_bytes=(
            b"SHIPPING IDENTIFICATION MARK\n"
            b"NUMERO DE PEDIDO 203302017\n"
            b"ITEM 700142617\n"
            b"G.W. 4.3 KGS\n"
            b"N.W. 3.1 KGS\n"
            b"BARCODE 197919619\n"
        ),
        front_image_bytes=b"not-an-image",
        side_image_bytes=b"not-an-image",
        customer_name="Dickie",
        po="203302017",
        item="700142617",
    )

    template_fields = {field.key: field.value for field in response.template_fields}
    front_template_fields = {field.key: field.value for field in response.front_template_fields}
    side_template_fields = {field.key: field.value for field in response.side_template_fields}
    assert template_fields["customer_name"] == "Dickie"
    assert template_fields["po"] == "203302017"
    assert template_fields["item"] == "700142617"
    assert template_fields["barcode"] == "197919619"
    assert front_template_fields["po"] == "203302017"
    assert side_template_fields["item"] == "700142617"

    assert response.summary.overall_status == "需复核"
    assert response.summary.review_count > 0
    assert any(item.side == "front" and item.field_key == "po" and item.status == "review" for item in response.comparisons)
    assert any(status.source == "front_photo" and not status.ok for status in response.extraction)


def test_carton_mark_batch_auto_check_keeps_front_and_side_images_independent(monkeypatch):
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services import carton_mark

    def status(source: str) -> CartonMarkExtractionStatus:
        return CartonMarkExtractionStatus(
            source=source,
            ok=True,
            engine="test",
            raw_text="",
        )

    monkeypatch.setattr(carton_mark, "extract_pdf_text", lambda _: (
        "PO 62098330\nITEM 203302017\nCOLOR MULTICOLOR",
        status("pdf_template"),
    ))
    monkeypatch.setattr(carton_mark, "extract_pdf_template_side_texts", lambda *_args, **_kwargs: (
        "PO 62098330\nITEM 203302017\nCOLOR MULTICOLOR",
        "PO 62098330\nITEM 203302017\nQTY 24 PCS",
        status("pdf_layout"),
    ))
    monkeypatch.setattr(carton_mark, "extract_image_text", lambda image, *, source: (
        image.decode("utf-8"),
        status(source),
    ))

    response = carton_mark.build_carton_mark_batch_auto_check(
        pdf_bytes=b"pdf",
        front_images=[("front-01.jpg", b"PO 62098330\nITEM 203302017\nCOLOR MULTICOLOR")],
        side_images=[("side-01.jpg", b"PO 62098330\nITEM 203302017\nQTY 24 PCS")],
        customer_name="Dickie",
        item="203302017",
    )

    assert [(item.side, item.file_name, item.file_index) for item in response.items] == [
        ("front", "front-01.jpg", 0),
        ("side", "side-01.jpg", 0),
    ]
    assert {item.side for item in response.items[0].result.comparisons} == {"front"}
    assert {item.side for item in response.items[1].result.comparisons} == {"side"}


def test_carton_mark_field_extraction_handles_noisy_photo_ocr_rows():
    from app.services.carton_mark import extract_fields

    fields = {
        field.key: field.value
        for field in extract_fields(
            (
                "P.0 N0 | 2033 | ITEM N0 | 2017\n"
                "QTY/CTN 24 PCS\n"
                "G W 4.3 KGS\n"
                "N W 3.1 KGS\n"
                "BULTO 1-10\n"
            ),
            source="front_photo",
        )
    }

    assert fields["po"] == "2033"
    assert fields["item"] == "2017"
    assert fields["quantity"] == "24"
    assert fields["gw"] == "4.3 KGS"
    assert fields["nw"] == "3.1 KGS"
    assert fields["carton_no"] == "1-10"


def test_carton_mark_photo_ocr_variants_include_detected_label_crop():
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

    from app.services.carton_mark import build_photo_ocr_variants, locate_photo_mark_boxes

    image = Image.new("RGB", (1200, 900), (174, 142, 96))
    draw = ImageDraw.Draw(image)
    draw.rectangle((270, 170, 910, 730), fill=(226, 214, 176), outline=(45, 42, 34), width=4)
    for y in range(245, 705, 70):
        draw.line((285, y, 895, y), fill=(45, 42, 34), width=3)
    for x in (470, 690):
        draw.line((x, 185, x, 715), fill=(45, 42, 34), width=3)
    draw.text((305, 205), "PO NO 2033", fill=(20, 20, 20))
    draw.text((305, 275), "ITEM NO 2017", fill=(20, 20, 20))
    draw.text((305, 345), "QTY/CTN 24 PCS", fill=(20, 20, 20))
    draw.text((305, 415), "G.W 4.3 KGS", fill=(20, 20, 20))
    draw.rectangle((285, 660, 895, 705), fill=(96, 24, 36))

    boxes = locate_photo_mark_boxes(image, ImageFilter, ImageOps)
    variants = build_photo_ocr_variants(image, ImageEnhance, ImageFilter, ImageOps)
    largest_box = boxes[0]

    assert boxes
    assert largest_box[0] > 0
    assert largest_box[1] > 0
    assert largest_box[2] < image.width
    assert largest_box[3] < image.height
    assert len(variants) > 3


def test_carton_mark_ocr_word_rows_recover_table_label_values():
    from app.services.carton_mark import OcrWord, build_ocr_word_table_text, extract_fields

    words = [
        OcrWord(text="NUMERO", left=10, top=10, right=70, bottom=28, confidence=82),
        OcrWord(text="DE", left=76, top=10, right=98, bottom=28, confidence=82),
        OcrWord(text="PEDIDO", left=104, top=10, right=170, bottom=28, confidence=82),
        OcrWord(text="62098330", left=260, top=10, right=345, bottom=28, confidence=88),
        OcrWord(text="MODELO", left=10, top=44, right=82, bottom=62, confidence=82),
        OcrWord(text="203302017", left=260, top=44, right=350, bottom=62, confidence=88),
        OcrWord(text="PESO", left=10, top=78, right=58, bottom=96, confidence=82),
        OcrWord(text="BRUTO", left=64, top=78, right=124, bottom=96, confidence=82),
        OcrWord(text="4.3", left=260, top=78, right=292, bottom=96, confidence=88),
        OcrWord(text="KGS", left=300, top=78, right=335, bottom=96, confidence=88),
    ]

    table_text = build_ocr_word_table_text(words)
    fields = {field.key: field.value for field in extract_fields(table_text, source="front_photo")}

    assert fields["po"] == "62098330"
    assert fields["item"] == "203302017"
    assert fields["gw"] == "4.3 KGS"


def test_carton_mark_checks_left_labels_and_right_values_for_side_table():
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services.carton_mark import compare_label_column, extract_fields

    template_text = (
        "DESCRIPCION VEHICULO DE JUGUETE\n"
        "MODELO 203302017\n"
        "NUMERO DE PEDIDO 62098330\n"
        "PIEZAS POR BULTO 24\n"
        "BULTO 1 DE 1\n"
        "CAJA NUMERO 1 DE 63\n"
        "TALLA NA\n"
        "COLOR MULTICOLOR\n"
        "SECCION / UNECO 424\n"
    )
    photo_text = template_text.replace("NUMERO DE PEDIDO", "NUMERO DE PROVEEDOR")
    status = CartonMarkExtractionStatus(
        source="side_photo",
        ok=True,
        engine="test",
        message="",
        raw_text=photo_text,
    )

    side_fields = {field.key: field.value for field in extract_fields(template_text, source="pdf_side_mark")}
    comparisons = compare_label_column("side", template_text, photo_text, status)
    comparison_map = {item.field_key: item for item in comparisons}

    assert side_fields["carton_no"] == "1 DE 1"
    assert side_fields["box_no"] == "1 DE 63"
    assert side_fields["size"] == "NA"
    assert side_fields["section"] == "424"
    assert comparison_map["left_label:po"].expected == "NUMERO DE PEDIDO"
    assert comparison_map["left_label:po"].actual == "NUMERO DE PROVEEDOR"
    assert comparison_map["left_label:po"].status == "mismatch"
    assert comparison_map["left_label:box_no"].status == "pass"
    assert comparison_map["left_label:section"].status == "pass"


def test_rapidocr_result_recovers_table_fields_from_detected_text_boxes():
    from app.services.carton_mark import extract_fields, rapidocr_result_to_text

    result = SimpleNamespace(
        txts=("NUMERO DE PEDIDO", "62098330", "MODELO", "203302017", "PIEZAS POR BULTO", "24"),
        scores=(0.98, 0.99, 0.97, 0.99, 0.96, 0.99),
        boxes=(
            ((10, 10), (170, 10), (170, 28), (10, 28)),
            ((260, 10), (345, 10), (345, 28), (260, 28)),
            ((10, 44), (82, 44), (82, 62), (10, 62)),
            ((260, 44), (350, 44), (350, 62), (260, 62)),
            ((10, 78), (180, 78), (180, 96), (10, 96)),
            ((260, 78), (292, 78), (292, 96), (260, 96)),
        ),
    )

    text = rapidocr_result_to_text(result)
    fields = {field.key: field.value for field in extract_fields(text, source="rapidocr")}

    assert fields["po"] == "62098330"
    assert fields["item"] == "203302017"
    assert fields["quantity"] == "24"


def test_carton_mark_auto_check_matches_photo_raw_values_when_labels_are_noisy(monkeypatch):
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services import carton_mark

    def fake_extract_image_text(image_bytes: bytes, *, source: str):
        text = "photo text only 2O 33 20I7 I979I96I9"
        return text, CartonMarkExtractionStatus(
            source=source,
            ok=True,
            engine="test",
            message="",
            raw_text=text,
        )

    monkeypatch.setattr(carton_mark, "extract_image_text", fake_extract_image_text)

    response = carton_mark.build_carton_mark_auto_check(
        pdf_bytes=(
            b"SHIPPING IDENTIFICATION MARK\n"
            b"PO 2033\n"
            b"ITEM 2017\n"
            b"BARCODE 197919619\n"
        ),
        front_image_bytes=b"front-photo",
        side_image_bytes=b"side-photo",
        customer_name="Dickie",
        po="2033",
        item="2017",
    )

    front_statuses = {
        item.field_key: item.status
        for item in response.comparisons
        if item.side == "front"
    }
    assert front_statuses["po"] == "pass"
    assert front_statuses["item"] == "pass"
    assert front_statuses["barcode"] == "pass"


def test_carton_mark_auto_check_backfills_unlabeled_pdf_values_from_photo_fields(monkeypatch):
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services import carton_mark

    def fake_extract_image_text(image_bytes: bytes, *, source: str):
        text = "COLOR MULTICOLOR\nBARCODE 4197919619"
        return text, CartonMarkExtractionStatus(
            source=source,
            ok=True,
            engine="test",
            message="",
            raw_text=text,
        )

    monkeypatch.setattr(carton_mark, "extract_image_text", fake_extract_image_text)

    response = carton_mark.build_carton_mark_auto_check(
        pdf_bytes=(
            b"SHIPPING IDENTIFICATION MARK\n"
            b"PO 203302017\n"
            b"MULTICOLOR\n"
            b"4197919619\n"
        ),
        front_image_bytes=b"front-photo",
        side_image_bytes=b"side-photo",
        customer_name="Dickie",
        po="203302017",
        item="2017",
    )

    front_expected = {
        field.key: field.value
        for field in response.front_template_fields
    }
    front_statuses = {
        item.field_key: item.status
        for item in response.comparisons
        if item.side == "front"
    }

    assert front_expected["color"] == "MULTICOLOR"
    assert front_statuses["color"] == "pass"


def test_carton_mark_auto_check_tolerates_extracted_identifier_ocr_confusions(monkeypatch):
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services import carton_mark

    def fake_extract_image_text(image_bytes: bytes, *, source: str):
        text = "PO 2O33\nITEM 20I7\nBARCODE I979I96I9"
        return text, CartonMarkExtractionStatus(
            source=source,
            ok=True,
            engine="test",
            message="",
            raw_text=text,
        )

    monkeypatch.setattr(carton_mark, "extract_image_text", fake_extract_image_text)

    response = carton_mark.build_carton_mark_auto_check(
        pdf_bytes=(
            b"SHIPPING IDENTIFICATION MARK\n"
            b"PO 2033\n"
            b"ITEM 2017\n"
            b"BARCODE 197919619\n"
        ),
        front_image_bytes=b"front-photo",
        side_image_bytes=b"side-photo",
        customer_name="Dickie",
        po="2033",
        item="2017",
    )

    front_statuses = {
        item.field_key: item.status
        for item in response.comparisons
        if item.side == "front"
    }
    assert front_statuses["po"] == "pass"
    assert front_statuses["item"] == "pass"
    assert front_statuses["barcode"] == "pass"


def test_pdf_template_region_selection_keeps_first_front_side_pair():
    from app.services.carton_mark import PdfMarkRegion, select_primary_pdf_mark_regions

    regions = [
        PdfMarkRegion(kind="front", text="FRONT 1", box=(100, 100, 360, 260)),
        PdfMarkRegion(kind="side", text="SIDE 2", box=(380, 100, 520, 260)),
        PdfMarkRegion(kind="front", text="FRONT 3", box=(700, 100, 960, 260)),
        PdfMarkRegion(kind="side", text="SIDE 4", box=(980, 100, 1120, 260)),
    ]

    selected = select_primary_pdf_mark_regions(regions)

    assert [(region.kind, region.text) for region in selected] == [
        ("front", "FRONT 1"),
        ("side", "SIDE 2"),
    ]


def test_pdf_template_side_texts_ignores_repeated_second_pair(monkeypatch):
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services import carton_mark
    from app.services.carton_mark import PdfMarkRegion

    regions = [
        PdfMarkRegion(kind="front", text="PO 2033\nFRONT 1", box=(100, 100, 360, 260)),
        PdfMarkRegion(kind="side", text="ITEM 2017\nSIDE 2", box=(380, 100, 520, 260)),
        PdfMarkRegion(kind="front", text="PO WRONG\nFRONT 3", box=(700, 100, 960, 260)),
        PdfMarkRegion(kind="side", text="ITEM WRONG\nSIDE 4", box=(980, 100, 1120, 260)),
    ]

    def fake_extract_pdf_mark_regions(pdf_bytes: bytes):
        return regions, CartonMarkExtractionStatus(
            source="pdf_template_regions",
            ok=True,
            engine="test",
            message="",
            raw_text="",
        )

    monkeypatch.setattr(carton_mark, "extract_pdf_mark_regions", fake_extract_pdf_mark_regions)

    front_text, side_text, status = carton_mark.extract_pdf_template_side_texts(
        b"pdf",
        fallback_text="fallback",
    )

    assert status.ok
    assert "FRONT 1" in front_text
    assert "FRONT 3" not in front_text
    assert "SIDE 2" in side_text
    assert "SIDE 4" not in side_text


def test_pdf_vector_regions_keep_only_the_leftmost_front_and_side_marks():
    from app.services.carton_mark import (
        PdfTextSpan,
        build_pdf_vector_mark_regions,
        classify_pdf_mark_regions,
        extract_fields,
        select_primary_pdf_mark_regions,
    )

    spans = [
        PdfTextSpan(text="SHIPPING IDENTIFICATION MARK", x=100, y=340),
        PdfTextSpan(text="IMPORTADOR DILISA", x=100, y=315),
        PdfTextSpan(text="62098330NUMERO DE PEDIDO", x=100, y=290),
        PdfTextSpan(text="MODELO 203302017", x=100, y=265),
        PdfTextSpan(text="DESCRIPCION", x=500, y=340),
        PdfTextSpan(text="VEHICULO DE JUGUETE", x=650, y=340),
        PdfTextSpan(text="NUMERO DE PEDIDO", x=500, y=315),
        PdfTextSpan(text="62098330", x=650, y=315),
        PdfTextSpan(text="PIEZAS POR BULTO", x=500, y=290),
        PdfTextSpan(text="24 24", x=650, y=290),
        PdfTextSpan(text="BULTO", x=500, y=265),
        PdfTextSpan(text="1 DE 1", x=650, y=265),
        PdfTextSpan(text="SHIPPING IDENTIFICATION MARK", x=900, y=340),
        PdfTextSpan(text="IMPORTADOR OTRO CLIENTE", x=900, y=315),
        PdfTextSpan(text="99999999NUMERO DE PEDIDO", x=900, y=290),
        PdfTextSpan(text="DESCRIPCION", x=1300, y=340),
        PdfTextSpan(text="OTRO PRODUCTO", x=1450, y=340),
        PdfTextSpan(text="NUMERO DE PEDIDO", x=1300, y=315),
        PdfTextSpan(text="99999999", x=1450, y=315),
        PdfTextSpan(text="PIEZAS POR BULTO", x=1300, y=290),
        PdfTextSpan(text="12", x=1450, y=290),
    ]

    regions = classify_pdf_mark_regions(
        build_pdf_vector_mark_regions(spans, page_width=1700, page_height=400),
    )
    selected = select_primary_pdf_mark_regions(regions)
    front_fields = {field.key: field.value for field in extract_fields(selected[0].text, source="pdf_front_mark")}
    side_fields = {field.key: field.value for field in extract_fields(selected[1].text, source="pdf_side_mark")}

    assert [(region.kind, region.box[0]) for region in selected] == [("front", 100), ("side", 500)]
    assert front_fields["po"] == "62098330"
    assert front_fields["item"] == "203302017"
    assert side_fields["po"] == "62098330"
    assert side_fields["quantity"] == "24"
    assert side_fields["carton_no"] == "1 DE 1"
