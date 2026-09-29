"""Private, leased image translation using the original Shinobu Node pipeline."""
import functools
import hashlib
import json
import math
import os
import queue
import shutil
import subprocess
import threading
import time
import warnings
import zlib
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, EncodedStreamObject, NameObject, NumberObject

from app.core.config import settings
from .document_ir import Block, Cancelled, DocumentIR, EngineResult, Issue, Page, SourceAnchor, ToolError, result_file
from .pdf_geometry import normalize_pdf, open_pdf, parse_page_groups
from .storage import safe_name
from .translation_engine import make_translator, validate_translation_options
from .image_terminology import translate_image_texts
from .image_text_regions import native_regions

IMAGE_TYPES = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}
MAX_PROTOCOL_BYTES = 4 * 1024 * 1024


@functools.lru_cache(maxsize=16)
def _verified_file(path, size, modified, digest):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


@functools.lru_cache(maxsize=4)
def _runtime_loads(node, runner, modified):
    try:
        result = subprocess.run([node, runner, "--check"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def runtime_status():
    """Readiness is not an inference accuracy claim; weights never leave this host."""
    runner = Path(settings.image_translation_runner)
    try:
        if not runner.is_file() or not shutil.which(settings.image_translation_node):
            return {"available": False, "reason": "服务器图片处理引擎尚未安装，请联系管理员"}
        if not _runtime_loads(settings.image_translation_node, str(runner.resolve()), runner.stat().st_mtime_ns):
            return {"available": False, "reason": "服务器图片运行依赖未就绪，请联系管理员"}
        manifest = json.loads(runner.with_name("models.json").read_text(encoding="utf-8"))
        root = Path(settings.image_translation_model_dir)
        for model in manifest["models"].values():
            assets = [(model["url"], model["size"], model["sha256"])]
            if model.get("dictUrl"):
                assets.append((model["dictUrl"], model["dictSize"], model["dictSha256"]))
            for url, size, digest in assets:
                file = root / Path(url).name
                stat = file.stat()
                if stat.st_size != size or not _verified_file(str(file.resolve()), stat.st_size, stat.st_mtime_ns, digest):
                    raise ValueError("Invalid model")
        for lang in ("CN", "TW"):
            if not (runner.parent / "fonts" / f"SourceHanSans{lang}-VF.ttf").is_file():
                raise ValueError("Missing font")
    except (OSError, ValueError, KeyError, TypeError):
        return {"available": False, "reason": "服务器图片模型未安装或校验未通过，请联系管理员"}
    return {"available": True, "reason": ""}


def require_runtime():
    status = runtime_status()
    if not status["available"]:
        raise ToolError("IMAGE_RUNTIME_UNAVAILABLE", status["reason"])


def read_image(path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != IMAGE_TYPES.get(Path(path).suffix.lower().lstrip(".")):
                    raise ToolError("INVALID_IMAGE", "图片内容与文件扩展名不一致")
                if image.width * image.height > settings.image_translation_max_pixels or max(image.size) > 12000:
                    raise ToolError("IMAGE_PIXEL_LIMIT", f"图片尺寸过大，请缩小至 {settings.image_translation_max_pixels / 1_000_000:g} 百万像素、最长边 12000 像素以内再上传")
                if getattr(image, "n_frames", 1) != 1:
                    raise ToolError("ANIMATED_IMAGE_UNSUPPORTED", "请将动态图另存为单张图片后上传")
                oriented = ImageOps.exif_transpose(image).convert("RGBA")
                result = Image.new("RGB", oriented.size, "white")
                result.paste(oriented, mask=oriented.getchannel("A"))
                return result
    except ToolError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ToolError("INVALID_IMAGE", "图片损坏或尺寸超过限制，请重新导出后上传") from None


def inspect_image(path, work, progress, cancelled):
    if cancelled():
        raise Cancelled()
    image = read_image(path)
    preview = work / "source-preview.png"
    image.save(preview)
    page = Page(page_index=0, display_page_number=1, width_pt=image.width, height_pt=image.height, classification="image")
    image.close()
    progress("inspect", 1, 1)
    return EngineResult(DocumentIR(source_type=path.suffix.lstrip("."), pages=[page]), [result_file(preview, "preview")])


def run_node(pages, options, work, progress, cancelled):
    """Check cancellation even during silent native inference; always reap the child."""
    stop = threading.Event()
    translate = make_translator(options, lambda *args: None if stop.is_set() else progress(*args),
                                lambda: stop.is_set() or cancelled())
    translation_cache = {}
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "FONTCONFIG_PATH", "LANG"}}
    environment["OMP_NUM_THREADS"] = "2"
    try:
        process = subprocess.Popen([settings.image_translation_node, str(Path(settings.image_translation_runner).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=work,
            env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError:
        raise ToolError("IMAGE_RUNTIME_UNAVAILABLE", "无法启动服务器图片处理引擎，请联系管理员") from None
    messages = queue.Queue(maxsize=32)

    def consume():
        try:
            while not stop.is_set():
                line = process.stdout.readline(MAX_PROTOCOL_BYTES + 1)
                value = None if not line else {"event": "error"} if len(line) > MAX_PROTOCOL_BYTES else json.loads(line)
                while not stop.is_set():
                    try:
                        messages.put(value, timeout=.2)
                        break
                    except queue.Full:
                        pass
                if not line or len(line) > MAX_PROTOCOL_BYTES:
                    return
        except (OSError, ValueError):
            while not stop.is_set():
                try:
                    messages.put({"event": "error"}, timeout=.2)
                    return
                except queue.Full:
                    pass

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    records = []
    deadline = time.monotonic() + settings.image_translation_timeout_seconds
    total_chars = 0
    try:
        process.stdin.write((json.dumps({"modelRoot": str(Path(settings.image_translation_model_dir).resolve()),
            "direction": options.get("translation_direction", "en_to_zh"), "pages": pages}) + "\n").encode())
        process.stdin.flush()
        while True:
            if cancelled():
                raise Cancelled()
            if time.monotonic() > deadline:
                raise ToolError("IMAGE_TIMEOUT", "图片处理超时，请减少页数或缩小图片后重试")
            try:
                message = messages.get(timeout=.2)
            except queue.Empty:
                continue
            if not isinstance(message, dict):
                raise ValueError("Missing response")
            event = message.get("event")
            if event == "translate":
                texts = message.get("texts")
                if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts):
                    raise ValueError("Invalid texts")
                total_chars += sum(map(len, texts))
                if total_chars > 500_000:
                    raise ToolError("TRANSLATION_TOO_LARGE", "文字超过处理上限，请拆分文件")
                # Keep the supervisor responsive while the provider/native model
                # is busy. Cancellation reaps Node immediately; late translation
                # results and progress are discarded, and the next batch stops.
                response_queue = queue.Queue(maxsize=1)
                def translated_batch(batch):
                    try:
                        missing = list(dict.fromkeys(t for t in batch if t not in translation_cache))
                        direction = options.get('translation_direction','en_to_zh')
                        converted = (translate(missing,direction) if options.get('translation_engine') == 'online'
                                     else translate_image_texts(missing,direction,translate)) if missing else []
                        translation_cache.update(zip(missing,converted,strict=True))
                        response_queue.put([translation_cache[t] for t in batch])
                    except Exception as error:
                        response_queue.put(error)
                threading.Thread(target=translated_batch,args=(texts,),daemon=True).start()
                while True:
                    if cancelled():
                        raise Cancelled()
                    if time.monotonic() > deadline:
                        raise ToolError('IMAGE_TIMEOUT','图片处理超时，请减少页数后重试')
                    try:
                        values = response_queue.get(timeout=.2)
                        break
                    except queue.Empty:
                        pass
                if isinstance(values, Exception):
                    raise values
                if cancelled():
                    raise Cancelled()
                process.stdin.write((json.dumps({"translations": values}, ensure_ascii=False) + "\n").encode("utf-8"))
                process.stdin.flush()
            elif event == "progress":
                stage = {"detect": "recognize", "ocr": "recognize", "translate": "translate"}.get(message.get("stage"), "rebuild")
                progress(stage, len(records), len(pages))
            elif event == "page":
                if message.get("index") != len(records) or len(records) >= len(pages) or not isinstance(message.get("record"), dict):
                    raise ValueError("Invalid page")
                records.append(message)
            elif event == "done":
                if len(records) != len(pages):
                    raise ValueError("Incomplete pages")
                process.stdin.close()
                while process.poll() is None:
                    if cancelled():
                        raise Cancelled()
                    if time.monotonic() > deadline:
                        raise ToolError("IMAGE_TIMEOUT", "图片处理超时，请重试")
                    stop.wait(.1)
                if process.returncode:
                    raise ValueError("Process failed")
                return records
            else:
                raise ValueError("Worker failed")
    except ToolError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise ToolError("IMAGE_PROCESSING_FAILED", "服务器图片处理未完成，请重试或联系管理员检查模型与运行环境") from None
    finally:
        stop.set()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        reader.join(timeout=2)
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


def append_image_pdf(writer, image_path, width, height):
    """Embed lossless RGB pixels, one result per page, retaining visible-page ratio."""
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    stream = EncodedStreamObject()
    stream._data = zlib.compress(image.tobytes())
    stream.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(image.width), NameObject("/Height"): NumberObject(image.height),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"), NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Filter"): NameObject("/FlateDecode")})
    image.close()
    page = writer.add_blank_page(width, height)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): writer._add_object(stream)})})
    content = DecodedStreamObject()
    content.set_data(f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)


def append_preserved_pdf(writer, original_page, source_path, result_path, width, height):
    """Keep original PDF objects. A lossless difference overlay changes only ink.

    Existing vectors, original text (including all digits), images and page
    geometry remain in the PDF. This is translation, never secure redaction.
    """
    import numpy as np
    from pypdf import PageObject
    page = writer.add_page(original_page)
    with Image.open(source_path) as source, Image.open(result_path) as result:
        a, b = np.asarray(source.convert('RGB')), np.asarray(result.convert('RGB'))
    changed = np.any(a != b, axis=2)
    if not changed.any():
        return
    alpha = EncodedStreamObject(); alpha._data = zlib.compress((changed.astype('uint8')*255).tobytes())
    alpha.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                  NameObject('/Width'):NumberObject(b.shape[1]),NameObject('/Height'):NumberObject(b.shape[0]),
                  NameObject('/ColorSpace'):NameObject('/DeviceGray'),NameObject('/BitsPerComponent'):NumberObject(8),NameObject('/Filter'):NameObject('/FlateDecode')})
    pixels = b.copy(); pixels[~changed] = 0
    image = EncodedStreamObject(); image._data = zlib.compress(pixels.tobytes())
    image.update({**alpha,NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/SMask'):writer._add_object(alpha)})
    overlay = PageObject.create_blank_page(width=width,height=height)
    overlay[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Translation'):writer._add_object(image)})})
    content=DecodedStreamObject(); content.set_data(f'q {width} 0 0 {height} 0 0 cm /Translation Do Q'.encode('ascii'))
    overlay[NameObject('/Contents')]=content
    page.merge_page(overlay)


def convert_image_translation(path, options, work, progress, cancelled, *, parent_ir=None):
    require_runtime()
    validate_translation_options(options, "image_translate")
    work.mkdir(parents=True, exist_ok=True)
    ir = DocumentIR(source_type=path.suffix.lstrip("."), engine_manifest={"image_pipeline": "shinobu-node", "translation": options.get("translation_engine", "offline")})
    inputs, metadata, native, raster_areas = [], [], {}, {}
    deadline = time.monotonic() + settings.image_translation_timeout_seconds
    def check():
        if cancelled():
            raise Cancelled()
        if time.monotonic() > deadline:
            raise ToolError("IMAGE_TIMEOUT", "图片处理超时，请减少页数后重试")
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        import pdfplumber
        reader = open_pdf(path, options.get("password"))
        if len(reader.pages) > settings.document_tools_max_pages:
            raise ToolError("PDF_PAGE_LIMIT", "PDF 页数超过当前处理上限")
        normalized = work / "normalized.pdf"
        geometry, _ = normalize_pdf(path, normalized, options.get("password"), cancelled)
        selected = list(dict.fromkeys(n for group in parse_page_groups(options.get("page_selection", "all"), len(geometry)) for n in group))
        scales = {}
        total_pixels = 0
        for index in selected:
            width, height = geometry[index]["width_pt"], geometry[index]["height_pt"]
            scale = min(2, 4096 / max(width, height), math.sqrt(settings.image_translation_max_pixels / (width * height)))
            total_pixels += math.ceil(width * scale) * math.ceil(height * scale)
            scales[index] = scale
        if total_pixels > settings.image_translation_max_total_pixels:
            raise ToolError("IMAGE_TOTAL_PIXEL_LIMIT", "PDF 总图像尺寸超过处理上限，请选择较少页码分批翻译")
        with pdfium.PdfDocument(str(normalized)) as document, pdfplumber.open(normalized) as text_document:
            for index in selected:
                check()
                g = geometry[index]
                width, height = g["width_pt"], g["height_pt"]
                scale = scales[index]
                native[index] = native_regions(text_document.pages[index], scale)
                raster_areas[index] = [{'x':max(0,im['x0'])*scale,'y':max(0,im['top'])*scale,
                    'width':(min(width,im['x1'])-max(0,im['x0']))*scale,
                    'height':(min(height,im['bottom'])-max(0,im['top']))*scale}
                    for im in text_document.pages[index].images
                    if (min(width,im['x1'])-max(0,im['x0']))*(min(height,im['bottom'])-max(0,im['top'])) > width*height*.06]
                if scale <= 0 or min(width, height) * scale < 1:
                    raise ToolError("PDF_PAGE_GEOMETRY", "PDF 页面比例超出处理范围")
                page = document[index]
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil().convert("RGB")
                bitmap.close()
                page.close()
                file = work / f"source-{index + 1:04d}.png"
                image.save(file)
                image.close()
                inputs.append(file)
                metadata.append(Page(page_index=index, display_page_number=index + 1, width_pt=width, height_pt=height, classification="image"))
                progress("extract", len(inputs), len(selected))
    else:
        image = read_image(path)
        file = work / "source-0001.png"
        image.save(file)
        metadata.append(Page(page_index=0, display_page_number=1, width_pt=image.width, height_pt=image.height, classification="image"))
        image.close()
        inputs.append(file)

    outputs = [work / f"page-{page.page_index + 1:04d}.png" for page in metadata]
    patch = options.get("_recognize_region")
    active = list(range(len(inputs)))
    paste_box = None
    if patch:
        if parent_ir is None:
            raise ToolError("RESULT_NOT_READY", "补翻原结果不可用，请重新翻译")
        selected_index = next((i for i, page in enumerate(metadata) if page.page_index == patch["page_index"]), None)
        if selected_index is None:
            raise ToolError("INVALID_REGION", "补翻页面不在当前结果中")
        active = [selected_index]
        for i, page in enumerate(metadata):
            prior = next((block for block in parent_ir.blocks if block.kind == "image" and block.source.page_index == page.page_index), None)
            if prior is None:
                raise ToolError("RESULT_NOT_READY", "补翻原结果不可用")
            # Paths are internal IR produced by this engine, never accepted from callers.
            from .storage import key_for, resolve
            shutil.copyfile(resolve(key_for(Path(prior.style["image_path"]))), outputs[i])
        i = selected_index
        with Image.open(inputs[i]) as image:
            page = metadata[i]
            x0, y0, x1, y1 = patch["bbox_pt"]
            paste_box = (math.floor(x0 * image.width / page.width_pt), math.floor(y0 * image.height / page.height_pt),
                         math.ceil(x1 * image.width / page.width_pt), math.ceil(y1 * image.height / page.height_pt))
            crop = work / "patch-source.png"
            image.crop(paste_box).save(crop)
            inputs[i] = crop
    calls = [{"input": str(inputs[i].resolve()), "output": str((work / "patch-result.png" if patch else outputs[i]).resolve())} for i in active]
    for call, i in zip(calls, active, strict=True):
        regions = native.get(metadata[i].page_index, [])
        if patch:
            x0, y0, x1, y1 = paste_box
            regions = [{**r, 'box':{**r['box'], 'x':r['box']['x']-x0, 'y':r['box']['y']-y0}}
                       for r in regions if x0 <= r['box']['x'] and y0 <= r['box']['y']
                       and r['box']['x']+r['box']['width'] <= x1 and r['box']['y']+r['box']['height'] <= y1]
        if regions:
            call['nativeRegions'] = regions
            call['rasterAreas'] = raster_areas.get(metadata[i].page_index,[]) if not patch else []
    def timed_cancelled():
        check()
        return False
    records = run_node(calls, options, work, progress, timed_cancelled)
    if patch:
        with Image.open(outputs[active[0]]) as base, Image.open(work / "patch-result.png") as result:
            if result.size != (paste_box[2] - paste_box[0], paste_box[3] - paste_box[1]):
                raise ToolError("INVALID_OUTPUT", "补翻结果尺寸不一致，请重试")
            merged = base.convert("RGB")
            from PIL import ImageDraw
            mask = Image.new('L',result.size,0)
            if records[0]['record'].get('policy') == 'document-safe-v1':
                draw=ImageDraw.Draw(mask)
                for region in records[0]['record'].get('translations',[]):
                    if region.get('rendered'):
                        box=region.get('renderBox') or region['box']
                        draw.rectangle((math.floor(box['x']),math.floor(box['y']),math.ceil(box['x']+box['width'])-1,
                                        math.ceil(box['y']+box['height'])-1),fill=255)
            else:
                import numpy as np
                with Image.open(work / 'patch-source.png') as before:
                    mask=Image.fromarray((np.any(np.asarray(before.convert('RGB'))!=np.asarray(result.convert('RGB')),axis=2).astype('uint8')*255))
            merged.paste(result, paste_box[:2], mask)
            merged.save(outputs[active[0]])
            merged.close()
    ir.pages = metadata
    pdf = PdfWriter()
    files = []
    for i, (page, output) in enumerate(zip(metadata, outputs, strict=True)):
        check()
        with Image.open(output) as result, Image.open(work / f"source-{page.page_index + 1:04d}.png") as source:
            if result.size != source.size:
                raise ToolError("INVALID_OUTPUT", "翻译图片尺寸与原图不一致")
        if path.suffix.lower() == '.pdf':
            if i == 0:
                preserved_reader = open_pdf(normalized)
            append_preserved_pdf(pdf, preserved_reader.pages[page.page_index], work / f"source-{page.page_index + 1:04d}.png", output, page.width_pt, page.height_pt)
        else:
            append_image_pdf(pdf, output, page.width_pt, page.height_pt)
        ir.blocks.append(Block(id=f"page-{page.page_index}", kind="image", source=SourceAnchor(page_index=page.page_index, method="image_translation"), style={"image_path": str(output.resolve())}))
        files.append(result_file(output, "result_page"))
        files.append(result_file(work / f"source-{page.page_index + 1:04d}.png", "source_page"))
    for call_index, record in enumerate(records):
        page = metadata[active[call_index]]
        for index, region in enumerate(record["record"].get("translations", [])):
            box = region.get('renderBox') or region.get('box')
            bbox = None
            if box:
                with Image.open(work / f"source-{page.page_index + 1:04d}.png") as full:
                    sx, sy = page.width_pt/full.width, page.height_pt/full.height
                dx, dy = paste_box[:2] if patch else (0,0)
                bbox = [(box['x']+dx)*sx,(box['y']+dy)*sy,(box['x']+box['width']+dx)*sx,(box['y']+box['height']+dy)*sy]
            ir.blocks.append(Block(id=f"p{page.page_index}-t{index}", text=(region.get("translatedText") or region['sourceText']) if region.get('rendered') else region['sourceText'], original_text=region["sourceText"],
                source=SourceAnchor(page_index=page.page_index, method=region.get('method','ocr'), bbox_pt=bbox),
                style={'rendered':region.get('rendered',False),'preserved_reason':region.get('skipReason','unchanged' if not region.get('rendered') else '')}))
        if record.get("status") == "no-translatable-text":
            ir.issues.append(Issue(id=f"empty-{page.page_index}", code="NO_TEXT", message="选区未识别出可翻译文字，保留已有结果" if patch else "该页未识别出可翻译文字，保留原图", source=SourceAnchor(page_index=page.page_index)))
    if patch and parent_ir:
        new_boxes = [b.source.bbox_pt for b in ir.blocks if b.kind!='image' and b.source.bbox_pt and b.style.get('rendered')]
        for block in parent_ir.blocks:
            if block.kind=='image':
                continue
            old_box=block.source.bbox_pt
            if block.source.page_index == patch['page_index'] and old_box and any(
                min(old_box[2],b[2])>max(old_box[0],b[0]) and min(old_box[3],b[3])>max(old_box[1],b[1]) for b in new_boxes):
                continue
            inherited=block.model_copy(deep=True)
            inherited.id=f'previous-{block.id}'
            ir.blocks.append(inherited)
        for issue in parent_ir.issues:
            if issue.source and issue.source.page_index is not None and issue.source.page_index != patch['page_index']:
                inherited=issue.model_copy(deep=True)
                inherited.id=f'previous-{issue.id}'
                ir.issues.append(inherited)
    review = [b for b in ir.blocks if b.kind != 'image' and b.style.get('preserved_reason') not in {'', 'protected', 'not-source-language'}]
    if review:
        ir.issues.append(Issue(id='preserved-text',code='IMAGE_PRESERVED_REGIONS',message=f'{len(review)} 处因识别、背景或排版限制保留原文，请对照核对。'))
    ir.issues.append(Issue(id="image-review", code="IMAGE_TRANSLATION_REVIEW", message="数字、型号和色号优先保留；请对照原文核对专业术语。PDF 保留原页面对象，译文以局部图层覆盖，原文字层仍可提取。"))
    report = work / 'translation-review.json'
    report.write_text(json.dumps({'pages':[p.model_dump() for p in ir.pages],
        'regions':[{'id':b.id,'source':b.original_text,'translation':b.text,'page_index':b.source.page_index,
                    'bbox_pt':b.source.bbox_pt,'rendered':b.style.get('rendered',False),'reason':b.style.get('preserved_reason','')}
                   for b in ir.blocks if b.kind != 'image'],
        'issues':[i.message for i in ir.issues]},ensure_ascii=False,indent=2),encoding='utf-8')
    files.append(result_file(report,'translation_review'))
    target = work / (Path(safe_name(options.get("output_name") or path.stem)).stem + "-翻译.pdf")
    pdf.write(target)
    pdf.close()
    check()
    files.insert(0, result_file(target))
    progress("rebuild", len(metadata), len(metadata))
    return EngineResult(ir, files, {"pages": len(metadata), "translation_engine": options.get("translation_engine", "offline"), "patch": bool(patch)})
