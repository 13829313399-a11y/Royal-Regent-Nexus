"""Local, fail-closed OCR for the ruled Green Toys purchase-order layout.

Table boundaries come from the uploaded pixels, not a particular PO or screenshot.
Physical rows anchor cell OCR so an unreadable cell cannot shift later rows.
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from io import BytesIO, StringIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


class GreenImageError(ValueError):
    pass


def _bands(indices):
    result = []
    for index in indices:
        if result and index == result[-1][1] + 1:
            result[-1] = (result[-1][0], index)
        else:
            result.append((index, index))
    return result


def _layout(image):
    width, height = image.size
    pixels = image.get_flattened_data()
    horizontal = _bands(y for y in range(height)
                        if sum(v < 205 for v in pixels[y * width:(y + 1) * width]) > width * .7)
    if len(horizontal) < 3:
        raise GreenImageError('未找到完整带表格线的 Green Toys 明细；请上传完整清晰截图或原始 HTML')
    header = max(horizontal, key=lambda band: band[1] - band[0])
    rows = [band for band in horizontal if band[0] > header[1]]
    if header[0] == 0 or header[1] - header[0] < 5 or not rows or len(rows) > 200:
        raise GreenImageError('Green Toys 明细表头或行边界无法确认')
    if rows[-1][1] + 1 >= height:
        raise GreenImageError('图片底部已截断，请上传包含总金额的完整截图')
    bottom = rows[-1][0]
    vertical = _bands(x for x in range(width)
                      if sum(pixels[y * width + x] < 205 for y in range(header[1], bottom))
                      > .75 * (bottom - header[1]))
    if len(vertical) != 8:
        raise GreenImageError('Green Toys 七列明细表不完整，无法安全定位货号、数量和金额')
    cells = [(vertical[i][1] + 2, vertical[i + 1][0] - 1) for i in range(7)]
    intervals = list(zip([header[1] + 1] + [band[1] + 1 for band in rows[:-1]],
                         [band[0] for band in rows]))
    if any(right - left < 5 for left, right in cells) or any(end - start < 5 for start, end in intervals):
        raise GreenImageError('Green Toys 图片分辨率不足以识别完整明细')
    return header, rows, cells, intervals


class _Reader:
    def __init__(self, command):
        self.command = command
        self.deadline = time.monotonic() + 45

    def read(self, image, *, psm=6, tsv=False, scale=3):
        if image.width == 0 or image.height == 0:
            raise GreenImageError('Green Toys 图片识别区域为空，请上传完整截图')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise GreenImageError('Green Toys 图片识别超时；请改用清晰完整图片或原始 HTML')
        if image.width * image.height * scale ** 2 > 16_000_000:
            raise GreenImageError('Green Toys 识别区域过大，请上传适当分辨率的截图')
        enlarged = ImageOps.expand(image.resize((image.width * scale, image.height * scale)),
                                  border=15, fill='white')
        buffer = BytesIO()
        enlarged.save(buffer, format='PNG')
        args = [self.command, 'stdin', 'stdout', '-l', 'eng', '--psm', str(psm)]
        if tsv:
            args.append('tsv')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise GreenImageError('Green Toys 图片识别超时')
        try:
            result = subprocess.run(args, input=buffer.getvalue(), capture_output=True,
                                    timeout=min(15, remaining), check=False,
                                    env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GreenImageError('Green Toys 本地 OCR 不可用或超时') from exc
        if result.returncode:
            # Do not expose a command's paths or document contents to the client.
            raise GreenImageError('Green Toys 本地 OCR 失败，请检查服务器 Tesseract 英文语言包')
        return result.stdout.decode('utf-8', errors='replace')


def _metadata(text):
    if not re.search(r'green\s+toys', text, re.I):
        raise GreenImageError('图片页眉未识别到 Green Toys，请上传包含完整页眉的截图')
    patterns = {
        'po': r'^\s*PO\s*(?:#|No\.?|=)\s*[:#]?\s*(\d{4,})\b',
        'date': r'PO\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})\b',
        'delivery': r'Deliver\s+By\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})\b',
    }
    values = {}
    for key, pattern in patterns.items():
        found = set(re.findall(pattern, text, re.I | re.M))
        if len(found) != 1:
            raise GreenImageError('图片 PO号或日期缺失/不唯一；不得用文件名代替，请上传完整清晰截图')
        values[key] = found.pop()
    try:
        for key in ('date', 'delivery'):
            datetime.strptime(values[key], '%m/%d/%Y')
    except ValueError as exc:
        raise GreenImageError('Green Toys 图片日期无效，请核对原单') from exc
    return values


def _column_rows(text, intervals, crop_top, *, scale=3):
    words = [[] for _ in intervals]
    try:
        for word in csv.DictReader(StringIO(text), delimiter='\t'):
            if word['level'] != '5' or not word['text'].strip():
                continue
            center = (int(word['top']) + int(word['height']) / 2 - 15) / scale + crop_top
            matches = [i for i, (start, end) in enumerate(intervals) if start <= center < end]
            if len(matches) != 1:
                raise GreenImageError('OCR 文字越过表格行边界，请上传完整清晰图片')
            # Glyph tops differ within the same line; sorting by top would put
            # "Truck" before "Dump". Tesseract's line identity preserves order.
            line = tuple(int(word[key]) for key in ('block_num', 'par_num', 'line_num'))
            words[matches[0]].append((line, int(word['left']), word['text'].strip()))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, GreenImageError):
            raise
        raise GreenImageError('Green Toys OCR 表格坐标无效') from exc
    return [' '.join(word[2] for word in sorted(row)) for row in words]


def _decimal(token, *, places=None):
    token = token.replace(' ', '').removeprefix('$')
    pattern = r'(?:\d+|\d{1,3}(?:,\d{3})+)'
    pattern += (rf'\.\d{{{places}}}' if places is not None else r'(?:\.\d+)?')
    if not re.fullmatch(pattern, token) or sum(char.isdigit() for char in token) > 20:
        raise GreenImageError('Green Toys 数量/价格/金额无法确认；请核对图片，不会自动猜数')
    return Decimal(token.replace(',', ''))


def recognize_green_toys_image(path: Path, command: str) -> str:
    try:
        with Image.open(path) as source:
            if source.width * source.height > 8_000_000 or getattr(source, 'n_frames', 1) != 1:
                raise GreenImageError('Green Toys 图片过大或包含多帧，请选择单张完整 PO 截图')
            # Composite transparent screenshots onto white, never modify the upload.
            rgba = source.convert('RGBA')
            background = Image.new('RGBA', rgba.size, 'white')
            background.alpha_composite(rgba)
            image = background.convert('L')
    except (OSError, Image.DecompressionBombError) as exc:
        raise GreenImageError('Green Toys 图片无法打开') from exc
    header, bands, columns, intervals = _layout(image)
    reader = _Reader(command)
    heading = image.crop((0, 0, image.width, header[0]))
    heading_scale = max(1, min(3, int((16_000_000 / (heading.width * heading.height)) ** .5))) if heading.height else 1
    metadata = _metadata(reader.read(heading, psm=11, scale=heading_scale))
    # Verify semantic columns before using the detected seven-column geometry.
    for column, expected in ((1, 'description'), (2, 'orderquantity'), (5, 'unitprice'), (6, 'amount')):
        left, right = columns[column]
        title = image.crop((left, header[0] + 1, right, header[1]))
        title = ImageOps.autocontrast(ImageOps.invert(title))
        recognized = re.sub(r'[^a-z]', '', reader.read(title).lower())
        if recognized != expected:
            raise GreenImageError('Green Toys 图片表头不符合支持的七列版式，请上传完整清晰原图或 HTML')
    top, bottom = header[1] + 1, bands[-1][0]
    values = {}
    for column in (1, 2, 5, 6):
        left, right = columns[column]
        crop = image.crop((left, top, right, bottom))
        draw = ImageDraw.Draw(crop)
        for start, end in bands[:-1]:
            draw.rectangle((0, start - top, crop.width, end - top), fill='white')
        values[column] = _column_rows(reader.read(crop, tsv=True), intervals, top)
    footer = reader.read(image.crop((columns[5][0], bands[-1][1] + 1, image.width, image.height)), psm=11)
    totals = re.findall(r'(?<![\d.])\$?((?:\d+|\d{1,3}(?:,\d{3})+)\.\d{2})(?![\d.])', footer)
    if not re.search(r'\bTotal\b', footer, re.I) or len(totals) != 1:
        raise GreenImageError('图片总金额缺失/不唯一，无法核实是否漏行；请上传包含 Total 的完整截图')
    total = _decimal(totals[0], places=2)
    lines, amounts = [], []
    for index, (start, end) in enumerate(intervals):
        left, right = columns[0]
        item_scale = max(1, min(5, 90 // (end - start)))
        item = reader.read(image.crop((left, start, right, end)), psm=7, scale=item_scale).strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{2,30}', item) or not values[1][index]:
            raise GreenImageError(f'图片第 {index + 1} 行货号/品名无法确认，不会跳过明细')
        quantity = _decimal(values[2][index])
        price = _decimal(values[5][index])
        amount = _decimal(values[6][index], places=2)
        if quantity <= 0 or quantity != quantity.to_integral_value() or price <= 0 or amount <= 0:
            raise GreenImageError(f'图片第 {index + 1} 行数量/价格/金额无效')
        with localcontext() as context:
            context.prec = 48
            calculated = (quantity * price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if calculated != amount:
            raise GreenImageError(f'图片第 {index + 1} 行数量×单价与金额不符，不会猜测修正')
        amounts.append(amount)
        lines.append(f'{item}  {values[1][index]}  {int(quantity)}  0  {price}  {amount}')
    if sum(amounts) != total:
        raise GreenImageError('图片明细与原单总金额不符，可能漏行；不会保存不完整订单')
    return (f"PO # {metadata['po']}\nPO Date {metadata['date']}\n"
            f"Deliver By Date {metadata['delivery']}\n" + '\n'.join(lines) + f'\nTotal ${total}')
