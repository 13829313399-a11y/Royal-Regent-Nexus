"""Reversible raw PDF to visible top-left point geometry."""
import copy
import math
import re

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject, RectangleObject

from .document_ir import Cancelled, ToolError


def geometry(page):
    media = list(map(float, page.mediabox))
    crop = list(map(float, page.cropbox))
    l, b, r, t = max(media[0], crop[0]), max(media[1], crop[1]), min(media[2], crop[2]), min(media[3], crop[3])
    u, rotation = float(page.get("/UserUnit", 1)), int(page.rotation) % 360
    if not all(math.isfinite(x) for x in (l, b, r, t, u)) or u <= 0 or r <= l or t <= b or rotation not in {0, 90, 180, 270}:
        raise ToolError("PDF_PAGE_GEOMETRY", "PDF 页框、旋转角度或 UserUnit 无效")
    width, height = ((r-l)*u, (t-b)*u) if rotation in {0, 180} else ((t-b)*u, (r-l)*u)
    matrices = {0: (u, 0, 0, u, -l*u, -b*u), 90: (0, -u, u, 0, -b*u, r*u),
                180: (-u, 0, 0, -u, r*u, t*u), 270: (0, u, -u, 0, t*u, -l*u)}
    a, bb, c, d, e, f = matrices[rotation]
    return {"media_box": media, "crop_box": crop, "effective_crop_box": [l,b,r,t], "user_unit": u,
            "rotation": rotation, "width_pt": width, "height_pt": height,
            "raw_to_normalized_pdf": list(matrices[rotation]), "raw_to_visible": [a,-bb,c,-d,e,height-f]}


def transform_rect(rect, matrix):
    a,b,c,d,e,f = matrix
    points = [(a*x+c*y+e,b*x+d*y+f) for x,y in [(rect[0],rect[1]),(rect[0],rect[3]),(rect[2],rect[1]),(rect[2],rect[3])]]
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def open_pdf(path, password=None):
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(password or ""):
            raise ToolError("PASSWORD_REQUIRED", "PDF 已加密，请输入打开密码")
        if not reader.pages:
            raise ToolError("PDF_EMPTY", "PDF 没有页面")
        return reader
    except ToolError:
        raise
    except Exception:
        raise ToolError("PDF_INVALID", "PDF 无法读取，请重新导出后上传") from None


def normalize_pdf(path, target, password=None, cancelled=lambda: False):
    reader, writer = open_pdf(path, password), PdfWriter()
    metadata, annotation_count = [], 0
    for page in reader.pages:
        if cancelled():
            raise Cancelled()
        g = geometry(page)
        metadata.append(g)
        source = copy.copy(page)
        # Annotation appearances/coordinates are not transformed by merge_page.
        # Keep ordinary page extraction on the original objects. This normalized
        # geometry copy explicitly drops interactive annotations and reports it.
        annotation_count += len(source.get("/Annots", []))
        source.pop(NameObject("/Annots"), None)
        source.cropbox = RectangleObject(g["effective_crop_box"])
        source.trimbox = RectangleObject(g["effective_crop_box"])
        target_page = PageObject.create_blank_page(width=g["width_pt"], height=g["height_pt"])
        target_page.merge_transformed_page(source, Transformation(g["raw_to_normalized_pdf"]), expand=False)
        writer.add_page(target_page)
    with open(target, "wb") as stream:
        writer.write(stream)
    return metadata, annotation_count


def parse_page_groups(expression, page_count, duplicate_policy="keep"):
    if expression in {None, "", "all"}:
        return [list(range(page_count))]
    groups, seen = [], set()
    for group in expression.split(";"):
        pages = []
        for token in group.split(","):
            token = token.strip()
            match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", token)
            if not match:
                raise ToolError("PAGE_RANGE_INVALID", "页码格式应为 1-3;4,6,5")
            start, end = int(match[1]), int(match[2] or match[1])
            if not 1 <= start <= page_count or not 1 <= end <= page_count or start > end:
                raise ToolError("PAGE_RANGE_INVALID", "页码范围超出文档或倒序；重排请使用逗号")
            for number in range(start-1, end):
                if duplicate_policy == "deduplicate" and number in seen:
                    continue
                pages.append(number)
                seen.add(number)
        if pages:
            groups.append(pages)
    if not groups:
        raise ToolError("PAGE_RANGE_INVALID", "没有可输出的页面")
    return groups


def validate_cuts(cuts, length):
    cuts = [float(x) for x in cuts]
    if any(not math.isfinite(x) or x <= 0 or x >= length for x in cuts) or any(a >= b for a,b in zip(cuts,cuts[1:])):
        raise ToolError("PDF_CUT_INVALID", "切线必须在页面内且严格递增")
    return [0.0, *cuts, length]
