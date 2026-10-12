"""Pure document extraction; child process has no DB or provider dependency."""
from io import BytesIO, StringIO
import csv
import json

class DocumentParseError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)

def extract(raw, extension, max_pages, max_characters):
    segments = []
    total = 0
    def add(text, locator):
        nonlocal total
        total += len(text)
        if total > max_characters:
            raise DocumentParseError("file_text_limit", "文件可抽取文字超过限制，请拆分后上传。")
        if text.strip():
            segments.append(dict(text=text, locator=locator))
    if extension == ".pdf":
        from pypdf import PdfReader
        try:
            pdf = PdfReader(BytesIO(raw), strict=True)
            if pdf.is_encrypted:
                raise DocumentParseError("pdf_encrypted", "请上传未加密的文本PDF。")
            if len(pdf.pages) > max_pages:
                raise DocumentParseError("file_page_limit", "PDF页数超过限制，请拆分上传。")
            for i, page in enumerate(pdf.pages):
                add(page.extract_text() or "", dict(kind="page", page=i+1))
        except DocumentParseError:
            raise
        except Exception:
            raise DocumentParseError("pdf_invalid", "PDF无法解析，请核对文件。") from None
        if not segments:
            raise DocumentParseError("pdf_ocr_required", "未抽取到文字；扫描PDF需要OCR，当前仅支持文本PDF。")
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
