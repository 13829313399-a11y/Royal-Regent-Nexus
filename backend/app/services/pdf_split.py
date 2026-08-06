from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from pypdf import PdfReader, PdfWriter


MAX_PDF_PAGES = 80


class PdfSplitError(ValueError):
    pass


@dataclass(frozen=True)
class PdfSplitResult:
    content: bytes
    page_count: int
    file_count: int
    output_file_name: str


def _safe_stem(source_file_name: str) -> str:
    source_name = Path(source_file_name or "PDF文件.pdf").name
    return re.sub(r'[\\/:*?"<>|]+', "_", Path(source_name).stem).strip(" .") or "PDF文件"


def _parse_page_segments(mode: str, page_ranges: str, page_count: int) -> list[list[int]]:
    if mode == "each_page":
        return [[page_number] for page_number in range(1, page_count + 1)]
    if mode != "ranges":
        raise PdfSplitError("不支持的拆分方式。")

    raw_segments = [segment.strip() for segment in re.split(r"[,，;；]", page_ranges) if segment.strip()]
    if not raw_segments:
        raise PdfSplitError("请输入要拆分的页码或页段，例如 1-3,4,5-7。")
    if len(raw_segments) > MAX_PDF_PAGES:
        raise PdfSplitError("拆分页段数量过多。")

    segments: list[list[int]] = []
    for raw_segment in raw_segments:
        match = re.fullmatch(r"(\d+)(?:\s*[-~至]\s*(\d+))?", raw_segment)
        if not match:
            raise PdfSplitError(f"页段“{raw_segment}”格式不正确；请使用 1-3,4,5-7。")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise PdfSplitError(f"页段“{raw_segment}”不是有效的顺序页码。")
        if end > page_count:
            raise PdfSplitError(f"页段“{raw_segment}”超出 PDF 的 {page_count} 页范围。")
        segments.append(list(range(start, end + 1)))
    return segments


def _segment_file_name(stem: str, pages: list[int]) -> str:
    suffix = str(pages[0]) if len(pages) == 1 else f"{pages[0]}-{pages[-1]}"
    return f"{stem}_第{suffix}页.pdf"


def split_pdf(
    pdf_bytes: bytes,
    source_file_name: str,
    *,
    mode: str,
    page_ranges: str = "",
) -> PdfSplitResult:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfSplitError("PDF 已加密，无法拆分；请先移除打开密码。")
        page_count = len(reader.pages)
    except PdfSplitError:
        raise
    except Exception as exc:
        raise PdfSplitError("PDF 无法读取；请确认文件未加密、未损坏。") from exc

    if page_count == 0:
        raise PdfSplitError("PDF 中没有可拆分的页面。")
    if page_count > MAX_PDF_PAGES:
        raise PdfSplitError(f"单次最多拆分 {MAX_PDF_PAGES} 页 PDF。")

    segments = _parse_page_segments(mode, page_ranges, page_count)
    stem = _safe_stem(source_file_name)
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output_zip:
        for pages in segments:
            writer = PdfWriter()
            for page_number in pages:
                writer.add_page(reader.pages[page_number - 1])
            split_output = BytesIO()
            writer.write(split_output)
            output_zip.writestr(_segment_file_name(stem, pages), split_output.getvalue())

    return PdfSplitResult(
        content=archive.getvalue(),
        page_count=page_count,
        file_count=len(segments),
        output_file_name=f"{stem}_拆分结果.zip",
    )
