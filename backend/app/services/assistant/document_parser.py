"""Pure document extraction; child process has no DB or provider dependency."""
from io import BytesIO, StringIO
import csv
import json

class DocumentParseError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)

def extract(raw, extension, max_pages, max_characters, previews=None):
    segments = []
    total = 0
    def add(text, locator, metadata=None):
        nonlocal total
        total += len(text) + (len(json.dumps(metadata, ensure_ascii=False)) if metadata else 0)
        if total > max_characters:
            raise DocumentParseError("file_text_limit", "文件可抽取文字超过限制，请拆分后上传。")
        if text.strip():
            segments.append(dict(text=text, locator=locator, **(dict(metadata=metadata) if metadata else {})))
    if extension in ('.docx', '.xlsx'):
        if __package__:
            from .office_parser import extract_office, OfficeError
        else:
            from office_parser import extract_office, OfficeError
        try:
            extract_office(raw, extension, max_pages, add)
        except OfficeError as exc:
            raise DocumentParseError(exc.code, 'Office文件未能安全解析，请核对格式或拆分后上传。') from None
    elif extension in ('.pdf', '.png', '.jpg', '.jpeg'):
        if __package__:
            from .document_ocr import LocalOcr, OcrError, image_document, pdf_page_image
        else:
            from document_ocr import LocalOcr, OcrError, image_document, pdf_page_image
        ocr = LocalOcr(previews if previews is not None else {})
        raster_pdf = None
        try:
            if extension != '.pdf':
                ocr.recognize(image_document(raw, extension), 1, add)
                return segments
            from pypdf import PdfReader
            pdf = PdfReader(BytesIO(raw), strict=True)
            if pdf.is_encrypted:
                raise DocumentParseError("pdf_encrypted", "请上传未加密的文本PDF。")
            if len(pdf.pages) > max_pages:
                raise DocumentParseError("file_page_limit", "PDF页数超过限制，请拆分上传。")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                add(text, dict(kind="page", page=i+1))
                resources = page.get('/Resources', {})
                if hasattr(resources, 'get_object'):
                    resources = resources.get_object()
                xobjects = resources.get('/XObject', {}) if resources else {}
                # Any image or Form XObject can carry text missing from the text
                # layer; do not declare a mixed page fully read from its header.
                if not text.strip() or xobjects:
                    if raster_pdf is None:
                        import pypdfium2
                        raster_pdf = pypdfium2.PdfDocument(raw)
                    ocr.recognize(pdf_page_image(raster_pdf, i), i+1, add)
        except OcrError as exc:
            raise DocumentParseError(exc.code, '图像识别未完成，请查看文件状态并核对原件。') from None
        except DocumentParseError:
            raise
        except MemoryError:
            raise
        except Exception:
            raise DocumentParseError("pdf_invalid", "PDF无法解析，请核对文件。") from None
        finally:
            if raster_pdf is not None:
                raster_pdf.close()
    else:
        try:
            text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
        except UnicodeError:
            raise DocumentParseError("file_encoding", "请使用UTF-8或带BOM的UTF-16文本。") from None
        if "\x00" in text:
            raise DocumentParseError("file_encoding", "文件包含无效文本编码。")
        if extension == ".csv":
            try:
                reader = csv.reader(StringIO(text), strict=True)
                start = 1
                for row in reader:
                    add(json.dumps(row, ensure_ascii=False), dict(kind="lines", start=start, end=reader.line_num))
                    start = reader.line_num+1
            except csv.Error:
                raise DocumentParseError("csv_invalid", "CSV引号或分隔结构无效。") from None
        else:
            lines = text.splitlines(keepends=True)
            for start in range(0, len(lines), 30):
                add("".join(lines[start:start+30]), dict(kind="lines", start=start+1, end=min(start+30, len(lines))))
    if not segments:
        raise DocumentParseError("file_empty", "文件没有可分析的文字。")
    return segments
