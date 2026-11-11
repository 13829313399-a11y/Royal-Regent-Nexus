"""Complete, copyable text and a readable PDF independent of original layout."""
from functools import lru_cache
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter

from app.core.config import settings
from .document_ir import Cancelled, ToolError


@lru_cache(maxsize=8)
def document_font(size):
    candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path(settings.image_translation_runner).parent / "fonts/SourceHanSansCN-VF.ttf"]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    raise ToolError("DOCUMENT_FONT_UNAVAILABLE", "完整译文所需的中文字体未就绪")


def write_complete_translation(ir, work, cancelled):
    from .image_translation import append_image_pdf
    blocks = [b for b in ir.blocks if b.kind != "image"]
    pdf = PdfWriter()
    page_paths = []
    plain = []
    font, heading = document_font(21), document_font(26)
    width, height, margin, line_height = 1000, 1414, 50, 31
    image = None
    draw = None
    y = 0

    def new_page():
        nonlocal image, draw, y
        if image is not None:
            target = work / f"complete-text-{len(page_paths)+1:04d}.png"
            image.save(target)
            append_image_pdf(pdf, target, 595.276, 841.89)
            page_paths.append(target)
            image.close()
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        y = margin

    def line(text, title=False):
        nonlocal y
        selected = heading if title else font
        for paragraph in str(text).replace("\x00", "").splitlines() or [""]:
            current = ""
            for character in paragraph:
                if current and draw.textlength(current + character, font=selected) > width - margin*2:
                    if y + line_height > height-margin:
                        new_page()
                    draw.text((margin, y), current, font=selected, fill="#202124")
                    y += line_height
                    current = ""
                current += character
            if y + line_height > height-margin:
                new_page()
            draw.text((margin, y), current, font=selected, fill="#202124")
            y += line_height

    new_page()
    for page in ir.pages:
        if cancelled():
            raise Cancelled()
        title = f"第 {page.display_page_number} 页 · 完整译文与原文对照"
        plain.append(title)
        line(title, True)
        for issue in ir.issues:
            if issue.status=='open' and issue.source.page_index==page.page_index:
                notice='需核对：'+issue.message
                plain.append(notice);line(notice)
        page_blocks = [b for b in blocks if b.source.page_index == page.page_index]
        if not page_blocks:
            plain.append("未识别到文字；请检查原页是否为空或存在未识别内容。")
            line(plain[-1])
        for index, block in enumerate(page_blocks, 1):
            status = block.style.get("translation_status", "translated" if block.text else "needs_review")
            label = {"preserved": "保留标识", "needs_review": "原文或译文需核对", "translated": "已翻译"}.get(status, "需核对")
            if not block.style.get("rendered") and status == "translated":
                label += "，原页版式未回填，译文如下"
            content = [f"[{index}] {label}", "原文：" + getattr(block, "original_text", ""),
                       "译文：" + (block.text if block.text.strip() else "[未得到可信译文，请核对原文]"),
                       *block.style.get("review_notes", []), ""]
            plain.extend(content)
            for text in content:
                line(text)
    if image is not None:
        target = work / f"complete-text-{len(page_paths)+1:04d}.png"
        image.save(target)
        append_image_pdf(pdf, target, 595.276, 841.89)
        image.close()
    text_path = work / "完整译文与原文对照.txt"
    text_path.write_text("\n".join(plain), encoding="utf-8")
    pdf_path = work / "完整译文与原文对照.pdf"
    pdf.write(pdf_path)
    pdf.close()
    return text_path, pdf_path


def append_complete_text(writer, complete_pdf):
    for page in PdfReader(complete_pdf).pages:
        writer.add_page(page)
